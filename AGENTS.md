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
| `cmake-lossless` | [`TODO.md`](crates/cmake-lossless/TODO.md) | Pretty-printer / emitter (round-trip rewriting) |
| `freight` | [`TODO.md`](crates/freight/TODO.md) | Compiler version gating for `std = "c++26"` on old GCC |
| `freight-registry` | [`TODO.md`](crates/freight-registry/TODO.md) | Real SMTP delivery; TOTP recovery codes; org role enforcement |
| `docify` | [`TODO.md`](crates/docify/TODO.md) | CUDA/ISPC/HIP/Python extractors; HTML output |
| `vcpkg-converter` | [`TODO.md`](crates/vcpkg-converter/TODO.md) | `!windows` platform expression; C standard detection; failure analysis |

---

## Open work — cross-crate

### 1. cmake-lossless `if` evaluator → freight + vcpkg-converter

**Status:** cmake-lossless half done (`eval::eval_condition`, `eval::platform_condition` implemented). Consumer wiring not started.

`eval::platform_condition` maps `WIN32`, `UNIX`, `APPLE`, `CMAKE_SYSTEM_NAME STREQUAL "<OS>"`,
etc. to freight OS names. Both consumers need to be wired up:

- **freight** `migration/cmake.rs`: map `if(WIN32)` blocks to
  `[os.windows.dependencies]` instead of silently dropping them.
- **vcpkg-converter** `cmake_probe.rs`: restrict `find_package` detections that
  appear inside `if(WIN32)` to `windows` platform deps only.

Touch order: freight migration tests → vcpkg-converter cmake_probe.

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

## Crate guide — cmake-lossless

A hand-written recursive-descent parser. No external parser dependencies. Everything
lives in `src/lib.rs` (~1 000 lines); semantic passes are in `src/vars.rs` and
`src/eval.rs`.

```
parse(src: &str) -> Result<CMakeFile, ParseError>
    └── Parser (private struct)
            parse_file()         → Vec<Node>
            parse_node()         → Node
            parse_command()      → CommandInvocation
            parse_if()           → IfBlock
            parse_foreach()      → ForeachBlock
            parse_while()        → WhileBlock
            parse_function()     → FunctionDef
            parse_macro()        → MacroDef
            parse_block()        → BlockDef
            parse_args()         → Vec<Arg>
            parse_bracket_arg()
            parse_quoted_arg()
            parse_unquoted_arg()
```

**Key invariants**

| Invariant | Where enforced |
|---|---|
| `name` is always lowercase; original case in `name_raw` | `parse_command` |
| Nested `(…)` groups are flattened into the parent arg list | `parse_args` |
| `Arg::raw` is the verbatim source text | all `parse_*_arg` fns |
| `Arg::value` has escapes decoded; `${V}` refs preserved as-is | `parse_quoted_arg`, `parse_unquoted_arg` |
| `AllCommands` skips `Function`/`Macro` bodies | `AllCommands::next` |
| `ParseError` carries 1-based line and column | `Parser::advance` |

**Lossless** means every byte of the original input is recoverable from `raw` fields.
Do not strip or transform `raw` during parsing.

New public API methods belong on `CMakeFile`, `CommandInvocation`, `IfBlock`, or
`Arg` as inherent `impl` blocks. Semantic analysis passes (`vars`, `eval`) stay in
their own files and re-export from `lib.rs`.

`eval::eval_condition` returns `Option<bool>` — `None` = "statically unknowable".
Never guess; callers must handle the unknown case.

Do not add external dependencies. Do not evaluate `${VAR}` inside the parser.

---

## Crate guide — docify

Extracts structured doc comments from source files, renders them as Markdown, JSON,
MessagePack, or a terminal TUI. Used by `freight doc`.

```
src/
├── lib.rs           — public API: extract_file(), extract_dir(), DocSet, DocItem
├── main.rs          — CLI binary
├── agent.rs         — freight doc wire protocol (JSON/MessagePack over stdout)
├── render_md.rs     — Markdown page renderer
├── render_tui.rs    — terminal output renderer
├── tui.rs           — interactive TUI
└── extract/
    ├── mod.rs       — DocExtractor trait, DocItem, DocSet, ExtractorRegistry
    ├── common.rs    — shared helpers (collect_c_block, collect_line_block, build_item, …)
    ├── cpp.rs / rust.rs / fortran.rs / ada.rs / d.rs / java.rs / go.rs
    ├── zig.rs / kotlin.rs / swift.rs
```

**Core types**

```rust
pub trait DocExtractor: Send + Sync {
    fn extensions(&self) -> &[&str];
    fn extract(&self, path: &Path, source: &str) -> Vec<DocItem>;
}
// DocItem fields: name, kind, lang, file, line, brief, tags, signature, access, meta
// DocKind: Function | Type | Constant | Module | Namespace | Subroutine | Variable | Unknown
// TagKind: Param | Return | Throws | Note | Example | See | Since | Deprecated | Author
```

**Adding a new language extractor** (5 steps):

1. Add a `DocLanguage` variant + `label()` + `display_signature()` arm in `extract/mod.rs`.
2. Add file extensions to `lang_from_ext` in `extract/mod.rs`.
3. Create `extract/<lang>.rs` implementing `DocExtractor`. Use `common.rs` helpers —
   `rust.rs` for `///`-style, `java.rs` for `/** */`-style.
4. Register via `ExtractorRegistry::new()` in `extract/mod.rs`.
5. Add tests calling the lang-specific `extract_*` function directly (not via registry).

**Common helpers in `common.rs`:** `collect_line_block`, `collect_c_block`,
`build_item`, `item_has_content`, `next_non_blank`, `first_ident`, `next_decl_sym`.

**Wire protocol (`agent.rs`):** `freight doc` reads MessagePack/JSON frames from
docify's stdout. `SymbolJson` fields are the wire format — renaming requires a
matching change in `freight/src/doc/` in the same commit.

Do not rename or remove `DocItem` fields or `TagKind` variants without updating the
`freight doc` reader. Do not add language-specific logic to `common.rs`.

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
