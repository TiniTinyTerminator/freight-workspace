# Freight — Architecture Overview

This document describes how the freight toolchain works end-to-end,
from parsing a `freight.toml` to producing a linked binary.

---

## Workspace layout

```
freight/                       ← workspace root (this repo)
├── crates/
│   ├── freight/               → TiniTinyTerminator/Freight.git
│   ├── freight-registry/      → TiniTinyTerminator/Freight-registry.git
│   ├── cmake-lossless/        → TiniTinyTerminator/cmake-lossless.git
│   ├── docify/                → TiniTinyTerminator/docify.git
│   └── vcpkg-converter/       → TiniTinyTerminator/vcpkg-converter.git
└── docs/                      ← you are here
```

All crates are git submodules. Commit and push inside the submodule
directory, then bump the workspace pointer with `git add crates/<name>`.

---

## `crates/freight` — build engine

### Manifest (`freight.toml`)

Every project has a `freight.toml` at the root.  The most important
sections:

```toml
[package]
name    = "mylib"
version = "0.1.0"

[[bin]]
name = "main"
src  = "src/main.cpp"      # entry-point file only; all other src/ files auto-compiled

[[lib]]
name = "mylib"
type = "static"            # or "shared"

[dependencies]
zlib     = "1.3.2"         # version dep  → resolved from registry
glfw     = { url = "https://github.com/glfw/glfw.git", tag = "3.4" }
myutil   = { path = "../myutil" }
freetype = { url = "https://...", sha256 = "abc", type = "cmake" }

[os.unix]
features = ["pthread"]     # -lpthread via platform feature

[os.linux]
features     = ["asound"]  # -lasound on Linux
dependencies = { alsa = "1.2" }   # Linux-only dep

[os.windows]
features = ["ws2_32"]      # -lws2_32 via platform feature
```

### Build pipeline

```
freight build
    │
    ├─ parse + validate freight.toml
    ├─ detect toolchain  (probe PATH, run .rhai scripts, check version cache)
    ├─ resolve dep graph (topo-sort; activate features; merge OS/arch sections)
    │
    ├─ fetch missing deps
    │   ├─ git deps:      git clone / fetch into .deps/<name>/
    │   ├─ URL deps:      download + extract into .deps/<name>/
    │   └─ registry deps: query registry → fetch from upstream (see below)
    │
    ├─ build foreign deps  (parallel via rayon)
    │   ├─ cmake deps:    cmake configure → make/ninja → install to .deps/<name>/.freight-build/install/
    │   ├─ make deps:     make -j<N>
    │   ├─ meson deps:    meson setup → ninja
    │   └─ autotools deps: ./configure → make
    │
    ├─ compile sources  (parallel via rayon or sequenced by C++20 module DAG)
    │   └─ each: compiler -c -I... -D... -std=... → .o
    │
    └─ link
        └─ linker .o + dep .a → binary / .a / .so
```

### Dependency resolution chain

For a version dep (`zlib = "1.3.2"`) at build time, freight tries in order:

1. **pkg-config** — `pkg-config zlib >= 1.3.2`
2. **System stubs** — hardcoded map: `pthread`, `m`, `dl`, `ws2_32`, …
3. **`.deps/<name>/.freight-fetched`** — already fetched, check for prebuilt lib/include layout
4. **`.deps/<name>/.freight-build-system`** — source dep fetched from registry; run cmake/make (see Registry section)

### Job count

`rayon::current_num_threads()` is the single source of truth, set once
in `main()` from `--jobs` (default: `min(available_parallelism, 6)`).
Do **not** pass job counts as function parameters.

---

## `crates/freight-registry` — self-hosted registry server

### Stack

Axum + SQLite (WAL mode). Two binaries:
- `freight-registry` — HTTP server + CLI admin
- `freight-registry-tui` — TUI monitor

### Wire format (publish)

```
[u32 LE: json_len][json bytes][u32 LE: tar_len][tarball bytes]
```

For metadata-only packages (vcpkg stubs), `tar_len = 0`.

### Database schema (migrations/)

| Migration | Description |
|---|---|
| 0001 | users, packages, versions, tokens, audit_log |
| 0002 | token scopes |
| 0003 | channels |
| 0004 | prebuilt tarballs |
| 0005 | organizations |
| 0006 | dependency JSON in versions |
| 0007 | upstream_url + build_system for metadata-only packages |

Schema changes are **always additive** (`ALTER TABLE … ADD COLUMN`).
Never drop or recreate tables; upgrades are transparent on restart.

### Metadata-only packages

When a package version has `upstream_url` set:

- The server stores no tarball.
- `GET /api/v1/packages/<name>` returns `download_url = upstream_url`.
- `GET /api/v1/packages/<name>/<ver>/download` returns `302 → upstream_url`.
- `build_system` (e.g. `"cmake"`) is also returned in the API response.

The freight client follows the redirect transparently, downloads the
upstream source archive, and runs the appropriate build system.

### Auth

- `password_hash` = Argon2id(SHA-256(plaintext)) — SHA-256 done client-side
- `token_hash` = SHA-256(raw_token) — raw tokens never stored
- `db.audit()` is fire-and-forget (`tokio::spawn`) — never `.await` on request path

---

## `crates/cmake-lossless` — CMake AST library

