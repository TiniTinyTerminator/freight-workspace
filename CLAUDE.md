# CLAUDE.md

Guidance for Claude Code when working in this workspace.

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
│   └── vcpkg-converter/         # git submodule → TiniTinyTerminator/vcpkg-converter.git
```

Submodule updates: `git submodule update --remote --merge`

---

## Crate map

### `crates/freight` — core build tool

Package name: `freight-core` (lib) + `freight` (binary).

**The library (`src/lib.rs`) is the entire build engine.** The binary only parses CLI args and calls into the library. Never print from library code; emit `BuildEvent`s instead and let the CLI layer format them.

```
src/
├── lib.rs / error.rs / event.rs
├── bin/freight/            # clap dispatch — one cmd_* per command
├── build/                  # compile.rs, link.rs, discover.rs, deps.rs, features.rs, modules.rs
├── manifest/               # freight.toml parsing + validation
├── toolchain/              # compiler detection, Rhai template evaluation, version cache
├── registry/               # HTTP registry client (FreightRegistry, PackageRepo trait)
├── fetch/                  # git.rs (git2), http.rs (curl + SHA-256 verify)
├── doc/                    # doc comment extraction + Markdown/JSON/msgpack rendering
└── meta/                   # foreign build system integrations (CMake, Meson, autotools…)
```

**Build pipeline** (in order):
1. Parse + validate `freight.toml`
2. Detect toolchain — probe `$PATH`, run `.rhai` scripts, consult version cache
3. Resolve dep graph — topo-sort, compile path deps (freight or foreign) in order
4. Walk sources — map extension → language key
5. Scan C++ sources for `export module` / `import` (C++20 module DAG)
6. Compile — parallel via rayon (flat) or batched by module topo-order
7. Link — `.o` + dep `.a` → binary / `.a` / `.so`

**`freight.toml` manifest — dependency system**

Every entry in `[dependencies]` (and its conditional variants) is one of:

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
| `sha256` | `String` | Checksum for `url` deps |
| `system` | `String` | Link `-l<name>` directly; no source, no fetch |
| `features` | `[String]` | Features to activate on this dep |
| `default-features` | `bool` (true) | Set `false` to skip the dep's `default` feature set |
| `optional` | `bool` (false) | Only active when a feature enables it via `dep:name` |
| `os` | `String \| [String]` | Filter: dep only active on these OSes |
| `arch` | `String \| [String]` | Filter: dep only active on these CPU architectures |
| `targets` | `[String]` | Cross-compilation triple allowlist; absent = all |
| `backend` | `String` | Foreign build system: `cmake`, `make`, `meson`, `autotools`, `scons`, `bazel`, `none` |
| `include` | `[String]` | Include dirs for `backend = "none"` (header-only) or foreign deps |
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

`system = "foo"` skips the chain and directly links `-lfoo`. Use only when the pkg-config name differs from the dep name or to force system-only linkage. For normal system libraries freight finds them automatically via pkg-config.

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

Inline `os`/`arch` filters on individual deps also work and follow the same valid key names:
```toml
[dependencies]
pthread = { system = "pthread", os = "linux" }
ws2_32  = { system = "ws2_32",  os = "windows" }
```

**Features** (`src/build/features.rs`):

```toml
[features]
default = ["logging"]         # active unless --no-default-features
logging = ["dep:spdlog"]      # activate optional dep "spdlog"
tls     = ["openssl"]         # implies feature "openssl"
full    = ["tls", "json"]     # transitive expansion
json    = []                  # leaf feature, no extra deps
```

Feature entry values are `Vec<String>`:
- `"feature-name"` — activates that feature transitively
- `"dep:name"` — activates an optional dep without emitting a define

Active features are uppercased and injected as preprocessor defines: `with-tls` → `-DWITH_TLS`. Cycles are rejected at validation time.

**Compiler templates** live in `toolchains/` as `.rhai` scripts. Each script registers callbacks via `compiler_option` / `language_option`. The script receives a `ctx` object (`ctx.value`, `ctx.version`, `ctx.arch`, `ctx.os`) and calls `add_flag(s)` to inject flags. See `docs/compiler-templates.md` for the full reference.

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

Run locally:
```sh
cargo run -p freight-registry -- --data /tmp/freight-dev serve --base-url http://localhost:7878
```

### `crates/docify` — doc comment extractor

Library + binary. Extracts structured doc comments from C/C++ (Doxygen `///`, `/** */`), Fortran (`!>`, `!!`), Rust (`///`), D (`/++ +/`), Ada (`--!`), and more. Outputs Markdown, JSON, or MessagePack. Used by `freight doc` via a git dependency in freight-core's `Cargo.toml`.

