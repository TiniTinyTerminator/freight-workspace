# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Agent coordination

Read [`chat.md`](chat.md) when starting work. It is the shared chatroom for
Claude, Codex, and other coding agents to leave handoff notes, questions, and
summaries of pushed changes.

When you make a meaningful change, add a short dated entry to `chat.md` with:
- what changed,
- what was tested,
- what was pushed or left uncommitted,
- any questions for the next agent.

---

## What this project is

**Freight** is a Cargo-inspired build tool and package manager for compiled languages that target GCC or Clang. A single `freight.toml` replaces Makefiles and CMake for C, C++, Fortran, CUDA, HIP, OpenCL, ISPC, D, Ada, Objective-C, and assembly projects.

This repository is the **monorepo workspace** that develops all freight tooling together. Each crate lives in its own GitHub repo and is pulled in as a git submodule.

---

## Workspace layout

```
/home/max/freight/               ← workspace root (this repo)
├── Cargo.toml                   # workspace manifest — no [package]
├── AGENTS.md                    # open tasks and known gaps
├── crates/
│   ├── freight/                 # git submodule → TiniTinyTerminator/Freight.git
│   ├── freight-registry/        # git submodule → TiniTinyTerminator/Freight-registry.git
│   ├── docify/                  # git submodule → TiniTinyTerminator/docify.git
│   ├── libtexprintf/            # workspace-local Rust binding for bartp5/libtexprintf
│   └── vcpkg-converter/         # git submodule → TiniTinyTerminator/vcpkg-converter.git
```

Submodule updates: `git submodule update --remote --merge`

`crates/libtexprintf` is currently not a submodule. Keep it in the root workspace
history unless it is later split into its own repository.

---

## Crate map

### `crates/freight` — core build tool

Package name: `freight` (package + binary); lib crate name is `freight_core`.

**The library (`src/lib.rs`) is the entire build engine.** The binary only parses CLI args and calls into the library. Never print from library code; emit `BuildEvent`s instead and let the CLI layer format them.

```
src/
├── lib.rs / error.rs / event.rs
├── bin/freight/            # clap dispatch — one cmd_* per command
├── build/                  # compile.rs, link.rs, discover.rs, deps.rs, features.rs, modules.rs, proto.rs
├── manifest/               # freight.toml parsing + validation
├── toolchain/              # compiler detection, Rhai template evaluation, version cache
├── registry/               # HTTP registry client (FreightRegistry, PackageRepo trait)
├── fetch/                  # git.rs (git2), http.rs (curl + SHA-256 verify)
├── doc/                    # doc comment extraction + Markdown/JSON/msgpack rendering
├── meta/                   # foreign build system integrations (CMake, Meson, autotools…)
└── migration/              # cmake.rs, make.rs, autotools.rs — `freight migrate` converters
```

**Build pipeline** (in order):
1. Parse + validate `freight.toml`
2. Detect toolchain — probe `$PATH`, run `.rhai` scripts, consult version cache
3. Resolve dep graph — topo-sort; foreign deps (cmake/make/meson/autotools) collected then built in parallel via rayon; pkg-config/system/version deps resolved sequentially first
4. Walk sources — map extension → language key; `src/` is walked automatically
5. **Proto codegen** (if `[language.proto]` declared) — runs `protoc` on `.proto` files in `src/`, injects generated `.pb.cc` files into the compile list, adds generated header dir to include path
6. Scan C++ sources for `export module` / `import` (C++20 module DAG)
7. Compile — parallel via rayon (flat) or batched by module topo-order
8. Link — `.o` + dep `.a` → binary / `.a` / `.so`

**Job count**: `rayon::current_num_threads()` is the single source of truth. Set once in `main()` from `--jobs` (default: `min(available_parallelism, 6)`). All of `meta/cmake.rs`, `meta/make.rs`, `meta/meson.rs`, `meta/autotools.rs` read it without taking a parameter.

**Source discovery**: freight walks `src/` and compiles every file with a recognised extension. `BinTarget.src` identifies the entry-point file (the one with `main()`) for linker deduplication only — it does not restrict which files get compiled. All other sources in `src/` are picked up automatically.

**`freight.toml` manifest — dependency system**

