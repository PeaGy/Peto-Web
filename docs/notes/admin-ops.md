# Admin and operations notes

Scope: Backend layout and ops tools, the `/admin` dashboard, configuration and the database.

Moved out of `CLAUDE.md` on 2026-11-12 (G0.2). Write new notes for this area here, not in `CLAUDE.md`. Current behaviour comes first, then the dated log, newest first.

# Current behavior

### Backend layout (2026-10-01)

Operational tools live in `backend/ops/`; see `deploy/OPERATIONS.md`. `ops.backup` requires all writers stopped
(`--offline`), verifies archives and only restores into a new directory. Archives cover SQLite/uploads, not credentials.
`ops.report` aggregates existing timing/provider usage logs; optional rates are operator-supplied, missing usage is
not zero cost. Optional read-only DB aggregates cover Agent/TTS quota, not invoices. Startup configures the `peto_web`
INFO logger once; new timing fields carry only categorical outcomes, never user text/owner identifiers.
The checked-in systemd backup timer is a template and must not be described as already enabled on the VPS.

See `backend/README.md` for the current directory map. `main.py` is the stable `uvicorn main:app` entry point;
`core/lifespan.py` owns startup. Feature routers and services live under `features/`, shared attachment/time/search
tools under `shared/`, SQLite schema and domain queries under `storage/`, and persona blocks under `prompts/`.
The old flat module names used in historical notes below refer to these feature modules; do not reintroduce flat shims
or import the bootstrap from a feature. `xai_auth.py` remains only as the existing `python -m xai_auth` CLI entry.

### Admin dashboard (`/admin`)

Built 2026-10-11. The owner chose an owner-only page with its own URL (not a Settings section) and picked the
"Tổng quan" mockup (four stat tiles, stacked daily cost by provider, outcome and p50/p95 cards, per-model table) over a
dense ledger and a narrative report. No per-account view, by the owner's call; Agent is included.
- **Data.** Logs only reach journald, so `core/usage_events.py` appends content-free rows to `usage_events` at the
  existing `model_usage` (`ai/xai.py`), `chat_timing` and `agent_timing` points: kind `call` or `turn`, surface,
  purpose (`chat`, `side` for title/memory/summary calls, `agent`, `compact`), service, catalog key and slug, outcome,
  timings, tokens. No owner, conversation id or text. `record` is synchronous, I/O-free and never raises; a lifespan
  task flushes every 5 s (shielded), prunes rows older than 90 days daily, and flushes on shutdown. The queue is
  bounded (oldest dropped and counted). Tests, benchmarks and ops commands never start it, so it stays off there.
  `get_provider` sets `provider.catalog_key`. Claude now reports cache reads as `input_tokens_details.cached_tokens`
  (summed over `pause_turn` requests) and Agent `done` usage carries `cached_tokens`; the CLI reads only
  `input_tokens`/`output_tokens`. No backfill command from journald exists yet.
- **API.** `GET /api/admin/overview?range=24h|7d|30d|90d` (`features/admin/`), `Cache-Control: private, no-store`.
  Non-owners and anonymous visitors get 404 before the range is validated. `stats.summarize` is pure: local-midnight
  day buckets (hourly for 24h) in `PETO_DEFAULT_TIMEZONE`, nearest-rank p50/p95 over completed turns only (first text
  over all turns), outcomes grouped complete/stopped/error/timeout/other, previous-period comparison only when data
  covers it. Missing tokens or prices are `null`, never 0; a provider with calls but no priced call gets `null` in
  `by_service`. Active accounts are one count from user messages plus Agent usage days.
- **Prices.** `PETO_COST_RATES_FILE`, same JSON and validation as `ops.report --rates` (slug → input/cached_input/output
  USD per million), reread on mtime/size change. Missing cached tokens price as uncached and are flagged. Grok is
  not in the rates file: since 2026-10-22 each xAI call stores xAI's own `cost_in_usd_ticks` (`usage_events.cost_ticks`,
  1 USD = 10^10 ticks, after cache discounts, tool calls included), which `stats.call_cost` uses for service `xai`
  (never `byok`); older rows stay "chưa có giá". An optional `long_context`
  tier (`threshold` plus the three prices) prices a whole call whose prompt, cache tokens included, exceeds the threshold
  (OpenAI >272K, Haiku 5.5 >100,000; `ops.report.token_cost` is shared). Claude cache writes (`cache_write_tokens`
  column, added to existing tables at startup) add 0.25 × input price, Anthropic's 5-minute write premium. A dated
  example file is in `deploy/OPERATIONS.md`.