### `crates/vcpkg-converter` (package: `vcpkg-scraper`)

Binary tool with two subcommands:
- `scrape <VCPKG_ROOT>` — walks `ports/*/vcpkg.json`, generates `[[package]]` registry stubs to populate the freight registry
- `convert <PATH> [--vcpkg-root DIR]` — converts a project's `vcpkg.json` into a `freight.toml`; resolves versions from `versions/baseline.json`; maps platform-conditional deps to `[os.*]` sections; filters vcpkg-internal pseudo-packages (`vcpkg-*`); propagates `features` and `default-features` on deps

---

## Development commands

```sh
cargo build                          # build all workspace crates
cargo build -p freight               # build just the freight binary
cargo check                          # fast type-check
cargo clippy --workspace             # lint everything
cargo test --workspace               # run all tests

# Registry server
cargo run -p freight-registry -- --data /tmp/freight-dev serve --base-url http://localhost:7878
cargo run -p freight-registry -- --data /tmp/freight-dev user add alice --email alice@example.com
cargo run -p freight-registry -- --data /tmp/freight-dev token add dev --user alice
```

---

## Coding rules

**Error handling**
- `freight-core`: use `thiserror` for typed errors, `anyhow` for internal call chains. Public API functions return `Result<_, FreightError>` or `Result<_, anyhow::Error>` depending on whether callers need to match on the variant.
- `freight-registry`: `ApiError` in `api/mod.rs` is the only error type crossing into handlers. Use `anyhow` everywhere else and let the `From<anyhow::Error>` impl convert it.
- Never use `.unwrap()` or `.expect()` in library code.

**No printing in library code**
- `freight-core`: emit `BuildEvent`s (or return structured results); the CLI layer in `src/bin/freight/` formats and prints them.
- Diagnostic output from the build engine must go through the event system, not `eprintln!`.

**Database (freight-registry)**
- Schema changes: add-only via `add_column_if_missing()`. Never drop or recreate tables — deployed databases upgrade on restart.
- Always run `db.audit()` in a `tokio::spawn`; never `.await` it on the request path.

**Compiler templates**
- New compiler support: add a `.rhai` file under `toolchains/<vendor>/`. Register capabilities with `compiler_option` / `language_option`. Base shared logic in `_<vendor>-base.rhai` and `#include` it.
- Fill in `min_compiler_version` for any standard flags you add (see AGENTS.md — per-standard version gating task).

**Workspace hygiene**
- Keep `AGENTS.md` at the workspace root updated: mark tasks done in the same commit that implements them; add new gaps as you find them.
- Wire protocol or API shape changes to freight-registry and freight-core must be made together.

**Style**
- Rust edition 2024 for new crates, 2021 for existing ones until a deliberate upgrade.
- `resolver = "2"` is set at the workspace level.
- No `unsafe` without a comment explaining the invariant being upheld.

---

## Git workflow

This workspace exists purely for development convenience — each submodule is an independent GitHub repo with its own history. Keep them clean:

- **Commit and push inside the submodule directory**, not from the workspace root. Each repo owns its own commits.
  ```sh
  cd crates/freight && git add -p && git commit && git push
  cd crates/freight-registry && git add -p && git commit && git push
  ```
- **One repo per commit.** If a change touches multiple crates, make a separate commit in each affected submodule repo. Don't bundle cross-repo changes into a single workspace-level commit.
- **Update the workspace submodule pointer** after pushing from a submodule, so the workspace root tracks the new HEAD:
  ```sh
  # from the workspace root
  git add crates/freight   # (or whichever submodule moved)
  git commit -m "bump crates/freight"
  git push
  ```
- The workspace root (`/home/max/freight`) should only ever contain pointer bumps and workspace-level files (`Cargo.toml`, `CLAUDE.md`, `AGENTS.md`). No source code lives here.
