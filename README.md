# Freight Workspace

This repository is the workspace for the Freight toolchain: a Cargo-inspired
build tool, package manager, registry, documentation extractor, CMake parser, and
vcpkg migration tooling for compiled-language projects.

Freight projects use a single `freight.toml` manifest to describe C, C++,
Fortran, CUDA, HIP, OpenCL, ISPC, D, Ada, Objective-C, and assembly builds that
target GCC or Clang.

## Workspace Layout

```text
.
├── Cargo.toml                 # workspace manifest, no package
├── AGENTS.md                  # guidance for AI coding agents
├── CLAUDE.md                  # detailed project reference
├── docs/                      # architecture and workflow documentation
└── crates/
    ├── cmake-lossless/        # lossless CMake parser
    ├── freight/               # core build tool library and CLI
    ├── freight-registry/      # self-hosted registry server
    ├── docify/                # doc-comment extractor used by freight doc
    └── vcpkg-converter/       # vcpkg to freight migration tooling
```

Each crate under `crates/` is a git submodule with its own upstream history.
Make source commits inside the relevant submodule, then update the workspace
submodule pointer from the repository root.

## Crates

| Crate | Package | Purpose |
|---|---|---|
| `crates/freight` | `freight-core` | Build engine library plus the `freight` CLI. |
| `crates/freight-registry` | `freight-registry` | Axum + SQLite registry server and admin CLI. |
| `crates/docify` | `docify` | Structured doc-comment extraction and rendering. |
| `crates/cmake-lossless` | `cmake-lossless` | Tree-sitter-backed CMake AST, evaluation helpers, and emission. |
| `crates/vcpkg-converter` | `vcpkg-scraper` | vcpkg registry scraping and project conversion. |

Internal dependencies are patched in the workspace `Cargo.toml` so local builds
use the in-tree submodules instead of fetching from GitHub.

## Getting Started

Clone with submodules:

```sh
git clone --recurse-submodules <repo-url>
cd freight
```

If the repository was cloned without submodules:

```sh
git submodule update --init --recursive
```

Build and check the workspace:

```sh
cargo check --workspace
cargo build
cargo test --workspace
```

Run the main CLI from the workspace:

```sh
cargo run -p freight-core -- --help
```

Run a local registry for development:

```sh
cargo run -p freight-registry -- --data /tmp/freight-dev serve --base-url http://localhost:7878
```

Convert a vcpkg project:

```sh
cargo run -p vcpkg-scraper -- convert /path/to/project --vcpkg-root ~/vcpkg
```

## Documentation

- [docs/README.md](docs/README.md) indexes architecture, registry setup, vcpkg
  migration, and CMake parser docs.
- [AGENTS.md](AGENTS.md) records workspace rules, crate boundaries, and open
  cross-crate work for coding agents.
- [CLAUDE.md](CLAUDE.md) is the most detailed project reference.
- Each crate has its own README and TODO file for crate-specific details.

## Development Notes

- The root `Cargo.toml` is only a workspace manifest. Do not add package metadata
  there unless the workspace structure changes.
- Public API changes in `cmake-lossless` may require coordinated updates in both
  `freight` and `vcpkg-converter`.
- Changes to the `docify` MessagePack/JSON agent protocol must be updated in
  `freight doc` at the same time.
- Generated build and conversion output should not be committed.

## Submodule Commit Flow

For changes inside one crate:

```sh
cd crates/<name>
git status
git add <files>
git commit -m "<crate change>"
git push

cd ../..
git add crates/<name>
git commit -m "bump crates/<name>"
```

For cross-crate work, make one commit per affected submodule, then commit the
workspace pointer updates together.