A library (+ re-export binary) that parses CMake files into a lossless
AST and re-emits them unchanged.

### Backend

Uses **tree-sitter-cmake** as the parser backend (since the tree-sitter
migration). The hand-written lexer was removed.

### Public API

```rust
let file: CMakeFile = cmake_lossless::parse(src)?;
// file.nodes: Vec<Node>  (Command, If, Foreach, While, Function, Macro, Block, Comment)

// Walk all commands (skips Function/Macro/Comment wrapper nodes):
for cmd in file.all_commands() { … }

// Platform condition from an if-block condition:
let scope: Option<&'static str> = cmake_lossless::eval::platform_condition(&condition);
// → Some("windows") | Some("linux") | Some("unix") | Some("macos") | None

// Re-emit:
let out = cmake_lossless::emit::emit(&file, &EmitOptions::default());
```

### `eval::platform_condition`

Maps CMake condition token sequences to a platform scope string:

| CMake condition | Scope |
|---|---|
| `WIN32` | `"windows"` |
| `UNIX` | `"unix"` |
| `APPLE` | `"macos"` |
| `CMAKE_SYSTEM_NAME STREQUAL Linux` | `"linux"` |
| Other / unknown | `None` |

---

## `crates/vcpkg-converter` — vcpkg → freight tooling

Four subcommands:

### `scrape <VCPKG_ROOT> --out DIR`

Walks `ports/*/vcpkg.json` in a cloned microsoft/vcpkg repo.
For each port, generates one `<name>.toml` stub:

```toml
[package]
name    = "zlib"
version = "1.3.2"
url     = "https://github.com/madler/zlib/archive/v1.3.2.tar.gz"
build   = "cmake"

[dependencies]
libfoo = "1.2"
```

No `sha256` in stubs — freight auto-detects on first fetch.

### `convert <PATH> [--vcpkg-root DIR]`

Converts a project's `vcpkg.json` → `freight.toml`:

1. Reads `vcpkg.json` deps and `vcpkg-configuration.json` overrides
2. Resolves concrete versions from `versions/baseline.json`
3. Maps platform-conditional deps to `[os.*]` sections
4. Probes `CMakeLists.txt` for C/C++ standard and `find_package` calls
5. Emits a `freight.toml` with version deps (name → concrete version)

### `registry-import <REGISTRY_DIR> --server URL --token TOKEN`

Pushes scraped stubs into a running freight-registry server as
metadata-only packages:

```sh
vcpkg-scraper registry-import registry-out/ \
    --server http://localhost:7878 \
    --token frt_... \
    --continue   # skip already-published packages
```

Each stub is published with `upstream_url` + `build_system` and an
empty tarball. The registry stores the pointer; freight clients follow
the 302 redirect to fetch from upstream.

### `freight-build-all <REGISTRY_DIR> --freight-bin BIN`

For each stub with a `url` + `build` field, creates a minimal test
project and runs `freight build`. Tests the full fetch+cmake pipeline
without using the registry server. Use this to batch-validate stubs.

### `build-all <VCPKG_ROOT>`

Builds every Linux-compatible vcpkg port with the native `vcpkg` binary.
Used for reference/comparison, not part of the freight pipeline.

---

## Registry integration flow

The full journey from `vcpkg.json` to a freight build:

```
1. vcpkg-scraper scrape ~/vcpkg --out registry-out/
   → one <name>.toml per vcpkg port with url + build

2. vcpkg-scraper registry-import registry-out/ \
       --server http://my-registry:7878 --token frt_...
   → each stub pushed as a metadata-only package
   → registry stores upstream_url + build_system

3. User project has freight.toml:
       [dependencies]
       zlib = "1.3.2"

4. freight build
   a. fetch_registry_deps()
      → GET /api/v1/packages/zlib
      ← { "upstream_url": "https://github.com/.../zlib-1.3.2.tar.gz",
           "build_system": "cmake" }
      → download source archive from upstream URL
      → extract to .deps/zlib/
      → write .deps/zlib/.freight-build-system = "cmake"
   
   b. build_foreign_deps()
      → detects .freight-build-system for version dep "zlib"
      → queues cmake build job: .deps/zlib/ → cmake configure+build+install
      → installs to .deps/zlib/.freight-build/install/{include,lib}/
   
   c. compile + link
      → -I.deps/zlib/.freight-build/install/include
      → -L.deps/zlib/.freight-build/install/lib -lz
      → binary linked ✓
```

---

## Development commands

```sh
# Build
cargo build --workspace
cargo build -p freight-core
cargo build -p freight-registry
cargo build -p vcpkg-scraper
cargo check --workspace
cargo clippy --workspace

# Test
cargo test --workspace
cargo test -p freight-core
cargo test -p cmake-lossless

# Run
cargo run -p freight-core -- build
cargo run -p freight-registry --bin freight-registry -- \
    --data /tmp/dev serve --base-url http://localhost:7878

# vcpkg workflow
cargo run -p vcpkg-scraper -- scrape ~/vcpkg --out registry-out
cargo run -p vcpkg-scraper -- convert /path/to/project --vcpkg-root ~/vcpkg
cargo run -p vcpkg-scraper -- registry-import registry-out \
    --server http://localhost:7878 --token frt_...
cargo run -p vcpkg-scraper -- freight-build-all registry-out \
    --freight-bin ./target/debug/freight
```
