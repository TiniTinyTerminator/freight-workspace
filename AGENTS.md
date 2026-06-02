# AGENTS.md — Workspace guide for AI coding agents

This file is for **AI coding agents** (Claude Code, Codex, etc.) working in the
freight monorepo. It explains the workspace layout, how the crates relate to each
other, what is safe to change, and where open work lives.

For human-oriented project documentation see `CLAUDE.md`.

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

## Workspace layout

```
freight/                         ← workspace root (this repo)
├── Cargo.toml                   # workspace manifest, no [package]
├── CLAUDE.md                    # full project reference for Claude Code
├── AGENTS.md                    # this file
├── chat.md                      # shared agent handoff/chat log
├── crates/
│   ├── cmake-lossless/          # lossless CMake parser (library)
│   ├── freight/                 # core build tool — library + CLI binary
│   ├── freight-registry/        # self-hosted package registry server
│   ├── docify/                  # doc-comment extractor (library + binary)
│   └── vcpkg-converter/         # vcpkg → freight migration tool
```

**Package cache layout** (written by `freight fetch`):
```
<project>/
├── .pkgs/                       # all deps downloaded by freight (survives `freight clean`)
│   └── <name>/                  # source tarball, prebuilt, git clone, or url archive
│       ├── .freight-fetched     # sentinel — present = fully extracted
│       ├── include/             # (prebuilt) headers
│       └── lib/                 # (prebuilt) static/shared libs + pkgconfig
└── target/                      # compiled build artifacts only (wiped by `freight clean`)
    ├── dev/                     # debug build outputs
    ├── release/                 # release build outputs
    └── deps/                    # NOT used — kept here for clarity; all deps are in .pkgs/
```

All crates are independent git submodules with their own history.
Commit and push those changes **inside the submodule directory**, not from the
workspace root.

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
| `cmake-lossless` | [`TODO.md`](crates/cmake-lossless/TODO.md) | `VERSION_*` comparison ops; `IN_LIST`; compound `platform_condition`; `include()` following |
| `freight` | [`TODO.md`](crates/freight/TODO.md) | `has_lang` dedup; `LINK_PRIORITY` constant; Ada whole-program `BuildEvent`; `add_compile_options` / `target_compile_options` migration |
| `freight-registry` | [`TODO.md`](crates/freight-registry/TODO.md) | Real SMTP delivery; TOTP recovery codes; org role enforcement; server-side prebuilt builds |
| `docify` | [`TODO.md`](crates/docify/TODO.md) | CUDA/ISPC/HIP/Python extractors; HTML output |
| `vcpkg-converter` | [`TODO.md`](crates/vcpkg-converter/TODO.md) | `add_subdirectory()` following; failure analysis subcommand |

---

## Open work — cross-crate

### ~~1. cmake-lossless `if` evaluator → freight + vcpkg-converter~~

**Status:** Done. `eval::platform_condition` wired into both consumers.

- **freight** `migration/cmake.rs`: `if(WIN32)`, `if(APPLE)`, `if(UNIX)`, `if(MSVC)` and
  `CMAKE_SYSTEM_NAME STREQUAL "<OS>"` blocks route their deps to
  `[os.windows.dependencies]` / `[os.macos.dependencies]` / `[os.unix.dependencies]`
  etc.; `elseif` chains each get their own scope; `else` falls through to unconditional.
- **vcpkg-converter** `cmake_probe.rs`: `!windows` platform expression mapped to
  `[os.unix.dependencies]`; `CMAKE_C_STANDARD` detected and emitted as `[language.c] std`;
  `find_package` calls inside `if(WIN32)` / `if(UNIX)` / etc. are now scoped correctly —
  the AST is walked manually with a `scope: Option<&'static str>` accumulator derived from
  `eval::platform_condition`, and `SysPackage.scope` gates which OS buckets are emitted.

### ~~2. Registry integration: vcpkg stubs → freight registry → freight build~~

**Status:** Done. Full end-to-end pipeline implemented and tested (50/50 build pass).

- **freight-registry**: new DB columns `upstream_url` + `build_system` in `versions`
  (migration `0007_source_deps.sql`); `publish` accepts metadata-only packages
  (empty tarball + `upstream_url`); `get_package` response includes both fields;
  `/download` returns `302 → upstream_url` for metadata-only packages.