Three dependency sections:
- `[dependencies]` — linked in all builds (release + debug)
- `[build-dependencies]` — executables needed during compilation (cmake, ninja, protoc, …). Fetched first; if an installed dep has a `bin/` directory, those executables are prepended to PATH for all subsequent build steps so locally-installed tools take precedence over system ones.
- `[dev-dependencies]` — linked only in debug/dev builds (test frameworks, sanitizers, debug utilities)

Every entry in `[dependencies]` (and `[build-dependencies]` / `[dev-dependencies]`) is one of:

```toml
# Simple: bare version constraint — freight resolves via pkg-config → stubs → registry
libfoo = "1.2"
libfoo = ">=1.0"
libfoo = "*"

# Detailed: table with extended fields
libfoo = { version = "1.2", features = ["tls"], default-features = false }
libfoo = { path = "../libfoo" }                          # local freight project or foreign
libfoo = { git = "https://github.com/x/y.git", tag = "v1" }
libfoo = { url = "https://example.com/foo.tar.gz", sha256 = "abc..." }
libfoo = { system = "foo" }                              # link -lfoo directly, no fetch
```

`DetailedDep` fields (all optional unless noted):

| Field | Type | Notes |
|---|---|---|
| `version` | `String` | Constraint: `"1.2"`, `">=1.0"`, `"*"` |
| `path` | `String` | Relative path; auto-detects `freight.toml` vs foreign build system |
| `git` | `String` | Repo URL; one of `branch`/`tag`/`rev` selects the ref |
| `branch` / `tag` / `rev` | `String` | Mutually exclusive; `rev` pins and blocks `freight update` |
| `url` | `String` | Archive URL (`.tar.gz`, `.zip`, etc.) |
| `sha256` | `String` | Optional checksum; omit to auto-detect on first fetch |
| `system` | `String` | Link `-l<name>` directly; no source, no fetch |
| `features` | `[String]` | Features to activate on this dep |
| `default-features` | `bool` (true) | Set `false` to skip the dep's `default` feature set |
| `optional` | `bool` (false) | Only active when a feature enables it via `dep:name` |
| `os` | `String \| [String]` | Filter: dep only active on these OSes |
| `arch` | `String \| [String]` | Filter: dep only active on these CPU architectures |
| `targets` | `[String]` | Cross-compilation triple allowlist; absent = all |
| `type` | `String` | How the dep content is handled: `cmake`, `make`, `meson`, `autotools`, `scons`, `bazel`, `none` |
| `include` | `[String]` | Include dirs for `type = "none"` (header-only) or foreign deps |
| `cmake-args` | `[String]` | Extra args passed to CMake configure |
| `patches` | `[String]` | Patch files applied after fetch (`patch -p1`) |
| `repo` | `String` | Registry to use: `"system"` (stubs only) or a named registry |
| `channel` | `String` | Registry channel (e.g. `"stable"`, `"experimental"`) |
| `unity` | `bool` | Override dep's unity-build setting |

**Dep type mutual exclusivity**: at most one of `path`, `git`, `url`, `system` (all combine with `version`). Git ref: at most one of `branch`, `tag`, `rev`.

**Resolution chain** for a version dep (no `path`/`git`/`url`/`system`):
1. **pkg-config** — query system `pkg-config` for `{name}` with version constraint
2. **System stubs** — hardcoded map of common libs (pthread, ws2_32, m, …)
3. **`.deps/` cache** — populated by `freight fetch` from registry

**Conditional dependency sections** — merged on top of `[dependencies]` for the current host:

```toml
[os.linux.dependencies]       # Linux only
[os.windows.dependencies]     # Windows only
[os.macos.dependencies]       # macOS only
[os.unix.dependencies]        # all Unix-like (applied before specific OS)
[arch.x86_64.dependencies]    # x86-64 only
[arch.aarch64.dependencies]   # ARM64 only
```

Valid `[os.*]` keys: `unix`, `bsd`, `linux`, `windows`, `macos`, `freebsd`, `openbsd`, `netbsd`, `dragonfly`, `android`, `ios`, `solaris`, `illumos`

Valid `[arch.*]` keys: `x86_64`, `x86`, `aarch64`, `arm`, `mips`, `mips64`, `powerpc`, `powerpc64`, `riscv64`, `s390x`, `sparc64`, `wasm32`, `wasm64`

Merge order: base → family (e.g. `unix`) → specific OS → arch. Later entries shadow earlier ones for the same dep key.

