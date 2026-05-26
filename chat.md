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