- **Frontend.** `AppView` gained `admin`; `/admin` is served by the static fallback. `features/admin/AdminDashboard.tsx`
  is a lazy chunk mounted only while open; the account menu shows "Quản trị" only when `/api/auth/me` returns
  `is_owner`, and a non-owner on `/admin` is replaced to `/`. Charts are hand-written SVG measured to real width; the
  three provider colours passed the dataviz CVD validator on Peto's light and dark surfaces. Refetch keeps the old
  frame dimmed. The chosen range persists in `peto-admin-range`.
- **Tests.** `backend/tests/test_admin.py` (access, empty data, recorder privacy/overflow/failure/prune, chat and Agent
  rows, statistics, rates file), `test_claude.py` cache reads, `test_static_files.py` paths; frontend
  `AdminDashboard.test.tsx` and two `App.test.tsx` cases. A real-browser run against a mock backend with seeded events
  checked menu entry, F5/Back, tooltip, 90-day coverage, a new chat turn appearing after the flush, phone layout and
  the regular-account redirect.

### Security headers (`core/security_headers.py`)

Every response, including static pages and SSE, gets `X-Content-Type-Options: nosniff`, `Referrer-Policy:
strict-origin-when-cross-origin`, `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'` (enforced;
the app never frames itself, printing uses a popup). The full CSP is `Content-Security-Policy-Report-Only`: nothing is
blocked, browsers report to `POST /api/csp-report`, which logs only `csp_violation directive=… blocked=<origin or keyword>
page=/<first path segment> mode=…` (no full URL, query, ids or samples; 16 KB body cap; at most 120 lines a minute per
process). Inline scripts in `index.html`/`404.html` are allowed by SHA-256 hashes computed from the served files and
refreshed when they change, never `'unsafe-inline'`. `'unsafe-eval'` is allowed because PixiJS 6 (Live2D) throws without
it; dropping it needs `@pixi/unsafe-eval` before the CSP is enforced. `script-src` also allows
`https://static.cloudflareinsights.com`: Cloudflare injects its Web Analytics beacon into every page served through
the proxy (its data goes to `cloudflareinsights.com`, covered by `connect-src https:`). `connect-src` allows any `https:` because own-key
voice and hearing providers are called from the browser, custom base URLs included. Middleware is pure ASGI (headers only,
bodies stream untouched).

### Configuration

`core/config.py` is where environment variables are read. Every numeric knob goes through
`_env_int` / `_env_float`, which clamp to a min/max so a bad value degrades instead of
crashing. When adding a setting: declare it in `core/config.py` **and** document it in
`.env.example`. Two exceptions exist: `XAI_API_KEY` is read directly in `ai/xai_auth.py`, and
`PETO_VOICE_WORKER_TOKEN` is read on every worker request in `features/voice/api.py` (see the voice relay below).

`XaiAuth` prefers OAuth tokens (`backend/data/xai_tokens.json`), refreshes them on expiry,
and falls back to `XAI_API_KEY` if refresh fails or no token file exists.

### Database

aiosqlite, WAL mode, connection per operation. `init_db()` creates tables with
`CREATE TABLE IF NOT EXISTS` and does schema upgrades **manually** via `PRAGMA table_info`
plus `ALTER TABLE` — there is no migration framework and no version table. Add a column the
same way, preserving existing rows. Every backend connection is opened by `storage.connection.connect()`, which turns
on `PRAGMA foreign_keys` when the connection opens (SQLite has it off by default, per connection, and ignores it inside
a transaction) and sets a 5-second busy timeout. Never open `aiosqlite.connect` elsewhere or toggle the pragma by hand;
`tests/test_sqlite_connection.py` scans for both. The one exception is `init_db()`, which opens
`connect(foreign_keys=False)`: rebuilding a table with `DROP TABLE` while foreign keys are on cascades into every child
row (the `users` rebuild would wipe `user_avatars` and `player_favorites`). The sync `ops/` tools use `sqlite3`
directly; `ops/purge_guests.py` turns foreign keys on itself.

Tables: `conversations`, `messages`, `attachments`, `users`, `user_profiles`, `user_avatars`,
`imagine_jobs`, `imagine_images`, `imagine_requests`, `agent_devices`, `agent_usage`, `voice_usage`,
`companion_memory_entries`, `companion_memory_state` (`companion_memories`, the old one-line notes, stays empty after the
startup migration; see "Memory (Brain)")
(`features/voice/cloud.py` also creates its own `speech_budget` on first use). `users` is the only place mapping
a web account to a Discord ID.
`conversations.mode` (`chat` or `companion`) was added with the same manual migration; older rows
default to `chat`. `conversations.persona` (`assistant` or `roleplay`) was added the same way; older rows default to
`assistant`. Since 2026-10-18 only old conversations carry `roleplay` (read-only), and `roleplay_consents` is no longer
created (old databases keep it, unused).

