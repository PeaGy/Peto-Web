# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Peto Web is a private chat UI for "Peto", a character that also exists as a Discord bot
(`Tracen Jukebox`) in a **separate repository**. This web app is deliberately independent:
its own database, its own xAI token file, its own persona prompt. The only link back to the
bot is a read-only memory gateway (see below).

Stack: FastAPI + SQLite (aiosqlite) backend, React 19 + Vite frontend, xAI Grok via the
Responses API. Registration is **open**: Discord, Google, or guest — there is no
allowlist.

## Language convention

Agent/CLI planning context is recorded in [PETO_AGENT_PLAN.md](PETO_AGENT_PLAN.md).
The clarified direction is a Windows CLI executing local project tools, with VPS
authentication, model calls and orchestration. Docker is optional; web Work is later scope.
It distinguishes agreed direction from open implementation choices and does not
authorize deployment. Consult it when continuing Agent/CLI discussions or work.

**Every comment, docstring, log message, error message, and user-facing string in this
codebase is written in Vietnamese.** Keep it that way when adding code — an English error
string would be visibly out of place in the UI. Identifiers, type names and this file stay
in English.

## Commands

Python 3.12+ (the checked-in venv runs 3.14). Vite 8 requires Node >= 22.12 to build.
The venv lives at the repo root; paths below are Windows — on the VPS use `.venv/bin/python`.

```bash
# Backend dev server (terminal 1)
cd backend && ../.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000

# Frontend dev server (terminal 2) — proxies /api to 127.0.0.1:8000, so no CORS setup
cd frontend && npm run dev                       # http://localhost:5173

# Backend tests (mock provider + temp DB; never touches real data)
cd backend && ../.venv/Scripts/python.exe -m pytest
cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_chat.py
cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_chat.py::test_name
cd backend && ../.venv/Scripts/python.exe -m pytest -k "imagine and not delete"

# Frontend tests and build
cd frontend && npm test                          # vitest run
cd frontend && npx vitest run tests/App.test.tsx
cd frontend && npx vitest run tests/App.test.tsx -t "partial test name"
cd frontend && npm run build                     # tsc -b && vite build -> frontend/dist

# xAI login (run once on the machine hosting the server; only for PETO_AI_PROVIDER=xai)
cd backend && ../.venv/Scripts/python.exe -m xai_auth login    # or: status | logout
```

Set `PETO_AI_PROVIDER=mock` to work on the UI without network calls or xAI quota. The mock
provider recognizes two magic substrings in a message for testing: `__error__` raises a
provider error, `__slow__` streams very slowly to exercise timeout/cancel paths.

## Architecture

### Two run modes

- **Dev = two processes.** uvicorn serves the API; Vite serves the UI and proxies `/api`.
- **Production = one process.** `static_files.mount()` serves `frontend/dist` from the
  backend itself, so the VPS needs one port for Cloudflare Tunnel and no nginx. It is a
  no-op when `dist` does not exist, which is why dev is unaffected.

Its catch-all route `/{full_path:path}` **must be registered after every API route** — it
is the last statement in `main.py`. Move it earlier and API 404s start returning
`index.html`. The handler also explicitly rejects paths starting with `api/` as a second
line of defense, and blocks path traversal by resolving under `static_dir`.

The index page is not served verbatim: the handler inserts `og:image` (plus alt text)
from `app_identity.get_app_identity()` — the bot's Discord CDN icon, already the absolute
URL Open Graph requires. That keeps the domain out of the build and makes link previews
follow the bot icon. The other preview tags are static in `frontend/index.html`; crawlers
such as Discordbot never run JS, so they must stay in the HTML. Because the home page now
awaits `get_app_identity`, that function must never raise.

### Identity and data isolation

`owner` is the single tenancy key, formatted `discord:<id>` (`config.owner_key`). Every
query in `db.py` takes `owner` and filters on it **in SQL** — there is no "load then check"
path. Knowing someone else's conversation id gets you a 404.

