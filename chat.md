# Agent Chat

This file is a lightweight shared chatroom for AI coding agents working in this
workspace. Use it to leave handoff notes, questions, and summaries of changes
that another agent should know about.

Guidelines:
- Add new entries at the top, under `## Log`.
- Include your agent name and date.
- Keep entries factual: what changed, what was pushed, what remains unclear.
- Do not use this file for long design documents; link to docs or TODOs instead.

## Log

### 2026-06-05 — Claude (session 5)

**Dep artifacts now go to root `target/deps/<name>/`; TCC ar fix**

- Added `PackageNode::target_dir()` — root → `dir/target`, dep → `root/target/deps/<name>/`
- Threaded `target_dir: &Path` through `compile_sources`, `link_targets`, `plan_module_build`, `compile_pch`, `compile_commands::generate`, and all callers in `mod.rs`
- `compile_commands.json` no longer written to project root during `freight build`; only written to `.freight/lsp/<profile>/`
- Fixed TCC builtin template: `("ar", "ar")` — TCC has no archiver; was silently failing with `tcc rcs ...`
- Cleaned up debug eprintln/walkdir from `tests/flat_pkgs.rs`
- Both flat_pkgs integration tests now pass

Pushed: `crates/freight` master → `320ecfa`; workspace bumped → `5abf199`

No open questions.

### 2026-06-05 — Claude (session 4)

**PackageNode pipeline — unified dep tree struct**

New file `src/build/pipeline.rs` introduces `PackageNode`: a single `Arc<PackageNode>` tree that represents both the root project and every transitive dep. Design:
- `parent: Option<Weak<PackageNode>>` — Weak to break reference cycles; children hold strong refs
- `children: RwLock<Vec<Arc<PackageNode>>>` — interior mutability for lazy append during dep resolution
- `pkgs_root_dir()` walks parent links to root so every dep anchors its `.pkgs/` lookup to the top-level project dir

Replaced the old `pkgs_root: Option<&Path>` parameter in `build_project_at` and `build_foreign_deps` with `parent_node: Option<&Arc<PackageNode>>` / `node: &Arc<PackageNode>`. The node carries profile, version, dir, and the full tree in one place.

Profile bug fixed: dep source-builds now use `root_node.profile` ("dev"/"release") instead of the version constraint string ("0.1.0"). Integration test assertions updated accordingly.

All 663 lib tests + 2 flat_pkgs tests pass. Pushed as `3ca6949`.

### 2026-06-05 — Claude (session 3)

**Fixed root bug in flat .pkgs/ pool: pkgs_root was wrong in nested source builds**

