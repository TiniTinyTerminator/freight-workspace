//! Foreign CMake project adoption: write a `build = "cmake"` manifest, harvest
//! `find_package` deps, and convert vendored submodules / FetchContent /
//! add_subdirectory into freight deps. Moved out of freight core.

use std::collections::BTreeSet;
use std::fs;
use std::path::Path;
use std::process::Command;

use freight::error::FreightError;
use freight::resolve::cmake::cmake_to_freight_name;
use freight::resolve::pkg_config::pkg_config_version;

use crate::cmake_scan::{
    detect_add_subdirectory_in_project, detect_cmake_packages_in_project,
    detect_fetchcontent_in_project, FetchContentDep, RegistryResolver,
};

/// Directory names that conventionally hold vendored third-party source.
const VENDOR_DIRS: &[&str] = &[
    "third_party",
    "thirdparty",
    "3rdparty",
    "external",
    "extern",
    "vendor",
    "deps",
    "subprojects",
    "contrib",
];

fn cmake_dependency_lines(packages: &[String], registry: &dyn RegistryResolver) -> String {
    let mut out = String::new();
    for pkg in packages {
        let key = cmake_to_freight_name(pkg);
        let reg_version = registry.lookup(&key).map(|h| h.version);
        let pc_version = pkg_config_version(&key);
        let version = if !pc_version.is_empty() {
            Some(pc_version)
        } else {
            reg_version.clone()
        };
        let hint = if reg_version.is_some() {
            " — also in registry (drop `external` to build it from there)"
        } else {
            ""
        };
        match version {
            Some(v) => out.push_str(&format!(
                "{key} = {{ version = \"{v}\", external = true }}   # find_package({pkg}){hint}\n"
            )),
            None => out.push_str(&format!(
                "# {key} = {{ version = \"*\", external = true }}   # find_package({pkg}) — set a version\n"
            )),
        }
    }
    out
}

/// Write a freight.toml for an existing CMake project: a foreign **self-build**
/// (`[package] build = "cmake"`) so the whole project is configured + built by
/// CMake (freight does not compile its sources natively), with the project's
/// harvested `find_package` dependencies recorded in `[dependencies]`.
pub fn write_cmake_manifest(
    root: &Path,
    name: &str,
    _lang_key: &str,
    _std: &str,
    registry: &dyn RegistryResolver,
) -> Result<Vec<String>, FreightError> {
    let packages = detect_cmake_packages_in_project(root);
    let harvested_keys: BTreeSet<String> =
        packages.iter().map(|p| cmake_to_freight_name(p)).collect();
    let mut deps = cmake_dependency_lines(&packages, registry);

    // Convert vendored git submodules (e.g. gRPC's `third_party/*`) into freight
    // url+rev deps, pinned to the exact committed commit — so the build can pull
    // them through freight instead of carrying the vendored trees.
    let submodules = detect_submodules(root);
    let (submodule_deps, mut pruneable_paths) =
        submodule_dependency_lines(&submodules, &harvested_keys);
    deps.push_str(&submodule_deps);

    // Convert CMake `FetchContent_Declare(...)` deps into freight url deps, so they
    // are pinned + resolved through freight instead of downloaded ad hoc by CMake.
    let mut used: BTreeSet<String> = harvested_keys.clone();
    used.extend(submodules.iter().map(|s| submodule_dep_name(&s.path)));
    let fetchcontent = detect_fetchcontent_in_project(root);
    deps.push_str(&fetchcontent_dependency_lines(&fetchcontent, &used));
    used.extend(fetchcontent.iter().map(|d| submodule_dep_name(&d.name)));

    // Convert vendored `add_subdirectory(third_party/x)` sub-projects. When the dir
    // is its own git checkout we recover url+rev (pruneable, like a submodule);
    // otherwise we can't pin upstream, so emit a commented path-dep suggestion.
    let add_subdirs = detect_add_subdirectory_in_project(root);
    let (asub_deps, asub_prune) = add_subdirectory_dependency_lines(root, &add_subdirs, &used);
    deps.push_str(&asub_deps);
    pruneable_paths.extend(asub_prune);

    let deps_section = if deps.is_empty() {
        String::new()
    } else {
        format!("\n[dependencies]\n{deps}")
    };

    let contents = format!(
        r#"# Adopted CMake project: `freight build` configures + builds it with CMake.
# Freight steers find_package to installed / freight-provided packages.
[package]
name        = "{name}"
version     = "0.1.0"
description = ""
license     = "MIT"
build       = "cmake"
{deps_section}"#,
    );

    fs::write(root.join("freight.toml"), contents)?;
    Ok(pruneable_paths)
}