The server never accepts a Discord ID from the browser. `auth.py` exchanges the OAuth code
server-side, calls `/users/@me` itself, and discards the Discord access token immediately
(nothing stored, nothing sent to the client). The session is an `itsdangerous` signed
cookie holding only the owner key.

There are three ways in, all in `auth.py`: Discord OAuth, Google OAuth, and `POST
/api/auth/guest`, which mints a `guest:<uuid>` owner with no external account behind it.
`owner_key(provider, external_id)` builds every owner; `provider_from_owner` is what
`session_owner` uses to reject a signed cookie carrying a malformed key.

The allowlist was **deliberately removed** — anyone who can reach the deployment can use
it and spend the server's AI quota. That was the owner's explicit call after being shown
the cost; do not reintroduce a gate unless asked. `tests/test_auth.py` asserts
`config.ALLOWED_DISCORD_IDS` no longer exists so a well-meaning revert gets caught.

Only `discord:` owners carry a Discord ID, so `discord_id_from_owner` returns `""` for
Google and guest accounts and `main.py` skips the memory gateway entirely for them. That
is what keeps open registration from exposing members' long-term memory.

### AI provider abstraction

`ai/base.py` defines `ChatProvider.stream()` — an async generator yielding text or
`StreamChunk` values (`thinking`, `search`, `sources`). Search progress stays transient;
source metadata is persisted with the assistant message, independently of answer text.
Nothing outside `backend/ai/` knows which provider is active. To add one: write a module in
`backend/ai/`, register it in `_PROVIDERS` in `ai/__init__.py`, set `PETO_AI_PROVIDER`.
Routes, DB and rate limiting need no changes. `xai` is imported lazily so running `mock`
does not require the `openai` SDK.

Providers must raise `ProviderError` for anything the user should see; the message is shown
verbatim in the UI, so it must be written in Vietnamese and be user-appropriate. Anything
else propagates and gets logged as an unexpected error behind a generic message.

### Chat request lifecycle (`POST /api/chat`)

This is the most intricate part of the codebase. The endpoint returns a `StreamingResponse`
of SSE events: `meta` then many `delta` then a terminal `error` or `done`.

Order of operations inside `event_stream()`, and why:

1. `admission.slot(owner)` wraps the whole turn. Cooldown and queue rejection happen
   **before anything is written to the DB**, so a throttled request leaves no orphan
   message. Cooldown is only recorded for requests actually admitted.
2. Conversation ownership is re-checked *inside* the slot — the conversation may have been
   deleted while the request sat in the queue.
3. All SQLite writes are wrapped in `anyio.CancelScope(shield=True)`. Without the shield,
   the `StreamingResponse` cancel scope aborts the persistence work when the user closes the
   tab, and the message is silently lost.
4. Attachments are written to disk and DB together; on failure the already-written files
   are deleted (`attachment_lib.delete_files`) before re-raising.
5. Streaming failures of any kind (timeout, provider error, disconnect) still persist the
   text collected so far, marked `status="incomplete"`. The UI renders that marker. Never
   change this to drop partial output.
6. Retry is deliberately limited to **exactly one** attempt, and only when
   `effort == "low"` *and* no text has been emitted yet — mirroring how the Discord bot
   caps retries.

A new conversation is also named here. The cut-from-first-message title is only a
fallback: the first turn starts a second, tiny provider call (`titles.suggest_title`)
**concurrently** with the answer and overwrites the title before the stream ends — the UI
refreshes the sidebar right after `done`, so no extra SSE event is needed. `titles.resolve`
caps the wait so a slow title never holds the turn, any failure keeps the fallback, and a
message with no text (attachments only) skips it since the title call cannot see images.
The mock provider recognises the request by `titles.TITLE_MARKER`; provider spies in tests
must filter it out or they capture the title call instead of the chat call.

