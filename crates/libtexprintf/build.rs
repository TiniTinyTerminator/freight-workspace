use std::path::{Path, PathBuf};
use std::process::Command;

fn main() {
    println!("cargo:rerun-if-env-changed=TEXPRINTF_LIB_DIR");
    println!("cargo:rerun-if-env-changed=TEXPRINTF_SOURCE_DIR");
    println!("cargo:rerun-if-env-changed=TEXPRINTF_STATIC");
    println!("cargo:rerun-if-env-changed=PKG_CONFIG_PATH");
    println!("cargo:rerun-if-env-changed=PKG_CONFIG_LIBDIR");
    println!("cargo:rerun-if-env-changed=PKG_CONFIG_SYSROOT_DIR");

    if std::env::var_os("CARGO_FEATURE_NATIVE").is_none() {
        return;
    }

    if let Some(dir) = std::env::var_os("TEXPRINTF_LIB_DIR") {
        println!("cargo:rustc-link-search=native={}", dir.to_string_lossy());
        println!("cargo:rustc-link-lib=texprintf");
        return;
    }

    if pkg_config::Config::new().probe("texprintf").is_ok() {
        return;
    }

    let source_dir = std::env::var_os("TEXPRINTF_SOURCE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(fetch_source);
    if link_built_source(&source_dir) {
        return;
    }
    build_from_source(&source_dir);
}

fn fetch_source() -> PathBuf {
    let out_dir = PathBuf::from(std::env::var_os("OUT_DIR").expect("OUT_DIR is set by Cargo"));
    let source_dir = out_dir.join("libtexprintf-src");
    if source_dir.join(".git").is_dir() || source_dir.join("configure").is_file() {
        return source_dir;
    }

    let tmp_dir = out_dir.join("libtexprintf-src.tmp");
    let _ = std::fs::remove_dir_all(&tmp_dir);
    run(
        Command::new("git")
            .arg("clone")
            .arg("--depth")
            .arg("1")
            .arg("https://github.com/bartp5/libtexprintf.git")
            .arg(&tmp_dir),
        "clone libtexprintf",
    );
    let _ = std::fs::remove_dir_all(&source_dir);
    std::fs::rename(&tmp_dir, &source_dir)
        .expect("move downloaded libtexprintf source into OUT_DIR");
    source_dir
}

fn build_from_source(source_dir: &Path) {
    let out_dir = PathBuf::from(std::env::var_os("OUT_DIR").expect("OUT_DIR is set by Cargo"));
    let work_dir = prepare_source_work_dir(source_dir, &out_dir);

    if !work_dir.join("configure").is_file() {
        run(
            Command::new("autoreconf").arg("-fi").current_dir(&work_dir),
            "bootstrap libtexprintf with autoreconf",
        );
    }

    if !work_dir.join("Makefile").is_file() {
        run(
            Command::new(work_dir.join("configure"))
                .arg("--disable-shared")
                .arg("--enable-static")
                .arg(format!(
                    "--prefix={}",
                    out_dir.join("libtexprintf-install").display()
                ))
                .current_dir(&work_dir),
            "configure libtexprintf",
        );
    }

    run(
        Command::new("make")
            .arg("-j")
            .arg(jobs())
            .current_dir(&work_dir),
        "build libtexprintf",
    );

    let lib_dir = work_dir.join("src/.libs");
    println!("cargo:rustc-link-search=native={}", lib_dir.display());
    println!("cargo:rustc-link-lib=static=texprintf");
}

fn prepare_source_work_dir(source_dir: &Path, out_dir: &Path) -> PathBuf {
    if source_dir.starts_with(out_dir) {
        return source_dir.to_path_buf();
    }

    let work_dir = out_dir.join("libtexprintf-work");
    let _ = std::fs::remove_dir_all(&work_dir);
    copy_source_tree(source_dir, &work_dir);
    work_dir
}

fn link_built_source(source_dir: &Path) -> bool {
    let lib_dir = source_dir.join("src/.libs");
    if !lib_dir.join("libtexprintf.a").is_file() {
        return false;
    }
    println!("cargo:rustc-link-search=native={}", lib_dir.display());
    println!("cargo:rustc-link-lib=static=texprintf");
    true
}

fn jobs() -> String {
    std::env::var("NUM_JOBS").unwrap_or_else(|_| "1".to_string())
}

fn copy_source_tree(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).expect("create libtexprintf source work directory");
    for entry in std::fs::read_dir(src).expect("read libtexprintf source directory") {
        let entry = entry.expect("read libtexprintf source entry");
        let path = entry.path();
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if should_skip_source_entry(&name) {
            continue;
        }
        let target = dst.join(name.as_ref());
        if path.is_dir() {
            copy_source_tree(&path, &target);
        } else {
            std::fs::copy(&path, &target).unwrap_or_else(|err| {
                panic!(
                    "copy libtexprintf source file {} to {}: {err}",
                    path.display(),
                    target.display()
                )
            });
        }
    }
}

fn should_skip_source_entry(name: &str) -> bool {
    name == ".git"
        || name == ".deps"
        || name == ".libs"
        || name == "Makefile"
        || name == "config.status"
        || name == "config.log"
        || name == "libtool"
        || name.ends_with(".o")
        || name.ends_with(".lo")
        || name.ends_with(".la")
}

fn run(cmd: &mut Command, action: &str) {
    let status = cmd
        .status()
        .unwrap_or_else(|err| panic!("failed to {action}: {err}"));
    if !status.success() {
        panic!("{action} failed with status {status}");
    }
}
