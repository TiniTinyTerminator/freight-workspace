//! `freight-migrate [--native] [PATH]` — generate a `freight.toml` for an existing
//! CMake project, either as a `build = "cmake"` self-build (default, safe) or — with
//! `--native` — by extracting real build data from CMake's File API.
use std::path::PathBuf;

use clap::Parser;
use freight_migrate::{adopt, cmake_scan, fileapi, native};

#[derive(Parser)]
#[command(about = "Migrate a CMake project into a freight.toml")]
struct Args {
    /// Project directory containing CMakeLists.txt (defaults to the current dir).
    #[arg(default_value = ".")]
    path: PathBuf,
    /// Extract real build data via CMake's File API and write a freight-native
    /// manifest, instead of a `build = "cmake"` self-build. Falls back to the
    /// self-build when the project's shape can't be represented natively.
    #[arg(long)]
    native: bool,
}

fn main() {
    let args = Args::parse();
    let dir = &args.path;

    if dir.join("freight.toml").exists() {
        eprintln!("error: freight.toml already exists in {}", dir.display());
        std::process::exit(1);
    }
    if !dir.join("CMakeLists.txt").is_file() {
        eprintln!("error: no CMakeLists.txt found in {} to migrate", dir.display());
        std::process::exit(1);
    }
    let name = dir
        .canonicalize()
        .ok()
        .and_then(|p| p.file_name().map(|n| n.to_string_lossy().into_owned()))
        .unwrap_or_else(|| "project".into());

    if args.native {
        if let Ok(model) = fileapi::extract(dir) {
            let walk = native::walk_source_set(dir, &model);
            if let Some(toml) = native::render_native_manifest(&name, &model, &walk) {
                if let Err(e) = std::fs::write(dir.join("freight.toml"), toml) {
                    eprintln!("error: {e}");
                    std::process::exit(1);
                }
                println!("✓ migrated `{name}` from CMake — native manifest (File API)");
                return;
            }
        }
        eprintln!(
            "note: native migration not possible for this project shape; \
             writing a build = \"cmake\" self-build instead"
        );
    }

    let config = freight::toolchain::cache::GlobalConfig::load();
    let registry = cmake_scan::ConfiguredRegistries::new(&config);
    match adopt::write_cmake_manifest(dir, &name, "cpp", "c++20", &registry) {
        Ok(pruneable) => {
            println!("✓ migrated `{name}` from CMake — foreign self-build (build = \"cmake\")");
            if !pruneable.is_empty() {
                println!(
                    "  converted {} vendored dependenc{} to freight deps; removable after a clean build:",
                    pruneable.len(),
                    if pruneable.len() == 1 { "y" } else { "ies" },
                );
                for p in &pruneable {
                    println!("    git rm {p}");
                }
            }
        }
        Err(e) => {
            eprintln!("error: {e}");
            std::process::exit(1);
        }
    }
}