**Features** (`src/build/features.rs`):

```toml
[features]
default = ["logging"]         # active unless --no-default-features
logging = ["dep:spdlog"]      # activate optional dep "spdlog"
tls     = ["openssl"]         # implies feature "openssl"
```

Active features are uppercased and injected as preprocessor defines: `with-tls` → `-DWITH_TLS`. Cycles are rejected at validation time.

**`freight migrate`** — in-place converters from foreign build systems:

```sh
freight migrate cmake /path/to/project      # reads CMakeLists.txt → writes freight.toml
freight migrate make  /path/to/project      # reads Makefile → writes freight.toml
freight migrate autotools /path/to/project  # reads configure.ac → writes freight.toml
```

Each migrator uses `cmake_lossless` to parse the source AST, routes `find_package` / `target_link_libraries` inside `if(WIN32)` / `if(UNIX)` blocks to `[os.windows.dependencies]` / `[os.unix.dependencies]`, and emits `src = "entry_point_file"` for `[[bin]]` targets (other sources in `src/` are auto-discovered).

**Compiler templates** live in `toolchains/` as `.rhai` scripts. Each script registers callbacks via `compiler_option` / `language_option`. The script receives a `ctx` object (`ctx.value`, `ctx.version`, `ctx.arch`, `ctx.os`) and calls `add_flag(s)` to inject flags.

---

### `crates/freight-registry` — self-hosted registry server

Single binary with two modes: CLI admin (`user`, `token` subcommands) and HTTP server (`serve`). Stack: **Axum + SQLite** (WAL mode).

Key invariants:
- `password_hash` = Argon2id(SHA-256(plaintext)) — SHA-256 is done client-side
- `token_hash` = SHA-256(raw_token) hex — raw tokens never stored
- DB migrations via `add_column_if_missing()` — never drop/recreate tables; upgrades are transparent on restart
- `db.audit()` is fire-and-forget (`tokio::spawn`) — never await it on the request path