`effort` is `auto` by default and resolved by `ai/routing.py`, which keyword-matches the
user text (math/technical markers give `medium`, multi-step reasoning markers give `high`).
Each level has its own timeout in `config.RESPONSE_TIMEOUTS` (180/300/480s).

`mode` is `chat` by default; `companion` comes only from the Companion tab. `_resolve_mode`
rejects anything else with a Vietnamese 400. A companion turn is forced to `effort="low"` and
`web_search="off"`, refuses attachments, skips the title call, and `_build_system_prompt` appends
`persona.COMPANION_PROMPT` last (one or two short English sentences). Conversations store their
`mode` and a turn must match the conversation's mode; `list_conversations` only returns `chat`
ones, and `GET /api/companion` returns the latest `companion` thread with its recent messages.

### Frontend SSE reader

The endpoint is POST, so `EventSource` cannot be used. `src/api.ts` does the framing by
hand: `fetch`, then `response.body.getReader()`, split on a blank line, parse the `data: `
line. If you add an SSE event type, update `ChatEvent` and `ChatHandlers` in `api.ts` as
well as the emitter in `main.py`.

### Tool calling

The tool loop lives **inside the provider** (`ai/xai.py`), not in the route. The provider
sends `TOOL_SCHEMAS`, runs the loop itself with `store=false` (conversation state is kept
in the `input` array rather than on xAI servers), and yields only assistant text upward.
Limits: `MAX_TOOL_ROUNDS = 3`, `MAX_TOOL_CALLS = 8`; exceeding either ends the turn with a
clear message instead of looping.

`chat_tools.execute_tool` is a hard-coded allowlist keyed by tool name. It never evals a
name or arguments produced by the model, caps the argument string length, and rejects
unknown parameter keys. Currently the only tool is `get_current_datetime`.

Web search is a separate native xAI tool, executed on xAI rather than by
`execute_tool`. Chat accepts `web_search: auto | on | off`. Auto exposes search and
lets the model decide; off omits the tool; on exposes only web search in the first
request with `tool_choice=required`, then checks for search completion or sources.
`PETO_WEB_SEARCH_ENABLED=false` disables it globally. Native search uses the service's
default bounds and the existing chat timeout; do not confuse the local clock-tool
round limit with native search calls. Do not automatically retry a timed-out turn once
search activity has been observed, or a forced search turn.

`web_search.py` validates HTTP(S) source URLs, removes duplicates and bounds the list.
Extract sources from tool outputs or URL annotations, never by scraping model prose
for links. Persist them in `messages.sources`, return them in history, and include them
as clearly marked old references in the next model input. Frontend `WebSources.tsx`
renders source links without downloading favicons; SSE `search` and `sources` events
flow through `api.ts` and stay separate from `delta` and `thinking`.
The chat UI always starts in auto mode. `ComposerMenu.tsx` puts attachments and the
auto/off switch under a plus button next to effort; it does not expose the API's forced
`on` mode. Close the menu on Escape, outside interaction, tab changes or streaming.

### Date and time

The **server clock** is the source of truth. The browser supplies an IANA timezone name
with every chat turn; `chat_tools.resolve_browser_timezone` validates it via `zoneinfo` and
falls back to `PETO_DEFAULT_TIMEZONE` with a logged warning when it does not resolve. It
used to return a 400, which meant a phone reporting something like `GMT+7` could not chat
at all — and sending *no* timezone already fell back, so the strict path was punishing the
better-informed case.

`get_current_datetime` stays strict on purpose: there the model asked for one specific zone,
so a bad name must surface as a tool error rather than silently becoming Vietnam time. `chat_tools.time_context()` is appended to the system prompt on **every**
model call, including when an old conversation is reopened or a queued request finally
runs, so "today" is always current. The `tzdata` dependency is what makes this behave
identically on Windows and Linux.

### Attachments