- **freight**: `PackageVersion` carries `upstream_url`/`build_system`; `fetch_registry_deps()`
  detects metadata-only packages and uses `fetch_url_dep()` + writes `.freight-build-system`;
  `build_foreign_deps()` checks `.freight-build-system` for version deps and queues them as
  foreign build jobs (cmake/make/etc.) before the normal prebuilt resolution chain.
- **vcpkg-converter**: new `registry-import` subcommand pushes scraped stubs as metadata-only
  packages to any running freight registry.

See `docs/registry-setup.md` for the full flow.

### ~~3. Registry admin TUI → freight CLI~~

**Status:** Done. `freight tui` is now the admin panel; `freight-registry-tui` binary removed.

- **freight**: new `tui` subcommand (`freight tui [--url URL] [--token TOKEN]`) with five tabs:
  Packages, Users, Tokens, Orgs, Audit. Implemented in `src/bin/freight/tui/registry/`.
  Added deps: `tokio 1`, `reqwest 0.12`, `toml 0.8`. Wraps async event loop in
  `tokio::runtime::Runtime` so `main()` stays synchronous.
- **freight-registry**: removed `freight-registry-tui` binary, `tui` feature gate, and `src/tui/`.
  `ratatui` + `crossterm` optional deps removed from `Cargo.toml`.
- Credentials saved to `~/.config/freight-registry/tui.toml` after login — subsequent
  runs skip the login screen.

### ~~4. Compiler version gating propagation~~

**Status:** Done. `TemplateDef` has `standard_min_versions`; `CompilerTemplate::check_standard_floor`
enforces the floor at compile time; `compile_one` rejects unsupported standards with
`FreightError::OptionError`. Floors set for GCC and Clang across c++20/23/26, c17/23, f2018.

### ~~5. Package dep storage — `.pkgs/` layout~~

**Status:** Done. All deps downloaded by freight (source tarballs, prebuilt tarballs, git
clones, URL archives) extract to `.pkgs/<name>/`. Only compiled build artifacts live in
`target/`. `freight clean` wipes `target/` only, leaving the package cache intact.

- `fetch/http.rs`, `registry/freight_registry.rs`: write to `.pkgs/`
- `dep_cmds.rs`, `build/deps.rs`, `build/mod.rs`, `meta/mod.rs`: read from `.pkgs/`
- `freight fetch --prebuilt <release|debug|source>`: variant selection
- `freight fetch --target <TRIPLE>`: cross-compile prebuilt selection

### ~~6. Registry website — channels, platform support, sidebar, versions~~

**Status:** Done. Full package browser UI delivered.

- **Channels**: moved from inline filter to a settings modal (gear icon); persisted in
  `localStorage`; `GET /api/v1/channels` endpoint; `search_packages` accepts `channels=`
  comma-separated param.
- **Platform support**: per-version `supports` string shown in its own sidebar widget.
- **Sidebar order**: Info → Owners → Platform support → Install → Dependencies → Quick links.
- **Versions table**: descending semver order; active version from server's `best_version()`.
- **Owners widget**: circular avatar placeholder (initial letter); ready for GitHub profile pictures.
- **S3 object layout**: `/{name}/{version}/source.tar.gz`, `/{name}/{version}/README.md`,
  `/{name}/{version}/{triple}/{name}-{version}-{triple}.tar.gz`.
- **Keywords**: server-side fallback term verification so empty clouds never appear.
- **Deps / supports fallback**: walks `pkg.versions` for first entry with data when the
  selected version has an empty field.

### ~~7. `freight doc` ↔ docify wire protocol versioning~~

**Status:** Done. `docify::agent::SCHEMA_VERSION = 1` and `Envelope<T>` added.

All JSON-outputting docify commands (`get`, `context`, `search`, `outline`) now wrap
their output in `{ "schema_version": 1, "data": ... }`. Consumers should reject
`schema_version` values they don't recognise. `freight doc` uses docify as a Rust
library (not a subprocess), so API changes there are caught at compile time.

### 8. IDE plugins

**Status:** In progress. `freight lsp` now exists as a first-pass stdio server in
`crates/freight/src/bin/freight/commands/lsp.rs`; first-pass VS Code and Neovim
wrappers live in `editors/vscode-freight/` and `editors/nvim-freight/`; JetBrains
is still planned.

