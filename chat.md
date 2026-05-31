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