`attachments.py` validates by **magic bytes first**, then declared MIME / extension. A file
claiming to be an image but failing `sniff_image_mime` is rejected outright. Images become
data URLs for the model. `document_reader.py` reads PDF text with page labels, DOCX body
paragraphs/tables, and UTF-8/UTF-16 text in a cancellable AnyIO worker process. PDF scans
are NOT OCRed; encrypted/broken/oversized documents retain honest reading status.
Do not promise image/chart/layout understanding for PDF/DOCX or legacy .doc support.

The `attachments.document` JSON cache stores text plus version/status/notice and counts.
`_public_attachment` exposes only the status metadata, never text or disk paths. Read new
documents inside admission, before shielded writes; emit `reading` SSE without treating it
as acceptance. `meta` acknowledges persistence. Legacy files are lazily cached with an
owner-filtered UPDATE, at most MAX_ATTACHMENTS total reads per turn including new files.
`_to_chat_messages` applies MAX_DOCUMENT_CONTEXT_CHARS, newest message first and shared
between files in that message. Always tell the model when text is missing/truncated.
PDF parsing has page/decompression/time limits; DOCX ZIP/XML has size limits and rejects
DTD/external entities. Dependencies: pinned pypdf and defusedxml in requirements.txt.

Only the `MAX_HISTORY_IMAGES` (default 4) most recent images are re-sent to the model;
older ones degrade to a text placeholder. This is computed twice — in
`main._to_chat_messages` (which decides what to read off disk) and in
`ai/xai._recent_image_keys` (which decides what to send). Keep them consistent.

### Imagine (image generation)

Fully separated from chat: its own router (`imagine_api.py`), its own REST call to
`/v1/images/generations` (`ai/imagine.py`), its own `imagine_jobs` / `imagine_images`
tables. Chat **intentionally has no image-generation tool**, so Peto never draws when the
user was just talking.

The request is synchronous (no background job): generate under
`asyncio.timeout(IMAGINE_TIMEOUT_SECONDS)` covering the whole batch, then persist. If
persistence fails partway, files and the job row are rolled back. Returned image bytes are
format-sniffed before being written. It uses the same `admission` limiter under a separate
key (`imagine:<owner>`) so image jobs and chat do not consume each other's cooldown.

### Configuration

`config.py` is where environment variables are read. Every numeric knob goes through
`_env_int` / `_env_float`, which clamp to a min/max so a bad value degrades instead of
crashing. When adding a setting: declare it in `config.py` **and** document it in
`.env.example`. One exception exists — `XAI_API_KEY` is read directly in `xai_auth.py`.

`XaiAuth` prefers OAuth tokens (`backend/data/xai_tokens.json`), refreshes them on expiry,
and falls back to `XAI_API_KEY` if refresh fails or no token file exists.

### Database

aiosqlite, WAL mode, connection per operation. `init_db()` creates tables with
`CREATE TABLE IF NOT EXISTS` and does schema upgrades **manually** via `PRAGMA table_info`
plus `ALTER TABLE` — there is no migration framework and no version table. Add a column the
same way, preserving existing rows. Note that `PRAGMA foreign_keys=ON` is set per connection
where cascade deletes matter (SQLite has it off by default).

Tables: `conversations`, `messages`, `attachments`, `users`, `user_profiles`,
`imagine_jobs`, `imagine_images`. `users` is the only place mapping a web account to a Discord ID.
`conversations.mode` (`chat` or `companion`) was added with the same manual migration; older rows
default to `chat`.

### User profile (Settings → Hồ sơ)

`profile_api.py` stores a self-written profile per owner in `user_profiles` — kept apart
from `users`, which is overwritten from Discord/Google on every login: full name, what
Peto should call them, an occupation code from a fixed server-side list, and free-form
instructions (1500 chars). `main._build_system_prompt` re-reads it on **every** turn and
appends `persona.build_profile_context` after the memory block, so an edit applies to the
very next message. Instructions are fenced with `USER_INSTRUCTIONS_START/END`, copies of
those markers are stripped from user text, and the block states it cannot override the
rules above it. Validation errors are Vietnamese 400s, not Pydantic's English 422s.