# Dated log (newest first)

## CSP: Cloudflare Web Analytics beacon (2026-11-13, branch `csp-cloudflare-insights`)

First production read after deploying G3.4 and G3.2 (`8838767`): enforced headers present through Cloudflare on `/`,
`/chat/…`, `/docs/` and `/api/health`; the only `csp_violation` lines were `script-src-elem
blocked=https://static.cloudflareinsights.com` on `/`, `/docs`, `/download` and the 404 page. Cloudflare injects that
script at the edge, so the local stack never saw it; it is now allowed in `script-src`. No errors in the journal since
the deploy. Not yet browsed live while signed in: Chat, Companion (Live2D, player), Imagine.

## Security headers, CSP report-only (G3.4) (2026-11-13, committed on branch `g3.4-security-headers`, not deployed)

Audit package G3.4; current behaviour is under "Security headers" above. Checked with a local production-like stack
(the backend serving `frontend/dist`, mock provider, temp data, a seeded test account): Chat (link chips, the `__sodo__`
diagrams, a table, Word and slide previews), Companion (Live2D stage, settings, a message, the YouTube player playing a
pasted link with `iframe_api` and the embed), Imagine (a mock image), Docs (index and an article), Download and the 404
page produced no report after `'unsafe-eval'` was added for PixiJS; a deliberate image from `example.org` produced the
expected `csp_violation directive=img-src blocked=https://example.org page=/chat mode=report` line. Before enforcing:
read the production journal for `csp_violation` for a while, then decide on `@pixi/unsafe-eval` and on narrowing
`connect-src`. Tests: `tests/test_security_headers.py` (headers on pages, API and SSE; streaming intact; hashes follow a
new build; content-free report logging for both report formats; size, parse and rate caps; the real app).

## One SQLite connection helper (G3.1) (2026-11-12, committed on branch `g3.1-sqlite-connect`, not deployed)

Audit package G3.1. `storage.connection.connect()` passes a `sqlite3.Connection` subclass as `factory` to
`aiosqlite.connect`, so `PRAGMA foreign_keys=ON` runs before any transaction, plus `timeout=5.0` (the sqlite3
default, now explicit: `busy_timeout` 5000 ms). The ten hand-written `PRAGMA foreign_keys=ON` lines in async code are
gone (`features/chat/conversations.py` ×2, `storage/avatars.py`, `storage/chat_turns.py` ×2, `storage/conversations.py`
×2, `storage/documents.py` ×2, `storage/imagine.py`); `features/voice/cloud.py` now opens through `connect(path=DB_PATH)`
(the parameter keeps its tests' separate speech-budget file working). `ops/purge_guests.py` keeps its own pragma.

Every `DELETE` on a parent table, checked before the change:
- `conversations` (`storage/conversations.delete_conversation`) and `chat_documents` (`storage/documents.delete_document`),
  and `messages` in `features/chat/conversations.py`: foreign keys were already on there; unchanged.
- `messages` in `storage/cards.py` (deleting one Companion message): foreign keys were off, so its `chat_lineage` row
  stayed behind; it is now removed with the message, which is what the lineage table is for.
- `imagine_jobs` (`storage/imagine.py`, three delete paths): the old pragma came after `BEGIN IMMEDIATE`, where SQLite
  ignores it, so it never took effect. Each path already deletes `imagine_images` by hand, so the result is the same.
- `projects` (`storage/projects.delete_project`): foreign keys were off; the explicit `DELETE FROM project_files` stays,
  and the cascade now does the same.
- `users`: only `ops/purge_guests.py` (already on) and the schema rebuild in `init_db` (kept off, see above).
- No `INSERT OR REPLACE` touches a parent table (the only one is `chat_contexts`, a child). Inserts of child rows whose
  parent is missing now fail with `IntegrityError` instead of leaving orphans. Checked: project files, Chat messages and
  Companion summaries check the parent in the same transaction; generated images are saved while their job is
  `queued`/`running`/`saving`, which `delete_imagine_job` refuses to delete (a failed insert also removes the file);
  avatars and favourites belong to an owner that `upsert_user` created at sign-in.
- Existing orphan rows in a production database are not checked or removed by this change (`PRAGMA foreign_key_check`
  on the VPS would list them). 2026-11-13: the owner ran it on a backup copy of the VPS database: 0 orphan rows.

Tests: `tests/test_sqlite_connection.py` (5): pragmas on every connection, still on inside `BEGIN IMMEDIATE`, an orphan
favourite is rejected, a source scan for stray `aiosqlite.connect` / `PRAGMA foreign_keys`, the old-`users` rebuild
keeps avatar and favourite rows (fails if `init_db` opens with foreign keys on), and a project delete cascades its files.