// ── Vendored git submodules → freight deps ───────────────────────────────────

/// A vendored git submodule discovered from `.gitmodules`.
struct Submodule {
    /// Path relative to the project root, e.g. `third_party/abseil-cpp`.
    path: String,
    /// Remote URL.
    url: String,
    /// The exact commit the superproject pins (the gitlink), if resolvable.
    rev: Option<String>,
}

/// Parse `.gitmodules` at `root` and resolve each submodule's pinned commit.
/// Returns empty when there is no `.gitmodules`.
fn detect_submodules(root: &Path) -> Vec<Submodule> {
    let Ok(text) = fs::read_to_string(root.join(".gitmodules")) else {
        return Vec::new();
    };
    let mut blocks: Vec<(String, String)> = Vec::new();
    let mut path: Option<String> = None;
    let mut url: Option<String> = None;
    let mut in_submodule = false;
    for line in text.lines() {
        let t = line.trim();
        if t.starts_with('[') {
            if let (Some(p), Some(u)) = (path.take(), url.take()) {
                blocks.push((p, u));
            }
            path = None;
            url = None;
            in_submodule = t.starts_with("[submodule");
            continue;
        }
        if !in_submodule {
            continue;
        }
        if let Some(v) = t
            .strip_prefix("path")
            .and_then(|r| r.trim_start().strip_prefix('='))
        {
            path = Some(v.trim().to_string());
        } else if let Some(v) = t
            .strip_prefix("url")
            .and_then(|r| r.trim_start().strip_prefix('='))
        {
            url = Some(v.trim().to_string());
        }
    }
    if let (Some(p), Some(u)) = (path, url) {
        blocks.push((p, u));
    }

    blocks
        .into_iter()
        .map(|(path, url)| {
            let rev = submodule_rev(root, &path);
            Submodule { path, url, rev }
        })
        .collect()
}

/// Resolve the commit a submodule path is pinned to via `git ls-tree HEAD <path>`
/// (a gitlink shows as mode `160000`, type `commit`). `None` if git can't tell us.
fn submodule_rev(root: &Path, path: &str) -> Option<String> {
    let out = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["ls-tree", "HEAD"])
        .arg(path)
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    let stdout = String::from_utf8_lossy(&out.stdout);
    let mut parts = stdout.lines().next()?.split_whitespace();
    let _mode = parts.next()?;
    let kind = parts.next()?;
    let sha = parts.next()?;
    (kind == "commit" && sha.len() >= 7).then(|| sha.to_string())
}

/// A freight dependency key derived from a submodule path (its last component,
/// lowercased, with non-key characters mapped to `-`).
fn submodule_dep_name(path: &str) -> String {
    let base = path.trim_end_matches('/').rsplit('/').next().unwrap_or(path);
    let mapped: String = base
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' || c == '_' {
                c.to_ascii_lowercase()
            } else {
                '-'
            }
        })
        .collect();
    mapped.trim_matches('-').to_string()
}

/// Render `[dependencies]` lines for vendored submodules and the list of paths
/// that can be pruned. A submodule with a resolved commit becomes an active
/// `{ url, rev }` dep; one whose commit can't be resolved is a commented
/// suggestion (so the manifest stays valid and nothing is silently floated).
/// Names colliding with an already-harvested `find_package` dep are skipped to
/// avoid duplicate keys.
fn submodule_dependency_lines(
    submodules: &[Submodule],
    harvested_keys: &BTreeSet<String>,
) -> (String, Vec<String>) {
    let mut out = String::new();
    let mut pruneable = Vec::new();
    let mut used: BTreeSet<String> = harvested_keys.clone();
    for s in submodules {
        let name = submodule_dep_name(&s.path);
        if name.is_empty() || used.contains(&name) {
            continue;
        }
        used.insert(name.clone());
        match &s.rev {
            Some(rev) => {
                out.push_str(&format!(
                    "{name} = {{ url = \"{}\", rev = \"{}\" }}   # vendored submodule {}\n",
                    s.url, rev, s.path,
                ));
                pruneable.push(s.path.clone());
            }
            None => out.push_str(&format!(
                "# {name} = {{ url = \"{}\" }}   # vendored submodule {} (pinned commit unresolved)\n",
                s.url, s.path,
            )),
        }
    }
    (out, pruneable)
}