The previous session passed `Some(project_dir)` to the recursive `build_project_at` call inside `resolve_version_dep` (adaptors). When building a transitive dep (e.g., mathlib from within vecmath's source build), `project_dir` is vecmath's dir — so the inner build resolved mathlib's deps from `vecmath/.pkgs/` instead of the root pool, creating nested directories and re-downloading packages.

Fix: changed `Some(project_dir)` → `Some(pkgs_root)` so all nested source builds always anchor dep lookups to the root flat pool.

Added two integration tests in `tests/flat_pkgs.rs`:
- `flat_pkgs_transitive_dep_at_root_level`: root → vecmath → mathlib; asserts mathlib builds in `root/.pkgs/mathlib/` and no `vecmath/.pkgs/` is created
- `flat_pkgs_two_deps_share_transitive`: root → vecmath + geometry → shared mathlib; same assertions

Both pass. Pushed as `958ecec` in freight, workspace bumped to `43e5515`.

**Goal met**: flat .pkgs/ structure is verified — recursive packages across multiple deps are correctly reused from the root pool.

### 2026-06-05 — Claude (session 2)

**Flat `.pkgs/` pool for transitive deps**

Threaded `pkgs_root: Option<&Path>` through `build_foreign_deps` and `build_project_at`. When a dep is built from source, its own transitive deps now resolve to the root project's `.pkgs/` instead of nesting inside the dep's own `.pkgs/`. All call sites pass `None` (root = self) except the source-build fallback in `adaptors/mod.rs`, which passes `Some(project_dir)` to point transitive lookups at the real root.

- Pushed to `freight` as `92545f4`; workspace pointer bumped to `9916c7f`.
- No compile_commands or ratatui changes in this session.

**Pending**: look at vscode-cpptools for DAP (debug) and live-reindex patterns.

### 2026-06-05 — Claude

**Fixed double "Resolving" output in `freight build`**

Root cause: two separate issues.

1. The speculative early emit (`via: query.to_string()`) before pkg-config was tried was already removed in commit 213c872 this session.
2. The source-build fallback (`build_project_at` at line 669 in `adaptors/mod.rs`) passes the same `progress` closure into the inner build. That inner `build_foreign_deps` call re-emits `ResolvingDep` for transitive deps that the outer build had already resolved — producing one duplicate line per shared transitive dep.

Fix: wrap the progress closure passed to the inner build to filter out `ResolvingDep` events. Each dep now appears exactly once in output.

- Pushed: `crates/freight` @ 5e08c66

No open questions.

### 2026-06-05 — Codex

**Added inline Freight task failure annotations in VS Code**

- Updated `editors/vscode-freight/src/extension.js` so Freight build/run/test tasks use a
  custom pseudoterminal execution instead of raw `ShellExecution`, preserving terminal output
  while capturing stdout/stderr for post-run failure parsing.
- Failed tasks now publish a separate `freight execution` diagnostic collection and render
  inline after-text on the affected source line for GCC/Clang-style, Freight summary, and
  MSVC-style diagnostics; runtime/startup failures fall back to the active source file or
  `freight.toml` with the exit reason and last meaningful output line.
- `freight run` / `freight test` failures that print C++ terminate output such as
  `terminate called after throwing an instance of 'std::runtime_error'` now raise a VS Code
  error notification with the exception type and `what():` text when available.
- The extension now detects that terminate output even when the `freight run` wrapper reports
  a zero exit status, and marks the VS Code task failed in that case.
- Added a Freight debug adapter protocol tracker so `Freight: Debug` sessions also watch DAP
  `output` events for the same C++ terminate pattern and raise the popup.
- Added parser coverage in `editors/vscode-freight/tests/dap-config.test.js`.
- Tested: `npm test` and `npm run check` in `editors/vscode-freight`.
- Not pushed.

### 2026-06-05 — Codex

**Split VS Code extension entrypoint into TypeScript modules**

- Replaced the large `editors/vscode-freight/src/extension.js` with a small
  `src/extension.ts` coordinator and split the implementation into `configuration.ts`,
  `debug.ts`, `execution.ts`, `explorer.ts`, `lsp.ts`, `state.ts`, `status.ts`, and
  `utils.ts`.
- Converted the extension source to TypeScript with ES `import` / `export`; no `require()`
  or `module.exports` remain under `src/`.
- Updated `package.json` so Bun builds `src/extension.ts` to CommonJS `dist/extension.js`
  for VS Code, and tests require a temporary bundled artifact.
- Added `tsconfig.json`, fixed strict TypeScript diagnostics, and added orienting comments to
  the split modules so each VS Code surface is easier to follow.
- Updated the extension debug setup so `bun run package` emits linked source maps and
  `.vscode/launch.json` maps `dist/extension.js` back to `src/*.ts` for TypeScript breakpoints.
- Tested: `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bunx tsc --noEmit`, `npm test`,
  `npm run check`, and `npm run compile` in `editors/vscode-freight`.
- Not pushed.

### 2026-06-05 — Codex

**Fixed LSP compile DB includes for cached registry deps**

- Updated `crates/freight/src/build/mod.rs` so `generate_lsp_compile_commands_at()`
  includes headers from manifest version deps already fetched under `.pkgs/`, including
  transitive cached version deps found through fetched packages' `freight.toml` files.
- This makes the hidden `.freight/lsp/<profile>/compile_commands.json` match the build
  path for registry packages such as `vecmath` and `mathlib` in `examples/cpp/hello`.
- Added regression tests for direct and transitive cached version dependency include dirs.
- Tested: `cargo test -p freight lsp_compile_commands --lib`, `cargo check -p freight --lib`,
  `cargo build -p freight`, and an LSP initialize smoke in `examples/cpp/hello` showing
  `-I.pkgs/vecmath/include` and `-I.pkgs/mathlib/include` in `.freight/lsp/dev/compile_commands.json`.
- Not pushed.

### 2026-06-05 — Claude (session 3, part 4)

**freight: source build fallback when no prebuilt triple available**

- `adaptors/mod.rs`: after a `.pkgs` cache hit, if `lib/` has no binary artifacts but `freight.toml` exists (source tarball), calls `build_project_at` on the dep dir and links `target/{profile}/lib{name}.a`.
- `fetch.rs`: when the host triple has no prebuilt, now prints an informational "will build from source" note.
- P8 (server-side Docker prebuilt builds) deferred — client-side fallback is the intended long-term approach.
- Pushed: `crates/freight` master `15bb7f0`; workspace pointer bumped.

### 2026-06-05 — Claude (session 3, part 3)

**Registry: E4 org-scoped tokens + T1 integration test suite**

- **E4 (org-scoped tokens)**: migration 0011 adds nullable `org_id` to `tokens`; `POST /api/v1/me/tokens` accepts `"org"` field (org owners only); publish enforces org ownership — org-scoped tokens can't publish to packages outside their org; new packages are auto-assigned to the token's org on first publish.
- **T1 (integration tests)**: `tests/integration.rs` — 11 tests: publish→download→yank→unyank flow, duplicate/non-owner/pending-version rejection, TOTP login enforcement, recovery code login + replay protection, org role gating (add_member, set_package_org), org-scoped token enforcement.
- All 123 tests pass (45 api + 11 integration + 17 db + 48 publish unit + 2 misc).
- Pushed: `crates/freight-registry` main `fa35377`; workspace pointer bumped.
- Only open item: P8 (server-side Docker prebuilt builds).

### 2026-06-05 — Claude (session 3, part 2)

**Registry gaps: E2 recovery codes, E3 org owner enforcement, E5 GC**

- **E2 (TOTP recovery codes)**: new `totp_recovery_codes` table (migration 0010 for SQLite + PG); 8 codes generated on TOTP `confirm`, SHA-256 hashes stored; plaintext returned once in confirm response; login now accepts a recovery code as a one-time alternative to a live TOTP code.
- **E3 (org owner enforcement)**: `set_package_org` was checking `is_org_member`; fixed to require `is_org_owner`.
- **E5 (blob GC)**: `freight-registry gc` subcommand; dry-run by default; `--execute` removes all blobs for yanked versions (DB rows kept).
- Pushed: `crates/freight-registry` main `298e67c`; workspace pointer bumped.

### 2026-06-05 — Claude (session 3)

**Fix: double "Resolving <lib>" line during `freight build`**

- Root cause: `adaptors/mod.rs` `resolve_version_dep` emitted `ResolvingDep` speculatively at the top of the `None` branch, then each resolution path (pkg-config, system-lib stub, `.pkgs`) emitted it again.
- Fix: removed the early speculative emit; moved the pkg-config path's emit inside the `if let Ok(...)` block (the other two paths already had their own single emits).
- Tested: `freight build` in `examples/cpp/hello` — each dep now resolves once.
- Pushed: `crates/freight` master `213c872`; workspace pointer bumped.

### 2026-06-04 — Claude (session 2)

**Registry test packages published; publish tarball bug fixed**

- Fixed two bugs in `crates/freight` `src/cli/commands/publish.rs`:
  1. `upstream_url` was being set to the checksum hash instead of `None`, causing registry to treat packages as metadata-only redirects → fetch would 302 to a bare hash string and 404.
  2. Source tarballs had no top-level `{name}-{version}/` wrapper directory, so `--strip-components=1` extraction in `http.rs` stripped `include/` from all paths → headers not found at compile time.
- Pushed fix to `crates/freight` master (`3bf3e3e`); workspace pointer bumped.
- Published to local registry (`http://localhost:7878`):
  - `mathlib@0.1.2` — C static lib, clamping/lerp/statistics helpers
  - `vecmath@0.1.0` — C++17 vec2/vec3/mat3, depends on `mathlib >= 0.1.2`
- Verified: `freight fetch` + `freight build` of vecmath succeeds end-to-end against local registry.
- Registry yank API: use `DELETE /api/v1/packages/{name}/{version}/yank` to yank, `PUT` to unyank.

### 2026-06-04 — Claude

**HeaderIndex owns include navigation — built from freight.toml dep graph**

- Freight LSP is now the sole authority for `#include`/`#import` hover, definition, links.
  clangd only gets compile flags.
- `HeaderOrigin` reworked: `Own` (project itself), `PathDep` (dep key known from `freight.toml`),
  `Fetched` (`.pkgs/` fetched packages), `System`. Old `Project`/`Local` removed.
- `HeaderDirSpec` carries `dep_key: Option<String>` — hover now shows `[dep: mylib]` instead
  of just `[project]`.
- `HeaderIndex::build` now walks `[compiler].includes` dirs and `src/` for `Own` packages
  (in addition to `include/`), since that's where project-relative `#include "..."` headers live.
- `build_header_specs()` builds the spec list directly from `load_workspace_manifest` +
  `load_manifest` so origins are accurate from the manifest graph, not filesystem guesses.
- All tests pass. Committed to `crates/freight` as `fbe0868`. Not yet pushed.

### 2026-06-04 — Claude

**libclang hover: fixed namespace recursion, TU reparse on cc_dir, and enriched output**

- `on_symbol` was returning `CXChildVisit_Continue` for all cursors — symbols inside namespaces,
  classes, and structs were never indexed. Fixed: returns `CXChildVisit_Recurse` for container
  kinds (`Namespace`, `ClassDecl`, `StructDecl`, `ClassTemplate`, etc.) so nested declarations
  are captured.
- `set_cc_dir` had no effect on TUs already parsed before `compile_commands.json` was found
  (common on first `didOpen`). Fixed: now re-opens all live TUs when `cc_dir` changes.
- `hover()` now skips `CXCursor_TranslationUnit` cursors (returned when nothing meaningful is
  under the point) in addition to the null cursor.
- Enriched `HoverInfo`: added `display_name` (`clang_getCursorDisplayName`, includes param types),
  `source_file`/`source_line` for declaration origin, and raw comment fallback with comment-marker
  stripping when `clang_Cursor_getBriefCommentText` returns empty.
- `hover_info_to_markdown` now renders `returnType displayName(params)`, doc comment, and
  `*file:line*` origin footer.
- Committed to `crates/freight` as `a846afc`, `3755d6d`. Not yet pushed to remote.
- **Current state**: Codex subsequently rolled back `mod.rs` to pre-libclang wiring (keeping
  `clang_index.rs` dormant on disk) and further expanded `clang_index.rs` with rich doxygen
  parsing, pretty-printer, compiler include probing, and relative path rendering — but this is
  **uncommitted**. `cargo check` passes on the uncommitted tree.
- **Next**: commit or integrate Codex's uncommitted `clang_index.rs` expansion and re-wire
  `mod.rs` to use the new `TuCache`.

### 2026-06-04 — Codex

**Moved LSP compile database into `.freight`**

- Changed `freight lsp` compile database generation to write
  `.freight/lsp/<profile>/compile_commands.json` under the active package/workspace instead of
  using a hashed temp directory.
- Added profile-path sanitizing so unusual profile strings cannot create nested paths, plus unit
  tests for the `.freight` location and sanitizer fallback.
- Updated the LSP docs to describe the new `.freight/lsp/<profile>` path and noted that the
  libclang prototype is currently paused/dormant after the active rollback.
- Tested: `cargo test -p freight lsp_compile_commands`,
  `cargo test -p freight lsp_profile_dir_is_path_safe`, `cargo test -p freight lsp::`, and
  `cargo check -p freight` pass. Existing warnings remain in doc/lang, doc_index, make tests, and
  publish.
- Not pushed.

### 2026-06-04 — Codex

**Rolled active LSP back to pre-libclang behavior**

- Restored active `freight lsp` wiring in `src/lsp/mod.rs` and `Cargo.toml` to the last pre-libclang state (`49d9d4d`): no `clang_index` module import, no `TuCache`, no libclang hover/definition/include resolution/inlay hints, no clang-tidy-on-save path, and no `clang-sys` dependency.
- Kept `src/lsp/clang_index.rs` on disk for future work, but it is dormant/not compiled by the LSP module.
- Kept the include/import hover path improvement in `doc_index.rs`, implemented locally there: include hovers display Freight/package-relative, `.pkgs/<package>`-relative, include-root-relative, or basename fallback paths instead of absolute paths.
- Tested: `cargo test -p freight lsp::` and `cargo check -p freight` pass. Remaining check warnings are pre-existing: `sig_go`, `HeaderIndex::is_empty`, and `publish.rs` `project_dir`.
- Not pushed.

### 2026-06-04 — Codex

**Expanded libclang hover detail**

- Checked `crates/freight/src/lsp/clang_index.rs` and the official libclang docs for cursor/type/comment APIs.
- Expanded hover extraction to use libclang's declaration pretty-printer, cursor result type, canonical type, params, semantic parent, access, availability, USR, definition/declaration status, and line/column.
- Ported the old `doc_index.rs` hover behavior into the libclang path: raw Doxygen comments are parsed into brief/body plus params, tparams, returns, throws, notes, warnings, examples, see-also, since, and deprecated sections.
- Suppressed noisy libclang type metadata when the pretty declaration already contains it, fixing hovers that showed `Type: int` / `Returns: int` for ordinary declarations.
- Fixed libclang compile flag lookup for relative `compile_commands.json` entries (`directory` + `file`), including absolutizing relative include paths like `-Iinc`; this caused the `std::vector<double> data` hover to parse without `-std=c++20`/includes and show `int data = <recovery-expr>(...)`.
- Added cached compiler include probing from the compile command's compiler executable (`clang++ -x c++ -E -v /dev/null`) and passes those paths as `-isystem` to libclang, so standard library headers like `<vector>` resolve outside clangd's driver emulation.
- Added a recovery guard so pretty declarations containing `<recovery-expr>` fall back to the original source line instead of leaking bogus AST recovery output into hovers.
- Trimmed libclang hover rendering to user-facing content only: concise declaration/prototype without class bodies or initializers, Doxygen docs, useful parameter/type tables, and source location. Removed rendered `Symbol`, `USR`, and `kind/access/parent/definition` debug metadata.
- Raw comments now fall back through `clang_getCanonicalCursor` when the immediate referenced cursor has no Doxygen text; constructor/destructor hovers also try the owning class declaration, and trailing right-side comments such as `extern ostream cout; /// ...` are parsed.
- Source footers are now hidden for namespaces and rendered relative to the nearest Freight package or `.pkgs/<package>` root instead of as absolute paths; fallback is just the basename.
- Include/import hovers now use relative paths too: Freight package-relative, `.pkgs/<package>`-relative, include-root-relative for system headers, or basename fallback.
- Updated TU symbol fallback hovers to reuse the rich hover renderer and record namespace/class/container symbols before recursing.
- Enabled `clang-sys` `clang_7_0` feature in `crates/freight/Cargo.toml` so the pretty-printing APIs are available while retaining runtime dlopen behavior.
- Tested: `cargo test -p freight lsp::` and `cargo check -p freight` pass. Tests cover Doxygen tag rendering, trailing right-side comments, concise declaration trimming, relative source/include footer rendering, namespace footer suppression, relative compile command flag extraction, compiler include-list parsing, and recovery-decl source fallback. Remaining check warnings are pre-existing: `sig_go`, `HeaderIndex::is_empty`, and `publish.rs` `project_dir`.
- Not pushed.

### 2026-06-04 — Claude

**libclang: replace text/heuristic include resolution and DocIndex for C/C++**

- `clang_getInclusions` replaces `parse_include_header` regex + `probe_system_include_dirs` (`gcc -v`).
  Per-TU inclusion map (line → full_path + is_system) cached on every open/reparse.
  `include_hover`, `include_definition`, `compute_document_links`, `compute_inlay_hints`
  all use the map when TU is loaded; text/HeaderIndex fallback retained for unopened files.
- `build_symbols` walker extracts top-level declarations + brief doc comments.
  `tu_symbol_hover` replaces `DocIndex` for C/C++ name-based hover.
- `TuSymbol.line` kept for upcoming document-symbol outline feature.
- Committed to `crates/freight` as `a745d0e`. Not yet pushed.

### 2026-06-04 — Claude

**libclang integration — Phases 4-5 (AST inlay hints + clang-tidy on-save)**

- Phase 4: `clang_visitChildren` walker in `clang_index.rs` collects parameter name hints
  from `CXCursor_CallExpr` and deduced-type hints from `auto` `CXCursor_VarDecl`.
  When a TU is loaded, `handle_inlay_hints` responds immediately without clangd.
  `clangd_pending` merge pipeline kept as fallback when TU isn't parsed yet.
- Phase 5: `textDocument/didSave` for C/C++ spawns `clang-tidy <file> -p <cc_dir>` in
  a background thread; output is parsed and pushed as `textDocument/publishDiagnostics`
  with `source = "clang-tidy"` and the check name as the code.
- All 5 phases of the libclang integration are complete.
- Committed to `crates/freight` as `109358f`. Not yet pushed.

### 2026-06-04 — Claude

**libclang integration — Phases 1-3 (TU lifecycle, hover, go-to-definition)**

- Added `clang-sys` (runtime dlopen) to `crates/freight/Cargo.toml`.
- New `src/lsp/clang_index.rs`: `TuCache` wraps `CXIndex` + per-file `CXTranslationUnit` map.
  - TUs opened/reparsed on `didOpen`/`didChange`, closed on `didClose`.
  - `cc_dir` updated when `compile_commands.json` refreshes so parse flags stay correct.
- Hover: libclang path fires before DocIndex for C/C++ — returns cursor spelling, type string,
  and brief doc comment; falls back to DocIndex → fortls/asm-lsp.
- Go-to-definition: libclang intercepts before clangd forwarding; `#include` line def still
  freight-owned as before.
- Committed to `crates/freight` as `d793d43`. Not yet pushed.
- Phases 4 (inlay hints from AST) and 5 (clang-tidy on-save) still TODO.

### 2026-06-04 — Claude

**Added Mermaid architecture diagrams (freight core + registry + DAP)**

- Appended six diagrams to `crates/freight/docs/architecture.md`:
  build pipeline flowchart, dependency resolution chain, CLI commands overview,
  compiler template evaluation, DAP adapter selection + launch/attach sequence,
  registry HTTP router + publish wire format + SHA-256/Argon2id auth flow.
- LSP architecture diagrams (from prior session) live in `docs/lsp-architecture.md`.
- Committed to `crates/freight` as `49d9d4d`. Not yet pushed.

### 2026-06-04 — Codex

**Adjusted VHS homepage demo scaffold output**

- Updated the org Pages VHS tape so the first real command remains visible long enough to show Freight's scaffold output:
  `✓ created \`hello\` (c++ project)`, followed by `cd hello` and `freight build`.
- Tape now follows the scaffold hint directly: `freight new hello --lang c++`, `cd hello`, `freight build`.
- Regenerated `img/freight-quickstart.gif` from the actual local Freight binary.
- Pushed: `freight-app.github.io` commit `908acd4` (`match quickstart gif to scaffold output`) to `main`.
- Tested: real `freight new hello --lang c++` output, VHS render, inspected frames showing the scaffold output and successful build, Pages workflow `26960166431`, and `curl -I https://freight-app.github.io/`.
- Note: separate post-deploy `curl -I` for the GIF asset was blocked by the environment's escalation usage limit after the page check; not retried.

### 2026-06-04 — Codex

**VHS homepage demo now uses real Freight**

- Replaced the mocked VHS homepage demo with a recording generated from the actual local Freight binary at `/home/max/freight/target/debug/freight`.
- Tape now runs real commands: `freight new hello --lang c++`, `cd hello`, `freight check`, and `freight run`.
- Removed `tapes/mock-freight.sh`; regenerated `img/freight-quickstart.gif`.
- Pushed: `freight-app.github.io` commit `33b5e1c` (`record vhs demo with real freight`) to `main`.
- Tested: real CLI commands in `/tmp/freight-vhs-real`, VHS render with `/home/max/go/bin/vhs`, inspected end GIF frame showing `Hello, world!`, Pages workflow `26959769474`, `curl -I https://freight-app.github.io/`, and `curl -I https://freight-app.github.io/img/freight-quickstart.gif`.

### 2026-06-04 — Codex

**Switched org Pages terminal demo to VHS GIF**

- Replaced the asciinema-player embed on `freight-app.github.io` with a VHS-rendered GIF.
- Added `tapes/freight-quickstart.tape`, `tapes/mock-freight.sh`, and generated `img/freight-quickstart.gif`.
- Removed the previous checked-in asciinema cast file from the org Pages repo.
- Pushed: `freight-app.github.io` commit `5e7aa3e` (`use vhs gif for quickstart demo`) to `main`.
- Tested: installed VHS with `go install github.com/charmbracelet/vhs@latest`, rendered the tape with `/home/max/go/bin/vhs`, inspected a late GIF frame, Pages workflow `26959351684`, `curl -I https://freight-app.github.io/`, and `curl -I https://freight-app.github.io/img/freight-quickstart.gif`.

### 2026-06-04 — Codex

**Live asciinema demo on org Pages main page**

- Replaced the static terminal block on `freight-app.github.io` with an embedded asciinema player.
- Added `casts/freight-quickstart.cast` to the org Pages repo and wired `AsciinemaPlayer.create()` to autoplay/loop inside the terminal frame.
- Pushed: `freight-app.github.io` commit `ff240fd` (`embed asciinema quickstart demo`) to `main`.
- Tested: cast JSON lines parse with `bun`, jsDelivr asciinema-player asset returns HTTP 200, GitHub Pages workflow `26958703586`, `curl -I https://freight-app.github.io/`, and `curl -I https://freight-app.github.io/casts/freight-quickstart.cast`.

### 2026-06-04 — Codex

**Docs terminal demo pipeline**

- Added a VHS/asciinema terminal demo pipeline to `freight-app/freight-docs`.
- New files: `examples/terminal/quickstart.tape`, matching `quickstart.sh` scenario, `scripts/render-terminal-examples.sh`, generated quickstart text transcript, and `docs/terminal-demos.md`.
- Added `bun run examples:terminal` to render VHS GIFs, asciinema `.cast` files, and text transcripts.
- Updated sidebar and intro docs to link the new Terminal demos page; fixed README path wording from old `docs-site/docs/` to `docs/`.
- Pushed: `freight-docs` commit `daa2506` (`add terminal demo pipeline`) to `main`.
- Tested: `bash -n` for scripts, `bun run build`, GitHub Pages workflow `26958217295`, and `curl -I https://freight-app.github.io/freight-docs/terminal-demos/`.

### 2026-06-04 — Codex

**Registry public cleanup + org Pages site**

- Created public org Pages repo `freight-app/freight-app.github.io` with a static main page for `https://freight-app.github.io/`; Pages workflow passed and the URL returned HTTP 200.
- Confirmed renamed private launch repo `freight-app/freight-registry-main` exists and is private; updated the local `/tmp/freight-registry-launch` clone's `origin` remote to `git@github.com:freight-app/freight-registry-main.git`.
- Cleaned `crates/freight-registry` public UI by removing registry-local guide/install pages, removing hardcoded Docs/Install links from static pages, deleting `/docs` and `/install` routes, and simplifying the homepage to a standard package search/browse entry point.
- Removed the `docify` path dependency from `freight-registry`; `src/api/docs.rs` now validates/decodes docify MessagePack with a local wire-format mirror plus `rmp-serde`, so the public registry repo can build standalone without a sibling `docify` crate.
- Updated registry README/TODO/example config to document optional-by-config S3, SMTP, OAuth/OIDC, external downloads, and CI verification; removed launch-specific CI image examples and moved S3/SMTP secrets out of TOML examples.
- Pushed: `crates/freight-registry` commit `e815879` (`clean public registry website`) to `freight-app/Freight-registry` `main`.
- Tested: `cargo check -p freight-registry`; GitHub Pages workflow `26957531967`; `curl -I https://freight-app.github.io/`.
- Not pushed: workspace `Cargo.lock`, `chat.md`, and the updated `crates/freight-registry` submodule pointer remain uncommitted in the workspace root.

### 2026-06-04 — Claude (session 2, part 8)

**Freight-doc hover pipeline complete** (`crates/freight`)

VS Code hover now runs through freight doc exclusively for C/C++, with language-server
fallback for Fortran and assembly. The pipeline is extensible to new languages via the
`DocExtractor` trait — just implement it and register in `ExtractorRegistry::default()`.

Hover order:
1. `freight.toml` key → manifest hover
2. `#include`/`#import` → `HeaderIndex` package origin
3. `DocIndex` position-based lookup (validates word-under-cursor matches item name)
4. `DocIndex` name-based fallback (word extracted from cursor position)
5. Fortran/asm miss → forward to `fortls`/`asm-lsp`; C/C++ miss → null

New `AsmExtractor` (`src/doc/lang/asm.rs`):
- Extensions: `.s`, `.S`, `.asm`, `.nasm`, `.nas`, `.inc`
- Doc comment styles: `;;`, `##`, `//` before label or PROC declarations
- Registered alongside C++, Fortran, Ada, D, Zig

Removed `enrich_hover_response` and `reformat_clangd_hover` (dead code since
clangd hover forwarding was removed).

Committed as `4af00f9` — not yet pushed.

### 2026-06-04 — Claude (session 2, part 7)

**Module restructure + LSP trace improvements** (`crates/freight`)

Two structural cleanups:
1. `dap` and `lsp` promoted from `commands/dap` and `commands/lsp` to
   `src/bin/freight/dap/` and `src/bin/freight/lsp/` — top-level bin modules.
   `main.rs` now has `mod dap; mod lsp;` and all `commands::dap::`/`commands::lsp::` refs updated.
2. `doc/docify/` flattened into `doc/` — lang extractors, markdown, and render_md
   move up; docify wrapper module deleted; `doc/mod.rs` re-exports everything directly.
   `freight_core::doc::docify::` refs updated to `freight_core::doc::`.

LSP tracing: all hover debug/trace lines now include file, line, and col fields:
- `hover request` log on every source-file hover: `file`, `line`, `col`
- `include hover`: `header`, `package`, `line`
- `doc-index hover`: `symbol`, `file`, `cursor_line`, `cursor_col`

Committed as `51bc0da` — not yet pushed.

### 2026-06-04 — Claude (session 2, part 6)

**Docify-only hover architecture** (`crates/freight`)

Clangd is now used only for diagnostics, completions, and go-to-definition.
All hover hints come exclusively from the freight doc index (docify).

- `DocIndex` restructured: `Vec<DocItem>` with `by_name` (name→idx) and
  `by_location` (file→BTreeMap<line, idx>) indexes
- `lookup_by_location(file, line)` finds the nearest doc item at or before
  the cursor line (range query on BTreeMap, ±5 line tolerance)
- `doc_hover` tries position-based lookup first, falls back to name lookup
- `extract_pkg_items` now scans `src/`, `include/`, `inc/` in the fallback path
- `item_to_markdown` heading now shows DocKind label (`fn`, `class`, etc.)
  and parent class context for member functions
- Removed: `PendingHover`, `pending_hovers`, `hover_seq`,
  `forward_hover_with_enrichment`, hover interception in passthrough thread
- Also fixed: `docify/mod.rs` was referencing deleted `extract` module;
  updated to `lang` (the extract types were inlined there in a prior session)

Committed to `crates/freight` as `2921c4c` — not yet pushed.

### 2026-06-04 — Claude (session 2, part 5)

**Added `FREIGHT_LOG` tracing** (`crates/freight`)

Two logging paths, both controlled by the `FREIGHT_LOG` env var:

*LSP mode* — `LspLogLayer` sends `window/logMessage` LSP notifications to VS Code. Shows up in the **Output** panel → select the **freight** channel. Key events logged: lifecycle (start/shutdown), every incoming client message method, hover routing (include-hover / doc-index / clangd paths), raw clangd hover text at `trace` level, enriched markdown at `debug` level, compile_commands.json refresh, doc index rebuild.

*Build/run mode* — plain stderr via `tracing-subscriber fmt`. Logged: build start/linking/archiving (`info`), per-file compile and dep resolution (`debug`), fresh-file skips (`trace`), warnings.

Usage:
```
FREIGHT_LOG=debug freight build          # stderr in terminal
FREIGHT_LOG=debug code .                 # Output panel in VS Code
```

Pushed to master; workspace pointer bumped.

### 2026-06-04 — Claude (session 2, part 4)

**Fixed C++ LSP hover rendering** (`crates/freight` → `src/bin/freight/commands/lsp/doc_index.rs`)

Root cause: `reformat_clangd_hover` was splitting only on the *first* `---` separator in clangd's hover text. Clangd appends a second `---\n```lang...```\n` block (the declaration snippet) after the doc text, which bled into `@param` continuation parsing — the entire code block was appended to the last `@param`'s text. Additionally, clangd's auto-generated `Parameters:` + typed-bullet block was preserved as body text alongside the reformatted `**Parameters**` section.

Changes:
- Split off the trailing code block (last `\n---\n\`\`\`` pattern) before tag parsing; render it as a clean footer
- After parsing, if `@param` tags exist, strip the `Parameters:` + typed-bullet lines from body
- Suppress `→ type` brief line when `@returns` tags are present (redundant)

All 7 hover probes verified clean: class, 2× member fn, pop (@throws), dot (@note+@warning), header declaration, and #include. Pushed to master; workspace pointer bumped.

### 2026-06-04 — Claude (session 2, part 3)

**MSIX installer for Windows sandbox**

- `freight package --installer --installer-format msix` → `.msix` via `makeappx.exe`.
  Works with Windows App Installer, Windows Sandbox, and the Microsoft Store.
- `AppxManifest.xml`: Identity (four-part version, arch, publisher from authors),
  FullTrustApplication entry point, VisualElements with logo paths.
- Logo PNGs (44×44 + 150×150) generated in pure Rust via flate2 — no image crate.
- Package is unsigned by default; prints `signtool sign` reminder. Sideloading
  requires Developer Mode or a trusted cert.
- `--installer-format nsis` remains the default on Windows.
- New export: `WindowsInstallerFormat` enum from `freight_core::install`.
- Pushed: crates/freight master, workspace pointer bumped.

### 2026-06-04 — Claude (session 2, part 2)

**`freight package --installer` → native platform installers**

- Linux: `.deb` built in pure Rust (no external tools). `ar` archive with `debian-binary`,
  `control.tar.gz`, `data.tar.gz`. Files install to `/usr/local/bin` + `/usr/local/lib`.
  Arch names mapped to Debian conventions (x86_64→amd64, aarch64→arm64, etc.).
- macOS: `.dmg` via `hdiutil create -format UDZO`. dylibs bundled + install names rewritten
  to `@executable_path/../lib/` via `install_name_tool`.
- Windows: NSIS `.exe` — generates `.nsi` script with welcome/directory/install/finish pages,
  desktop shortcut, Add/Remove Programs entry; runs `makensis`. Clear error if not installed.
- Shared-lib bundling (ldd/otool/dumpbin) reused across all three formats.

Pushed: `crates/freight` master, workspace pointer bumped.

### 2026-06-04 — Claude (session 2)

**`freight package --installer` — self-contained bundles**

**What changed (crates/freight):**
- New `installer_project()` in `src/install.rs`: builds, installs to staging, then
  collects transitive shared-lib dependencies (ldd/otool -L/dumpbin) and bundles
  them into `lib/` alongside the binary.
- System libs excluded from bundling: glibc family on Linux, `/usr/lib`+`/System/`
  on macOS, system32 DLLs on Windows.
- Launcher script written at the archive root (Linux/macOS) that sets
  `LD_LIBRARY_PATH`/`DYLD_LIBRARY_PATH` to `$DIR/lib` before exec-ing the binary.
- macOS: bundled dylibs get install names rewritten to `@executable_path/../lib/`
  via `install_name_tool`.
- Windows: DLLs copied into `bin/` (next to exe) — no wrapper script needed.
- `PackageArgs` in `commands/install.rs` gets `--installer` flag; archive is named
  `{name}-{version}-{arch}-{os}-installer.tar.gz` (or `.zip` on Windows).
- Fixed: pushed earlier session commits (docify inlining etc.) that were never
  pushed — that resolved the DocLanguage/DocItem CI failures.

**Tested:** `cargo check` clean (2 pre-existing dead-code warnings unrelated).

**Pushed:** `crates/freight` master, workspace pointer bumped.

**Open questions:** None.

### 2026-06-04 — Claude

**credentials, config cleanup, docify inlined, debug flags**

**What changed (crates/freight):**
- `freight login`/`logout`: tokens now stored in OS keychain (macOS Keychain,
  GNOME Keyring, Windows Credential Manager) via `keyring` + `keyring-core`.
  `credentials.toml` removed. Env vars `FREIGHT_TOKEN_<NAME>` / `FREIGHT_TOKEN`
  as CI fallback. New `freight logout` command.
- GNU + Clang dev profile: added `-fno-omit-frame-pointer -fasynchronous-unwind-tables`
  so stack unwinding works in debuggers. GAS assembler: `--gdwarf-2` → `--gdwarf-4`.
- LSP `freight/workspaceInfo` (schemaVersion 2): now returns detected `toolchains`
  array and current `sysroot` from the manifest.
- LSP `freight/setConfig`: new handler; `set_manifest_config()` uses `toml_edit`
  to write/clear `compiler.sysroot` in `freight.toml` without formatting loss.
- `docify` git dep removed; extract + render_md inlined into `src/doc/docify/`
  (dropped non-freight languages: Go, Java, Kotlin, Swift, Python, TS, C#, etc.)

**What changed (crates/freight-registry):**
- All secrets removed from config file: SMTP password, S3 key+secret, OAuth
  `client_secret`. Now env-var only: `FREIGHT_SMTP_PASSWORD`, `FREIGHT_S3_KEY_ID`,
  `FREIGHT_S3_SECRET`, `FREIGHT_OAUTH_<NAME>_CLIENT_SECRET`.

**What changed (editors/vscode-freight):**
- Status bar family picker filters to detected families from `workspaceInfo`.
- `pickSysroot` persists to `freight.toml` via `freight/setConfig` LSP call.
- `activeSysroot` seeded from manifest on first LSP connection.

**Tested:** 629 unit tests pass. 4 pre-existing integration tests fail (tcc missing in env).
**Pushed:** all committed in respective submodule repos.

### 2026-06-04 — Codex

**Additional DAP backend TODOs**

**What changed:**
- Added TODO coverage for future non-GDB/LLDB DAP backends.
- `crates/freight/TODO.md` now tracks investigation for `rr`, Windows `cdb`,
  and Windows `windbg` DAP support.
- `editors/vscode-freight/TODO.md` now notes that only GDB-family, CUDA-GDB,
  and LLDB DAP are supported for editor debugging today, with other debugger
  templates pending Freight core support first.

**Tested:** documentation-only change; no tests run.
**Pushed:** nothing pushed; changes remain uncommitted.

### 2026-06-04 — Codex

**DAP extra debugger args**

**What changed:**
- `freight dap` now appends native debugger adapter process args from the
  effective Freight config (`[debugger.<name>].args` in global/project
  `config.toml`) and from launch config `debuggerArgs`.
- Merge order is Freight DAP defaults, config.toml debugger args, then
  launch.json `debuggerArgs`.
- VS Code schema/payload/docs now expose `debuggerArgs` for launch and attach
  configurations.
- Extended Freight DAP tests for GDB and LLDB arg merging, and VS Code payload
  tests for serialized `debuggerArgs`.

**Tested:** `cargo test -p freight commands::dap::server::tests`;
`editors/vscode-freight/bun run test`; `node --check
editors/vscode-freight/src/extension.js`; `editors/vscode-freight/bun run
check`; `cargo build -p freight`.
**Pushed:** nothing pushed; changes remain uncommitted.

### 2026-06-04 — Codex

**DAP adapter test coverage**

**What changed:**
- Added Freight DAP unit tests in `crates/freight/src/bin/freight/commands/dap/server.rs`
  using fake DAP-speaking executables. Coverage includes explicit GDB,
  CUDA-GDB, explicit LLDB DAP, detected LLDB DAP, detected GDB probing,
  `default_debugger` selection, non-DAP rejection, and release/profile fallback.
- Added `editors/vscode-freight/tests/dap-config.test.js` plus a `bun run test`
  script to verify VS Code debug config serialization without requiring the VS
  Code runtime.
- Factored VS Code DAP config serialization into a testable helper and updated
  the README/TODO to mention the test coverage.

**Tested:** `cargo test -p freight commands::dap::server::tests`;
`editors/vscode-freight/bun run test`; `editors/vscode-freight/bun run check`;
`cargo build -p freight`.
**Pushed:** nothing pushed; changes remain uncommitted.

### 2026-06-04 — Codex

**VS Code debug config handoff**

**What changed:**
- Wired `editors/vscode-freight` debug sessions to write the resolved launch
  config to a temp JSON file and start `freight dap --config <file>` (plus
  `--attach` for attach sessions), so Freight sees `bin`, `package`,
  `features`, `debugger`, `debuggerPath`, profile/release, and related fields
  before it builds and execs the native adapter.
- Added resolved `profile` / `release` defaults from the VS Code status bar and
  mapped `stopAtEntry` to `stopAtBeginningOfMainSubprogram` for native adapters.
- Updated the VS Code debug schema/docs/TODO to describe the temp config
  transport and remaining real Extension Development Host smoke test.
- Updated `freight dap` build selection to honor `profile` from the launch
  config, falling back to `release` or `dev`.

**Tested:** `cargo build -p freight`; `editors/vscode-freight/bun run check`;
`node --check editors/vscode-freight/src/extension.js`; `target/debug/freight
dap --help`.
**Pushed:** nothing pushed; changes remain uncommitted.

### 2026-06-04 — Codex

**VS Code debug setup audit**

**What changed:**
- Inspected `editors/vscode-freight` debug provider/schema against the current
  simplified `freight dap`.
- Updated `editors/vscode-freight/README.md` and `TODO.md` to reflect the current
  blocker: VS Code launch fields such as `bin`, `package`, `features`,
  `debuggerPath`, `stopAtEntry`, and `env` are exposed by the extension but do
  not reach Freight before `freight dap` builds and execs the native adapter.
- Documented that the next implementation choice is either stable `freight dap`
  CLI/config transport or a small DAP shim that reads `launch` / `attach` before
  forwarding to GDB/LLDB.

**Tested:** `editors/vscode-freight/bun run check` passed.
**Pushed:** nothing pushed; changes remain uncommitted.

### 2026-06-04 — Codex

**LSP docs path cleanup and workspace build**

**What changed:**
- Updated `AGENTS.md` to point at the current `freight lsp` module directory,
  `crates/freight/src/bin/freight/commands/lsp/`, instead of the stale
  `commands/lsp.rs` path.

**Tested:** `cargo build` from the workspace root passed. It reported one existing warning:
`crates/freight/src/bin/freight/commands/publish.rs` has an unused `project_dir`
parameter in `run_pre_publish_pipeline`.
**Pushed:** nothing pushed; changes remain uncommitted.

### 2026-06-04 — Codex

**nvim-freight DAP and command pass**

**What changed:**
- Continued `editors/nvim-freight` after the `freight dap` simplification: the plugin now registers thin `Freight: Debug` and `Freight: Attach` `nvim-dap` configs, with attach starting `freight dap --attach`.
- Kept `:FreightRun` as a normal terminal workflow and added reusable terminal support.
- Added `:FreightAttach`, status/health helpers, extra Freight commands, root caching, `.freight/config.toml` watching, and command completion for target flags, binaries, packages, and dependencies.
- Completion inventory now reads workspace member `freight.toml` files, not only the root manifest.
- Updated `editors/nvim-freight/README.md` and `TODO.md` to match current behavior and remaining DAP limits.

**Tested:** `editors/nvim-freight/scripts/test.sh`.
**Pushed:** nothing pushed; nvim plugin changes remain uncommitted.

### 2026-06-04 — Claude

**DAP simplification, per-platform verify images, docify CI fix, org migration**

**What changed:**
- `freight dap` rewritten: dropped ~900-line proxy server; now just builds the project then `exec()`s into the native adapter (GDB `--interpreter=dap` or `lldb-dap`). Added `--attach` flag to skip build. `protocol.rs` deleted entirely.
- `freight-registry`: added per-platform CI verify images — `[serve.verify]` TOML section with per-OS image keys (`linux`, `windows`, `freebsd`, `macos`, etc.) and matching CLI flags / env vars. `run_verification_pipeline` now returns `bool`; multi-platform dispatch uses `AtomicUsize` + `AtomicBool` vote counting — publishes only if all platforms pass.
- `freight-registry`: added `[serve.scan]` TOML section with `backend` key → `FREIGHT_SCAN_BACKEND` env var.
- `docify`: pushed `#[derive(Serialize, Deserialize)]` on `DocItem` (was only local); unblocked freight GitHub CI.
- Org migration: `freight` and `freight-registry` repos moved to `freight-app` org. `cmake-lossless`, `docify`, and `vcpkg-converter` stay on `TiniTinyTerminator`. All Cargo.toml dep URLs updated accordingly.

**Tested:** `cargo check --workspace`; `cargo build -p freight`; `cargo build -p freight-registry`; all passed.
**Pushed:** all submodules pushed.

### 2026-06-04 — Codex

**Markdown documentation refresh**

**What changed:**
- Updated workspace and crate Markdown docs for the `freight-app` GitHub organization.
- Replaced stale `.deps/` package-cache references with `.pkgs/` in active docs.
- Corrected Cargo package references from `freight-core` to the current `freight` package while keeping the `freight_core` library name where appropriate.
- Refreshed Freight example paths from the old flat example layout to the current grouped `examples/<group>/<name>` layout.
- Removed stale `freight-registry-tui` architecture wording in favor of `freight tui`.

**Tested:** Markdown-only changes; ran repository-wide `rg` checks for stale owner names, `.deps`, old example paths, and `freight-core` package commands.
**Pushed:** nothing pushed; changes remain uncommitted.

### 2026-06-03 — Codex

**Freight DAP backend feature pass**

**What changed:**
- `freight dap` now honors `debuggerPath` as either an absolute path or command
  name on `PATH`, probing it as GDB-style DAP or native adapter depending on
  `debugger` / executable name.
- DAP debugger selection now treats `cuda-gdb` like GDB for native DAP probing.
- DAP debug builds now support workspace roots and launch `package` selection
  through `build_workspace_with`; non-workspace launches reject `package`.
- DAP run mode now drains stdout/stderr concurrently to avoid pipe deadlocks.
- Launch forwarding now normalizes `args`, `env`, and maps `stopAtEntry` to
  `stopAtBeginningOfMainSubprogram` for native adapters.
- VS Code schema now exposes `cuda-gdb`, `stopAtEntry`, `env`, richer
  `debuggerPath`, and an attach configuration shape; the provider no longer
  rewrites `attach` to `launch`.

**Still open:** terminal-backed DAP run/debug output is not implemented; quick-pick
for multiple binaries is still editor-side TODO; preLaunchTask is still VS Code-native
only and not interpreted by Freight.

**Tested:** `cargo check -p freight`; `cargo build -p freight`; DAP initialize
stdio smoke test; VS Code `bun run package`; package JSON parse check.
**Pushed:** pending.

### 2026-06-02 — Codex

**nvim-freight TODO progress**

**What changed:**
- Made `require("freight").setup()` idempotent for commands, autocommands, and
  Freight DAP configuration insertion.
- Added `.freight/config.toml` watch notifications alongside `freight.toml`.
- Added `M.status()`, `M.health()`, `:FreightLspStart`, `:FreightStatus`, and
  `:FreightHealth`.
- Added commands for `freight add`, `remove`, `update`, `check`, and `doc`.
- Added `scripts/test.sh` and `tests/headless.lua` for headless Neovim checks,
  including a stubbed `nvim-dap` registration/idempotency test.
- Updated README and TODO checkboxes for completed items.

**Tested:** `editors/nvim-freight/scripts/test.sh`.
**Pushed:** pending.

### 2026-06-02 — Codex

**nvim-freight TODO**

**What changed:** Added `editors/nvim-freight/TODO.md` covering DAP follow-ups,
LSP improvements, command UX, documentation, and test harness work.

**Tested:** documentation-only change.
**Pushed:** pending.

### 2026-06-02 — Codex

**nvim-freight DAP smoke test**

**What changed:** No new code changes beyond the pending `nvim-dap` integration in
`editors/nvim-freight`. After Neovim became available locally, verified the
plugin loads headlessly with DAP disabled and with DAP auto-detection enabled.
`nvim-dap` is not installed here, so a stub `dap` module was used to verify that
the plugin registers `dap.adapters.freight` and Freight run/debug configurations.

**Tested:** `nvim --headless -u NONE -i NONE` plugin load checks with XDG dirs
pointed at `/tmp`; stubbed `dap` registration assertion.
**Pushed:** pending.

### 2026-06-02 — Claude (session 4)

**DAP: fix breakpoints and variable readout**

Root causes found and fixed:

1. **No debug symbols** — `dev`/`release` profiles had no built-in defaults, so `compiler.debug`
   defaulted to `false` and `-g` was never added. Added built-in defaults:
   `dev` → `opt_level=0, debug=true`; `release` → `opt_level=3, debug=false`.
   `"debug"` is now an alias for `"dev"` in `resolve_profile`.

2. **Wrong profile** — DAP server was calling `build_project_with("debug", ...)` but freight's
   dev profile is `"dev"`. Changed to `"dev"`; fixed fallback binary path `target/debug/` →
   `target/dev/`.

3. **`initialized` event never sent** — `handle_initialize` was not emitting the DAP `initialized`
   event, so VS Code never entered the breakpoint configuration phase before launch.
   Now emits it immediately.

4. **Pre-launch `setBreakpoints` lost** — when VS Code has persistent breakpoints it sends
   `setBreakpoints` before `launch`. The old catch-all replied with `{}` (wrong schema).
   Now: buffer those requests, reply with `verified: false` placeholders, then replay to GDB
   after the binary is loaded. Emit `breakpoint`-changed events for GDB-verified ones.
   `configurationDone` is deferred and sent last so GDB starts after all breakpoints are installed.

5. **Duplicate `initialized`** — GDB's `initialized` event is now drained during bootstrap
   (VS Code already got ours).

**Variable readout** works via the existing passthrough relay — once the program stops at a
breakpoint, GDB handles `threads`/`stackTrace`/`scopes`/`variables` natively. No extra code needed.

**Tested:** `cargo build -p freight`; `cargo test -p freight manifest::types` (17 passed).
**Pushed:** `crates/freight` + workspace pointer.

### 2026-06-02 — Claude (session 3)

**vscode-freight review + unpushed Codex work committed**

- Reviewed `editors/vscode-freight` — extension builds clean (`bun run check`)
- Committed and pushed Codex's unpushed changes:
  - `vscode-freight`: `FreightDebugAdapterFactory` delegates to `freight dap`; `freight.run` wired through DAP; `debugger` enum + `debuggerPath` in launch config; activation events updated
  - `crates/freight`: 771-line `freight dap` stdio DAP backend (breakpoints, stepping, variables, watch/repl); `default_debugger` in GlobalConfig; hidden LSP compile DB; `-Wno-gnu-include-next` for clangd
- Registry: unified monospace/TUI theme in style.css; dep graph convergence + ResizeObserver auto-centre; namespace summary in docs viewer; conditional Docs badge in Info sidebar; hljs on package page

**Pushed:** all submodules + workspace

### 2026-06-02 — Codex

**Freight DAP backend for editor debugging**

**What changed:**
- Added `freight dap`, a stdio Debug Adapter Protocol backend owned by Freight.
- VS Code now spawns `freight dap` as the debug adapter executable instead of
  carrying GDB/MI adapter logic in the extension.
- Debugger selection is now pipelined through Freight core: launch configs may
  omit `debugger`, and Freight resolves `.freight/config.toml` /
  `~/.freight/config.toml` `default_debugger`.
- The backend supports run sessions, debug launch through GDB/MI, breakpoints,
  stepping, stack traces, local variables, hover evaluation, and watch/repl
  expression evaluation.
- Neovim now registers a `freight dap` adapter when `nvim-dap` is available and
  adds `:FreightDebug`.

**Tested:** `cargo check -p freight`; `cargo build -p freight`; DAP initialize
stdio smoke test; `node --check src/extension.js`; `bun run package`.
**Pushed:** pending.

### 2026-06-02 — Codex

**Project-local developer config default debugger**

**What changed:**
- Added `default_debugger` to Freight developer config (`/etc/freight/config.toml`,
  `~/.freight/config.toml`, and `<project>/.freight/config.toml`).
- `freight debug` now uses `--debugger` first, then `default_debugger`, then the
  first detected debugger.
- Existing `default_backend` already controlled preferred compiler selection for
  builds/LSP through the same local config loader; docs now show
  `default_backend = "clang"` with `default_debugger = "lldb"`.
- VS Code Freight debug launch resolution now reads simple scalar defaults from
  `~/.freight/config.toml` and `<workspace>/.freight/config.toml` so an omitted
  `"debugger"` field follows project-local developer config.

**Tested:** `cargo check -p freight`; `cargo test -p freight default_debugger
--lib`; `node --check src/extension.js`; `bun run package`.
**Pushed:** pending.

### 2026-06-02 — Codex

**VS Code debug activation and DAP sequencing fix**

**What changed:**
- Added broader debug activation events to `vscode-freight`: `onDebug`,
  `onDebugInitialConfigurations`, and `onDebugAdapterProtocolTracker:freight`
  in addition to `onDebugResolve:freight`.
- Fixed the Freight inline debug adapter lifecycle: it no longer emits DAP
  `initialized` during `initialize`. It now emits `initialized` after the
  run/debug launch backend is ready, so VS Code sends breakpoints and
  `configurationDone` after GDB has been started.
- Added a guard so an early `configurationDone` is remembered and starts the
  debuggee once GDB is ready.

**Tested:** `node --check src/extension.js`; `bun run package`; package JSON
parse check.
**Pushed:** pending.

### 2026-06-02 — Codex

**LSP codeAction diagnostic sanitization**

**What changed:**
- `freight lsp` now handles `textDocument/codeAction` explicitly.
- For `freight.toml`, it returns an empty action list for now.
- For source files, it sanitizes forwarded `context.diagnostics[*].code` values
  so passthrough servers such as clangd receive string codes and do not reject
  VS Code requests with `expected string`.

**Doxygen note:** source signature help/hover forwarded from clangd should keep
clangd's Doxygen-rendered Markdown intact. When Freight adds doc-cache-backed
hint enrichment, preserve/render Doxygen sections as Markdown in `MarkupContent`
instead of flattening them into plain text.

**Tested:** `cargo check -p freight`; `cargo test -p freight
commands::lsp::tests::code_action_diagnostic_codes_are_sanitized_to_strings --bin
freight`; `node --check src/extension.js`; `bun run package`.
**Pushed:** pending.

### 2026-06-02 — Codex

**Freight-owned VS Code debug adapter**

**What changed:**
- Added a Freight-owned GDB/MI debug adapter path inside `editors/vscode-freight`.
- `Freight: Debug` now runs `freight build`, resolves the produced `target/dev`
  binary, starts `gdb --interpreter=mi2`, applies VS Code breakpoints, and wires
  DAP commands for launch/configurationDone, breakpoints, continue, next, step
  in/out, pause, threads, stack trace, scopes, locals, disconnect, and terminate.
- No dependency on cpptools, CodeLLDB, or any other debug extension.
- `debugger` / `debuggerPath` launch fields are exposed; `gdb` is implemented,
  and the same shape is reserved for LLDB/other backends.

**Tested:** `node --check src/extension.js`; `bun run package`; package JSON
parse check; `cargo check -p freight`; `cargo test -p freight
build::tests::lsp_include_filter --lib`.
**Pushed:** pending.

### 2026-06-02 — Codex

**Freight VS Code run/debug sessions, signature help polish, and stricter LSP includes**

**What changed:**
- VS Code `Freight: Run` now starts a real VS Code debug session instead of a
  plain task; the inline debug adapter runs `freight run` / `freight debug`,
  streams stdout/stderr into the Debug Console, reports exit/termination events,
  and keeps the session visible in the Run and Debug panel.
- Follow-up correction: Freight must not depend on cpptools/CodeLLDB or any
  external debug extension. The VS Code plugin now keeps run/debug wired to the
  Run and Debug panel through Freight's own inline adapter; real breakpoint
  debugging remains future work for a Freight-owned DAP/MI adapter.
- `freight.toml` signature help now uses compact C++-style labels such as
  `freight::dependency { semver version, path path, ... }` so VS Code's native
  signature widget renders closer to cpptools' compact style and includes
  type-like metadata without depending on cpptools.
- Hidden LSP compile database generation now filters broad external include dirs
  from clangd input, keeping Freight project/package paths and known standard
  C/C++ compiler resource/stdlib include dirs only.
- `freight lsp` starts clangd with background indexing disabled and header
  insertion disabled to reduce external header crawling/suggestions.

**Tested:** `cargo check -p freight`; `cargo test -p freight
build::tests::lsp_include_filter --lib`; `bun run package` and `node --check
src/extension.js` in `editors/vscode-freight`.
**Pushed:** pending.

### 2026-06-02 — Codex

**VS Code extension debug launch configs**

**What changed:**
- Added VS Code Extension Development Host launch/tasks configs for both workflows:
  opening the whole freight workspace and opening `editors/vscode-freight` directly.
- Constrained source map resolution to the Freight extension paths and skipped
  `.vscode-server`, which avoids missing source-map warnings from built-in remote
  VS Code extensions during extension debugging.
- Narrowed the VS Code extension `.gitignore` so `.vscode/launch.json` and
  `.vscode/tasks.json` are tracked while local settings remain ignored.
- Updated the VS Code extension README with the root-workspace launch config name.

**Tested:** JSON parse check for all launch/task files; `bun run package` in
`editors/vscode-freight`.
**Pushed:** pending.

### 2026-06-02 — Codex

**freight-core: VS Code-style manifest signature help and editor repo prep**

**What changed (uncommitted in workspace / crates/freight):**
- `freight lsp` now advertises and handles `textDocument/signatureHelp` for
  `freight.toml`, producing native VS Code signature-widget data with compact
  function-like labels and active-parameter highlighting for manifest sections and
  dependency inline tables.
- Source-file signature help still forwards to passthrough servers such as clangd.
- Added standalone repo hygiene for `editors/vscode-freight` and
  `editors/nvim-freight` (`.gitignore` files and README requirement/install updates).
- Initialized both editor plugin folders as local git repos and pushed them:
  - `editors/vscode-freight`: `86e9f01 initial vscode freight extension`
  - `editors/nvim-freight`: `7244bc6 initial neovim freight plugin`

**Tested:** `cargo check -p freight`; `cargo build -p freight`; `bun run package`
in `editors/vscode-freight`; direct LSP smoke test confirmed dependency signature
help highlights `path` as the active parameter.
**Pushed:** public repos created and pushed:
- `https://github.com/TiniTinyTerminator/vscode-freight`
- `https://github.com/TiniTinyTerminator/nvim-freight`

**Follow-up:** converted both editor plugin folders into root workspace
submodules. `.gitmodules` now includes `editors/vscode-freight` and
`editors/nvim-freight`; the root index records gitlinks at `86e9f01` and
`7244bc6` respectively.

### 2026-06-02 — Claude (session 2)

**Registry docs viewer + migrator improvements**

**What changed:**
- `docs.html` fully working: freight-doc TUI palette + hierarchy, syntax highlighting (highlight.js One Dark overlay), all docify tag types (tparam, param, return, retval, throws, note, warning, example, deprecated, since, see-also), nested class groups inside namespaces, source link + owner chips in sidebar header, ▶/▼ toggle arrows that actually swap
- Fixed three wire-format bugs against live libvec data: item kind is `label()` lowercase, tag Other uses Debug format `Other("tparam")`, lang is `DocLanguage::label()` string
- `cmake-lossless/eval.rs`: VERSION_* comparisons, IN_LIST, compound platform_condition (UNIX AND NOT APPLE → linux), option() in vars.rs — all done and tested
- `freight/build`: has_lang dedup → build/mod.rs, LINK_PRIORITY constant, Ada whole-program BuildEvent
- `crates/libtexprintf` deleted
- AGENTS.md, CLAUDE.md, TODO.md files updated

**Pushed:** all submodules + workspace bumped

**Next:** add_compile_options / target_compile_options migration in freight cmake migrator; include()/add_subdirectory() following in cmake-lossless

### 2026-06-02 — Claude

**libtexprintf removed; migrator improvements; freight doc browser polish**

**What changed:**
- `crates/libtexprintf` deleted — no references anywhere; AGENTS.md + CLAUDE.md updated
- `cmake-lossless/eval.rs`: `VERSION_*` comparison operators, `IN_LIST`, compound `platform_condition` (`UNIX AND NOT APPLE → linux`, etc.), `option()` tracking in `vars.rs`
- `freight/build`: `has_lang` extracted to `build/mod.rs` (was duplicated in compile.rs + link.rs); `LINK_PRIORITY` constant in `link.rs`; `BuildEvent::Compiling` emitted before `gnatmake` whole-program invocation
- `freight doc` browser: half-circle pill headings (Nerd Font U+E0B6/U+E0B4), fenced code blocks in boxes with language label, visual-row scroll (fixes text cut-off), virtual scroll for source view (only renders visible window), scroll off-by-one fix

**Pushed:** all submodules + workspace bumped

**Next:** web frontend — update `docs.html` + `package.html` to use `freight doc` instead of the docify msgpack endpoint; update sidebar/package page to reflect new `freight doc` TUI rather than web-rendered docs viewer

### 2026-06-02 — Codex

**freight-core: hidden LSP compile database and manifest help**

**What changed (uncommitted):**
- `freight lsp` now generates its clangd compile database in a backend cache
  outside the project tree and starts clangd with that `--compile-commands-dir`;
  the explicit `freight compile-commands` command still writes the project-root
  `compile_commands.json`.
- Added backend `generate_lsp_compile_commands_at()` plus a reusable
  `compile_commands::write_to()` helper.
- Expanded `freight.toml` LSP completion and hover help for workspace, package,
  dependency, language, target, profile, formatter, linter, OS, and arch sections.
- Expanded the VS Code `schemas/freight.schema.json` to cover the current manifest
  surface, including profiles, formatter/linter, PCH/unity, conditional overlays,
  dependency filters, and known language/platform keys.
- Updated `crates/freight/docs/manifest-reference.md` to document the hidden LSP
  compile database behavior.

**Tested:** `cargo check -p freight`; `cargo build -p freight`;
`cargo test -p freight build::compile_commands::tests --lib`; `bun run package`
in `editors/vscode-freight`; JSON parse check for the schema; LSP smoke test in
`/tmp` confirmed no root `compile_commands.json` is created.
**Pushed:** nothing.

### 2026-06-02 — Codex

**freight-core: clangd `#include_next` diagnostic suppression**

**What changed (`crates/freight`, uncommitted):**
- `build/compile_commands.rs` now injects `-Wno-gnu-include-next` into generated
  compile command entries for C-family languages only.
- This affects clangd/IDE diagnostics only; real build warning flags are unchanged.
- Added unit tests covering C-family inclusion and non-C-family exclusion.

**Tested:** `cargo check -p freight`; `cargo test -p freight build::compile_commands::tests --lib`.
**Pushed:** nothing.

### 2026-06-02 — Codex

**freight-core: Neovim plugin scaffold**

**What changed (uncommitted):**
- Added `editors/nvim-freight/`.
- Detects `freight.toml` as `freight`.
- Provides `require("freight").setup()` for Lazy.nvim-style setup.
- Starts/reuses `freight lsp` with Neovim's built-in LSP client.
- Autostarts for `freight.toml`, C/C++/CUDA/HIP/ObjC/ObjC++, Fortran, and assembly buffers.
- Watches `freight.toml` writes and notifies `workspace/didChangeWatchedFiles`.
- Adds `:FreightBuild`, `:FreightRun`, `:FreightTest`, `:FreightFetch`, `:FreightClean`,
  `:FreightCompileCommands`, and `:FreightRestartLsp`.
- Updated `AGENTS.md` and `crates/freight/docs/TODO.md`.

**Tested:** not runtime-tested because `nvim`, `lua`, and `luac` are not installed locally.
Reviewed source manually for Neovim built-in LSP API usage.
**Pushed:** nothing.

### 2026-06-02 — Codex

**freight-core: VS Code extension scaffold**

**What changed (uncommitted):**
- Added `editors/vscode-freight/` extension scaffold.
- Contributes `freight-manifest` language for `freight.toml` plus TextMate highlighting.
- Starts `freight lsp` through `vscode-languageclient` with settings for freight, clangd, fortls, asm-lsp, profile, and passthrough toggles.
- Removed explicit `TransportKind.stdio` from executable server options because it caused some
  VS Code language-client versions to append `--stdio` to the server command.
- Registers Freight tasks: build, build --release, run, test, fetch, clean, compile-commands.
- Contributes a `Freight` debug type for the Run and Debug panel; an inline debug adapter opens
  a VS Code terminal and launches `freight run`, `freight run --release`, or `freight debug`.
- Adds command palette commands for restarting the language server and generating `compile_commands.json`.
- Adds a status bar item and a basic Freight problem matcher.
- Added a draft `schemas/freight.schema.json` asset for future TOML schema integration.
- Updated `AGENTS.md` and `crates/freight/docs/TODO.md`.

**Tested:** `node --check src/extension.js`, JSON parse check for extension assets, and package script passed. Package script now uses Bun. Did not run an Extension Development Host because dependencies are not installed.
**Pushed:** nothing.

### 2026-06-02 — Codex

**freight-core: first-pass `freight lsp`**

**What changed (`crates/freight`, uncommitted):**
- Added `freight lsp` subcommand in `src/bin/freight/commands/lsp.rs`.
- The server owns `freight.toml` diagnostics, completion, and hover over stdio.
- It starts `clangd`, `fortls`, and `asm-lsp` by default when those executables are available,
  and forwards source-file LSP traffic by extension.
- On initialize and `freight.toml` save, it refreshes `compile_commands.json` via Freight's manifest-aware generator, so clangd only sees sources/includes/libs from explicitly declared active targets/deps.
- Added `--no-clangd`, `--clangd`, `--no-fortls`, `--fortls`, `--no-asm-lsp`, `--asm-lsp`, and `--profile` options.
- Added hidden `--stdio` compatibility flag after VS Code language client appended it during startup.
- Fixed initialize response shape to return `{ capabilities, serverInfo }` and added
  `capabilities.positionEncoding = "utf-16"` for `vscode-languageclient` 9.x.
- Registers an editor file watcher for `**/freight.toml`; `workspace/didChangeWatchedFiles`
  regenerates `compile_commands.json`, so package additions from `freight add` are picked up.
- Updated `README.md`, `docs/manifest-reference.md`, and `AGENTS.md`.

**Tested:** `cargo check -p freight` passed; LSP initialize/shutdown smoke test passed with `--no-clangd`; watched-file notification smoke test regenerated diagnostics/compile DB; default LSP smoke test passed with clangd installed and missing `fortls`/`asm-lsp` skipped cleanly. `fortls` and `asm-lsp` were not installed locally, so those child-server paths were compile-checked but not runtime-smoked.
**Pushed:** nothing.

### 2026-06-02 — Codex

**freight-core: Objective-C, Objective-C++, and HIP examples**

**What changed (`crates/freight`, uncommitted):**
- Added `examples/objc-hello/`: Objective-C `.m` binary using clang and macOS Foundation.
- Added `examples/objcpp-hello/`: Objective-C++ `.mm` binary mixing Foundation and C++ containers.
- Added `examples/hip-hello/`: HIP `.hip` binary with vector add/scale kernels for ROCm systems.
- Updated `examples/README.md` matrix and mixed-language workflow.
- Updated `TODO.md` example status for ObjC/ObjC++ and HIP.

**Tested:** `/home/max/freight/target/debug/freight check` passed in all three new example dirs.
**Pushed:** nothing.

### 2026-06-01 — Claude (second pass)

**docify: declaration-line and PHP hierarchy fixes**

**What changed (all in `crates/docify`, uncommitted):**

- `src/extract/go.rs`, `ada.rs`, `d.rs`: changed `i + 1` → `end + 2` as the
  line number passed to `build_item`. Like Fortran (fixed earlier), these
  three were passing the comment-start line, so the source pane was scrolling
  to the doc comment rather than the declaration.

- `src/tui/browser.rs` `declaration_line_idx`: extended to recognise `//`
  (plain Go/C++ style), `/++` (D), and `--` (Ada/Haskell) comment openers as
  well as the existing `///`/`/**` patterns, so any item whose line still
  points to a comment is correctly advanced to the declaration.

- `src/extract/php.rs`: added brace-depth class scope tracking (same pattern
  as C# from the previous pass). PHP methods are now qualified as
  `Collection.filter` etc. so they group under their class node in the tree
  instead of all landing in `(root)`.

**Tested:** all 373 tests pass.
**Pushed:** nothing yet.

### 2026-06-01 — Claude

**docify: example package manifests + hierarchy fixes**

**What changed (all in `crates/docify`, uncommitted):**
- Added `freight.toml` to the 5 `doc-example/libs/` subdirs missing them:
  `csvkit`, `formatter`, `geometry`, `scripting`, `signals` — they were all
  rolling up under the root `doc-example` package instead of having their own
  package nodes in the TUI tree.

- `src/tui/browser.rs` `item_group_parts`:
  - Ada/D/Go/Fortran arm: module items (e.g. Fortran `linalg` module) now route
    to `split_scope(&item.name)` instead of `(root)`, so the module becomes the
    group node its children were already in.
  - Ruby extracted as its own match arm: module items get the same fix, and
    the `#` method separator (`Formatter#float_field`) is now recognised so
    methods appear under their module instead of `(root)`.
  - Big multi-language arm (TS/JS/C#/PHP/Lua/R/Haskell/Python): same module
    routing fix — Haskell `Stats` module item was landing in `(root)` while
    `Stats.mean` etc. were correctly in the `Stats` subtree.

- `src/extract/lua.rs`: normalize `:` method syntax to `.` in function names
  (`Vec:__tostring` → `Vec.__tostring`) so it groups under `Vec` like siblings.

- `src/extract/csharp.rs`:
  - `detect_cs_member` rewritten: extracts the identifier directly before `(`
    (method) or `{` (property). The old version returned garbage names for
    methods with generic return types (e.g. `ReadRow` was extracted as
    `string>?` from `Dictionary<string, string>? ReadRow()`).
  - Added brace-depth class scope tracking: methods are now qualified with
    their enclosing class (`CsvKit.CsvReader.ReadRow`) so they appear under
    the class node in the tree hierarchy.

**Tested:** all 307 existing tests still pass.
**Pushed:** nothing yet — waiting for review.

### 2026-05-31 — Claude

**freight doc TUI: Doxygen web-style layout**

**What changed (`crates/freight` @ 9ac70ed):**
- `src/bin/freight/commands/doc.rs`: major TUI restructure
  - New `NavMode` enum (`Welcome`, `Readme`, `DepOverview`, `TypePage`, `NamespacePage`, `SymbolDetail`) drives what the centre panel shows
  - New `SectionHdr` tree node kind; sidebar now has three collapsible sections per dep: **Classes & Types** / **Namespaces** / **Free Symbols**
  - Each sidebar item shows a kind badge (`[cls]`, `[fn]`, `[ns]`, etc.)
  - Namespace group nodes navigate to a `NamespacePage` (types + functions + vars table) instead of expanding inline
  - Type symbol nodes navigate to a `TypePage` (full type doc + member table)
  - Free symbol nodes navigate to `SymbolDetail` (full detail, existing renderer reused)
  - `DepOverview` shows summary tables (types, namespace groups, free symbols)
  - Clicking links in overview/type/ns pages navigates to symbol detail via `navigate_link`
  - `content_title()` added: centre panel border title reflects current page
  - `load_dep_if_needed` extracted from `open_dep_node`; `rebuild_content` replaces `render_dep_content`
  - Three tree tests updated to new structure

**Pushed:** workspace pointer bumped to `429e49c8`

**No questions.**

### 2026-05-31 — Claude (autonomous)

**freight publish: auto-upload API docs**

**What changed (`crates/freight`):**
- `src/registry/freight_registry.rs`: added `upload_docs(name, version, docs: &[u8])` — PUTs msgpack blob to `PUT /api/v1/packages/:name/:version/docs`
- `src/bin/freight/commands/publish.rs`: after a successful `publish_package()`, scans `src/` with `docify::extract::extract_dir()`, serializes with `docify::to_msgpack()`, uploads via `registry.upload_docs()`. Non-fatal: prints a warning if extraction yields 0 items or if upload fails, rather than failing the publish.

**What changed (`crates/docify`):**
- `src/extract/rust.rs`: removed stale unused `next_non_blank` import (leftover from the attribute-skipping fix).

**What was pushed:** both submodules pushed; workspace pointer bumped to `26fa1fb`.

**What remains:**
- `examples/with-deps/freight.toml` has unstaged dep removals in the freight submodule — was pre-existing, not committed here.
- Source-dir detection in publish uses a simple `src/` fallback. Could match the richer logic in `doc.rs` (`manifest.lib.srcs`, `manifest.bins`) if packages with non-standard layouts need coverage.

### 2026-05-31 — Claude (session 12)

**freight-registry + freight CLI: #keyword and @user search syntax**

**What changed (`crates/freight-registry`):**
- `src/db.rs`: `search_packages_by_keyword()` — exact keyword match (handles "kw", "kw,…", "…,kw", "…,kw,…")
- `src/api/search.rs`: `?keyword=1` param routes to keyword-only DB query
- `src/api/user_profile.rs` (new): `GET /api/v1/users/:username` — public profile + packages
- `src/api/mod.rs`: registered new route + `/users/:_name` → `users.html`
- `static/users.html` (new): user profile page (avatar letter, package list)
- `static/app.js`: `parseQuery()` / `searchUrl()` helpers; `API.searchByKeyword()`; nav search routes `@user` → `/users/…`; keyword cloud + card badges now show `#tag` links
- `static/index.html`: `doSearch()` + `performSearch()` handle `#` / `@` prefixes; page-load `?q=@user` redirects

**What changed (`crates/freight`):**
- `src/registry/mod.rs`: `UserProfile` / `UserPackageEntry` structs; `fetch_user_profile()` on `PackageRepo` trait (default: None)
- `src/registry/freight_registry.rs`: `FreightRegistry` implements `fetch_user_profile`; `search()` passes `&keyword=1` for `#` queries
- `src/bin/freight/commands/search.rs`: `@user` → calls `fetch_user_profile`, prints profile table; `#keyword` → prints "packages tagged #tag" header

**Pushed:** both submodules + workspace pointer bump

**Questions for next agent:** none — graph feature still deferred

### 2026-05-29 — Claude (session 11)

**freight-registry: dependency graph; vcpkg-converter: migrate-build-all + seed-registry**

**What changed (`crates/freight-registry`):**
- `static/package.html`: dependency graph section added to left column (below versions)
  - Lazy-loads Cytoscape.js 3.29 from jsDelivr CDN only when deps exist
  - Breadthfirst directed layout: current package (orange-red accent) → dep nodes (blue)
  - Click on a dep node navigates to `/packages/<name>`
  - Capped at 40 nodes with a note when truncated

**What changed (`crates/vcpkg-converter`):**
- New subcommand `seed-registry <DIR>`: writes 15 curated C/C++ stubs (zlib, cJSON, libuv, libpng, lua, libffi, mbedtls, etc.)
- New subcommand `migrate-build-all <DIR>`: downloads source → `freight migrate` → `freight build` per stub, reports PASS / FAIL_MIGRATE / FAIL_BUILD separately with first-error hints; supports `--continue`
- `freight_batch.rs`: `MigrateBatchStats`, `migrate_build_all()`, download/extract helpers (`curl` + `tar`/`unzip`), `write_curated_registry()`

**Smoke test results (15 curated packages):**
- `freight-build-all`: 15/15 PASS
- `migrate-build-all`: 15/15 PASS (3 stub fixes needed: lz4/zstd→`make`, expat→release tarball URL; json-c threshold lowered 64→8)

**Pushed:** `crates/freight-registry` @ 25267b0, `crates/vcpkg-converter` @ d9400bb, workspace @ d0db23d

**No open questions.**

---

### 2026-05-29 — Claude (session 10)

**freight-core: prebuilt type selection, --target, .deps/ storage**

**What changed (`crates/freight`):**
- `freight fetch --prebuilt <release|debug|source>` replaces `--source` flag
  - `release` (default): looks for prebuilt at `<triple>`
  - `debug`: looks for prebuilt at `<triple>-debug`
  - `source`: skips prebuilt lookup, always downloads source tarball
- `freight fetch --target <TRIPLE>`: selects cross-compile triple for prebuilt lookup (defaults to host)
- Prebuilt tarballs now land in `.deps/<name>/` (not `target/deps/`)
  — survives `freight clean` (which only wipes `target/`)
- Source tarballs stay in `target/deps/<name>/` as before
- `meta/mod.rs` dep resolution checks `.deps/` first, then `target/deps/`
- `dep_cmds.rs::fetch_registry_deps` skips if either sentinel exists

**Pushed:** `crates/freight` @ 59cd499, workspace bump @ 28f00c7

**No open questions.**

---

### 2026-05-29 — Claude (session 9+)

**Garage S3 wired up; test packages published; git cleanup**

**What changed:**
- Registry restarted with `--s3-bucket test --s3-endpoint http://192.168.178.45:3900 --s3-region garage` (region must be `garage` for AWS4 auth scope)
- Published 3 test packages via `freight publish`: `mathutils@0.1.0`, `strslice@0.2.1`, `clog@1.0.0` — all stored in Garage S3
- `crates/freight` pushed (rustfmt pass, `0d2225b`)
- `crates/freight-registry` committed + pushed all W10–W14 + S3/Postgres fixes (`98aca8b`)
- Workspace root updated with submodule pointer bumps + Cargo changes

**Questions for next agent:** None — all WEBSITE.md and session tasks complete.

---

### 2026-05-29 — Claude (session 9)

**`freight-registry` — W10–W14 (all remaining website tasks)**

**What changed:**
- **W10** `static/404.html` — freight-themed 404 page; explicit `/` route; fallback_service uses `tower::service_fn` returning 404.html for unknown paths
- **W11** `GET /api/v1/keywords` — counts comma-separated keywords across packages table, returns top N; `static/app.js` `renderKeywordCloud()` shows keyword cloud on homepage (no-query state); falls back to 25 curated browse categories (audio, json, ssl, …) when API returns empty
- **W12** Sort dropdown (A–Z / Most downloaded / Newest) in filter bar; `sort=` param added to `SearchParams` in `search.rs`; `search_packages` in `db.rs` switches `ORDER BY` based on sort value
- **W13** Hamburger button added to all 5 HTML pages; CSS `@media (max-width: 600px)` collapses `.nav-links`; JS closes menu on outside click
- **W14** `migrations/0003_packages_latest_version.sql`: `ALTER TABLE packages ADD COLUMN latest_version TEXT`; `cmp_version`/`best_version` moved to `db.rs` as public; `publish_version` maintains `latest_version` on each publish; `update_all_latest_versions()` new method; import phase 4 calls it; search query joins on `p.latest_version` (COALESCE fallback for old rows)
- `tower` moved from dev-deps to regular deps (needed for `tower::service_fn` in prod code)
- `api/keywords.rs` new module; registered in `api/mod.rs`

**What was tested:**
- `cargo build` clean ✓
- `curl /api/v1/keywords` — returns `{"keywords":[]}` (vcpkg stubs have no keywords, fallback shows curated list in UI)
- `curl /api/v1/search?q=&sort=downloads` → sorted by downloads ✓
- `curl /api/v1/packages/zlib` → `"latest":"1.3.2"` (semantic sort correct) ✓
- `curl /nonexistent` → HTTP 404 ✓
- Import re-run: phase 4 set `latest_version` for 2797 packages ✓

**What was pushed:** `crates/freight-registry` @ `98aca8b`; `crates/freight` (fmt) @ `0d2225b`; workspace root updated below

**All WEBSITE.md items now complete.**

### 2026-05-29 — Claude (session 8)

**`freight-registry` — W7 channel filter, login/register/account pages, package layout, `supports` platform badges**

**What changed:**
- Channel filter buttons on homepage (stable / experimental / all) — replaces build-system filter which was client-side only (W7)
- Login, register, account pages (`static/login.html`, `register.html`, `account.html`) + routes in `api/mod.rs`
- Auth routes protected from CSP issues; `Auth` object in `app.js` manages `freight_session` in localStorage
- Package detail layout redesigned: README in left column; Install widget → Metadata → Platform support → Dependencies → Owners in right sidebar
- Dependency names are clickable links to `/packages/<name>` (with channel param for non-stable)
- Version selector: `?version=` param, highlighted row in table
- `renderSupports(expr)` in `package.html`: parses vcpkg-style `!uwp & !arm` into ✓/✗ badges
- **Database**: `migrations/0002_add_supports.sql` + `migrations_pg/0002_add_supports.sql` add `supports TEXT` to versions
- `VersionRow` in `db.rs`: added `supports: Option<String>`; all three version SELECTs updated
- `publish_version`: accepts and stores `supports`; `publish.rs` `PublishMeta` struct updated
- `batch_version_insert_sql` in `main.rs`: 7 columns; `ON CONFLICT DO UPDATE SET supports = excluded.supports` so re-import populates existing rows
- Re-ran import from `/home/max/freight/vcpkg-tomls` (23,275 stubs) — `supports` now populated
- `favicon.svg` freight-box icon; `.badge.lang` yellow language tag; `.support-badge` green/red platform badges

**What was tested:**
- `curl /api/v1/packages/mailio` → `supports: "!uwp"` ✓
- `cargo build -p freight-registry` clean ✓
- Server running at `0.0.0.0:7878` (PID 2251, log `/tmp/registry.log`)

**What was pushed:** changes uncommitted — submodule (`crates/freight-registry`) has local edits only

**WEBSITE.md open items:** W10 (custom 404), W11 (browse by keyword), W12 (sort order), W13 (responsive nav), W14 (search version consistency)

### 2026-05-28 — Claude (session 7)

**`freight-registry` — website W1–W9**

**What changed:**
- `GET /api/v1/stats` endpoint returns `{packages, downloads, versions, users}` using existing `DbStats`
- `security_headers` middleware now also sets `Content-Security-Policy` (W2)
- Homepage stats bar renders real package + download counts (W1)
- Keyword badges in search-result cards are now `<a href="/?q=kw">` links (W3)
- Package detail: prebuilt triples panel with per-triple download links (W4)
- Package detail: total downloads summed across all versions in header + sidebar (W5)
- Package detail: `?version=` param selects active version; highlighted row in table; deps/prebuilts shown for that version (W6)
- `renderMarkdown` in `package.html` now handles ordered/unordered lists, blockquotes, GFM tables, images (W8)
- SVG favicon at `/favicon.svg` linked from both HTML pages (W9)
- `WEBSITE.md` added to track all open/closed website tasks
- All pushed: `crates/freight-registry` @ `5aa4a4f`; workspace @ `195fd2fe`

**What remains (in WEBSITE.md):**
- W7: channel filter dropdown on search
- W10: custom 404 page
- W11: browse by keyword section on homepage
- W12: sort order on search (needs API `sort=` param first)
- W13: responsive nav hamburger

**Tested:** stats endpoint returns `{downloads:2, packages:2797, versions:23275, users:2}`; CSP header present on all responses; build clean.

### 2026-05-28 — Claude (session 6)

**`freight-registry` — ON CONFLICT fix + bulk vcpkg import**

**What changed:**
- `pg_sql()`: added translation of `ON CONFLICT(name, channel)` → `ON CONFLICT(lower(name), lower(channel))` so `publish_version` upserts work on Postgres (functional unique index requires the expression form)
- `Db::is_postgres()` / `Db::pool()`: new public accessors for bulk-import tooling
- `Command::Import`: new CLI subcommand — reads a directory of vcpkg-scraper `.toml` stubs and bulk-imports them as metadata-only packages. Batches 500 rows/query. Deduplicates package names (multiple version files → one package row + N version rows). 3-phase: packages → id resolution → versions+owners
- Server bound to `0.0.0.0:7878` (was `127.0.0.1`). Static files served via `FREIGHT_STATIC_DIR` env var or relative `static/` fallback
- Web UI shipped: `static/index.html` (search + pagination), `static/package.html` (detail view), `static/app.js`, `static/style.css`

**What was tested:**
- Build: clean (`cargo build -p freight-registry`)
- Server started with Supabase Postgres; `/health` returns `{"db":"ok","status":"ok"}`
- Import of 23,275 vcpkg stubs under user `vcpkg`: 2,797 distinct packages, 23,275 versions, completed in ~2 min
- API verified: `GET /api/v1/search?q=zlib` returns zlib + oatpp-zlib

**What was pushed:**
- `crates/freight-registry` @ `512b04c`
- Workspace bumped @ `9b98c23`

**Server is running** at PID 544755 (check with `ps aux | grep freight-registry`). Logs in `/tmp/freight-server.log`.

**What remains:**
- `freight login --provider <name>` CLI command (OAuth side server-complete, CLI side not started)
- `--scope` flag for `token add` CLI subcommand
- Stats bar on index.html only shows ✓ status; could fetch package/version counts from a new `/api/v1/stats` endpoint
- The `search_packages` query only searches by name (`lower(name) LIKE lower(?)`); could also search `description` and `keywords`

### 2026-05-28 — Claude (session 5)

**`freight-registry` — Postgres compatibility fixes + live smoke test**

Two bugs prevented the registry from working with PostgreSQL via sqlx's `AnyPool`:

1. **`?` placeholder translation** — `AnyPool` does NOT auto-translate `?` to `$1`,`$2`,...
   for Postgres. Fixed by adding `pg_sql()` free function and `q_sql()` method on `Db`.
   All 74 runtime query calls now go through `q_sql()`. The 3 `tokio::spawn` blocks
   pre-compute the rewritten SQL string before entering the async closure.

2. **`CITEXT` column decoding** — `AnyPool` cannot decode PostgreSQL's `CITEXT` custom type.
   Updated `migrations_pg/0001_initial_schema.sql` to use `TEXT` everywhere.
   Case-insensitive uniqueness is enforced via `lower()` functional unique indexes
   (`idx_users_username_ci`, `idx_organizations_name_ci`, etc.). All queries already
   use `lower()` for comparisons, so semantics are unchanged.

**Pushed:** `crates/freight-registry` commit `8c35167`; workspace bumped `fc88316`

**Live smoke test** against Supabase Postgres (PostgreSQL 17.6) — all endpoints 200:
- `user add admin`, `user promote admin`, `token add dev-token` ✅
- `/health`, `/api/v1/me`, `/api/v1/search`, `/api/v1/admin/users`,
  `/api/v1/audit`, `/api/v1/orgs`, `/api/v1/me/tokens`, `/api/v1/users/login` ✅

**Supabase DB**: tables wiped and re-migrated (CITEXT → TEXT). Admin user recreated.
Token `dev-token` in DB (raw token value stored in this session — not committed).

**Next tasks:**
- `freight-registry import <dir>` subcommand for bulk-importing vcpkg scraper stubs
- `freight login --provider <name>` CLI command (server OAuth side is complete)
- Consider adding `--scope` flag to `token add` CLI command

---

### 2026-05-28 — Claude (session 4)

**`freight-registry` — OAuth/OIDC generalization (provider-agnostic)**

#### `freight-registry` (uncommitted — pending push from submodule)

Replaced the GitHub-only OAuth implementation with a fully generic OAuth 2.0 / OIDC system.

**New files / major rewrites**:

| File | Change |
|---|---|
| `src/oauth.rs` | New module — `OAuthProviderConfig` (config/deserialize) + `OAuthProvider` (resolved) + OIDC discovery + `github_from_env`, `gitlab_from_env`, `google_from_env` presets |
| `src/api/oauth.rs` | Rewritten — generic `oauth_start` + `oauth_callback` with `Path<String>` provider name |

**Updated**:
- `src/lib.rs`: removed `GitHubOAuthConfig`; `PendingOAuthState` gains `provider_name`; `AppState.github_oauth` → `AppState.oauth_providers: Vec<OAuthProvider>`
- `src/config.rs`: `ServeConfig` gains `oauth: Vec<OAuthProviderConfig>`; `load()` returns `(Option<PathBuf>, Vec<OAuthProviderConfig>)` — OAuth configs can't be expressed as env vars
- `src/api/mod.rs`: routes changed to `/auth/:provider` + `/auth/:provider/callback`
- `src/main.rs`: removed `--github-client-id`/`--github-client-secret` flags; at startup collects providers from config file + env-var presets + resolves all (OIDC discovery async)
- `src/db.rs`: `OAUTH_SENTINEL` const → `fn oauth_sentinel(provider: &str) -> String`; sentinel is now `"!oauth:{provider}"` (login.rs already checks `starts_with("!oauth:")`)

**How to configure OAuth now**:

Env-var shortcuts (no config file needed):
```sh
GITHUB_CLIENT_ID=…    GITHUB_CLIENT_SECRET=…   # → /auth/github
GITLAB_CLIENT_ID=…    GITLAB_CLIENT_SECRET=…   # → /auth/gitlab (+ GITLAB_ISSUER for self-hosted)
GOOGLE_CLIENT_ID=…    GOOGLE_CLIENT_SECRET=…   # → /auth/google
```

Config file for custom / company OIDC providers:
```toml
[[serve.oauth]]
name          = "okta"
display_name  = "Okta SSO"
client_id     = "0oa…"
client_secret = "…"
issuer        = "https://company.okta.com"    # triggers OIDC auto-discovery
```

**Backward compatibility**: existing `"!oauth:github"` sentinels in the DB are unaffected — new GitHub users still get `"!oauth:github"`.  Workspace `cargo check --workspace` passes clean. Zero clippy warnings.

**Not yet done**: `freight login --github` / `freight login --provider okta` CLI commands (open browser + local listener). Server side is complete; CLI side is a follow-on task.

### 2026-05-28 — Claude (session 3, cont.)

**`freight-registry` — GitHub OAuth login**

#### `freight-registry` `main` (`a376e06` pushed)

Two new endpoints — no existing endpoints changed:

| Route | Purpose |
|---|---|
| `GET /auth/github[?redirect_uri=<url>]` | Redirect browser to GitHub OAuth authorize page |
| `GET /auth/github/callback` | Exchange code → user info → issue freight token, return HTML page |

**Configuration**: `--github-client-id` / `GITHUB_CLIENT_ID` + `--github-client-secret` / `GITHUB_CLIENT_SECRET`.
Both must be set; omitting both is a no-op (OAuth stays disabled). One without the other logs a warning.

**Account model**:
- OAuth users get `password_hash = "!oauth:github"` (not a valid Argon2 hash)
- `login.rs` detects the prefix → returns `400 "this account uses github login — visit /auth/github"` instead of 500
- If GitHub email matches an existing local user → link OAuth identity, no duplicate created
- New user: `username = github_login` (sanitized), with `_{n}` suffix if taken

**DB**:
- `migrations/0010_oauth.sql` + `migrations_pg/0008_oauth.sql` — `oauth_accounts` table
- `db.rs`: `find_oauth_user`, `link_oauth_account`, `find_or_create_oauth_user`, `get_user_by_email`

**Callback response**: HTML page with the access token + "copy" button + `freight login --token <TOKEN>` instructions.
If `?redirect_uri` was passed to `/auth/github`, the callback redirects there with `?token=<access_token>` appended (for CLI local-listener flows).

**Not yet done**: `freight login --github` CLI command (open browser + local listener). The server side is complete; the CLI side is a follow-on task.

#### Workspace: `851fdaa0`

### 2026-05-28 — Claude (session 3)

**`docify` library API cleanup + Codex accumulated work committed**

#### `docify` `main` (`0c2c002` pushed)

Library API gaps closed (see `TODO.md` — all four items now marked done):
- **`lib.rs` re-exports**: `DocItem`, `DocSet`, `DocExtractor`, `ExtractorRegistry`,
  `DocKind`, `DocLanguage`, `DocMeta`, `DocTag`, `TagKind`, `Access`,
  `extract_file`/`extract_dir`/`extract_dir_with` now accessible as `docify::DocItem` etc.
- **`resolve_refs(item, set) -> Vec<&DocItem>`**: resolves `@see` tag texts to target items
  via exact → suffix → substring match. Strips Rust `[`backtick`]` link syntax.
- **`source_line_range(item, max_lines) -> (usize, usize)`**: 1-based `(start, end)` line
  range of a function's source block, same heuristic as `extract_source` but no allocation.
- **`tui` feature gate**: `ratatui` + `crossterm` are now optional behind `[features] tui`.
  Enabled in `default`. Binary requires `tui`. Library users: `default-features = false`.

Also committed Codex's accumulated-but-never-pushed work:
- `cache.rs` (new): `DocCache` save/load/list DocSets as JSON to `~/.docify/`
- Extractor improvements: `extract/cpp.rs`, `extract/common.rs`, `extract/mod.rs`
- TUI: collapsible tree, source pane, overload dropdown, mouse support (browser.rs)
- Default command is now `docify browse` (no subcommand needed)
- CUDA/Rust/Go integration tests added

#### Workspace: `67ee17fe` (submodule pointer bumped)

No outstanding questions.

### 2026-05-28 — Claude (session 2)

**`freight add` — info pane: keywords + owners; versions panel: dependencies tab**

#### `freight-registry` `main` (`a4f77c8` pushed)
- `migrations/0009_keywords.sql` + `migrations_pg/0007_keywords.sql`: `ALTER TABLE packages ADD COLUMN keywords TEXT`
- `db.rs`: `PackageRow` gains `keywords: Option<String>`; all SELECT queries updated; `publish_version` takes new `keywords: Option<&str>` param
- `publish.rs`: `extract_keywords()` parses `package.keywords` from `freight.toml` inside the tarball; stored as comma-joined `TEXT`
- `packages.rs`: `GET /api/v1/packages/{name}` now returns `"keywords": [...]` array

#### `freight` `master` (`e2e0092` pushed)
- `registry/mod.rs`: `PackageInfo` gains `keywords: Vec<String>` + `owners: Vec<String>`; `PackageRepo` trait gets `fn fetch_owners()` (default: `vec![]`)
- `freight_registry.rs`: `FreightRegistry` implements `fetch_owners()` via `GET /api/v1/packages/{name}/owners`
- `browser.rs`:
  - `VersionTab` enum (Versions | Dependencies)
  - Info pane height = `area.height / 2` (was content-height); shows Tags (keywords in yellow) + Owners (magenta)
  - Versions panel tab header; Dependencies tab shows `dep  @version` for the selected version's deps
  - `t` key toggles tab when Versions pane is focused
  - Detail+owners fetched in one background thread (both returned in `PackageDetail` response)

#### Workspace: `55f168a8` (both submodule pointers bumped)

No outstanding questions.

### 2026-05-28 — Claude

**`freight add` — 3-pane layout + tui-markdown README; removed `freight tui` command**

#### `freight` `master` (1 commit pushed: `556200a`)

- **`src/bin/freight/tui/browser.rs`** — redesigned wide layout (≥100 cols) as 3
  columns: package list (30%) | README via tui-markdown (46%) | Info + Versions (24%).
  Narrow fallback (2-column) unchanged. `WIDE_THRESHOLD` dropped from 150 → 100.
- **Removed `freight tui` command** (`commands/tui.rs` deleted, `Commands::Tui` removed
  from `main.rs`). Scope of TUI: only `add`, `login`, `register`.
- **Removed `freight build --panel`** (`build_panel.rs` deleted, `--panel` flag removed).
- **Removed `admin` feature gate** from `Cargo.toml` (nothing uses it).
- `tui/registry/` code preserved for reference but not compiled.

Workspace pointer bumped.

---

### 2026-05-28 — Claude

**`freight build --panel` — live build progress TUI**

#### `freight` `master` (1 commit pushed: `c018ac9`)

- **New: `src/bin/freight/tui/build_panel.rs`** — full-screen ratatui panel for
  `freight build --panel`. Streams `BuildEvent`s from a background `std::thread` via
  `sync_channel`; no tokio required for this screen.
- **`src/bin/freight/commands/build.rs`** — added `--panel` flag; dispatches to
  `crate::tui::build_panel::run()` with workspace/single-project detection.
- **`src/bin/freight/tui/mod.rs`** — `pub mod build_panel` added; TODO updated.

**Features:**
- Rounded bordered panel with spinner + elapsed time (top-right)
- Coloured event log with auto-scroll (tracks bottom while building, disengages on user scroll; `G` re-engages)
- Keyboard: ↑/↓/j/k, PgUp/PgDn, g/G (top/bottom), q/Esc to quit
- Success: green border, ✓ elapsed, appended summary with binary path
- Failure: red border, compiler diagnostic lines in red
- Exit codes: 0 = success, 1 = build failed, 130 = quit while building

**Tested:** single-project (hello-panel) and incremental (fresh) paths confirmed working.

Workspace pointer bumped.

---

### 2026-05-28 — Claude

**Registry example libraries + tarball extraction fix**

#### `freight-registry` `main` (1 commit pushed: `2052725`)

- **Bug fix: `src/api/publish.rs` — `extract_file` and `extract_dependencies_inner`**
  - Both functions used `?` inside a `for` loop over tar archive entries. The very first entry in `tar -czf . ./` tarballs is `.` (the current-directory marker), whose `Path::file_name()` is `None`. The `?` on that `None` early-returned `None` from the entire function, so **README.md and `freight.toml` were never found in any published package**.
  - Fix: replaced all `entry.ok()?` / `path.file_name()?` with `match … continue` so the loop moves past unreadable or nameless entries instead of aborting.

**Example library packages pushed to `http://localhost:7979`:**

| Package | Versions | License |
|---|---|---|
| `strutils` | 0.1.0, 0.2.0, 0.3.0 | MIT |
| `mathext` | 1.0.0 | Apache-2.0 |
| `usestrutils` | 0.1.0 | MIT |

Verified: versioning (`latest` tracks highest), README served at `/api/v1/packages/:name/readme`, source tarball downloadable with all source files intact, dependency extraction from `freight.toml` inside tarball (`usestrutils 0.1.0` shows `dependencies: {strutils: "0.2"}`).

Example projects at `/tmp/freight-examples/`. Registry still running on `http://localhost:7979`.

Workspace pointer bumped.

---

### 2026-05-28 — Claude

**`[language.proto]` — protobuf code generation**

#### `freight` `master` (1 commit pushed: `018c04e`)

- **New: `src/build/proto.rs`** — `run_protoc()` discovers `.proto` files in `src/`, runs `protoc --cpp_out=<out>` (incremental: skips files whose `.pb.cc`/`.pb.h` are newer), and returns the generated `.pb.cc` files as `SourceFile { lang_key: "cpp" }` entries plus the output dir as an include path.
- **`src/build/mod.rs`** — proto codegen step wired into `build_project_at`, `test_project_at`, and `bench_project_at` (between dep include-dir setup and `build_sources`). `load_project_at` updated to allow proto-only projects (no regular `.cpp` files in `src/`).
- **`src/meta/mod.rs`** — `build_foreign_deps` return type extended from `(Vec<ForeignBuilt>, Vec<ResolvedPkgConfig>)` to include `Vec<PathBuf>` (tool_paths from build-deps). All three call sites updated.
- **`docs/manifest-reference.md`** — new `[language.proto]` subsection with all config keys.

**Supported config keys in `[language.proto]`:**
| Key | Default | Purpose |
|---|---|---|
| `out` | `target/<profile>/proto-gen/` | Output dir for generated C++ files |
| `proto_path` | `src/`, project root | Extra `--proto_path` roots (comma-separated) |
| `grpc` | `false` | Enable gRPC stub generation |
| `grpc_plugin` | `grpc_cpp_plugin` | Path to `grpc_cpp_plugin` binary |
| `extra_flags` | — | Extra flags forwarded verbatim to protoc |

**Not yet done:** CLAUDE.md build pipeline step updated (proto step 5); no example project yet. Consider adding `examples/proto-hello/` to demonstrate the full workflow.

Workspace pointer bumped (`e3ddca9`).

---

### 2026-05-28 — Claude

**Registry clean re-import — zero failures**

#### `vcpkg-converter` `main` (1 commit pushed: `89f588d`)

- **`scraper.rs`** — two fixes for bad historical version strings:
  - `sanitize_version()`: now truncates at first space, `~`, or `+` before the hash-stripping regex. Converts `0.46~alpha` → `0.46`, `2.4.2-c43afa08d~vcpkg1` → `2.4.2`, `2.0.0-beta1+android11~vcpkg1` → `2.0.0-beta1`.
  - `looks_like_version()`: new guard; skips any version that does not start with an ASCII digit after sanitization. Catches `gl2ps` whose historical "version" field was its description ("OpenGL to PostScript Printing Library").
- **`main.rs`** — `Scrape --all-versions` no longer calls `scrape_ports()` first (prevents duplicate latest-version stubs → 409 conflicts on import).

**Registry state:**
- Old DB wiped (`/tmp/freight-registry-test/registry.db`).
- Fresh user `alice` created; new token stored in `~/.freight/credentials.toml`.
- Registry restarted at `http://localhost:7979` (PID in `/tmp/freight-registry-test/server.log`).
- Re-scraped: **23,275 version stubs** (was 23,646 — 371 invalid-version entries eliminated).
- Re-imported: **23,275 total | 23,275 imported | 0 skipped | 0 already existed | 0 failed**.
- Spot-checks: `aubio` now has clean `0.46` version; `gl2ps` only shows `1.4.0`/`1.4.2`.

**Restart command:**
```sh
./target/debug/freight-registry --data /tmp/freight-registry-test serve \
  --bind 0.0.0.0:7979 --base-url http://localhost:7979 \
  --rate-limit-write 100000 --rate-limit-read 100000 \
  > /tmp/freight-registry-test/server.log 2>&1 &
```

Workspace pointer bumped (`4d384e3`).

---

### 2026-05-27 — Claude

**Language examples — all machine-testable ones done**

#### `freight` `master` (4 commits pushed)

- **`f9b190e` examples: add opencl-hello; READMEs for cuda-hello and d-hello; nvcc std map**
  - `examples/opencl-hello/` — new: vec_add + vec_scale via OpenCL runtime API;
    dep declared as `OpenCL = "*"` (resolved via `pkg-config --libs OpenCL`);
    graceful error message when no ICD is loaded
  - `examples/cuda-hello/README.md` — GPU arch table, expected output, feature table
  - `examples/cuda-hello/freight.toml` — added `[language.cuda] std = "c++17"`
  - `examples/d-hello/README.md` — ranges, UFCS, C interop feature table
  - `src/toolchain/template.rs` — nvcc test fixture: add standards map + `std` default
  - `examples/README.md` — added opencl-hello row

- **`40136af` todo: mark OpenCL/CUDA/D examples as done**

- **`2fabaf5` ispc: add ispc-hello example; [language.ispc] target option**
  - `examples/ispc-hello/` — new: vec_add, vec_scale, dot_product; ISPC kernels
    compiled to AVX2 with `[language.ispc] target = "avx2-i32x8"`; C++ host uses
    `extern "C"` declarations instead of auto-generated header
  - `toolchain/builtin/intel/mod.rs` — `ispc_target_h` language_option handler:
    `[language.ispc] target = "..."` → `--target=<value>` flag
  - All 330 tests pass

- **`c6132dd` d-hello: mention gdc as third D compiler option**
  - `gdc` 16.1.1 confirmed working; d-hello builds with gdc/ldc2/dmd

**Tested and working:**
- `freight run` in each example: opencl-hello (build OK, runtime fails — no GPU driver), ispc-hello (all checks passed), d-hello (ldc2 + gdc)

**Language examples status:**
- ✅ CUDA, OpenCL, D, ISPC — all done and documented
- ⏸ HIP (ROCm hardware needed), ObjC/ObjC++ (GNUstep), MSVC (Windows), nvfortran (NVIDIA HPC SDK)

---

### 2026-05-27 — Claude

**VHS demo tapes** — all four recorded and committed to workspace `main`.

Files added in `tapes/` (commit `fda39d1`):
- `freight-new.tape` / `.gif` (960×540) — `freight new demo`, build, run
- `freight-fetch-build.tape` / `.gif` (960×576) — `freight fetch` + `freight build` with `zlib = "1.3.2"` dep
- `freight-add-tui.tape` / `.gif` (1280×720) — `freight add` TUI: search zlib, arrow nav, add; search abseil, add; Esc; `cat freight.toml`
- `freight-doc-tui.tape` / `.gif` (1280×720) — `docify --tui src/` tree nav, Tab to docs panel, `docify src/ --format md`

Notes for Codex:
- Demo files for fetch/add tapes are at `/tmp/demo-fetch/` and `/tmp/demo-tui/` (not committed, easy to recreate)
- `ROD_BROWSER=/usr/bin/chromium` is required for VHS on this machine (system chromium, not vhs-bundled)
- Tape `Type` blocks can't contain special chars (`\`, `$`, `:`, `%`, `.`); workaround is to pre-create project files before the `Show` block

---

### 2026-05-27 — Claude

**Summary for Codex** — all changes pushed, workspace pointers bumped.

#### `freight` `master` (3 commits since last Codex entry)

- **`030f226` fix fetch: substitute `${VERSION}` in upstream_url; paginate search**
  - `dep_cmds.rs`: `fetch_registry_deps()` now calls `.replace("${VERSION}", &concrete)` on `upstream_url` before passing to `fetch_url_dep()`. Fixes `freight fetch` / `freight build` for all vcpkg-imported packages (the all-versions scraper had left `${VERSION}` unsubstituted).
  - `freight_registry.rs`: `search()` paginates with `limit=100` + `offset` (includes Codex's earlier uncommitted work).

- **`1eadf12` tui: Enter on installed package removes it (toggle add/remove)**
  - `install_selected()` checks `self.installed`: if already in `freight.toml`, calls `manifest_remove_dep()` and flips checkbox to `[ ]` with `✗ removed` status.

- **`a564402` tui: sort versions descending (newest first) in Versions panel**
  - Added local `cmp_version()` helper; `version_lines()` reverse-sorts before rendering.

#### `vcpkg-converter` `main` (2 commits)

- **`e4260c9` scraper: fix `${VERSION}` substitution in `scrape_all_versions()`** — root cause of fetch failures; `convert_port()` did the substitution, the historical path didn't.

- **`97446df` scraper: sanitize hash suffixes; expand CMake-computed URL vars**
  - `portfile.rs` — new `expand_url(portfile_src, url, version)`: expands `${VERSION}` and CMake-computed variables (e.g. 7zip's `upstream_version` via `string(REGEX REPLACE)`). Converts CMake `\$` → regex `$` end-of-string anchor. 7zip@26.0 now resolves to `archive/26.00.tar.gz`.
  - `scraper.rs` — new `sanitize_version(v)`: strips trailing git-hash suffixes (e.g. `2017-11-03-c38887c5` → `2017-11-03`). Requires ≥6 hex chars with at least one letter a–f; preserves numeric port revisions (`-1`) and all-digit date suffixes.

#### `docify` `main` (`5973386` — Codex's accumulated work, committed by Claude)

62 tests pass, zero warnings:
- **Extractor improvements**: CUDA qualifier stripping (`__global__`, `__device__` etc.); ISPC qualifiers; `.cuh`; `Access` enum; improved Ada/Fortran/D/Go/Java/Kotlin/Rust/Swift/Zig extraction.
- **HTML output** (`render_md.rs`): multi-page output, per-namespace/class/module pages, cross-reference hyperlinks, `SymbolIndex`.
- **Rich TUI** (`tui/browser.rs`): tree view with overload grouping, source panel, mouse support, search highlighting.
- **LaTeX** (`util/latex.rs`): expanded LaTeX→terminal conversion.
- **New crate**: `crates/libtexprintf` — workspace-local Rust bindings for `bartp5/libtexprintf` terminal TeX rendering (optional `libtexprintf` feature for docify).

**Open items for Codex:**
- `vcpkg-tomls/` re-scraped locally (23,454 stubs with fixed URLs) but not committed — check if it should be tracked or regenerated on demand.
- Registry DB still has stubs with raw `${VERSION}` in `upstream_url`; client-side fix handles it at fetch time but a server-side migration would be cleaner.
- `with-deps` example still can't fully build (7zip cmake patches, Windows-only ports). Not a freight bug.

### 2026-05-27 — Claude

`freight fetch` / `freight build` fixes:

- **Root cause**: vcpkg stubs for historical versions were imported with `${VERSION}` unsubstituted in `upstream_url`. The `scrape_all_versions()` path in `scraper.rs` used `u.clone()` instead of `u.replace("${VERSION}", &entry.version)`, while `convert_port()` (single-version scrape) did the substitution correctly.
- **`freight` `030f226` fix fetch: substitute `${VERSION}` in upstream_url; paginate search results**:
  - `dep_cmds.rs`: in `fetch_registry_deps()`, apply `.replace("${VERSION}", &concrete)` on `upstream_url` before passing to `fetch_url_dep()`. Fixes existing stubs already in the registry without re-import.
  - `freight_registry.rs`: `search()` now paginates with `limit=100` + `offset` (was returning only the first 20 results). Includes the uncommitted pagination work from Codex.
- **`vcpkg-converter` `e4260c9` scraper: fix `${VERSION}` substitution in `scrape_all_versions()`**: prevents future scrape runs from generating stubs with unsubstituted template literals.
- Re-scraped all 23559 version stubs (`vcpkg-tomls/` regenerated with correct URLs). Re-import was not needed since the client-side fix handles the existing registry data.

Tested:
- `freight fetch` with `abseil = "20260107.1"` → fetches `https://github.com/abseil/abseil-cpp/archive/20260107.1.tar.gz`, extracts, writes sentinel.
- `freight build` → CMake configure → 247 targets compiled → link → success.
- `zlib = "1.3.2"` → correctly resolved via system pkg-config (not re-fetched).

Workspace: bumped `crates/freight` + `crates/vcpkg-converter` pointers.

### 2026-05-27 — Claude

`freight add` TUI improvements (all three pushed to `freight` `master`):

- **`e67be07` remove dead templates_dir / load_templates**: `load_templates(path)` ignored its argument; `templates_dir()` searched for an external `toolchains/` directory that no longer exists. Both removed. All callers updated to `load_all_templates()`. `freight add` no longer errors "toolchains directory not found" on lock write.
- **`2bfdf8c` tui: all versions + installed checkboxes**: When a package is selected, a background `lookup()` call fetches all versions and populates the Versions panel (previously only the latest version was visible from search results). Each package row now shows `[✓]` (green) if already in `freight.toml`, `[ ]` (gray) if not.
- **`e353277` tui: Enter adds in-place, Esc closes**: `Enter` now calls `manifest_add_dep()` directly inside the browser, flips the checkbox to `[✓]`, shows a green status message, and keeps the browser open. `Esc` closes. Previously Enter closed the browser and returned a single selection.

### 2026-05-26 — Claude

`freight add` investigation + two bug fixes:

**Bug 1 — `freight add <pkg>` returned wrong (old) version:**
- Root cause: `GET /api/v1/packages/:name` computed `latest` as the first version by `created_at DESC`. After the historical import, old versions appeared first (they were imported after the current latest).
- Fix (`freight-registry` `c4b30cb`): add `cmp_version()` (numeric-segment comparison on `.`, `-`, `_` separators) + `best_version()` that picks the highest non-yanked version. The `search_packages` DB query changed from `ORDER BY created_at DESC` to `ORDER BY version DESC` per package. `abseil` now correctly resolves to `20260107.1` instead of `2019_01_30-1`.

**Bug 2 — `freight add <url>` wrote empty inline table `{}`:**
- Root cause: `manifest_add_dep` in `dep_cmds.rs` built an `InlineTable` for `DetailedDep` but never inserted the `url` field. All other fields (`path`, `git`, `branch`, `tag`, `rev`, `version`, `backend`, `include`, `channel`) were handled except `url`.
- Fix (`freight` `03e53df`): added `inline.insert("url", ...)` before the `git` case.
- After fix: `freight add https://github.com/madler/zlib/archive/v1.3.2.tar.gz` writes `"v1.3.2" = { url = "https://..." }` correctly.

**Known non-bugs:**
- `freight add` displays `via freight.dev` even when using the local registry — because credentials entries with `name = "freight"` have `repo_key()` return `""` by design (so deps are stored without a `repo = "..."` field, making them portable). Functionally correct.
- Lock file write fails in this environment because `FREIGHT_TEMPLATES_DIR` is not set. The dep IS added to `freight.toml` correctly.

### 2026-05-26 — Claude

Changes pushed:
- `vcpkg-converter` `main`: `e0c89cb` `scraper: add --all-versions flag; batch-read historical vcpkg versions via git cat-file`
  - New `scrape_all_versions()` — reads `versions/<x>-/<name>.json`, deduplicates by upstream version string, batch-reads portfile + vcpkg.json via a single `git cat-file --batch` subprocess (stdin written on background thread to avoid deadlock)
  - Writes stubs as `<name>-<version>.toml` (version sanitized: `/` and ` ` → `_`)
  - `Scrape` command gains `--all-versions` flag
  - Tested: 2800 packages · 23559 version stubs written · 3461 skipped (no url)
  - Full re-import into local registry (`localhost:7979`): **23505 imported | 197 skipped (no url) | 2644 already existed | 33 failed** (26379 total)
- `freight-registry` `main`: `d3de5d7` `add --max-packages-per-user limit for non-admin users`
  - `AppState` gains `max_packages_per_user: Option<u32>`
  - `Serve` command gains `--max-packages-per-user` / `FREIGHT_MAX_PACKAGES_PER_USER`; logs limit on startup
  - `Db::count_owned_packages(user_id)` — counts rows in `package_owners`
  - `publish`: when creating a *new* package, non-admins are checked against the cap → 403 with clear message if at limit. Admins and re-publishes (new version on owned package) bypass the check entirely.
- `workspace` `main`: bumped pointers for both submodules.

Verification:
- `cargo build -p vcpkg-scraper` and `cargo build -p freight-registry` both passed with zero warnings.

Notes for next agent:
- The 33 import failures from the historical import were all 409 Conflict (already existed with a different version) — not actual errors.
- The local registry at `localhost:7979` now has 26379 total versions across ~2800 packages.
- `--max-packages-per-user` is not yet set on the running server; it defaults to `None` (no limit). Restart with the flag to enforce it.
- Open question from Codex (mixed registry ownership): `max_diegast` owns 2594 packages, `testuser` owns 50. Admin ownership-transfer path not yet implemented.

### 2026-05-26 — Claude

Registry wiped and re-imported from scratch:
- Old database deleted (`/tmp/freight-registry-test/` wiped).
- Fresh user `max_diegast` created (admin). New token stored in `~/.freight/credentials.toml` for `http://localhost:7979`.
- Server restarted on port 7979 (`--bind 0.0.0.0:7979 --base-url http://localhost:7979`).
- All 2820 stubs re-imported: **1832 imported | 812 already existed (first pass) | 176 skipped (no url) | 0 failed**.
- Verified: `GET /api/v1/packages/abseil` returns `"license": "Apache-2.0"` and full description.
- Verified: `PUT /api/v1/packages/zlib/readme` + `GET` round-trip works.

To restart the server after a reboot:
```sh
./target/debug/freight-registry --data /tmp/freight-registry-test serve \
  --bind 0.0.0.0:7979 --base-url http://localhost:7979 \
  --rate-limit-write 10000 --rate-limit-read 10000 \
  >/tmp/registry.log 2>&1 &
```

### 2026-05-26 — Claude

Changes pushed:
- `freight-registry` `main`: `6394a90` `add license field and PUT readme endpoint`
  - Migration `0008_license.sql`: `ALTER TABLE packages ADD COLUMN license TEXT` (+ Postgres `0006_license.sql`)
  - `PackageRow` gains `license: Option<String>`; all `SELECT … FROM packages` queries updated
  - `publish_version()` now accepts `license`; stored with `COALESCE` so a later publish with no license won't overwrite an existing one
  - `publish.rs`: `license` was already deserialized from the wire format but marked `#[allow(dead_code)]` and discarded — now passed through
  - `GET /api/v1/packages/:name` response now includes `"license"` field
  - **New endpoint:** `PUT /api/v1/packages/:name/readme` — owner or admin auth, accepts raw Markdown body (max 512 KiB), saves via `storage.save_readme()`, audited as `"update_readme"`
- `vcpkg-converter` `main`: `364df81` `registry-import: send description and license from stub`
  - `registry_import.rs`: `publish_stub()` now reads `description` and `license` from the stub `.toml` and includes them in the publish JSON metadata
  - Previously both fields were scraped into stubs but silently dropped on import
- `workspace` `main`: bumped pointers for both submodules.

Verification:
- `cargo build -p freight-registry` and `cargo build -p vcpkg-scraper` both passed with zero warnings.

Notes for next agent:
- The 2644 packages already imported into the local registry at `localhost:7979` do NOT have description or license populated — they were imported before this fix. A re-import (delete + re-import, or a one-time UPDATE query patching the existing rows from the stub files) would be needed to backfill them.
- `PUT /api/v1/packages/:name/readme` exists but the vcpkg import does NOT call it yet — README content for vcpkg packages would need to be fetched from upstream (GitHub etc.) and uploaded separately. See the original design decision: Option B (deferred, per-package manual/scripted upload).

### 2026-05-26 — Codex

Changes made locally:
- Updated `AGENTS.md` to point agents at `chat.md`, matching the existing
  `CLAUDE.md` coordination note.
- Updated `freight add` package browser in `crates/freight/src/bin/freight/tui/browser.rs`:
  - Up/down navigation now crosses page boundaries and refreshes the visible
    package list automatically.
  - Left/right still page explicitly, but now select the edge item on the new
    page.
  - The list title now shows the visible range and total count, e.g.
    `Packages 21-40 of 2644`.
  - The details pane fetches and caches package README text via the registry
    client and renders it in the scrollable details panel.
- Fixed the underlying search result cap in `crates/freight/src/registry/freight_registry.rs`:
  - The registry defaults `/api/v1/search` to 20 results and clamps each request
    to 100.
  - `FreightRegistry::search` now requests `limit=100` pages and follows
    `offset` until it has the full result set.

Verification:
- Ran `cargo build -p freight-core`; it passed.
- Ran `cargo fmt -p freight-core`.
- Ran `cargo build -p freight-core` again after the search pagination fix; it
  passed.

Not pushed yet:
- `AGENTS.md`
- `chat.md`
- `crates/freight` submodule changes

### 2026-05-26 — Claude

Changes pushed:
- `docify` `main`: `6ce99f2` `refactor tui — extract common module (term, theme, widgets)`
  - Split the monolithic `src/tui.rs` into a proper module tree:
    - `tui/common/term.rs`    — `enter_tui()` / `leave_tui()` (raw mode + alternate screen)
    - `tui/common/theme.rs`   — shared colour constants (`COLOR_SEARCH`, `COLOR_BORDER`, …) + `highlight_style()`
    - `tui/common/widgets.rs` — `word_wrap()`, `truncate()`, `render_search_bar()`, `render_hint_bar()`, `render_error_bar()`, `render_empty_panel()`
    - `tui/browser.rs`        — `App`, `run_doc_browser()`, event loop, all render functions (slimmed down to use common)
    - `tui/mod.rs`            — re-exports `run_doc_browser`
  - Matches the same structure already applied to `freight`'s `tui/common/` in the previous session.
  - Zero new warnings; `cargo build` clean.
- `workspace` `main`: bumped `crates/docify` pointer to `6ce99f2`.

Verification:
- `cargo build` in `crates/docify` completed with no warnings.

Notes for Codex:
- **Codex's open question** (mixed registry ownership): No action taken yet. Up to Max whether to add an admin ownership-transfer path before next bulk import. Current state: `max_diegast` owns 2594 packages, `testuser` owns 50.
- `vcpkg-converter` `registry-import` 403-as-resumable-skip and `--dry-run` improvements are still open from Codex's last entry.

### 2026-05-26 — Codex

Changes pushed:
- `docify` `main`: `f9b69c3` `gate clang-only extract helpers`
  - Gated `lang_from_ext` and `extract_file_heuristic` behind the `clang`
    feature so normal builds do not warn about clang-only fallback helpers.
- `vcpkg-converter` `main`: `cea19ea` `clean up converter build warnings`
  - Replaced deprecated `toml_edit::Table::key_decor_mut` usage with
    `key_mut(...).leaf_decor_mut()`.
  - Removed an unnecessary initial assignment in `freight_batch.rs`.
  - Marked parsed-but-not-yet-read metadata fields in `PortSource` and
    `VcpkgFeature` with narrow `#[allow(dead_code)]`.
- `freight` `master`: `89cb586` `clean up freight build warnings`
  - Removed stale imports and dead TUI helper code.
  - Updated ratatui `Table` selection styling to `row_highlight_style`.
  - Removed unused registry TUI client methods.
  - Included `DocDependency.source` in CLI/TUI doc dependency output.
- workspace `main`: `27f0d5d` `update workspace docs and submodule pointers`
  - Replaced the placeholder root `README.md` with a real workspace overview.
  - Updated submodule pointers for the three commits above.

Verification:
- `cargo build` completed with no warnings before the commits were pushed.

Registry import:
- Imported scraped vcpkg stubs from `vcpkg-tomls` into the local registry at
  `http://localhost:7979` using the existing local token.
- Result: `2820 total | 2594 imported | 176 skipped (no url) | 0 already existed | 50 failed`.
- The 50 failures were HTTP 403 because those packages already existed and are
  owned by `testuser`; examples include `7zip`, `abcmake`, `ableton-link`,
  `abseil`, `absent`, and `ada-idna`.
- Registry database `/tmp/freight-registry-test/registry.db` now has `2644`
  packages and `2644` versions. Ownership split: `max_diegast` owns `2594`,
  `testuser` owns `50`.

Suggested next work:
- In `vcpkg-converter`, improve `registry-import` so a 403 for an already-owned
  package can be reported as a resumable skip instead of a failure.
- While there, consider closing the TODO items for `registry-import` progress
  reporting and `--dry-run`.

Open question for Claude:
- Should the local test registry keep mixed ownership (`testuser` plus
  `max_diegast`), or should we add an admin/ownership-transfer path before
  future bulk imports?

### 2026-05-26 — Codex

Local changes, not pushed yet:
- `freight/src/registry/freight_registry.rs`
  - `FreightRegistry::search` now follows registry pagination with
    `limit=100` and `offset`, instead of returning only the registry default
    page of 20 packages.
- `freight/src/bin/freight/tui/browser.rs`
  - The `freight add` browser now works with a 100-package result window so
    scrolling is less page-like.
  - Selection still crosses result-window boundaries automatically, but the
    visible window only shifts when needed.
  - Package titles now show the current result range and total count.
  - README/detail loading is cached and debounced so holding the down key or
    wheel-scrolling through many packages does not synchronously fetch details
    for every transient selection.
  - Search and README requests now run on background threads and report back
    over a channel. The TUI only applies the latest matching response, so stale
    search/readme results are ignored and input/rendering do not block on
    registry I/O.
  - The full search result set is retained in memory; moving between 100-item
    windows no longer re-queries the registry.
  - Search results are cached by repo/query inside the browser. Returning to a
    query reuses already loaded package metadata instead of hitting the
    registry again.
  - Mouse position/clicks now determine focused panel. Wheel and PgUp/PgDn
    scroll the package list, details, or versions panel based on that focus.
  - On wide terminals, versions render in a separate `Versions` panel with its
    own scroll state; narrower terminals keep versions inline in details.

Verification:
- Ran `cargo build -p freight-core`; it passed.
- Ran `rustfmt` on `freight/src/bin/freight/tui/browser.rs`.
- Ran `cargo build -p freight-core` again; it passed.

### 2026-05-27 — Codex

Started on `docify` language-support TODOs:
- `docify/src/extract/cpp.rs`
  - Added `.cuh` to the C++/CUDA-family heuristic extractor extensions.
  - Added C-family accelerator qualifiers to the leading qualifier stripper:
    `__global__`, `__device__`, `__host__`, `__shared__`, `__constant__`,
    `__managed__`, plus initial ISPC qualifiers `task`, `export`,
    `unmasked`.
- `docify/src/extract/mod.rs`
  - Added the same qualifier stripping for C-style display signatures, so
    CUDA qualifiers do not show up as part of the return type.
  - Routed `.cuh` as C++ in the clang-feature extension detector.
- `docify/tests/fixtures/cuda/kernels.cu`
  - Added a small CUDA fixture with a `__global__` kernel and `__device__`
    helper.
- `docify/tests/extract_examples.rs`
  - Added integration coverage that CUDA-qualified functions classify as
    `DocKind::Function` and display without CUDA qualifiers.
- `docify/TODO.md`
  - Marked the explicit CUDA `__global__` classification test item done and
    narrowed the remaining CUDA work to broader semantic coverage.

Verification:
- Ran `cargo test` in `crates/docify`; it passed.

### 2026-05-27 — Codex

Docify TUI tree index update:
- `docify/src/tui/browser.rs`
  - Replaced the flat filtered symbol index with a collapsible tree.
  - Top level is language. Below that, C/C++ groups by file/header, then
    namespace/class scopes where present. Other languages group by module or
    parent scope where available.
  - Group rows show disclosure markers and symbol counts.
  - Click, Enter, or Space toggles a group. Selecting a symbol leaf keeps the
    existing documentation/source detail pane behavior.
  - Filtering auto-expands matching branches so search results remain visible
    without manually opening every parent.

Verification:
- Ran `cargo test` in `crates/docify`; it passed.
- Ran `git -C crates/docify diff --check`; it passed.

### 2026-05-27 — Codex

Docify TUI documentation rendering update:
- `docify/src/tui/browser.rs`
  - Parameters and returns now render as a compact table-style section instead
    of separate prose blocks.
  - Source view now uses lightweight syntax coloring for comments, keywords,
    built-in types, literals, and punctuation.
  - Function signatures in the documentation pane use the same lightweight
    syntax coloring.
- `docify/src/extract/mod.rs`
  - C/C++ `display_signature()` now stays in native C/C++ syntax instead of
    converting to `fn name(...) -> ret`.
  - The native C/C++ display path still strips leading compiler/kernel
    qualifiers like `__global__` and `__device__`.

Verification:
- Ran `cargo test` in `crates/docify`; it passed.
- Ran `git -C crates/docify diff --check`; it passed.

### 2026-05-27 — Codex

Docify TUI scroll/focus follow-up:
- `docify/src/tui/browser.rs`
  - Mouse wheel no longer moves the selected tree row up/down.
  - The tree pane has an independent viewport offset. Wheel and PgUp/PgDn
    scroll the focused pane: tree viewport or detail/source text.
  - Arrow keys still move the selected tree row.
  - Mouse movement/clicks update focused pane and focused pane border.
  - C and C++ now share a top-level `C/C++` tree group.
  - Symbol leaf rows now display only the simple/local name inside their group
    (`mean` under `stats`, not `stats::mean`). The detail pane still shows the
    full qualified name.

Verification:
- Ran `cargo test` in `crates/docify`; it passed.
- Ran `git -C crates/docify diff --check`; it passed.

### 2026-05-27 — Codex

Docify TUI ordering update:
- `docify/src/tui/browser.rs`
  - The symbol list is now sorted by language first, then by group, then kind,
    then name.
  - C/C++ grouping currently uses the source/header file name, per Max's note
    that header-level grouping is good enough for now.
  - Rust grouping uses `::` module prefixes; Ada/D/Go/Fortran use dotted
    prefixes where available; Java/Kotlin/Swift/Zig prefer `meta.parent` and
    then fall back to dotted or `::` prefixes.
  - The list rows now show the group/header after the language so the ordering
    is visible while browsing and filtering.

Verification:
- Ran `cargo test` in `crates/docify`; it passed.

### 2026-05-27 — Codex

Docify math/rendering and binding update:
- Added a new workspace crate, `crates/libtexprintf`, as a small Rust wrapper
  around `bartp5/libtexprintf`.
  - The crate builds without native linking by default.
  - Enabling its `native` feature links `-ltexprintf`, optionally using
    `TEXPRINTF_LIB_DIR` as an extra library search path.
  - The wrapper exposes `libtexprintf::render()` and `RenderOptions`.
  - Calls are serialized with a mutex because the C API uses global render
    settings (`TEXPRINTF_LW`, `TEXPRINTF_FONT`, `TEXPRINTF_ERR`).
  - Input percent signs are escaped before calling `stexprintf`, since the C
    API is printf-style.
- Updated the root workspace manifest to include `crates/libtexprintf`.
- Updated `docify`:
  - `rich-math` now actually runs doc text through `util::latex` in both the
    interactive browser and `render_tui`.
  - Added an optional `libtexprintf` feature that enables `rich-math` and
    routes math blocks through the new crate's native backend when available,
    falling back to docify's built-in renderer on render errors.
  - Cleaned up the TUI parameters/returns table with box borders and padded
    columns. The table now sizes to content and caps the description column so
    it does not stretch across the whole detail pane on wide terminals.
  - TUI function kind labels now render as `func` while the core Markdown
    labels/anchors remain unchanged.
  - TUI detail text now underlines clickable documented references. `See also`
    refs, matching names in prose, and documented type names in signatures can
    be clicked to jump to their declaration in the tree.
  - Heuristic C++ extraction now tracks both class and struct scopes, so
    documented methods are named/grouped under `Namespace::Class::method` or
    `Namespace::Struct::method` even without libclang.
  - C++-looking `.h` headers now route through the C++ extractor instead of the
    C extractor. This fixes `stats::OrderStatistics` members so `median`,
    `percentile`, and the constructor appear under `OrderStatistics` in the
    tree.
  - Class/struct/interface detail pages in the TUI now include a `Type Overview`
    section for documented public functions, documented variables, and parsed
    inheritance when available.
  - TUI index rows now render the symbol name first and the kind label
    right-aligned at the edge of the list pane.
  - Clickable reference resolution no longer falls back across languages. A
    C++ symbol mention will only become a link to a C++ item, preventing
    accidental C++ -> Go links when simple names overlap.
  - C/C++ class/struct items now use their full type path as the tree group path,
    so the type item and its methods sit under the same expandable type group
    instead of as sibling groups.
  - Tree groups can now carry their own documented item. Selecting an expandable
    class/struct/file/module group shows that group's docs in the detail pane,
    while expanding it shows children below. Top-level Doxygen file/module docs
    now live on the tab/group row itself instead of as a separate child item.
  - The source pane now opens the full file and scrolls near the declaration
    line, with line numbers and a marker on the selected declaration, instead
    of only showing the extracted doc/declaration block.
  - Added an overload dropdown in the detail pane. Press `o` to list overloads
    for the selected function/subroutine; click an overload row to jump to it.
  - Added a TODO for replacing/supplementing the coarse cross-language
    `DocKind` enum with language-specific symbol-kind enums. This is a schema
    change and should be coordinated with `freight doc`.
  - Added a native `libtexprintf` Rust smoke test. With the local build in
    `/home/max/downloads/libtexprintf-1.31/src/.libs`, rendering
    `\frac{\alpha}{\beta+x^2}` returns `" α\n────\nβ+x²"`.
  - Exact-output tests for docify's built-in compact LaTeX renderer are now
    disabled when the `libtexprintf` feature is active, because the native
    backend intentionally returns different multiline terminal layouts.
- Added extra extraction examples for CUDA, Rust, Go, and Java in the fixture
  set and integration tests.

Verification:
- Ran `cargo test -p libtexprintf`; it passed.
- Ran `cargo test -p docify`; it passed.
- Ran `cargo test -p docify --features rich-math`; it passed.
- Ran focused `cpp_class_and_struct_members_are_qualified`; it passed.
- Ran focused `doc_example_stats_class_members_are_nested`; it passed.
- Ran `cargo check -p docify --features libtexprintf`; it passed.
- Ran `cargo test -p libtexprintf --features native native_render_sample_output -- --nocapture`
  with `TEXPRINTF_LIB_DIR`/`LD_LIBRARY_PATH` pointing at the local native build;
  it passed and printed the rendered output above.
- Ran `cargo test -p docify --features libtexprintf` with the same native env;
  it passed.
- Ran `cargo check --workspace`; it passed.
- Ran `git diff --check`; it passed.

Follow-up docify TUI update:
- Tree groups now keep a separate source target in addition to an optional
  documentation item. Selecting a file/module/namespace/group with no own docs
  now says there is no documentation, and `Tab` opens source at the nearest
  declaration instead of doing nothing.
- TUI index names and group labels now use kind-aware colors while keeping
  file/module/container rows visually distinct from typed symbols.
- `docify browse` now expands scan roots from local project manifests without
  downloading anything. It reads Cargo/freight/pyproject TOML path deps, Cargo
  workspace members, npm/package.json installed or `file:` dependencies,
  CMake local package/subdirectory hints, Go `replace => ./path`, and editable
  Python requirements. Missing libraries are skipped, so they do not show in
  the browser until present on disk.

Verification:
- Ran `cargo test -p docify --features rich-math`; it passed.
- Ran `cargo check -p docify --features libtexprintf`; it passed.
- Ran `cargo check --workspace`; it passed.
- Ran `git diff --check`; it passed.

## 2026-05-31 — freight-registry: docs, keyword search, seed data

### What changed
- **#keyword / @user search** on website and freight CLI — `#rust` filters by keyword
  (4-pattern exact LIKE match), `@alice` navigates to user profile page.
- **Docs page** (`/packages/:name/docs`) — stores docify msgpack via Storage
  (local/S3, not SQL), GET endpoint transcodes to JSON for web; viewer has
  sidebar with symbol search, kind grouping, and signature/body detail panel.
- **API Docs badge** added to package page.
- **User profile page** (`/users/:username`) — shows avatar + owned packages.
- **Account page** — my packages table, change password (SHA-256 client-side),
  TOTP enroll/disable, API token management.
- **seed.py** — idempotent Python seeder: creates 3 users, 11 packages with
  READMEs in a local data dir. Run with:
  ```
  python3 crates/freight-registry/seed.py --data /tmp/freight-seed
  cargo run -p freight-registry -- --data /tmp/freight-seed serve --base-url http://localhost:7878
  ```
  Credentials: alice/hunter2!  bob/password1  carol/letmein99

### Tested
- `cargo build -p freight-registry` — passes
- Seed script ran successfully; registry shows 11 packages, 3 users

### Pushed
- `crates/freight-registry` — all above, through commit `32ba519`
- Workspace bumped to `80fc429f`

### Uncommitted
- Nothing.

### Questions for next agent
- Graph physics feature is still deferred (intentionally disabled).
- No open questions.

## 2026-05-31 — autonomous: commit workspace settings + Cargo.lock

- Committed `.claude/settings.json` (5 new `git -C *` allow-patterns from /fewer-permission-prompts)
- Committed `Cargo.lock` (rmp-serde + docify dep additions from session work)
- Left `crates/freight/examples/with-deps/freight.toml` (4 dep removals) untouched — origin unclear
- No open PRs on any submodule; all session work is pushed and clean

## 2026-06-03 — Codex: editor-neutral Freight DAP contract

What changed:
- Generalized `freight dap` comments and relay docs away from VS Code-specific wording.
- Added a `freight/dapInfo` custom DAP request that reports `schemaVersion`, supported
  launch/attach requests, Freight config fields, forwarded standard fields, and detected
  native DAP debuggers.
- Made DAP launch/attach/run config reads prefer an editor-neutral `arguments.freight`
  namespace, with backwards-compatible top-level fields still accepted.
- Kept debugger execution as native-DAP passthrough for GDB/cuda-gdb and LLDB adapters.

Tested:
- Ran `cargo fmt -p freight`.
- Ran `cargo test -p freight commands::dap::server::tests --bin freight`; it passed.
- Ran `cargo check -p freight`; it passed with two unrelated LSP warnings.
- Ran `cargo build -p freight`; it passed with the same unrelated LSP warnings.
- Smoke-tested raw DAP frames through `target/debug/freight dap` for `initialize`,
  `freight/dapInfo`, and `disconnect`; all returned valid DAP responses.

Pushed:
- Nothing pushed.

Questions for next agent:
- Consider adding a documented DAP config schema for IDE/MCP adapters once the exact
  MCP surface is chosen.

## 2026-06-03 — Codex: LSP workspace recognition start

What changed:
- Added LSP TODOs for workspace/package recognition and native Fortran support. `fortls` is now
  documented as a temporary/reference passthrough, not the long-term dependency.
- Added `load_workspace_manifest_str()` so LSP diagnostics can parse workspace manifests from
  open editor text.
- `freight lsp` diagnostics now treat `[workspace]` manifests as first-class and validate
  member entries instead of reporting missing `[package]`/target errors.
- `generate_lsp_compile_commands_at()` now detects workspace roots and writes one hidden merged
  backend compile DB for all members under `/tmp/freight/lsp/...`.
- Hidden LSP compile commands now keep include dirs from explicitly resolved Freight dependency
  roots while still filtering broad system include dirs except stdc/stdc++ headers.
- When the editor root is a workspace, watched member `freight.toml` changes refresh the
  workspace compile DB instead of narrowing state to that member.

Tested:
- Ran `cargo fmt -p freight`.
- Ran `cargo test -p freight commands::lsp::manifest::tests --bin freight`; it passed before
  unrelated publish-manifest edits made the binary target fail to compile.
- Ran `cargo test -p freight lsp_include_filter --lib`; it passed with one unrelated
  make-migration test warning.
- Ran `cargo check -p freight --lib`; it passed.
- `cargo check -p freight --bin freight` is currently blocked by unrelated dirty
  `publish.rs` changes referencing missing `PublishPolicy`, `package.publish`, and
  package `include`/`exclude` fields.

Pushed:
- Nothing pushed.

Questions for next agent:
- Remaining LSP work: workspace target inventory for `[lib]`/`[[bin]]`, workspace-wide doc index,
  and native Fortran indexing/completion to replace the fortls dependency over time.

## 2026-06-03 — Codex: LSP workspace targets and docs

What changed:
- Added a `WorkspaceInventory` for `freight lsp` that records workspace member package names,
  member paths, `[[bin]]` targets, and `[lib]` target presence/type.
- Added `freight/workspaceInfo` custom LSP request returning the workspace inventory for editor
  run/debug/build pickers.
- Manifest completions in `[dependencies]` now suggest workspace libraries as explicit
  `{ path = "..." }` dependencies, while binary-only workspace packages are not suggested as libs.
- Workspace member completions are available in `[workspace]`.
- The doc hover index now merges source docs from every workspace member instead of only the
  nearest manifest's `src/` tree.
- Removed the dead `DocIndex::build()` helper after switching to `build_many()`.
- Updated `crates/freight/TODO.md` to mark workspace target inventory and workspace doc-index
  refresh done; explicit path dependency doc indexing remains open.

Tested:
- Ran `cargo fmt -p freight`.
- Ran `cargo test -p freight commands::lsp --bin freight`; it passed.
- Ran `cargo check -p freight --bin freight`; it passed with one unrelated `publish.rs`
  unused-variable warning.
- Ran `cargo test -p freight lsp_include_filter --lib`; it passed with one unrelated
  make-migration test warning.
- Ran `cargo check -p freight --lib`; it passed.

Pushed:
- Nothing pushed.

Questions for next agent:
- Next LSP step is explicit path-dependency doc indexing plus native Fortran symbol support.

## 2026-06-03 — Codex: LSP doc index follows freight doc rules

What changed:
- Updated the LSP doc hover index to use the same package extraction order as `freight doc` TUI:
  `[lib].hdrs` first, then `[lib].srcs`, then `src/`, then package root.
- Added explicit path dependency package dirs to the LSP doc index for single packages and
  workspace members, including dev dependencies.
- Added tests that path dependencies are included in doc indexing and that public headers win
  over private source docs when `[lib].hdrs` is declared.
- Marked the explicit path-dependency doc indexing TODO done.

Tested:
- Ran `cargo fmt -p freight`.
- Ran `cargo test -p freight commands::lsp --bin freight`; it passed with one unrelated
  `publish.rs` unused-variable warning.
- Ran `cargo check -p freight --bin freight`; it passed with the same unrelated warning.
- Ran `cargo check -p freight --lib`; it passed.
- Ran `cargo test -p freight lsp_include_filter --lib`; it passed with one unrelated
  make-migration test warning.

Pushed:
- Nothing pushed.

Questions for next agent:
- Native Fortran indexing/completion remains the main LSP gap now that workspace and explicit
  path dependency docs are indexed.

## 2026-06-03 — Codex: DAP breakpoint path fix for moved examples

What changed:
- Fixed `build::compile::is_up_to_date()` so a `.d` dependency file entry that no longer exists
  marks the object stale. This prevents reused objects from carrying old `DW_AT_name` /
  `DW_AT_comp_dir` debug paths after a project/example directory is moved.
- Added a regression test for missing dependency entries triggering recompilation.
- Rebuilt `examples/cpp/hello`; it recompiled both sources and now emits debug info for
  `/home/max/freight/crates/freight/examples/cpp/hello/src/main.cpp` instead of the old
  `/examples/hello-cpp/...` path.

Tested:
- Ran `cargo fmt -p freight`.
- Ran `cargo test -p freight missing_dependency_entry_triggers_recompile --lib`; it passed with
  one unrelated make-migration test warning.
- Ran `cargo check -p freight --lib`; it passed.
- Ran `cargo check -p freight --bin freight`; it passed with one unrelated `publish.rs`
  unused-variable warning.
- Ran `/home/max/freight/target/debug/freight build` in `examples/cpp/hello`; it compiled 2 files.
- Verified `readelf --debug-dump` shows the current `examples/cpp/hello` path.
- Verified `gdb --batch` can bind a breakpoint at `src/main.cpp:17`.

Pushed:
- Nothing pushed.

## 2026-06-03 — Codex: DAP filters GDB pending-breakpoint noise

What changed:
- Fixed `freight dap` bootstrap waiting so the native adapter's initialize response is consumed
  instead of occasionally leaking back to VS Code after a short timeout.
- Kept GDB DAP's normal `initialized` / `setBreakpoints` / `configurationDone` flow intact and
  filtered only GDB's transient console lines for pending source breakpoints:
  `No source file named ...` and `Breakpoint ... pending.`
- Added DAP frame-helper coverage for command matching and pending-breakpoint output filtering.

Tested:
- Ran `cargo fmt -p freight`.
- Ran `cargo test -p freight commands::dap --bin freight`; it passed with one unrelated
  `publish.rs` unused-variable warning.
- Ran `cargo check -p freight --bin freight`; it passed with the same unrelated warning.
- Ran `cargo build -p freight`; it passed with the same unrelated warning.
- Ran a VS Code-like DAP smoke through `/home/max/freight/target/debug/freight dap` in
  `examples/cpp/hello`; no pending-breakpoint output was relayed, and GDB still emitted verified
  breakpoint events for `src/main.cpp:17` and `src/main.cpp:19`.

Pushed:
- Nothing pushed.

## 2026-06-03 — Codex: DAP stop/disconnect exits promptly

What changed:
- Added an explicit DAP server exit flag so `disconnect` / `terminate` requests consumed inside
  the native-adapter passthrough also make the outer `freight dap` process exit.
- Replaced unbounded adapter `child.wait()` on shutdown with a short graceful drain and kill
  fallback, while still forwarding final adapter output/responses.
- Run mode now handles Stop by killing the spawned `freight run` child and returning a DAP
  `terminated` event instead of waiting for the program to exit naturally.

Tested:
- Ran `cargo fmt -p freight`.
- Ran `cargo test -p freight commands::dap --bin freight`; it passed with one unrelated
  `publish.rs` unused-variable warning.
- Ran `cargo check -p freight --bin freight`; it passed with the same unrelated warning.
- Ran `cargo build -p freight`; it passed with the same unrelated warning.
- Ran a VS Code-like DAP stop smoke through `/home/max/freight/target/debug/freight dap` in
  `examples/cpp/hello`; after `disconnect`, Freight exited in about 49 ms and forwarded GDB's
  disconnect response.

Pushed:
- Nothing pushed.

## 2026-06-04 — Codex: Registry profile, docs, and install pages

What changed:
- Updated `freight-registry` account/profile UI so it no longer fetches or renders active API
  tokens from `/api/v1/me/tokens`; the account page now shows profile, package, security, and
  developer-access sections, with CLI login guidance instead of token inventory.
- Added top-level registry routes for `/docs`, `/docs/`, and `/install`; package source docs remain
  on `/packages/:name/docs`.
- Added a static Freight ecosystem guide and install page, updated registry nav/footer links to
  point at those pages, and moved GitHub links to `freight-app/freight-registry`.
- Added a Docusaurus docs source tree under `crates/freight-registry/docs-site/` with guide,
  install, and publish pages; its build script targets `../static/docs`.

Tested:
- Ran `cargo check -p freight-registry`; it passed.
- Ran `node --check docs-site/docusaurus.config.js`; it passed.
- Ran `node --check docs-site/sidebars.js`; it passed.
- Ran `rg` checks for stale external docs links, removed token UI functions, and the obsolete
  `freight publish-docs` snippet; only backend `/api/v1/me/tokens` routes remain intentionally.

Pushed:
- Nothing pushed by Codex. The `freight-registry` submodule is clean at local commit `86517d8`
  (`config: remove all secrets from config file`) and is ahead of `origin/main` by one commit;
  that commit contains these web/docs changes plus pre-existing Docker/config changes.

Questions for next agent:
- Decide whether to split or push the local `freight-registry` commit as-is. I did not rewrite it.

## 2026-06-04 — Codex: Expanded registry ecosystem docs tabs

What changed:
- Extended the served registry guide at `crates/freight-registry/static/docs/index.html` with tabs
  and sections for `freight.toml`, `config.toml`, DAP, LSP, and Freight's DAG build system.
- Mirrored those topics into Docusaurus source pages:
  `docs-site/docs/freight-toml.md`, `config-toml.md`, `dap-lsp.md`, and `dag.md`.
- Updated the Docusaurus sidebar and intro page to link the new docs.

Tested:
- Ran `node --check docs-site/docusaurus.config.js`; it passed.
- Ran `node --check docs-site/sidebars.js`; it passed.
- Ran `rg` checks to verify the new docs topics appear in the served static guide and Docusaurus
  source.
- The dev server session `29444` is still running; sandboxed `curl` could not connect to
  `localhost:7878`, but the server log showed active localhost browser traffic.

Pushed:
- Nothing pushed.

Questions for next agent:
- Docusaurus dependencies are still not installed here, so `npm run build` has not been run.

## 2026-06-04 — Codex: Cleaned registry docs navigation

What changed:
- Reworked `/docs/` navigation so top tabs are page-level only (`Guide`, `Install`) and the
  sidebar is grouped by Start, Reference, Tooling, and Registry.
- Added a compact topic shortcut grid under the docs intro for `freight.toml`, `config.toml`,
  DAP, LSP, and DAG.
- Grouped the Docusaurus sidebar into the same Start / Reference / Tooling / Registry structure.

Tested:
- Ran `node --check docs-site/sidebars.js`; it passed.
- Ran `node --check docs-site/docusaurus.config.js`; it passed.
- Ran `rg` checks for the new navigation classes and Docusaurus category sidebar entries.

Pushed:
- Nothing pushed.

## 2026-06-04 — Codex: Markdown-first Docusaurus docs with Bun

What changed:
- Made `crates/freight-registry/docs-site/docs/*.md` the docs source of truth and generated
  `static/docs/` with Docusaurus instead of maintaining the long-form docs in hand-written HTML.
- Switched docs tooling to Bun: added `packageManager = bun@1.3.14`, `bun.lock`, and
  `docs-site/README.md` with `bun install` / `bun run build`.
- Removed the npm `package-lock.json` artifact and added `docs-site/.gitignore` for
  `node_modules/`, `.docusaurus/`, `.bun-tmp/`, and local build output.
- Updated registry nav/footer install links to `/docs/install/`; changed the backend `/install`
  route to redirect there and deleted the obsolete hand-authored `static/install.html`.

Tested:
- Ran `bun install`; it completed and saved `bun.lock` after a long dependency-resolution phase.
- Ran `env BUN_TMPDIR=... bun run build`; it generated `static/docs/` successfully from Markdown.
- Ran `cargo check -p freight-registry`; it passed.
- Ran checks confirming `bun.lock` exists and `package-lock.json` is absent.

Pushed:
- Nothing pushed.

Questions for next agent:
- Restart the registry server before testing the legacy `/install` redirect route; the running
  server binary predates that route change. Direct `/docs/install/` works through static files.

## 2026-06-04 — Codex: Created private launch registry repo

What changed:
- Created private GitHub repo `freight-app/freight-registry-launch` for the launch variant:
  https://github.com/freight-app/freight-registry-launch
- Seeded it from the current `freight-registry` checkout into `/tmp/freight-registry-launch`.
- Configured launch clone remotes:
  - `origin`: `git@github.com:freight-app/freight-registry-launch.git`
  - `upstream`: `git@github.com:freight-app/Freight-registry.git`
- Committed the launch seed as `940c16f seed private launch registry`.
- Initial push warned about inherited `target/debug` artifacts, so I rewrote the private launch
  branch history to remove `target/` and `__pycache__/`, then force-pushed the cleaned branch.

Tested:
- Verified with `gh repo view` that `freight-app/freight-registry-launch` exists and has
  visibility `PRIVATE`.
- Verified `git ls-remote origin refs/heads/main` returns `940c16f`.
- Verified `git rev-list --objects main` in `/tmp/freight-registry-launch` has no `target/`,
  `__pycache__/`, or `.pyc` paths.

Pushed:
- Pushed cleaned private launch branch to `freight-app/freight-registry-launch`.

Questions for next agent:
- The private launch clone currently lives in `/tmp/freight-registry-launch`; clone it somewhere
  persistent if ongoing launch work should happen locally.

## 2026-06-04 — Codex: Created public GitHub Pages docs site

What changed:
- Created public repo `freight-app/freight-docs` for the framework/docs website:
  https://github.com/freight-app/freight-docs
- Seeded it from the registry Docusaurus Markdown docs in `/tmp/freight-docs`.
- Configured Docusaurus for GitHub Pages at:
  https://freight-app.github.io/freight-docs/
- Added `.github/workflows/pages.yml` using Bun and GitHub Pages deployment.
- Enabled GitHub Pages for the repo with workflow deployment.
- Updated `freight-registry` nav/footer Docs links to
  `https://freight-app.github.io/freight-docs/`.
- Updated Install links and the legacy `/install` redirect to
  `https://freight-app.github.io/freight-docs/install/`.
- Removed the registry-local Docusaurus source/generated docs that I had added earlier.

Tested:
- Ran `bun install --frozen-lockfile` in `/tmp/freight-docs`; it passed.
- Ran `bun run build` in `/tmp/freight-docs`; it passed.
- Pushed `freight-app/freight-docs` and reran the Pages workflow after enabling Pages; it passed.
- Verified `curl -I https://freight-app.github.io/freight-docs/` returns `HTTP/2 200`.
- Verified `curl -I https://freight-app.github.io/freight-docs/install/` returns `HTTP/2 200`.
- Ran `cargo check -p freight-registry`; it passed after the registry route/link changes.

Pushed:
- Pushed `freight-app/freight-docs` main branch.
- Did not push the `freight-registry` link/redirect cleanup.

Questions for next agent:
- The docs source clone currently lives at `/tmp/freight-docs`; clone it somewhere persistent for
  ongoing docs work.
