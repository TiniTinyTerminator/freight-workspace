# AGENTS.md — Workspace guide for AI coding agents

This file is for **AI coding agents** (Claude Code, Codex, etc.) working in the
freight monorepo. It explains the workspace layout, how the crates relate to each
other, what is safe to change, and where open work lives.

For human-oriented project documentation see `CLAUDE.md`.

---

## Workspace layout

```
freight/                         ← workspace root (this repo)
├── Cargo.toml                   # workspace manifest, no [package]
├── CLAUDE.md                    # full project reference for Claude Code
├── AGENTS.md                    # this file
├── crates/
│   ├── cmake-lossless/          # lossless CMake parser (library)
│   ├── freight/                 # core build tool — library + CLI binary
│   ├── freight-registry/        # self-hosted package registry server
│   ├── docify/                  # doc-comment extractor (library + binary)
│   └── vcpkg-converter/         # vcpkg → freight migration tool
```

Each crate is an independent git submodule with its own history. Commit and push
**inside the submodule directory**, not from the workspace root.

---

## Crate dependency graph

```
cmake-lossless  ←── freight (migration module)
cmake-lossless  ←── vcpkg-converter (cmake_probe module)
docify          ←── freight (freight doc command)
freight-registry    (standalone; no internal deps)
```

Changes to `cmake-lossless`'s public API will require updates in both `freight`
and `vcpkg-converter`.

---

## Open work — per-crate

Each crate has its own `TODO.md` with detailed items. Start there:

| Crate | TODO | Top open item |
|---|---|---|
| `cmake-lossless` | [`TODO.md`](crates/cmake-lossless/TODO.md) | Expose `AllCommands` publicly; variable tracker; `if` evaluator |
| `freight` | [`TODO.md`](crates/freight/TODO.md) | Compiler version gating for `std = "c++26"` on old GCC |
| `freight-registry` | [`TODO.md`](crates/freight-registry/TODO.md) | Real SMTP delivery; TOTP recovery codes; org role enforcement |
| `docify` | [`TODO.md`](crates/docify/TODO.md) | Zig / Swift / Kotlin extractors; HTML output |
| `vcpkg-converter` | [`TODO.md`](crates/vcpkg-converter/TODO.md) | Complex platform expression mapping; failure analysis command |

---

## Open work — cross-crate

### 1. cmake-lossless `if` evaluator → freight + vcpkg-converter

**Status:** Not started. Blocked on cmake-lossless work.

Once cmake-lossless can evaluate constant `if` conditions (`WIN32`, `UNIX`, `APPLE`,
`CMAKE_SYSTEM_NAME STREQUAL`), both consumers benefit:

- **freight** `migration/cmake.rs`: map `if(WIN32)` blocks to
  `[os.windows.dependencies]` instead of silently dropping them.
- **vcpkg-converter** `cmake_probe.rs`: restrict `find_package` detections that
  appear inside `if(WIN32)` to `windows` platform deps only.

Touch order: cmake-lossless → freight migration tests → vcpkg-converter cmake_probe.

### 2. Compiler version gating propagation

**Status:** Not started.

`freight` needs the version floor table in the compiler templates. Once that
exists, the `vcpkg-converter`'s C++ standard detection can cross-check the
detected standard against the system compiler and warn if the floor is too low.

Touch order: freight toolchain templates → freight `assemble_compile_flags` →
optional warning in vcpkg-converter `convert` output.

### 3. `freight doc` ↔ docify wire protocol versioning

**Status:** Implicit — no version field in MessagePack envelope.

The `freight doc` command shells out to `docify` and reads MessagePack. If the
docify schema changes, `freight` will silently misparse the output. Add a
`schema_version: u32` field to the envelope and reject unknown versions with a
clear error.

Touch order: docify `agent.rs` → freight `doc/` → bump both crates together.

---

## What agents should and should not touch

### Safe to modify freely
- Any file inside a single crate that has no cross-crate API surface.
- Tests, documentation, and `TODO.md` files.
- `CLAUDE.md` and `AGENTS.md` (this file) to reflect completed or new work.

### Requires coordinated change across crates
- **cmake-lossless public API** (`pub` items in `src/lib.rs`): changing a type or
  removing a method breaks `freight/src/migration/cmake.rs` and
  `vcpkg-converter/src/cmake_probe.rs`. Update all three in the same logical change.
- **docify MessagePack schema** (`agent.rs`): must stay in sync with the
  `freight doc` reader. Bump together.
- **freight-core `BuildEvent` variants**: the CLI layer (`src/bin/freight/`) pattern-
  matches exhaustively. Adding a variant requires updating the match arms there too.

### Do not modify
- `Cargo.toml` at the workspace root except to add/remove workspace members.
- Submodule `.git` internals.
- Generated files under `build-all-out/` and `log/converter/` in vcpkg-converter.

---

## How to run things

```sh
# Build and check
cargo build                          # all crates
cargo check --workspace              # fast type-check
cargo clippy --workspace             # lint
cargo test --workspace               # all tests

# Individual crates
cargo build -p freight               # freight binary
cargo build -p freight-registry      # registry server
cargo build -p vcpkg-scraper         # vcpkg converter

# Registry server (local dev)
cargo run -p freight-registry -- --data /tmp/freight-dev serve --base-url http://localhost:7878

# vcpkg converter
cargo run -p vcpkg-scraper -- convert <path/to/vcpkg.json> --vcpkg-root ~/vcpkg
cargo run -p vcpkg-scraper -- build-all ~/vcpkg --jobs 6          # fresh run
cargo run -p vcpkg-scraper -- build-all ~/vcpkg --jobs 6 --continue  # resume
```

---

## Commit conventions

- Commit and push **inside each submodule** for source changes.
- After pushing a submodule, update the workspace pointer:
  ```sh
  git add crates/<name>
  git commit -m "bump crates/<name>"
  ```
- Cross-crate changes get one commit per affected submodule, then a workspace bump
  that references all of them in the message.
- Keep `AGENTS.md` and the relevant `TODO.md` up to date in the same commit that
  implements or closes an item.