/// Render `[dependencies]` lines for CMake `FetchContent_Declare` deps. A git
/// source becomes `{ url, tag|rev }`; an archive becomes `{ url, sha256 }` (or just
/// `{ url }`, freight auto-detects the checksum on first fetch). Names colliding
/// with an already-used dep key are skipped to avoid duplicate keys.
fn fetchcontent_dependency_lines(deps: &[FetchContentDep], used: &BTreeSet<String>) -> String {
    let mut out = String::new();
    let mut seen: BTreeSet<String> = used.clone();
    for d in deps {
        let name = submodule_dep_name(&d.name);
        if name.is_empty() || seen.contains(&name) {
            continue;
        }
        seen.insert(name.clone());
        let mut fields = format!("url = \"{}\"", d.url);
        if d.is_git {
            if let Some(r) = &d.git_ref {
                let key = if d.ref_is_rev { "rev" } else { "tag" };
                fields.push_str(&format!(", {key} = \"{r}\""));
            }
        } else if let Some(sha) = &d.sha256 {
            fields.push_str(&format!(", sha256 = \"{sha}\""));
        }
        out.push_str(&format!("{name} = {{ {fields} }}   # cmake FetchContent\n"));
    }
    out
}

/// Recover a vendored git checkout's upstream: `remote.origin.url` + `HEAD` commit.
/// Only call when `<dir>/.git` exists — otherwise `git -C` would walk up to the
/// superproject and report *its* remote, mislabeling the dep.
fn git_checkout_origin(dir: &Path) -> Option<(String, String)> {
    let git = |args: &[&str]| {
        let out = Command::new("git").arg("-C").arg(dir).args(args).output().ok()?;
        out.status
            .success()
            .then(|| String::from_utf8_lossy(&out.stdout).trim().to_string())
            .filter(|s| !s.is_empty())
    };
    let url = git(&["config", "--get", "remote.origin.url"])?;
    let rev = git(&["rev-parse", "HEAD"]).filter(|r| r.len() >= 7)?;
    Some((url, rev))
}

