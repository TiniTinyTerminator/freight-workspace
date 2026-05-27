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