`ProfileSettings.tsx` ties labels to inputs with `htmlFor` instead of wrapping them:
every `<label>` is `user-select: none` for tap handling, and iOS Safari can refuse to
edit inputs nested inside such an element.

`/api/auth/me` also returns the profile's `nickname`, so the empty-state greeting can use
it on first paint without a second request or a visible name swap. The greeting line
comes from `frontend/src/timeGreeting.ts`: a few lines per time-of-day slot on the
**browser** clock (unlike chat, which trusts the server clock), re-picked when the tab
becomes visible again in a new slot or day.

### Discord memory gateway

`discord_memory.py` calls the bot's gateway over loopback. It is **one-way, read-only, and
fails soft** — any error, bad JSON, wrong token or unreachable host returns `EMPTY` and chat
continues normally. It re-queries every turn and never caches, because the gateway also
reports the user's anonymity status; a cached snapshot could surface memory a user just
disabled. `PETO_MEMORY_CACHE_TTL` is kept only for config compatibility and does nothing.

Disabled unless both `PETO_MEMORY_GATEWAY_URL` and `PETO_MEMORY_GATEWAY_TOKEN` are set;
half-configured setups log a warning at startup rather than failing silently.

### Companion tab and local voice

`Companion.tsx` is mounted alongside Chat like `Imagine.tsx` (an `active` prop, kept alive once
visited) and owns one continuous thread from `GET /api/companion`; "Bắt đầu lại" deletes it. It
sends `mode: "companion"`, speaks each completed reply unless muted, and stops speaking when the
tab is left.

Speech runs on the user's own machine, never on the VPS. `local-tts/speak_server.py` lives in a
gitignored experiment folder with its own venvs, loads Qwen3-TTS 0.6B through faster-qwen3-tts,
and serves `GET /health` and `POST /speak` (up to 300 characters in, WAV out) on
`127.0.0.1:7862`. It rejects any Origin other than the production site and the local dev origins,
and any Host other than 127.0.0.1/localhost (DNS rebinding). There is no credential anywhere.

`localSpeech.ts` holds markdown → speakable text, chunking and the player; `LocalVoice.tsx` holds
`useLocalVoice`, `SpeakButton` and `VoiceControls`. Keep those file names distinct beyond letter
case: on Windows `./LocalVoice` resolves to a `localVoice.ts` before the `.tsx`.

- Voice stays off until the user presses "Bật giọng nói trên máy này", and nothing touches
  127.0.0.1 before that: a public origin fetching loopback triggers Chrome's Local Network Access
  prompt, and visitors who never asked for voice must not see it. `tests/Companion.test.tsx`
  asserts this.
- Chunks stay roughly equal (target 150 characters). Generation is only slightly faster than real
  time; the next chunk is requested when the previous one arrives, so it is ready in time only if
  it is not much longer than the one playing.
- Never add TTS models or their npm packages to the frontend, and never proxy speech through the
  backend: `npm ci` on the VPS would ship them to every user.

## Frontend conventions

- **Stale-response guarding.** Async loads use a monotonically increasing `useRef` counter
  (`loadVersion`, `listVersion`, `authVersion`) plus an `AbortController`; results are
  discarded unless the version still matches. Follow this pattern for any new fetch — fast
  conversation switching is a tested scenario.
- **Draft preservation.** The composer keeps text and files until the server acknowledges
  the message (the `meta` event). Stop, error and disconnect all keep the draft.
- Modals are native `<dialog>` with `showModal()`; `tests/setup.ts` polyfills those methods
  for jsdom.
