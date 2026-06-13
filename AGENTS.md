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
│   ├── clang-bridge/            # in-process clang AST bridge (C++ FFI + Rust API) for the LSP
│   ├── cmake-lossless/          # lossless CMake parser (library)
│   ├── fortran-lsp/             # native Rust Fortran indexer/LSP primitives (fortls port)
│   ├── freight/                 # core build tool — library + CLI binary
│   ├── freight-registry/        # self-hosted package registry server
│   ├── docify/                  # doc-comment extractor (library + binary)
│   └── vcpkg-converter/         # vcpkg → freight migration tool
├── editors/
│   ├── vscode-freight/          # VS Code extension (LSP client + tasks + grammar)
│   └── nvim-freight/            # Neovim plugin (lazy.nvim, auto-starts freight lsp)
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
clang-bridge    ←── freight (LSP ClangIndexer; default feature, runtime-gated by --use-clang-bridge)
fortran-lsp     ←── freight (planned: native Fortran indexer behind freight lsp; not yet wired)
freight-registry    (standalone; no internal deps)
```

Changes to `cmake-lossless`'s public API will require updates in both `freight`
and `vcpkg-converter`. Changes to `clang-bridge`'s Rust API surface require a
matching `freight/src/lsp/indexers/Clang.rs` update in the same logical change.

---

## Open work — per-crate

Each crate has its own `TODO.md` with detailed items. Start there:

| Crate | TODO | Top open item |
|---|---|---|
| `clang-bridge` | [`TODO.md`](crates/clang-bridge/TODO.md) | Differential verification vs clangd (diagnostics, hover, hierarchies, completion) |
| `cmake-lossless` | [`TODO.md`](crates/cmake-lossless/TODO.md) | `include()` following; `add_subdirectory()` following; `MATCHES` regex |
| `fortran-lsp` | [`TODO.md`](crates/fortran-lsp/TODO.md) | Wire into `freight lsp` as a native indexer replacing the fortls passthrough |
| `freight` | [`TODO.md`](crates/freight/TODO.md) | Include-hygiene Phase 2 (enforce in build); clang-bridge default-on; fortran-lsp embed |
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

### ~~8. Registry web documentation viewer~~

**Status:** Done. `static/docs.html` in `freight-registry` is a full in-browser documentation browser that mirrors the `freight doc` TUI aesthetic and grouping logic.

- **Styling**: monospace font (JetBrains Mono), One Dark Pro palette, heading pills (H1–H4 each have their own fg/bg), fenced code blocks with `─── lang ─────` header box.
- **Syntax highlighting**: highlight.js wired in with custom CSS overlay matching the TUI token colours.
- **Sidebar**: pure hierarchy matching `freight doc` — type items (expandable if they have class members) → namespaces (expandable, type items inside namespaces also get a nested sub-group) → free symbols. No section headers, matching `rebuild_rows()` in `browser.rs`.
- **Tag rendering**: reads `item.tags` (DocTag array) correctly, handling both plain-variant kinds (`"Param"`, `"Return"`) and the Debug-format `Other("tparam")` serialisation. Renders: tparams table, params table, returns, retvals, throws, notes (blue box), warnings (amber box), examples (syntax-highlighted), deprecated banner, since badge, see-also pills.
- **Sidebar header**: package name + version + source link (derived via `repoUrl()` from `upstream_url` in the latest version entry) + owner chips (from `/api/v1/packages/:name/owners`, using the `login` field).
- **Wire format quirks fixed**: item `kind` is `DocKind::label()` lowercase (`"fn"`, `"class"`, `"mod"`); `lang` is `DocLanguage::label()` string (`"C++"`, `"Rust"`); tag `Other` uses Debug format not JSON object.

### 9. IDE plugins / `freight lsp`

**End goal:** `freight lsp` is the *only* language server a freight project needs —
manifest intelligence plus native, manifest-aware C/C++/Fortran/asm source
intelligence — consumed identically by VS Code, Neovim, and JetBrains, with no
external server (clangd/fortls) required in the default configuration.

**Status:** In progress. `freight lsp` is a working stdio server
(`crates/freight/src/lsp/`, entry in `src/bin/freight/commands/lsp.rs`); VS Code
(`editors/vscode-freight/`) and Neovim (`editors/nvim-freight/`) wrappers ship;
JetBrains is still planned. Manifest diagnostics/completion/hover, source
passthroughs (clangd / fortls / asm-lsp), include-hygiene Phase 1 warnings,
scoped `#include` completion, include/import inlay hints, `import std;` support
(BMI build shared with `freight build`), and the DAP subcommand are all live.

Remaining work, by track — each says what the end state is and how to get there:

#### 9a. C/C++: clang-bridge to parity, then default-on