#### Two-component architecture

**Component A — `freight lsp` subcommand** (Rust, manual stdio LSP bridge)
A language server for `freight.toml` that runs over stdio from
`crates/freight/src/bin/freight/commands/lsp.rs`.

Capabilities:
- **Diagnostics** — first pass implemented: parse + manifest validation + path-dep compatibility
- **Completion** — first pass implemented: known manifest sections/keys and dependency forms
- **Hover** — first pass implemented: manifest section help, including explicit-dep semantics
- **source passthroughs** — first pass implemented: `freight lsp` starts clangd for C-family
  files, fortls for Fortran, and asm-lsp for assembly; it refreshes `compile_commands.json`
  from explicitly declared Freight targets/deps and forwards source-file LSP traffic by extension
- **Go to definition** — for `path = "../foo"` deps, open that `freight.toml`
- **Code actions** — "Update to latest version", "Add missing section"

**Component B — `vscode-freight`** (TypeScript VS Code extension)
Shell that wires the LSP and provides IDE-native features.

| Feature | How |
|---|---|
| `freight.toml` syntax highlighting | TextMate grammar (TOML base + freight-specific scopes) |
| Validation + completion + hover | delegates to `freight lsp` via `vscode-languageclient` |
| Build tasks | VS Code task provider — `build`, `build --release`, `test`, `run`, `clean`, `fetch` |
| Inline diagnostics | Problem matcher on freight's stderr (`error:`, `warning:`, file:line) |
| Status bar | Current profile (dev/release), last build result |
| Keybinding | `Ctrl+Shift+B` → `freight build` |
| clangd integration | Auto-detect `compile_commands.json` generated by freight |

**Phase 1 — VS Code MVP** (no LSP yet)
- TextMate grammar for `freight.toml`
- JSON Schema for `freight.toml` → free validation via VS Code's TOML extension
- Task provider with standard commands + problem matcher
- Status bar item

**Phase 2 — Language server**
- `freight lsp` subcommand implementing LSP over stdio — first pass done
- Plugged into the VS Code extension via `vscode-languageclient` — scaffold done
- Diagnostics, hover, completion using the local registry msgpack cache

**Phase 3 — Rich features + other IDEs**
- Dependency tree panel (codelens / tree view)
- Inline "newer version available" codelens
- JetBrains (CLion) plugin — reuses the same `freight lsp` binary, Kotlin wrapper
- Neovim — minimal `lazy.nvim` plugin that auto-starts `freight lsp` — scaffold done

**Key decisions:**
- LSP is a `freight lsp` subcommand in the main binary, not a standalone crate.
- Registry queries: always from local msgpack cache; never block on network in the LSP hot path.

---

## Crate guide — cmake-lossless

Uses **tree-sitter-cmake** as the backend parser (migrated from a hand-written lexer).
The tree-sitter CST is translated into a typed `Node` enum in `src/lib.rs`.

```
parse(src: &str) -> Result<CMakeFile, ParseError>
    └── translate_source_file() → Vec<Node>
            translate_node()          → Option<Node>
            translate_command()       → CommandInvocation
            translate_if()            → IfBlock
            translate_foreach()       → ForeachLoop
            translate_while()         → WhileLoop
            translate_function()      → FunctionDef
            translate_macro()         → MacroDef
            translate_block_def()     → BlockDef
            translate_argument_list() → Vec<Arg>
            decode_unquoted()         → String
            decode_quoted()           → String
```

**Key invariants**

| Invariant | Where enforced |
|---|---|
| `name` is always lowercase | `translate_command` |
| `Arg::value` has escape sequences decoded (`\t`, `\n`, `\;`, line-continuation) | `decode_unquoted`/`decode_quoted` |
| `AllCommands` skips `Function`/`Macro`/`Comment` nodes | `AllCommands::next` |
| `Node::Comment(String)` preserves comment text verbatim | `translate_node` |

New public API methods belong on `CMakeFile`, `CommandInvocation`, `IfBlock`, or
`Arg` as inherent `impl` blocks. Semantic analysis passes (`vars`, `eval`) stay in
their own files and re-export from `lib.rs`.

`eval::platform_condition` returns `Option<&'static str>` — `None` = "statically unknowable".
Never guess; callers must handle the unknown case.

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