Wire format (matches cargo's publish endpoint):
```
[u32 LE: JSON length][JSON bytes][u32 LE: tarball length][tarball bytes]
```

API modules: one file per handler group in `src/api/`, registered in `api/mod.rs::router()`. `ApiError` is the standard error type; its `From<anyhow::Error>` logs at error and returns 500.

---

### `crates/docify` — doc comment extractor

Library + binary. Extracts structured doc comments from C/C++ (Doxygen `///`, `/** */`), Fortran (`!>`, `!!`), Rust (`///`), D (`/++ +/`), Ada (`--!`), and more. Outputs Markdown, JSON, or MessagePack. Used by `freight doc` via a git dependency in freight-core's `Cargo.toml`.

---

### `crates/libtexprintf` — optional terminal TeX binding

Workspace-local Rust wrapper for [`bartp5/libtexprintf`](https://github.com/bartp5/libtexprintf). It builds without native linking by default. Enable the crate's `native` feature to link `-ltexprintf`; set `TEXPRINTF_LIB_DIR` if the library is installed outside the default linker search path.

`docify` uses this only behind its optional `libtexprintf` feature. Plain `rich-math` uses docify's built-in Unicode renderer and does not require the GPL-3.0 native library.

---

### `crates/vcpkg-converter` (package: `vcpkg-scraper`)

Binary tool with four subcommands:

- **`scrape <VCPKG_ROOT> --out DIR`** — walks `ports/*/vcpkg.json`, generates one `[package]` stub `.toml` per port (one file per version). Resolves `${VERSION}` in source URLs, filters `vcpkg-*` internal packages from deps. No `sha256` in stubs — freight auto-detects on first fetch.

- **`convert <PATH> [--vcpkg-root DIR]`** — converts a project's `vcpkg.json` into a `freight.toml`. Resolves versions from `versions/baseline.json`; maps platform-conditional deps to `[os.*]` sections; probes `CMakeLists.txt` for C/C++ standard and `find_package` calls (scoped by `if(WIN32)` / `if(UNIX)` blocks); filters `vcpkg-*` pseudo-packages. Emits a `# Add [[bin]] / [[lib]] sections as needed.` comment because source layout isn't known from `vcpkg.json` alone.

- **`build-all <VCPKG_ROOT> [--jobs N] [--continue]`** — builds every Linux-compatible vcpkg port sequentially using the `vcpkg` binary, one at a time. `--jobs` controls `VCPKG_MAX_CONCURRENCY` (cmake/ninja threads per port, default 6). `--continue` resumes from a previous run.

- **`freight-build-all <REGISTRY_DIR> --freight-bin BIN [--continue]`** — for each scraped stub with a `url` and `build` field, creates a test project with that package as a URL dep and runs `freight build`. Tests whether freight can fetch and compile the upstream source.

**Registry stub format** (one file per version, e.g. `zlib.toml`):
```toml
[package]
name    = "zlib"
version = "1.3.2"
url     = "https://github.com/madler/zlib/archive/v1.3.2.tar.gz"
build   = "cmake"

[dependencies]
libfoo = "*"

[features]
bar = ["baz"]
```

**cmake_probe** (`src/cmake_probe.rs`) — walks the CMake AST manually (not `all_commands()`) with a `scope: Option<&'static str>` accumulator from `eval::platform_condition`. `find_package` calls inside `if(WIN32)` only emit Windows features; inside `if(UNIX)` only emit Linux/macOS features.

---

## Development commands

```sh
# Build
cargo build                          # all workspace crates
cargo build -p freight               # freight binary
cargo build -p vcpkg-scraper         # vcpkg converter
cargo build -p freight-registry      # registry server
cargo check --workspace              # fast type-check
cargo clippy --workspace             # lint

# Test
cargo test --workspace               # all tests
cargo test -p freight                # one crate
cargo test -p freight -- migration::cmake::tests::win32_deps_in_platform_section  # single test

# Run
cargo run -p freight -- build        # freight build (from a project dir)
cargo run -p freight-registry -- --data /tmp/freight-dev serve --base-url http://localhost:7878
cargo run -p freight-registry -- --data /tmp/freight-dev user add alice --email alice@example.com
cargo run -p freight-registry -- --data /tmp/freight-dev token add dev --user alice

# vcpkg-converter
cargo run -p vcpkg-scraper -- scrape ~/vcpkg --out registry-out
cargo run -p vcpkg-scraper -- convert /path/to/project --vcpkg-root ~/vcpkg
cargo run -p vcpkg-scraper -- build-all ~/vcpkg --jobs 6
cargo run -p vcpkg-scraper -- build-all ~/vcpkg --jobs 6 --continue
cargo run -p vcpkg-scraper -- freight-build-all registry-out --freight-bin ./target/debug/freight
```

---

## Coding rules

**Error handling**
- `freight` (`freight_core` lib): use `thiserror` for typed errors, `anyhow` for internal call chains. Public API functions return `Result<_, FreightError>` or `Result<_, anyhow::Error>` depending on whether callers need to match on the variant.
- `freight-registry`: `ApiError` in `api/mod.rs` is the only error type crossing into handlers. Use `anyhow` everywhere else and let the `From<anyhow::Error>` impl convert it.
- Never use `.unwrap()` or `.expect()` in library code.

**No printing in library code**
- `freight` lib: emit `BuildEvent`s (or return structured results); the CLI layer in `src/bin/freight/` formats and prints them.

**Database (freight-registry)**
- Schema changes: add-only via `add_column_if_missing()`. Never drop or recreate tables.
- Always run `db.audit()` in a `tokio::spawn`; never `.await` it on the request path.

**Compiler templates**
- New compiler support: add a `.rhai` file under `toolchains/<vendor>/`. Register capabilities with `compiler_option` / `language_option`. Base shared logic in `_<vendor>-base.rhai` and `#include` it.

**Style**
- Rust edition 2024 for new crates, 2021 for existing ones until a deliberate upgrade.
- `resolver = "2"` is set at the workspace level.
- No `unsafe` without a comment explaining the invariant being upheld.
- Keep `AGENTS.md` updated in the same commit that implements or closes an item.

---

## Git workflow

Each submodule is an independent GitHub repo with its own history.

- **Commit and push inside the submodule directory**, not from the workspace root.
- **One repo per commit.** Cross-crate changes get one commit per affected submodule.
- **Update the workspace submodule pointer** after pushing from a submodule:
  ```sh
  git add crates/<name>
  git commit -m "bump crates/<name> — <brief reason>"
  git push
  ```
- The workspace root should only ever contain pointer bumps and workspace-level files (`Cargo.toml`, `CLAUDE.md`, `AGENTS.md`).