/// Render `[dependencies]` lines for vendored `add_subdirectory(<path>)` sub-projects.
/// A path only qualifies as *vendored* when it has its own `CMakeLists.txt` and is
/// either under a conventional vendor dir or its own git checkout — this excludes the
/// project's own subdirs (`src/`, `lib/`, …). A git checkout yields `{ url, rev }`
/// (pruneable); otherwise a commented path-dep suggestion (upstream unknown). Returns
/// the rendered lines and the paths that became pruneable deps.
fn add_subdirectory_dependency_lines(
    root: &Path,
    paths: &[String],
    used: &BTreeSet<String>,
) -> (String, Vec<String>) {
    let mut out = String::new();
    let mut pruneable = Vec::new();
    let mut seen: BTreeSet<String> = used.clone();
    for path in paths {
        let abs = root.join(path);
        if !abs.join("CMakeLists.txt").is_file() {
            continue;
        }
        let under_vendor = path
            .split('/')
            .any(|c| VENDOR_DIRS.contains(&c.to_ascii_lowercase().as_str()));
        let has_git = abs.join(".git").exists();
        if !under_vendor && !has_git {
            continue; // the project's own subdir, not a vendored dep
        }
        let name = submodule_dep_name(path);
        if name.is_empty() || seen.contains(&name) {
            continue;
        }
        seen.insert(name.clone());
        match has_git.then(|| git_checkout_origin(&abs)).flatten() {
            Some((url, rev)) => {
                out.push_str(&format!(
                    "{name} = {{ url = \"{url}\", rev = \"{rev}\" }}   # vendored add_subdirectory {path}\n",
                ));
                pruneable.push(path.clone());
            }
            None => out.push_str(&format!(
                "# {name} = {{ path = \"{path}\" }}   # vendored add_subdirectory — set a url/version to pull via freight\n",
            )),
        }
    }
    (out, pruneable)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Registry that knows nothing — keeps the manifest-generation tests offline.
    /// (find_package scanning + name mapping are covered in `resolve::cmake`.)
    struct NullRegistry;
    impl RegistryResolver for NullRegistry {
        fn lookup(&self, _name: &str) -> Option<crate::cmake_scan::RegistryHit> {
            None
        }
    }

    /// Registry that knows one package, to exercise the hint.
    struct OneRegistry(&'static str, &'static str);
    impl RegistryResolver for OneRegistry {
        fn lookup(&self, name: &str) -> Option<crate::cmake_scan::RegistryHit> {
            (name == self.0).then(|| crate::cmake_scan::RegistryHit {
                version: self.1.to_string(),
                installed: false,
            })
        }
    }

    fn sub(path: &str, url: &str, rev: Option<&str>) -> Submodule {
        Submodule {
            path: path.to_string(),
            url: url.to_string(),
            rev: rev.map(str::to_string),
        }
    }

    #[test]
    fn submodule_dep_name_uses_basename() {
        assert_eq!(submodule_dep_name("third_party/abseil-cpp"), "abseil-cpp");
        assert_eq!(submodule_dep_name("third_party/cares/cares"), "cares");
        assert_eq!(submodule_dep_name("vendor/Foo.Bar"), "foo-bar");
    }

    #[test]
    fn gitmodules_parse_path_and_url() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(
            dir.path().join(".gitmodules"),
            "[submodule \"third_party/abseil-cpp\"]\n\
             \tpath = third_party/abseil-cpp\n\
             \turl = https://github.com/abseil/abseil-cpp.git\n\
             [submodule \"third_party/re2\"]\n\
             \tpath = third_party/re2\n\
             \turl = https://github.com/google/re2.git\n",
        )
        .unwrap();
        let subs = detect_submodules(dir.path());
        assert_eq!(subs.len(), 2);
        assert_eq!(subs[0].path, "third_party/abseil-cpp");
        assert_eq!(subs[0].url, "https://github.com/abseil/abseil-cpp.git");
        // Not a git repo → pinned commit can't be resolved, but parsing still works.
        assert!(subs[0].rev.is_none());
    }

    #[test]
    fn resolved_submodule_becomes_active_dep_and_pruneable() {
        let subs = [sub(
            "third_party/abseil-cpp",
            "https://github.com/abseil/abseil-cpp.git",
            Some("4a2c63365eff8823a5221db86ef490e828306f9d"),
        )];
        let (lines, prune) = submodule_dependency_lines(&subs, &BTreeSet::new());
        assert!(lines.contains(
            "abseil-cpp = { url = \"https://github.com/abseil/abseil-cpp.git\", rev = \"4a2c63365eff8823a5221db86ef490e828306f9d\" }"
        ));
        assert_eq!(prune, vec!["third_party/abseil-cpp".to_string()]);
    }

    #[test]
    fn unresolved_submodule_is_commented_not_pruneable() {
        let subs = [sub("third_party/x", "https://example.com/x.git", None)];
        let (lines, prune) = submodule_dependency_lines(&subs, &BTreeSet::new());
        assert!(lines.trim_start().starts_with("# x = {"));
        assert!(prune.is_empty());
    }

    #[test]
    fn submodule_name_colliding_with_harvested_is_skipped() {
        let subs = [sub("third_party/re2", "https://github.com/google/re2.git", Some("abc1234"))];
        // `re2` already harvested from a find_package → skip to avoid a duplicate key.
        let mut taken = BTreeSet::new();
        taken.insert("re2".to_string());
        let (lines, prune) = submodule_dependency_lines(&subs, &taken);
        assert!(lines.is_empty());
        assert!(prune.is_empty());
    }

    #[test]
    fn fetchcontent_renders_git_and_archive_and_dedups() {
        let deps = vec![
            FetchContentDep {
                name: "googletest".into(),
                url: "https://github.com/google/googletest.git".into(),
                is_git: true,
                git_ref: Some("release-1.12.1".into()),
                ref_is_rev: false,
                sha256: None,
            },
            FetchContentDep {
                name: "json".into(),
                url: "https://x/json.tar.xz".into(),
                is_git: false,
                git_ref: None,
                ref_is_rev: false,
                sha256: Some("deadbeef".into()),
            },
            // collides with an already-harvested key → skipped.
            FetchContentDep {
                name: "zlib".into(),
                url: "https://x/zlib.git".into(),
                is_git: true,
                git_ref: None,
                ref_is_rev: false,
                sha256: None,
            },
        ];
        let mut used = BTreeSet::new();
        used.insert("zlib".to_string());
        let lines = fetchcontent_dependency_lines(&deps, &used);
        assert!(lines.contains(
            "googletest = { url = \"https://github.com/google/googletest.git\", tag = \"release-1.12.1\" }"
        ));
        assert!(lines.contains("json = { url = \"https://x/json.tar.xz\", sha256 = \"deadbeef\" }"));
        assert!(!lines.contains("zlib ="), "collision with harvested dep must be skipped");
    }

    #[test]
    fn add_subdirectory_vendored_nongit_commented_own_subdir_skipped() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        // Vendored, no .git → commented path suggestion.
        fs::create_dir_all(root.join("third_party/bar")).unwrap();
        fs::write(root.join("third_party/bar/CMakeLists.txt"), "").unwrap();
        // Project's own subdir (not under a vendor dir, no .git) → skipped.
        fs::create_dir_all(root.join("src")).unwrap();
        fs::write(root.join("src/CMakeLists.txt"), "").unwrap();

        let paths = vec!["src".to_string(), "third_party/bar".to_string()];
        let (lines, prune) = add_subdirectory_dependency_lines(root, &paths, &BTreeSet::new());
        assert!(
            lines.contains("# bar = { path = \"third_party/bar\" }"),
            "vendored non-git dir should be a commented path suggestion: {lines}"
        );
        assert!(!lines.contains("src ="), "the project's own src/ must be skipped");
        assert!(prune.is_empty(), "nothing pruneable without a recovered url+rev");
    }

    #[test]
    fn add_subdirectory_missing_cmakelists_ignored() {
        let dir = tempfile::tempdir().unwrap();
        // third_party/x exists but has no CMakeLists.txt → not a buildable subproject.
        fs::create_dir_all(dir.path().join("third_party/x")).unwrap();
        let paths = vec!["third_party/x".to_string()];
        let (lines, prune) =
            add_subdirectory_dependency_lines(dir.path(), &paths, &BTreeSet::new());
        assert!(lines.is_empty());
        assert!(prune.is_empty());
    }

    #[test]
    fn unknown_packages_become_commented_suggestions() {
        let pkgs = vec!["Totally_Made_Up_Pkg_Xyz".to_string()];
        let lines = cmake_dependency_lines(&pkgs, &NullRegistry);
        assert!(lines.contains("# totally_made_up_pkg_xyz = { version = \"*\", external = true }"));
        assert!(lines.contains("find_package(Totally_Made_Up_Pkg_Xyz)"));
    }

    #[test]
    fn registry_match_fills_version_and_hints() {
        // A package pkg-config doesn't know but the registry does: the registry
        // version fills the (still external) dep, and a hint is appended.
        let pkgs = vec!["MadeUpRegPkg".to_string()];
        let lines = cmake_dependency_lines(&pkgs, &OneRegistry("madeupregpkg", "4.5.6"));
        assert!(
            lines.contains("madeupregpkg = { version = \"4.5.6\", external = true }"),
            "{lines}"
        );
        assert!(lines.contains("also in registry"), "{lines}");
    }

    #[test]
    fn init_emits_cmake_self_build_package() {
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path();
        fs::write(
            root.join("CMakeLists.txt"),
            "cmake_minimum_required(VERSION 3.10)\nproject(demo)\n",
        )
        .unwrap();
        write_cmake_manifest(root, "demo", "cpp", "c++20", &NullRegistry).unwrap();
        let text = fs::read_to_string(root.join("freight.toml")).unwrap();
        // A foreign self-build: the whole project is built by CMake.
        assert!(text.contains("build       = \"cmake\""), "{text}");
        // No find_package → no [dependencies] table emitted.
        assert!(!text.contains("[dependencies]"), "{text}");
        // Parses, and validation accepts it with no [[bin]]/[lib] (foreign build).
        let m = freight::manifest::load_manifest_str(&text).expect("parses");
        assert_eq!(m.package.build.as_deref(), Some("cmake"));
        let errs = freight::manifest::validate::validate(&m, &[]);
        assert!(
            !errs.iter().any(|e| e.to_string().contains("at least one")),
            "no target error: {errs:?}"
        );
    }
}