- An empty chat puts greeting + composer together mid-screen on desktop
  (`.chat.empty-state`); phones keep the composer docked. Only the **first send** slides
  the composer down (FLIP via `element.animate` in `App.tsx`); opening a conversation or
  starting a new one switches instantly on purpose — those are frequent navigation.
- Code blocks only colour the grammars registered in `App.tsx` (`HIGHLIGHT_LANGUAGES`,
  `HIGHLIGHT_ALIASES`, display names in `CODE_LABELS`) — the `common` bundle is
  deliberately not used. Anything else renders as plain text under an uppercased tag, so a
  new language needs a grammar import **and** a label. Each grammar costs bundle size; add
  ones Peto actually answers with.
- Per-user preferences (effort, theme, imagine quality/resolution/ratio/count, local voice on/off and voice, Companion
  mute) live in
  `localStorage` behind try/catch helpers. In-flight Imagine state lives in component state,
  so it survives switching tabs but not a page reload.
- `App.tsx` owns chat plus the app shell; `Imagine.tsx` and `Companion.tsx` are mounted alongside
  it and receive an `active` prop rather than being unmounted — that is what keeps a running generation
  alive when the user switches back to Chat.
- The composer is `Composer.tsx`, presentational only: draft text, the file list and the send
  flow stay in `App.tsx` because they hang off the draft-preservation rule; just the drag
  state is local to it. `files.tsx` holds what the composer and the message bubbles share
  (`DraftFile`, `formatSize`, `FileGlyph`) so `Composer.tsx` never imports from `App.tsx`
  and no import cycle can form.

## Invariants — do not break these

- **Never** point `PETO_WEB_DB` or `PETO_XAI_TOKEN_PATH` at the Discord bot's files
  (`bot_memory.db`, `.xai_tokens.json`). Separate database, separate tokens, no shared files
  with the bot's production data.
- `persona.py` must not contain real names or Discord IDs of members — `tests/test_persona.py`
  asserts this. Personal context is loaded per account at runtime, not baked into the prompt.
- Nothing writes back to the bot's memory. The gateway is read-only and loopback-only; it
  must never sit behind Cloudflare Tunnel.
- No AI credential ever reaches the browser.
- Registration is open by the owner's explicit decision. Do not add an allowlist, invite
  code, or per-account quota back unless asked for it.
- Guest and Google accounts must never resolve to a Discord ID — that isolation is the
  only thing keeping the bot's memory private now that anyone can sign in.
- Do not rename model slugs (`grok-4.6`, `grok-imagine-image-2.0`), the `/api/imagine` path,
  or table names into branded equivalents — the API needs the real identifiers. Product
  naming ("Peto tạo ảnh") belongs in display strings only.

## Testing

`backend/tests/conftest.py` sets environment variables **before importing any module that
imports `config`** — the `# noqa: E402` imports at the bottom are deliberate. `load_dotenv`
runs with `override=False`, so these test values win over a developer's real `.env`.
Preserve that ordering or tests will hit real data. It also pops `XAI_API_KEY` so a machine
credential cannot leak into a test run.

Tests use `PETO_AI_PROVIDER=mock`, a temp directory for DB/uploads/tokens, and
`httpx.ASGITransport` (no network, no live server). Fixtures: `client` is authenticated as a
fake Discord identity, `anon_client` is not. `read_events(response)` collects SSE events
from a streaming response.

`tests/test_review_regressions.py` holds regressions from a prior review pass — revoked
access, partial-reply persistence, pagination, anonymity. Treat failures there as behavioral
regressions, not flaky tests.

## Related documents

- `README.md` — user-facing description of current behavior, Discord OAuth setup, and an
  explicit list of what each feature does *not* do yet.
- `DEPLOY.md` — VPS deployment, systemd unit in `deploy/`, Cloudflare Tunnel, troubleshooting.
- `PETO_WEB_HANDOFF.md` — original project brief. Historical context, **not** a description
  of the current code; prefer `README.md` and the source when they disagree.