- **End goal:** the in-process `clang-bridge` indexer replaces the clangd
  subprocess as the default C/C++ backend (no clangd install needed; freight
  controls flags, modules, and include policy directly).
- **Now:** bridge is feature-complete API-wise (all LSP methods implemented, 144
  tests) but opt-in via `freight lsp --use-clang-bridge`; clangd is the default.
- **How to finish:**
  1. Complete the clangd-oracle differential audit (see
     `crates/clang-bridge/TODO.md`): diagnostics (async publish — pump the raw
     fd), signature-help active-parameter, hover content/range, call/type
     hierarchy edges, completion item kinds/details, formatting.
  2. Fix the known risk areas: UTF-16 vs byte column encoding on multi-byte
     lines; cross-file/multi-TU reference collection via
     `cb_workspace_index_add`.
  3. Run the bridge as daily driver on the example projects; when no
     regressions vs clangd remain, flip the default (clangd becomes the
     escape hatch) and update vscode-freight/nvim-freight settings + docs.

#### 9b. Fortran: native indexer replaces fortls

- **End goal:** Fortran files are served by `crates/fortran-lsp` embedded as a
  `LanguageIndexer` (like ClangIndexer), scoped by freight's manifest source
  graph; fortls passthrough survives only behind a flag until removal.
- **Now:** the crate covers parsing (free/fixed form, preprocessor, includes),
  indexing, hover, definition, completion, signature help, references, and a
  growing diagnostic set (48 tests) — but **nothing in `freight lsp` calls it yet**.
- **How to finish:**
  1. Add a `FortranIndexer` in `freight/src/lsp/indexers/` wrapping
     `fortran_lsp::Workspace`; feed it the manifest's source roots + include
     dirs; route `.f90`/`.f`/etc. URIs to it behind a `--use-native-fortran`
     flag (mirror the clang-bridge gating pattern).
  2. Map `fortran-lsp` model types to LSP responses for the methods it already
     supports; forward the rest to fortls while gaps remain.
  3. Differential-test against fortls on real projects (same oracle technique
     as clang-bridge vs clangd), close gaps, then flip the default.

#### 9c. Include hygiene: enforce, not just warn

- **End goal:** `#include`/`import` of headers from undeclared packages is a
  *build* error under `deny`, the compile command itself only exposes declared
  dirs, and declared system libs resolve via pkg-config.
- **Now:** Phases 1–3 (first cut) done. Phase 1 — LSP warnings,
  `[lints].undeclared-include`, scoped include completion. Phase 2 —
  `build::validate_include_hygiene` enforces at build time. Phase 3 —
  `build::header_ownership` attributes system headers to declared packages/slots
  (Tier A ownership table + Tier B pkg-config dedicated dirs), in both build and
  LSP, with candidate-naming diagnostics; BLAS/LAPACK are slots (shared header =
  OR). The module→package map is also done. See `docs/include-hygiene.md` +
  `-audit.md` (Step 11).
- **How to finish:** Phase 3 remaining — host + generate the per-OS Tier-A data
  file (hook the vcpkg/registry scraper; registry stubs carry `provides-headers`);
  a lazy `pkg-config --list-all` reverse index to name owners of headers not in
  Tier A; macOS/Windows seeds; finalize the POSIX/OS-header policy. Optional
  stronger Phase 2: hermetic includes (stop relying on the compiler's default
  search paths).

#### 9d. Editor surfaces

- **End goal:** feature-parity wrappers for VS Code, Neovim, and JetBrains that
  are thin clients — all intelligence lives in `freight lsp`.
- **How to finish:**
  - VS Code: dependency-tree panel, "newer version available" codelens (read
    the local registry msgpack cache — never network on the hot path), remove
    the dead `clangdPath`/`enableClangd` settings.
  - Neovim: bring the scaffold to parity (tasks, DAP wiring).
  - JetBrains/CLion: Kotlin LSP-client wrapper around the same binary — start
    after 9a flips the default, so it never has to know about clangd.

#### 9e. DAP backends

- **End goal:** `freight dap` debugs on every platform freight builds for.
- **Now:** GDB-family (`gdb`, `cuda-gdb`) and LLDB-family (`lldb-dap`) work.
- **How to finish:** investigate `rr` (replay through GDB-DAP), `cdb`/`windbg`
  (needs a Windows machine — same blocker as MSVC support). Fake-adapter unit
  tests + real smoke notes before exposing any new backend in the editors.

**Key decisions (unchanged):**
- LSP is a `freight lsp` subcommand in the main binary, not a standalone crate;
  language backends are crates (`clang-bridge`, `fortran-lsp`) embedded as
  `LanguageIndexer` implementations, not subprocesses.
- Registry queries: always from local msgpack cache; never block on network in
  the LSP hot path.

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
