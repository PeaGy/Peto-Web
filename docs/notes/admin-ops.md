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
same way, preserving existing rows. Note that `PRAGMA foreign_keys=ON` is set per connection
where cascade deletes matter (SQLite has it off by default).

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
