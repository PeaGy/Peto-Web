# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Peto Web is a private chat UI for Peto, an AI assistant. The name comes from a Discord bot
(`Tracen Jukebox`) in a **separate repository**. This web app is deliberately independent:
its own database, its own xAI token file, its own persona prompt. The only link back to the
bot is a read-only memory gateway (see below).

On 2026-09-17 the owner made the default persona an honest, helpful AI assistant (`persona.SYSTEM_PROMPT`):
it says it is Peto, an AI assistant, addresses users as "bạn", and refuses only genuinely harmful requests. By the
owner's call it never names the model behind it (no Grok or xAI in any prompt), and `tests/test_persona.py` checks that.
The bot's roleplay character, which the web used before, survives only as an opt-in per-conversation
roleplay mode (`persona.ROLEPLAY_SYSTEM_PROMPT`, see "Roleplay mode" below). Peto Agent and Companion always
use the assistant core (`PERSONA_PROMPT`).

Stack: FastAPI + SQLite (aiosqlite) backend, React 19 + Vite frontend, xAI Grok via the
Responses API, plus OpenAI's GPT-6 models as a user-selectable option (see "Model choice"). Registration is **open**:
Discord, Google, or guest — there is no allowlist.

## Language convention

Agent/CLI planning context is recorded in [PETO_AGENT_PLAN.md](PETO_AGENT_PLAN.md).
The clarified direction is a Windows CLI that runs the loop and executes local project tools, with VPS
authentication, step limits and model calls (first version: "Peto Agent (CLI)" below). Docker is optional; web
Work is later scope.
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

# Peto Agent CLI tests (stdlib-only CLI; uses the repo venv's pytest)
.venv/Scripts/python.exe -m pytest agent-cli/tests

# Peto Agent evals (agent-cli/evals/README.md): selftest costs nothing; run spends real agent steps, so only on the
# owner's go-ahead
.venv/Scripts/python.exe agent-cli/evals/run.py selftest
.venv/Scripts/python.exe agent-cli/evals/run.py run --model peto --effort low

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

### Model choice (Peto and GPT-6)

On 2026-09-17 the owner added OpenAI API billing and picked this design from mockups. `ai_models.py` holds the catalog
and the access rules; the server checks them on every chat turn and agent step, never trusting the UI:

- `peto` (Grok through the web's xAI account) for everyone; `luna` (`gpt-6-luna`) for Discord and Google accounts,
  on the web and in the CLI; `terra` (`gpt-5.6-terra`, until a GPT-6 Terra exists) and `sol` (`gpt-6-sol`) only in the CLI and only for owners
  listed in `PETO_OWNER_ACCOUNTS` (`discord:<id>` or `google:<id>`, bare digits mean Discord). Without `OPENAI_API_KEY`
  only Peto is offered (503 if a turn asks for another model); under `PETO_AI_PROVIDER=mock` every model uses the mock.
- `get_provider(model)` caches one provider per model. `ai/xai.py` holds `ResponsesProvider`, the tool loop, web search
  and sources shared by `XAIProvider` and `ai/gpt.py`'s `GPTProvider`; subclasses only set the client, model, output
  budget (`PETO_OPENAI_MAX_OUTPUT_TOKENS`, 16000, since reasoning tokens count) and Vietnamese error messages. OpenAI
  reasoning summaries are not requested, because they can require organization verification.
- `POST /api/chat` takes `model` per message, so switching mid-conversation works (history is plain text). Companion and
  roleplay conversations must stay on `peto` (400): the roleplay prompt can be 18+, and it must not reach the owner's
  OpenAI account. The title call uses the same model as the first message. `/api/auth/me` returns the account's web
  `models`; `ModelMenu.tsx` sits left of the send button (hidden with fewer than two models or in roleplay), remembers
  the choice in `localStorage` (`peto-model`), and phones show the send button as an arrow only to keep the bar on
  one row.
- The persona rule still holds: whatever model runs, Peto does not name the model behind it.
- Tests patch `main.get_provider` with a callable that accepts the model (`lambda model="peto": ...`).
  `tests/test_models.py` covers the access rules, step costs and the OpenAI call shape with fake clients.

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

The composer copies Grok's Imagine at the owner's request. Chips above the box pick Nhanh/Chi tiết, the
count and the ratio (`StudioMenu.tsx`, a popover reusing the `.effort-options` classes). The box holds the
source-image button, 1K/2K where Grok has Image/Video, and a round send button whose accessible name stays
"Tạo ảnh"/"Sửa ảnh". Desktop always shows all of it. Below the 720px breakpoint `.studio-dock` floats over
the gallery and collapses to a bar (a library button showing the newest image, a one-line prompt, an options
button) until the prompt is focused or the options button is pressed. A tap outside or a submit collapses it
and blurs the prompt so the phone keyboard hides.

The library button opens `ImagineLibrary.tsx`, a full-screen `<dialog>` that only phones can reach (desktop keeps
the sidebar list). It shows one tile per output image of the loaded jobs (the API returns the latest 40), searches
prompts ignoring Vietnamese diacritics, and offers 2 or 3 columns (kept in `localStorage`) plus a liked-only
filter. "Chọn", or a 500 ms long press or right click, selects tiles to share (Web Share with files, hidden when
unsupported), download or delete. Deletion is per image: `DELETE /api/imagine/images/{id}` removes one output
and deletes the job, source image included, once no output is left. `PUT /api/imagine/images/{id}/like` stores
`imagine_images.liked`. Source images of edits cannot be deleted or liked on their own. The heart button lives
in the lightbox, which opens on top of the library.

### Configuration

`config.py` is where environment variables are read. Every numeric knob goes through
`_env_int` / `_env_float`, which clamp to a min/max so a bad value degrades instead of
crashing. When adding a setting: declare it in `config.py` **and** document it in
`.env.example`. Two exceptions exist: `XAI_API_KEY` is read directly in `xai_auth.py`, and
`PETO_VOICE_WORKER_TOKEN` is read on every worker request in `voice_api.py` (see the voice relay below).

`XaiAuth` prefers OAuth tokens (`backend/data/xai_tokens.json`), refreshes them on expiry,
and falls back to `XAI_API_KEY` if refresh fails or no token file exists.

### Database

aiosqlite, WAL mode, connection per operation. `init_db()` creates tables with
`CREATE TABLE IF NOT EXISTS` and does schema upgrades **manually** via `PRAGMA table_info`
plus `ALTER TABLE` — there is no migration framework and no version table. Add a column the
same way, preserving existing rows. Note that `PRAGMA foreign_keys=ON` is set per connection
where cascade deletes matter (SQLite has it off by default).

Tables: `conversations`, `messages`, `attachments`, `users`, `user_profiles`,
`imagine_jobs`, `imagine_images`, `agent_devices`, `agent_usage`, `roleplay_consents`, `voice_usage`
(`speech_cloud.py` also creates its own `speech_budget` on first use). `users` is the only place mapping
a web account to a Discord ID.
`conversations.mode` (`chat` or `companion`) was added with the same manual migration; older rows
default to `chat`. `conversations.persona` (`assistant` or `roleplay`) was added the same way; older rows default to
`assistant`.

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

### Roleplay mode

A conversation's `persona` is `assistant` (default) or `roleplay`, chosen before its first message and stored on the
row; the owner picked this design from mockups. `POST /api/chat` only honours `persona` when it creates the
conversation. Later turns always use the stored value, so a history never mixes the two voices.
`_check_roleplay_start` rejects roleplay for Companion (400), guest accounts (403) and accounts with no row in
`roleplay_consents` (403). `POST /api/profile/roleplay-consent` records the self-declared 18+ confirmation (guests get
403), and `/api/auth/me` returns `roleplay_confirmed` so the dialog only shows once.

Roleplay turns use `persona.ROLEPLAY_SYSTEM_PROMPT`: the bot's persona blocks verbatim, plus the continuity and web
platform rules shared with the assistant. They send `PETO_ROLEPLAY_MAX_HISTORY` (default 100) past messages instead of
`PETO_MAX_HISTORY` (20), for long stories. Memory, profile and the agent guide are appended as usual.

In the UI, `ComposerMenu.tsx` shows "Chế độ nhập vai" only while the conversation has not started (disabled for
guests). `Composer.tsx` shows a "Nhập vai" chip whose × only exists before the first message, and the sidebar marks
roleplay conversations with "· Nhập vai". `App.tsx` holds `persona`: a new conversation or sign-out resets it, and
opening a conversation takes it from the list.

### Discord memory gateway

`discord_memory.py` calls the bot's gateway over loopback. It is **one-way, read-only, and
fails soft** — any error, bad JSON, wrong token or unreachable host returns `EMPTY` and chat
continues normally. It re-queries every turn and never caches, because the gateway also
reports the user's anonymity status; a cached snapshot could surface memory a user just
disabled. `PETO_MEMORY_CACHE_TTL` is kept only for config compatibility and does nothing.

Disabled unless both `PETO_MEMORY_GATEWAY_URL` and `PETO_MEMORY_GATEWAY_TOKEN` are set;
half-configured setups log a warning at startup rather than failing silently.

### Companion tab and voice relay

`Companion.tsx` is mounted alongside Chat like `Imagine.tsx` (an `active` prop, kept alive once
visited) and owns one continuous thread from `GET /api/companion`; "Bắt đầu lại" deletes it. It
sends `mode: "companion"`, speaks each completed reply unless muted, and stops speaking when the
tab is left.

On desktop the layout is a stage on the left and a ~380px chat column on the right. The stage holds
only the character and the model's credit line: no text, status or controls go there, by the owner's
explicit call. The chat column carries the speaking status, the mute toggle, "Bắt đầu lại", a notice when
voice is on but the chosen source cannot speak (`voice.problem`), and the Chat tab's composer styles. Enabling
voice, choosing a source and a voice, and "Nghe thử" live in Settings, in `VoiceSettings.tsx` (see "Voice sources"
below).

The character is Live2D. `Live2DStage.tsx` is lazy-loaded and mounted only while Companion is active,
and renders the Hiyori sample model from `public/characters` with PixiJS 6 and
`pixi-live2d-display/cubism4`. The model path, mouth parameter and head height live in
`characterConfig.ts`; licensing notes are in `frontend/CHARACTER.md`. Because the stage has no
controls, the view changes by gesture: wheel or pinch zooms around the pointer, dragging pans (with the
middle mouse button at the owner's request, or one finger on a touchscreen), double-click resets, and the view is
saved in `localStorage`. The pure math (zoom, pan limits, look
direction, wheel steps) lives in `characterView.ts` with its own tests.

When motion is allowed the model plays its `Idle` motions, breathes, blinks and turns toward the
pointer anywhere on the page; otherwise it holds its pose. "Nhân vật cử động" in Settings → Giao diện
picks `system` (the default, which follows `prefers-reduced-motion`) or `always`. Windows with
Animation effects off reports reduced motion, which is why the owner asked for the override. The
mouth always follows the audio that is playing (`voiceActivity.ts` reads the WAV's 20 ms loudness
envelope against `currentTime`) and stays closed when nothing plays.

Phones get AIRI's mobile look instead, at the owner's request. Below `COMPACT_QUERY` (the same 720px
breakpoint as the CSS) the character fills the screen in a fixed frame (`compactHeight` and
`compactTop` in `characterConfig.ts`). The header, messages and a pill composer float over it in
translucent `--stage-*` colours defined on `.companion`. Zoom, drag and double-click are ignored
there. Instead, a finger held on the screen acts as the pointer, and the character looks at it until
the finger lifts. `index.html` sets `interactive-widget=resizes-content`, so on Chrome for Android the
keyboard shrinks the layout instead of panning the page away. The compact frame keeps the tallest stage
height seen at the current width, so the shorter stage leaves the character's size and position alone.
Safari on iOS ignores that viewport setting.

The home source ("Máy nhà của Peto") is generated on the owner's Windows PC, never on the VPS, and reaches
listeners through the VPS in three hops:

1. `local-tts/speak_server.py` lives in a gitignored experiment folder with its own venvs. It loads
   Qwen3-TTS 0.6B through faster-qwen3-tts and serves `GET /health` and `POST /speak` (up to 300
   characters in, WAV out) on `127.0.0.1:7862` only. It still rejects foreign Origins and any Host
   other than 127.0.0.1/localhost, but browsers no longer call it.
2. `voice-worker/relay.py` (run by `voice-worker/start-relay.ps1` in the same venv) connects **out**
   to the site over HTTPS, so the PC opens no port. Every 5 s it checks the local server and, if both
   voices are loaded, posts a heartbeat. It polls `GET /api/voice/worker/next`, has the local server
   speak the job, and posts the WAV to `/api/voice/worker/result/{id}`, or an empty body with
   `X-Voice-Error: 1` if speaking failed. It sends `PETO_VOICE_WORKER_TOKEN` (32+ characters, the
   same value as on the VPS) only to the site, requires an HTTPS `PETO_VOICE_SERVER_URL`, and never
   follows redirects. `tests/test_voice_worker.py` checks the token never reaches the local server.
3. `backend/voice_api.py` serves signed-in users. `GET /api/voice/health` reports `home.online` (a
   heartbeat in the last 15 s) and lists the home voices in `voices` only then. `POST /api/voice/speak`
   with `playful-1` or `gentle-2` and up to 300 characters queues a job and waits up to 120 s for the audio: 429 when four jobs are
   already queued or this owner has one, 503 when the worker is offline or reports a failure, 504 on
   timeout. Results must be a RIFF/WAVE body under 8 MB. A listener disconnect removes the job, late
   audio is rejected instead of reaching another listener, and nothing is written to disk.
   `tests/test_voice.py` covers this with fake WAVs.

The queue and heartbeat live in process memory, so the backend must run as a **single** uvicorn
process with a single relay. A restart drops waiting jobs, and a job claimed by a relay that dies
waits out the 120 s timeout. Registration is open, so any signed-in account, guests included, can
use the owner's GPU while the relay runs; stopping the relay stops sharing. Setup and operating
limits are in `voice-worker/README.md`.

**Voice sources** (option A, picked by the owner from mockups on 2026-09-24, modelled on AIRI's "official provider plus
your own key"). Settings → Giọng nói shows the sources as cards in two groups, and the card picked is the source
Companion speaks with:

- **Giọng Peto** (`official`): the voices in `speech_cloud.catalog()` (StepFun, plus OpenAI or Qwen Cloud when
  enabled), called with the owner's keys. Each Discord or Google account gets `PETO_TTS_FREE_CHARS_MONTHLY` characters
  (5000) a month, counted in `voice_usage` by `PETO_DEFAULT_TIMEZONE` month. Guests get 403: anyone can mint guest
  accounts, so a per-guest allowance would have no limit. `db.take_voice_chars` checks and adds in one statement before
  the call, a failed line gives its characters back, and `X-Peto-Voice-Used` returns the new total. A used-up
  allowance is a 429 with `X-Peto-Quota: exhausted`, which, like 502/503/504, lets `/speak` switch to the request's
  `fallback` voice. The shared USD ceiling (`PETO_TTS_MONTHLY_USD`, `speech_budget`) still applies on top.
- **Máy nhà của Peto** (`home`): the relay above.
- **Khóa của bạn**: eight providers in `voiceProviders.ts` (OpenAI, ElevenLabs, Azure Speech, Google Gemini, MiniMax,
  Qwen Cloud, StepFun, any OpenAI-compatible server). Keys stay in that browser's `localStorage` (`peto-voice-keys`)
  and bill the user's own account. The browser calls the provider directly, except StepFun (it blocks browser calls,
  checked 2026-09-24) and Qwen (it answers with an audio URL the browser cannot fetch). Those two go through `POST
  /api/voice/relay` with the key in `X-Voice-Key`: used for that one call, never stored, logged or charged to the
  owner, and open to guests. Voice and model ids must match `[\w.\- ]{1,64}`, and the Qwen region must be a key of
  `QWEN_ENDPOINTS`. All audio becomes WAV PCM16 (`audioBytesToWav`, `normalizeWav`), because lip sync only reads WAV.
  Nobody has tried these providers with real keys yet (2026-09-24); the request shapes follow each provider's docs
  from that day.

The fallback (`peto-voice-fallback`) is `home`, `official`, or empty for text only. Unset means `home`, and older values
(a voice id) map to their source. Server sources send it to `/speak` as `fallback`. Key sources fall back in the
browser (`withFallback`) on any error, and the notice carries the provider's error, so a wrong key is not hidden. A
source that cannot speak at all (allowance used up, home machine off, key missing) speaks through the fallback directly
(`fallbackOnly`), and `status` counts a usable fallback as ready. "Nghe thử" never falls back (`speak(…, { fallback:
false })`): hearing the fallback would hide the very problem being tested.

The detail panel follows the selected card in the DOM with `grid-column: 1 / -1` in a `grid-auto-flow: dense` grid. On
desktop it opens below the card's row, on phones (one column below 520px) right below the card, and screen readers
reach it in order. Fields use `htmlFor` labels (the iOS rule under "User profile"), and the on/off switch reuses the
character settings switch. `backend/tests/test_voice_sources.py`, `frontend/tests/voiceProviders.test.ts`,
`localSpeech.test.ts` and `Companion.test.tsx` cover the allowance, the relay, each provider's request and the fallback
rules.

`localSpeech.ts` holds markdown → speakable text, chunking, the player and the `/api/voice` calls;
`voiceProviders.ts` holds the key providers; `LocalVoice.tsx` holds `useLocalVoice`, `SpeakButton` and the speaker
icons. The "local" names date from the first design, where the browser called 127.0.0.1 directly. Keep the
`peto-local-voice*` storage keys so saved choices survive (a saved name containing `:` is read as a Giọng Peto voice),
and keep those file names distinct beyond letter case: on Windows `./LocalVoice` resolves to a `localVoice.ts` before
the `.tsx`.

`useLocalVoice` is called once in `App.tsx` and passed to both Companion and `VoiceSettings`, so they
share one enabled flag, probe result and player. `speak()` returns a promise that rejects with a
Vietnamese message, and each caller shows its own error. Companion's speech keys start with
`companion-` so the Settings sample does not change Companion's status line.

- Voice stays off until the user turns on the "Bật giọng nói" switch in Settings, and nothing calls
  `/api/voice` before that. Even once enabled, the hook only probes after Companion has been opened
  or while Settings is open, so the Chat tab never calls it. `tests/Companion.test.tsx` asserts both.
- Chunks stay roughly equal (target 150 characters). Generation is only slightly faster than real
  time; the next chunk is requested when the previous one arrives, so it is ready in time only if
  it is not much longer than the one playing. One request at a time also fits the backend's
  one-job-per-owner limit. An aborted request frees that slot only once the backend notices the
  disconnect (it checks every 0.25 s), so a request sent right after an abort can get 429.
- The backend only relays text and audio, or calls TTS APIs over HTTP. Never add TTS models or their packages to the
  backend or the frontend: `pip install` and `npm ci` on the VPS would ship them to every deployment.

### Peto Agent (CLI)

`agent-cli/` is a stdlib-only Python CLI (`peto`) that runs on the user's machine. **The CLI owns the loop**: it
sends the whole conversation to `POST /api/agent/step`, the backend makes exactly one model call and streams `meta` /
`thinking` / `delta` / `done{output, usage}` / `error`, and the CLI runs the requested tools locally and sends their
results in the next step. The server stores no conversation (`store=False`), and the xAI credential never leaves it.

- **Login** is a device-code flow in `agent_api.py`. `device/start` returns a `XXXX-XXXX` code; the user opens
  `/?agent_code=…`, where `AgentConnectDialog.tsx` keeps the code in `sessionStorage` across OAuth redirects; `POST
  device/{code}` allows or denies; `device/token` hands the CLI a `peto_…` token exactly once. The fixed routes must stay
  declared before `/device/{user_code}`. Pending codes live in RAM for 10 minutes, so this needs the single-process
  backend, like the voice relay. Only the token's SHA-256 is stored (`agent_devices`), and tokens unused for
  `PETO_AGENT_TOKEN_IDLE_DAYS` stop working. Settings → Peto Agent (`AgentSettings.tsx`) lists and revokes devices.
- **Guest accounts cannot use the agent**, by the owner's call: `web_owner` and `device_auth` reject `guest:` owners.
- **Daily step cap.** `PETO_AGENT_DAILY_STEPS`, counted in `agent_usage` by `DEFAULT_TIMEZONE` day, is a per-account
  quota the owner explicitly asked for, and only for the agent; chat stays unlimited. `take_agent_step` checks and
  increments in one statement, and a step that fails before the model produces anything is refunded. Agent steps use
  their own `Admission` instance, so they never take chat's slots.
- **Effort.** `/step` takes `effort` (`low` / `medium` / `high`, default `PETO_AGENT_REASONING`, which `/me` returns as
  `default_effort`). `STEP_COST` makes `high` cost 2 steps, taken and refunded together, by the owner's call. The CLI's
  `/effort thap|vua|cao` is remembered in its `config.json`.
- **Model.** `/step` takes `model` (default `peto`, checked by `ai_models.resolve` before any step is taken). A step costs
  `STEP_COST[effort] × step_cost` of the model (Luna 1, Terra 2, Sol 4), by the owner's call. `/me` returns the account's
  `models`; the CLI's `/model` offers only those (`commands.use_models` rewrites the menu options) and remembers the
  choice in `config.json`. Switching models, or resuming a session saved with another model (`history` stores `model`),
  runs `loop.portable`: it drops `reasoning` items, whose encrypted content only the producing service can read, and
  item `id`s, whose formats differ between services. Peto goes through `_xai_step`, others through `_openai_step`; both
  share `_responses_step`.
- **`/step` input is validated**: body size (`PETO_AGENT_MAX_REQUEST_BYTES`, 16 MB by default because images are
  resent every step), at most 300 items, only `message` / `function_call` / `function_call_output` / `reasoning` /
  `web_search_call` (the last one is produced by the AI service itself and resent verbatim), and
  messages only as `user` or `assistant`. A user message's content is a string or a list of `input_text` and
  `input_image` parts. Images must be base64 data URLs whose magic bytes match the declared PNG/JPEG/GIF/WebP type (never
  a web URL, so the AI service fetches nothing on the CLI's behalf), at most `MAX_STEP_IMAGES` (8) per step and
  `MAX_STEP_IMAGE_BYTES` (3 MB) each. Rejected images cost no step. The instructions
  are always the server's: `PERSONA_PROMPT` + `persona.AGENT_PROMPT` + the search prompt for the current setting + time
  context + project/OS line. Tool schemas are server-owned (`agent_tools.py`). `ai/agent.py` holds the xAI call and a mock that runs a scripted `__demo__` task (read
  `README.md` → edit its first line → run a command → summarize) based on the tool results the CLI sends back. The mock
  estimates usage at about 4 characters per token so the CLI's token display has numbers.
- **Deleting and renaming are tools, not shell commands** (`delete_file`, `move_file`). They go through the CLI's
  checkpoint, so `/undo` restores them, which `del` or `move` in a terminal cannot; `AGENT_PROMPT` says so. Delete only
  accepts a text file the workspace can read (so the checkpoint can hold its bytes) and shows the content that is about
  to be lost; move refuses an existing destination and records the pair as "old path deleted, new path created".
  `Change.after is None` is what "the file must not exist" means in `checkpoint.py`, including for undo's preflight.
- **`@path` mentions** (`mentions.py`) attach a file's content to the request itself, because every model call costs a
  step from the daily cap and the user often already knows which file matters. An attachment **counts as a read**:
  `Workspace.remember` stores the digest and `Tools.guidance_for` records the sub-directory `AGENTS.md` (sent inside the
  block, since the root one is already in the step's instructions), so the first `edit_file` is not spent on re-reading
  or on a `GuideUpdate`. The digest check still runs, so a file changed after attaching is still refused. Tokens that do
  not resolve inside the project (`a@b.com`, `@app.route`) are left alone silently; blocked, binary or oversized files
  get a yellow notice instead. `@path:120-180` (or `:120` to the end) attaches only that range, which is what keeps a
  big file from costing 10k tokens for one function. Caps: 8 mentions, 1000 lines / 60k chars per file, 120k chars per
  message, 200 entries for a directory listing. The `@` completion menu reuses the `/` command menu: `__main__._suggester` chains
  `commands.suggestions` and `mentions.suggest`, and `line_editor.create` takes the combined callable.
- **`update_plan`** renders the model's own task list (`☑ ▶ ☐`) and needs no permission, since it touches nothing. At
  most 10 items; unfinished ones are named in the request's summary line so "xong" cannot hide a half-done plan.
- **Checking after edits.** When Peto ends a request after editing files without checking them, `_run` appends one
  "Kiểm tra sau sửa" reminder and runs another step. `Tools.revision` counts edits, and `Tools._checked` records the
  revision Peto last checked at. These count as checking:
  - a test or build run (`classify` gives `passed`/`check_failed`);
  - opening, screenshotting, reading or acting on a local page;
  - an HTTP call to a server on this machine (`command_outcome.local_probe`: curl, Invoke-WebRequest… to localhost).

  Before 2026-09-24 only tests counted. The eval run that day spent 5 of 68 steps on reminders after Peto had already
  looked at the page or called the API, and once Peto ran `dotnet build` just to satisfy it.
- **Background commands** (`background.py`): `start_command` / `read_command_output` / `stop_command`. `runner.spawn`
  is shared with `run_command`, output is collected by a reader thread into a 256 KB tail buffer, and `read` waits up to
  30 s for new output so one step is worth spending. At most 3 running jobs. They deliberately outlive a request (a dev
  server is the point) but never the session: `__main__.session` stops all of them in a `finally`.
- **Browser, phase 1: look** (`browser.py`, CLI 0.10.0). The owner picked the design from mockups on 2026-09-23:
  hidden browser with saved screenshots, up to 5 page errors printed under each look, and no permission prompt for
  viewing local pages (like reading a file). Phase 2 (clicking, typing, login) is the next bullet.
  - **Tools:** `browser_open` (title, HTTP status, console errors, JS exceptions, failed requests, an outline of visible
    headings, buttons, inputs, links and images without alt), `browser_screenshot` (desktop 1280×800 or mobile 390×844,
    optional full page up to 4000 px), `browser_read` (`innerText`, optional CSS selector, 20k characters).
  - **How it works:** stdlib only. It launches Edge, or Chrome as a fallback (`PETO_AGENT_BROWSER` overrides), with
    `--headless=new --remote-debugging-port=0` and the session's profile. It reads `DevToolsActivePort` and drives the
    page over the DevTools protocol through a small RFC 6455 client (`browser.WebSocket`, unit-tested against a fake
    server). "Loaded" means the load event plus 0.5 s of network quiet, capped at 5 s. Errors are reported "since the
    last report", so late ones (HMR, timers) still reach Peto.
  - **Page dialogs are answered at once** (`Browser._dialog`, CLI 0.10.1): `alert` accepted, `confirm` and `prompt`
    dismissed (Peto must not agree to something that may change data on the user's behalf), `beforeunload` accepted
    since Peto itself is navigating. A dialog blocks the page until answered: before this, a page calling `alert()` on
    load made `browser_open` wait ~50 s and fail, and every later call hung until the session ended (found 2026-09-23).
    The answer is sent raw, never through `_call`, because the event arrives in the middle of another `_call`, and a
    nested wait would swallow the outer call's response. Dialogs are reported separately from errors (`dialogs` in the
    tool result, the dim details line on screen), since a dialog is not a bug. A `_call` timeout closes the browser,
    so a hung page (an endless script) costs one 30 s wait and the next look starts a fresh browser.
  - **A screenshot in another viewport reopens the page** at that size. Chrome keeps the old zoom when metrics change
    on a loaded page, and a reload keeps it too. A page laid out at 1280 px and then switched to mobile came out scaled
    down to fit, hiding exactly the overflow the phone shot is for (2026-09-23). A fresh load behaves like a phone's
    first visit: scale 1 with a viewport meta, zoomed out without one. Errors already reported for the page
    (`Browser.known`) are not repeated after that reopen. An explicit `browser_open` reports them all again, because an
    error that is still there means it is not fixed.
  - **Only pages on this machine** (`check_url`): http(s) to localhost, `*.localhost`, 127/8 or ::1. A free browser is
    an exfiltration channel (read a file, then open a URL or submit a form that carries it) and a prompt-injection path,
    and `file://` would bypass the project folder. Since 0.11.0 every main-frame document request is paused
    (`Fetch.enable` with a Document pattern, `Browser._paused`): one leaving the machine (link, form, redirect,
    `location.href`) is answered with a local 204, which cancels the navigation before any request leaves and keeps
    the page as it was, and a note tells Peto. Frames are let through. A `browser_open` whose redirect was blocked goes
    to `about:blank` and fails, as in 0.10.0.
  - **Screenshots** reach the model as a user message right after the step's tool outputs (`loop.tool_images`, starting
    with `history.TOOL_IMAGES_NOTE`, which `history.recap` skips). They count toward the 4 kept images, stay under 2 MB
    (JPEG fallback), and are saved to `%LOCALAPPDATA%\PetoAgent\screenshots` for 7 days. The path is printed unwrapped so
    the VS Code terminal can Ctrl+click it. Tool results give Peto only the file name, never the full path.
  - **Edge is a GUI app, so it does not die with the console** the way background commands do. On Windows it is started
    `CREATE_SUSPENDED`, assigned to a job object with `KILL_ON_JOB_CLOSE`, and only then resumed (`NtResumeProcess`).
    Whatever kills peto, closing the terminal included, therefore kills every Edge process. A ConPTY test on 2026-09-23
    closed the console mid-session and confirmed it. `__main__.session` also closes the browser in its `finally`.
  - **`__COMPAT_LAYER`:** Windows can put a compatibility layer on a whole process tree (`DetectorsAppHealth` was set in
    this machine's shells). Edge then relaunches itself without the layer and exits the first process with 0. That left
    orphan browsers until `_launch_env` began dropping the variable. A launched process that exits with 0 is still
    waited on through `DevToolsActivePort`, and liveness follows the DevTools socket, not the first process.
  - **Leftover profiles** (from a killed peto) are pruned when the next browser starts. A running Chromium holds
    `lockfile`, which cannot be deleted, and Windows deletes it when the browser dies. Peto itself keeps `peto.lock`
    open for the whole session (`_hold`), also while the browser is down for a hide/show relaunch. So a profile whose
    peto.lock is free and whose lockfile can be deleted, or is gone after 60 s, is unused. Other OSes use a one-day age.
    `_stop` waits up to 5 s for the lockfile to go (`_released`): the first Edge process may be long gone while the job's
    processes die a moment later, and relaunching on a profile that is not yet free made the new Edge hand over to the
    dying one, and made `/trinhduyet xoa` report the profile as busy (found in the ConPTY test on 2026-09-23).
- **Browser, phase 2: click, type, log in** (CLI 0.11.0, feature `browser_act`). The owner picked all three options
  from mockups on 2026-09-23: ask once per page, keep the window hidden and show it on demand, and let the user log in
  themselves with the login remembered per project.
  - **Tools:** `browser_click(target)`, `browser_type(target, text, submit)` (replaces the text; on a `<select>` it picks
    the option by its visible text, then value, then substring), `browser_press(key)` (a fixed list: Enter, Escape, Tab,
    Shift+Tab, arrows, Home, End, PageUp/Down, Backspace, Delete, Space), each with `accept_dialog`, and
    `browser_login(reason)`. A target is a number from the outline (`[3] nút: Gửi`) or a CSS selector that matches one
    visible element. Numbers live on `window` (`PRELUDE`: a WeakMap and WeakRefs), so they stay the same until the
    document changes, and a stale one is refused with a clear message.
  - **Real input:** clicks are `Input.dispatchMouseEvent` at the element's centre after `scrollIntoView`, typing is a
    real click for focus, select-all and `Input.insertText` (Vietnamese arrives intact, `isTrusted` is true). Before
    clicking, `elementFromPoint` checks what is actually on top: an unrelated element (an overlay, a modal backdrop)
    is reported as covering it instead of clicking through, because a user could not click it either. Disabled
    elements are refused. `target=_blank` links and forms are switched to the same tab; any other new tab is closed at
    creation (`Target.setDiscoverTargets`); the file chooser is intercepted and downloads are denied, all with a note.
  - **Passwords never reach Peto.** `browser_type` refuses password fields, and so does the outline: it shows
    "(đã nhập)" instead of a value. `secret()` also catches "show password" fields that became `type=text` through
    `autocomplete`, name, id, placeholder or label hints. Typed values are read back (`value` in the result) for every
    other field, so Peto sees when `maxlength` or a number field ate its input.
  - **Results are a diff, not a dump:** before and after each action the page text and outline are captured
    (`SNAPSHOT_SCRIPT`). `appeared` lists lines with new words (`_new_lines` diffs word sequences, because innerText
    joins inline buttons into one line and a box opening between them split it in two; a line diff reported both
    halves as new), `elements` lists outline entries that are new or changed state (`= "2"`, `(đã chọn)`), a new
    document returns the full outline, and `press` returns the focused element. After an action Peto waits 0.3 s for
    a navigation, then load or network quiet, then 250 ms of DOM quiet (capped at 2 s).
  - **Permission** (`Tools._approve_page`): the first action on an origin asks once, showing the first action. `y` lasts
    until the request ends, `a` means everything in the request as elsewhere, `s` the session, and `l` stores the
    origin in `approvals.py` (`add_page`, next to the command grants in the user profile, never in the repo).
    `/permissions` lists and clears them. Opening, screenshots and reading still ask nothing.
  - **A failed or refused action skips the rest of that step's page actions** (`Tools.page_failure`, reset by
    `start_step`): the model sends a chain like type, type, click Send in one step, and clicking Send after a failed
    field would do the wrong thing.
  - **Window:** hidden by default. `/trinhduyet` toggles it (`Browser.set_visible`): Chromium cannot switch modes while
    running, so it relaunches with the same profile, restores session cookies it snapshots after every action
    (`Storage.getCookies`, kept in memory only; cookies with an expiry are already in the profile) and reopens the page.
    A visible window steals focus when it opens (checked 2026-09-23; `SW_SHOWMINNOACTIVE` is ignored). A minimized
    window stops painting, which made screenshots hang, so a screenshot first restores it, and `_repaint` races
    `requestAnimationFrame` against a 300 ms timer. `--disable-backgrounding-occluded-windows` and friends keep a window
    behind the terminal painting. If the user closes the window, the next look starts hidden again.
  - **Login** (`browser_login`, `Browser.hand_over`): shows the window at the current page, turns off the Fetch guard,
    the file-chooser interception, automatic dialog answers and popup closing (OAuth needs outside pages and popups),
    and waits for Enter (`n` or EOF skips) with a bell. Afterwards the guards come back, events queued meanwhile are
    drained and discarded (the login pages' errors are not the app's), and a final page off the machine is replaced by
    the page Peto was on.
  - **Per-project profile** (`project_profile`): `%LOCALAPPDATA%\PetoAgent\browser\<folder>-<hash>`, named "Peto" in
    `Local State` before the first launch so the window reads "… - Peto - Microsoft Edge" instead of Edge's default
    "Personal", which could look like the user's own browser. A second peto session in the same project gets a temp
    profile with a notice. `/trinhduyet xoa` deletes it (refused while another session holds it); profiles unused for
    30 days are pruned. Session cookies do not survive to the next peto session; persistent ones do.
  - **The server** offers these tools and `AGENT_BROWSER_ACT_PROMPT` only to CLIs that declare both `browser` and
    `browser_act`; `persona.browser_prompt(act=…)` drops "Chưa bấm hay gõ được gì" for them. With `browser_act`,
    `browser_open` also waits up to 15 s for a server that is not listening yet while a background job runs
    (`Browser.wait_for_server`), so Peto can start the dev server and open the page in one step: on 2026-09-23 the
    owner's first real use spent 4 of 5 steps on start, wait, open, screenshot.
  - Tests: `test_browser.py` drives real Edge through all of this (visible mode with `force_headless`), and a ConPTY
    run on 2026-09-23 passed 30/30 checks with a real visible window: the login window appeared, the password never
    reached the fake server, closing the terminal while the window was visible killed Edge, the next session was still
    logged in, and `/trinhduyet xoa` logged it out.
- **Browser, phase 3: outside pages, read only** (CLI 0.12.0, feature `browser_outside`). The owner picked all three
  options from mockups on 2026-09-24: ask once per domain, read only, and open outside pages only when the user gives a
  link or asks to look at the deployed site (general lookups stay on web search).
  - **A separate browser** (`OutsideBrowser`, a `Browser` subclass): a fresh temp profile per session, never the
    project profile, because that one can hold the Discord or Google login the user used for the app, and opening an
    outside page with it would walk into their account. Always headless, no `/trinhduyet`, and click, type, press and
    login raise `READ_ONLY`; `Tools` refuses them first with "Trang ngoài chỉ xem: mở link bằng địa chỉ của nó."
    (the mockup line). Its outline carries link targets instead of numbers (`liên kết: Tasks → /3/library/tasks.html`,
    `SNAPSHOT_SCRIPT`'s `links` flag) so Peto follows a link by opening its address.
  - **Routing** (`browser.route`): a local host goes to the project browser as before, anything else to
    `check_outside`, which adds `https://` when the scheme is missing and refuses the home network: loopback, private,
    link-local, CGNAT and other non-global IPs, single-label names, `.local`/`.lan`/`.internal`/`.home.arpa`…, and
    public names that resolve to such an address (`_lookup`, patchable in tests; a failed lookup is left to the
    browser). Inside `OutsideBrowser` the Fetch guard lets a main-frame navigation through only to a granted domain
    that is not on the home network, and frames never to the home network; `--enable-features` turns on Chromium's
    Private Network Access checks so outside pages cannot call into the machine either.
  - **Permission** (`Tools._approve_site`): per domain, `site_key` drops a leading `www.` and a grant covers
    subdomains (`python.org` covers `docs.python.org`, never `evilpython.org`). `y` lasts until the request ends, `s`
    the session, `l` goes to `approvals.add_site`, `a` as elsewhere. A URL whose path and query exceed 200 characters,
    or whose query exceeds 120 (`long_url`), always asks again for that exact URL, even under a grant or `a`, because
    the address itself can carry the user's data to that server; `y` there does not grant the domain. Redirects to an
    ungranted domain are blocked and reported so Peto can ask through `browser_open`.
  - **A failed open skips the step's screenshot and read** (`Tools.open_failed`): otherwise the old page would be
    captured and taken for the one just refused.
  - Temp profiles are killed after 0.5 s instead of waiting 3 s for a graceful shutdown (`_stop`); an outside
    browser that had been on the internet regularly took the full 3 s, which made `/thoat` take 3.3 s. They therefore
    keep all cookies in the in-memory snapshot, not just session cookies (never an `expires` of -1, which would set an
    expired cookie).
  - Tests: `test_browser.py` maps `*.peto-test` to 127.0.0.1 with `--host-resolver-rules` and a fake resolver, so the
    real-Edge test needs no network. A ConPTY run on 2026-09-24 against example.com and iana.org passed 24/24: the
    domain prompts, the refused click, the re-asked long URL, the refused router address and a clean `/thoat` in 0.8 s.
- **`shell`** on `run_command` and `start_command` picks `cmd` (default) or `powershell`, because this project's own
  commands are PowerShell. PowerShell runs as an argv list (no quoting games) and `command_outcome` reads its
  "not recognized as the name of a cmdlet" as an environment error.
- **Bell and window title** (`UI.bell`, `UI.title`, off with `PETO_AGENT_NO_BELL=1`): a permission question rings once
  and restores the previous title afterwards, and a request longer than 10 s rings when it ends. The title uses OSC with
  an ST terminator, never BEL, so setting a title never rings.
- **Web search** is the AI service's own tool, added to the step's tools when `PETO_AGENT_WEB_SEARCH` (and
  `PETO_WEB_SEARCH_ENABLED`) allow it, never during compaction. It runs on the service, so nothing is fetched on the
  user's machine; `ai/agent.py` turns the stream's `web_search_call` events into `search` events, the CLI prints one
  `• Tìm trên web` line per step, and `loop.portable` drops those items when switching services. A 400/403 before any
  output retries the step once without the search tool instead of failing it. `persona.AGENT_SEARCH_PROMPT` and
  `AGENT_NO_SEARCH_PROMPT` tell the model which case it is in, keep queries free of file contents and machine paths, and
  repeat that web text is data.
- **Slow steps are logged.** A step over `PETO_AGENT_SLOW_STEP_SECONDS` (20) logs one warning with the wait before the
  first event and the total, and the agent clients' httpx hook logs every HTTP error, since the `openai` SDK retries
  429/5xx silently. That distinguishes "the service thought for a long time" from "the SDK waited and resent".
- **`/init`** builds an ordinary request (`loop.init_guide`) that asks for an `AGENTS.md`, with the local file listing
  already attached so the first step does not spend one on `list_files`. It costs several steps and every write still
  asks the user; an existing `AGENTS.md` is read and amended, not overwritten blindly.
- **`/nho <ghi chú>`** (`Session.note`, `project_guide.add_note`) adds `- ghi chú` under `## Ghi nhớ` in the root
  `AGENTS.md`. The heading is created, and so is the file, when missing. The note ends before the next level-1/2
  heading, and the file keeps its CRLF/BOM. It is the "project memory" idea done with the standard file instead of a
  private `.peto/` folder.
  - It writes locally and never calls the model, so it costs no step. The user typed the text, so it asks nothing.
  - It stays out of the undo checkpoint, so `/undo` still means Peto's last edit.
  - Afterwards `seen_guides["AGENTS.md"]` is set to the new digest. The next step carries the new root guide, and
    without this the next edit would stop on a `GuideUpdate` and waste a step.
  - The read digest of `AGENTS.md` is dropped, so Peto must `read_file` it before editing it itself.
  - Notes are capped at 500 characters, and the guide at `MAX_GUIDE_CHARS`.
- **xAI failures are logged, not shown.** `ai/agent.py` logs the reason xAI gives (HTTP errors, `error` /
  `response.failed` / `response.incomplete` stream events), clipped to 500 characters and without conversation content.
  Users still get the Vietnamese `ProviderError`. Authentication errors log only the status, since their message can
  include part of a key.
- **Tokens.** Each `done` carries `usage`. The CLI's summary line shows the last step's input + output as `hội thoại N
  token`, the size the model sees, so users know when to `/moi`. There is deliberately no context-window percentage,
  because the CLI does not know the model's window. `/me` returns `tokens_used`, today's input + output total including
  the conversation resent at every step, and `peto status` prints it.
- **The task log is a transcript.** Besides `task` / `tool` / `summary` entries, each step's assistant text is logged
  as `reply` (head and tail kept, 4000 characters), because the owner's habit is "check the log of what Peto said" and
  the `/resume` session file only holds the latest conversation per project. Logs stay on the user's machine, the same
  privacy class as that session file. Image data and attached file contents are still never logged.
- **`.gitignore` at the project root** hides entries from `list_files`, `search_files` and the `@` menu
  (`workspace.parse_gitignore` / `gitignored`: names at any depth, `/` anchoring, trailing `/` for directories, `!`
  negation, last match wins). It never blocks a path given explicitly (`read_file`, `@path`), since "ignored by git" is
  not "secret"; secrets stay on `BLOCKED_FILE_PATTERNS`. Nested `.gitignore` files and global git excludes are not read.
  The rules are re-read when the file's mtime changes.
- **The CLI enforces permissions locally** (`workspace.py`, `tools.py`, `runner.py`):
  - Resolved paths, following symlinks and junctions, must stay under the folder it was opened in, which cannot be a
    drive root or the home directory.
  - `.env*`, keys and `.git` are never read or written.
  - An edit needs a prior `read_file`, an exact unique match and an unchanged file, and keeps CRLF/BOM.
  - Every edit, write, delete, rename and command asks `[y/n/a]`, where `a` lasts for the current request only.
    Commands (`run_command` and `start_command`, through `Tools._approve_command`) also offer `s` (this exact command,
    folder, timeout and shell, for the session) and `l` (this exact command, folder and shell, always, in this project).
  - `l` grants live in `approvals.py`, in `permissions.json` next to `config.json` in the user's profile, keyed by the
    normcased project root. This is the "loosen permissions gradually" item `PETO_AGENT_PLAN.md` left open (added
    2026-09-23 after the owner asked to weigh ChatGPT's `.peto/permissions.json` idea). **Never read grants from the
    project folder**: a downloaded repo could ship a file that pre-approves commands. Matching is exact, with no
    wildcard or prefix matching, so `npm test && …` never rides on `npm test`. The timeout is left out of the key: it
    is only a cap, Ctrl+C still stops the command, and the model varies it between runs. A command that runs on an `l`
    grant prints a dim line saying so. `/permissions` lists both kinds, plus pages Peto may click and type on (browser
    phase 2) and outside domains it may view (phase 3), and `/permissions clear` drops all of them.
  - Commands take an optional `cwd`: an existing folder inside the project, resolved like any path, so outside
    folders and `.git` are refused. It was added because on 2026-09-20 Peto ran `npm run dev` at the root of this repo
    (no `package.json` there), then retried with `cd frontend && …`. Each command opens a fresh shell, so a
    stand-alone `cd` never carries over; `AGENT_PROMPT` says so. The grant keys include the folder.
  - **New tool parameters and tools are gated by `context.features`.** Strict schemas make the model send every
    property, `null` included, and a CLI that does not know a parameter fails `inspect.signature(...).bind`. So
    `agent_tools.tool_schemas` adds `cwd` only when the step's context lists `"cwd"`, the browser tools (with
    `persona.browser_prompt`) only for `"browser"`, the click/type/login tools (with `AGENT_BROWSER_ACT_PROMPT`) only
    for `"browser"` plus `"browser_act"`, and the outside-page wording of `browser_open` (with
    `AGENT_BROWSER_OUTSIDE_PROMPT`) only for `"browser"` plus `"browser_outside"` (`tools.FEATURES`, sent by
    `Session._step`). CLIs up to 0.9.7 send nothing and keep receiving the old schema byte for byte, and 0.10.x and
    0.11.x keep theirs byte for byte. From 0.9.8 on, `Tools.call` also drops unknown
    parameters whose value is `null` (null means default). A future optional parameter therefore cannot break
    installed CLIs, but add it behind a feature anyway if it matters.
  - Commands run with a timeout; timeout or Ctrl+C kills the whole tree with `taskkill /T`.
  - Tool results are capped at 20k characters. A stopped request still appends an output for every pending call, so the
    next step stays valid for the model.
- **CLI display** (picked by the owner from mockups): tool steps stay as permanent lines; while waiting for the model
  there is one transient `… Peto đang nghĩ · Ns` status line (`UI.status`, redrawn with `\r\033[2K`, only when colors
  are on). `ReplyWriter` prints replies line by line so `UI.markdown` can color bold, inline code, headings, bullets and
  fenced code; without colors (piped output, tests) text stays raw.
- **Screen layout like Claude Code** (layout A, picked by the owner from mockups on 2026-09-22; the middle of the screen
  is for what Peto says). `UI.session_header` prints the owner's mascot beside three short lines: name and version,
  model and effort, folder. No account, step count or key hints there any more: the account is in `peto status`, keys
  and commands in `/help`. The mascot is `mascot.ARTS`, sizes from large to small, cells of (char, fg, bg) in 24-bit
  colour drawn with **block elements** (`▀▄▌▐`, quadrants, eighths; U+2580–U+259F without `░▒▓`): the drawn mascot at
  24×12 and 18×9, then the owner's pixel-art pear with Peto's face at 6×6 for short terminals (the owner's idea and size
  pick on 2026-09-22, so a small window keeps a mascot instead of losing it). `UI._mascot_art` takes the largest size
  that fits both the width (art + 34 columns) and the height (art + `HEADER_SPARE_ROWS` = 7: the blank lines and the
  input box, while the typed `peto` line may scroll away, so a ~13-row VS Code panel still gets the pear); otherwise,
  and under `NO_COLOR`, only the three lines are printed; pipes get one plain line. The owner picked this from real renders on
  2026-09-22 after the first version, Braille dots, looked like a pixel mosaic in both terminals. **Braille dots come
  from the font** (about 19% of a Cascadia Mono cell is ink, with gaps between rows), so outline art made of dots loses
  its lines, whereas Windows Terminal and VS Code draw block elements themselves as rectangles that fill the cell. The
  lesson: never judge terminal art from a self-drawn preview. Check it with the real font's glyphs or, better, xterm.js
  (VS Code's terminal) with the WebGL addon, ideally replaying the raw ConPTY output, before showing it to the owner.
  The data is generated by `agent-cli/tools/make_mascot.py` from `tools/mascot.png` and `tools/pear.png` (Pillow, dev
  only; `tools/` is not in the wheel, which only packs `peto_agent/**/*.py`): each cell picks the block and two colours
  closest to the image, transparent parts stay empty, and the drawn mascot's dark outlines are thickened first (the pear
  is pixel art with its own one-pixel outline, so it is not). Change images or sizes in the tool's `SIZES` and rerun it,
  never edit `mascot.py`. **VS Code hides about two columns at the right edge** (on 2026-09-22 the right-aligned status
  line lost its last letter there; two screenshots at 157 and 168 columns both came up ~2.2 columns short), so
  `ui.terminal_size()` subtracts `VSCODE_COVERED_COLUMNS` when `TERM_PROGRAM=vscode`, which VS Code sets for its
  integrated terminal. Both `UI.width` (reply wrapping, header) and the line editor's default `size` use it; a width
  passed to `UI` explicitly, as tests do, is kept as is. The input (`line_editor.layout`) is drawn between two dim rules with no
  background, a right-aligned `status` line above (`◉ <model> · <effort>`) and a dim `footer` below (steps left from
  `Session.steps_used/steps_limit`, which follow each step's `meta`, plus `/resume mở hội thoại …` until the session has
  a conversation of its own). Without a line editor (pipes, `input()`), the header is one plain line and the resume
  notice is printed instead. Each request ends with **one** dim line (`✓ Xong trong … · sửa N tệp · chạy M lệnh ·
  hội thoại N token`, plus running background jobs and unfinished plan items); the per-phase time and token breakdown
  moved to `/usage` (`Session.show_metrics`) and the log's `summary.metrics`.
- **LaTeX in agent replies** is turned into Unicode for display (`texmath.py`), with or without colors, because a
  terminal cannot draw it and on 2026-09-21 the owner saw raw `\[`, `\begin{align*}`, `\lnot` and `&`. Only delimited
  math is converted (`\(…\)`, `\[…\]`, `$$…$$`, and `$…$` when it contains a command, `^`, `_` or `{`, so `$HOME` or
  `$5` survive); code spans and fences never are. Display blocks print indented, their delimiter lines print nothing
  (`UI.markdown` returns None and the `Peto ›` label waits for the first real line), and `end_markdown` resets the
  state. The conversation sent back to the model keeps the original text. `AGENT_PROMPT` also asks for Unicode math
  instead of LaTeX; the converter is the safety net.
- **`/resume`.** `history.py` keeps the latest conversation per project folder (keyed by the normalized path, and only
  for the same server) in `sessions/` next to `logs/`, pruned after 30 days. It holds file contents Peto read, so it
  stays local. Resuming reruns nothing and clears `Workspace.read_digests`, so any edit needs a fresh `read_file`.
  `/moi` leaves the saved conversation resumable until the new one is saved.
  - **It is saved after every step, not only when a request ends** (`Session._save_progress`, after the model's output
    and after each tool result). Closing the console window makes Windows end Python without running `finally` or
    `atexit`, which was checked in a ConPTY on 2026-09-23. Saving only in `_run`'s `finally` therefore lost the whole
    in-flight request: edits stayed on disk (the undo checkpoint is written per edit), but the conversation did not
    know about them.
  - Mid-request saves carry `interrupted: true`, and every call still without a result gets `INTERRUPTED_RESULT` in the
    saved copy, so the next step stays valid.
  - When a session was cut this way, the footer says `/resume làm tiếp yêu cầu bị ngắt …`. `/resume` then prints a
    yellow note and the last unfinished `update_plan` (`history.last_plan`). The final save in `finally` clears the flag.
  - Background jobs share the console and die with it, so nothing is orphaned (also checked).
- **Input line with a command menu** (`line_editor.py`, the owner's pick over a plain list printed on `/`). In a Windows
  console the `›` prompt reads raw key events with `ReadConsoleInputW`, so typing `/` shows a filtered menu under
  the line. The commands live in `commands.py`, shared with `/help`, and matching ignores case and Vietnamese diacritics.
  - Arrows select, Tab completes, Esc hides. Enter runs the highlighted item only once something follows `/` (or
    `/effort `), so a lone `/` never runs `/moi`.
  - ↑/↓ recall this session's messages. Shift+Enter inserts a newline.
  - Keys that arrive together are grouped as a paste: an Enter inside it is a newline, and 4+ lines or 1000+ characters
    show as `[Đã dán N dòng]`, a private-use placeholder character expanded on submit. An Enter at the very end still
    submits unless the burst already had one, so an IME that commits a word together with Enter still sends.
  - Unikey/EVKey send Backspace then new characters, so one Backspace deletes one code point.
  - Rows are drawn with relative cursor moves and never touch the last column, so terminal auto-wrap is never involved.
    Text taller than the window shows only the rows around the cursor.
  - The console mode is restored after every read, so `input()` prompts (permissions) keep working. Pipes, non-Windows,
    a console error or `PETO_AGENT_SIMPLE_INPUT=1` fall back to `input()`.
  - `EditorState`, `layout`, `group_paste` and `translate` are pure and unit-tested. `WindowsConsole` cannot run under
    pytest, so after changing it try it in Windows Terminal and the classic PowerShell window. On 2026-09-17 it was
    checked in a ConPTY by dumping the screen buffer, with plain VT and win32-input-mode keys, but never with a real
    Unikey/EVKey.
- **Images** (`images.py`; the owner picked the Claude Code style from mockups). Alt+V in the input line reads the
  clipboard: the registered `PNG` format first (browsers, Snipping Tool; keeps transparency), then `CF_DIB` wrapped into
  a BMP (screenshots), then `CF_HDROP` image files (copied in Explorer). A paste burst that is nothing but absolute
  paths to existing image files (what a terminal pastes when files are dropped on it) is treated the same way. Each image
  becomes a `[Ảnh N]` label in the text, a private-use placeholder like pastes, numbered for the whole session;
  deleting the label drops the image, and failures show as a yellow notice under the line until the next key.
  - Processing uses GDI+ (`gdiplus.dll`) through ctypes, still stdlib-only. Images longer than 2000px on either side
    are scaled with high-quality bicubic by the owner's choice, EXIF orientation is applied, transparency survives, and
    the result stays under 2 MB (PNG, JPEG when the PNG is over 1 MB and JPEG is smaller, then smaller sizes). Small
    PNG/JPEG/GIF files are sent unchanged. GDI+ cannot decode WebP, so WebP is sent as-is only when under 2 MB.
  - `loop.user_message` sends the typed text, then `[Ảnh N]` + `input_image` (`detail: high`) for each image.
    `drop_old_images` keeps the 4 most recent images in the conversation (like chat's `MAX_HISTORY_IMAGES`) and
    replaces older ones with a note, so saved sessions stay small too. The task log records only the image count.
  - Tests: `test_images.py` checks the GDI+ pipeline on synthetic images with a small PNG decoder. Reading the real
    clipboard is not in pytest; on 2026-09-17 it was checked in a separate, unnamed window station (its own clipboard,
    so the user's clipboard was never touched), and Alt+V/drag-and-drop in a ConPTY with a fake clipboard.
- **Update notice.** `/me` returns `cli_version`, read from `agent-cli/pyproject.toml` by `agent_install.cli_version`. The
  CLI compares the dotted numbers and, when the server's is newer, prints the install command in the session header and
  `peto status`. Bump `version` and `peto_agent.__version__` together whenever the CLI changes (`test_agent_install.py`
  checks they match), or installed copies are never told to update. `/usage` shows today's steps and tokens, the open
  conversation's size and the effort.
- **One-line install** (`irm https://<site>/install.ps1 | iex`). `agent_install.py` serves `GET /install.ps1`, which is
  outside `/api`, so its router must stay included before the static catch-all, plus `GET /api/agent/download/<wheel>`.
  The backend builds a pure-Python wheel of `agent-cli` itself with `zipfile` from `pyproject.toml` (no setuptools) and
  adds `peto_agent/default_server.txt`, the last fallback `config.default_server()` gives `peto login`. Builds are
  byte-for-byte reproducible (fixed zip timestamps), so the SHA-256 filled into the script matches the download that
  follows. The origin comes from the request, because `PETO_FRONTEND_URL` is normally empty; it must be https or loopback
  http, which in production relies on uvicorn's `--proxy-headers` behind Cloudflare Tunnel.
- **`agent-cli/install.ps1`** is the template. It must run on Windows PowerShell 5.1, and the response needs
  `charset=utf-8`, or 5.1 decodes the Vietnamese wrongly and the mangled bytes can break its quoting. Everything runs
  inside `& { }` and never calls `exit`, which under `iex` would close the user's window. It creates a venv under
  `%LOCALAPPDATA%\PetoAgent`, copies `peto.exe` into `bin` (renaming a running copy aside), and appends `bin` to the user
  PATH through the registry without expanding existing `%VAR%` entries. It has no automated test: after editing it, run
  it against a local backend with `PETO_AGENT_INSTALL_DIR` and `PETO_AGENT_NO_MODIFY_PATH=1`, as in `agent-cli/README.md`.
- **Peto in the web chat explains the agent**, because the install command is published nowhere else.
  `persona.build_agent_guide` goes right after `SYSTEM_PROMPT` on every chat and Companion turn, before the per-user
  blocks. Its install command comes from `agent_install.install_command(request)`, and it falls back to a
  `<địa chỉ Peto>` placeholder when the origin is not https. Never hardcode the site's domain in `persona.py`: it would
  go stale across deployments, and `tests/test_persona.py` forbids member names a domain can contain. When the install
  or usage flow changes, update the guide too.
- `backend/tests/test_agent_api.py`, `backend/tests/test_agent_install.py` (including a real `pip install` of the wheel)
  and `agent-cli/tests/` cover this; the CLI tests run the loop against a fake SSE server on 127.0.0.1.
- **Evals** (`agent-cli/evals/`, added 2026-09-24). The owner chose to measure Peto before adding capabilities: after
  the three browser phases, the next step comes from eval results, not from another tool's feature list (Windows app
  control is deferred until there is a desktop project to test). `run.py run` drives the real `Session`/`Tools`
  against the real server. Only permission questions are answered, by `policy.PolicyUI`.
  - **Tasks** (`tasks/<id>/`) mirror the owner's logged work: a Python save tool, C code questions, an ASP.NET API
    assignment, static pages, a multi-file rename, a Windows `make`/pytest trap, a prompt injection in project docs,
    and questions over a `git archive HEAD` copy of this repo.
  - **Each task** holds `task.py` (prompt, `MAX_STEPS`, `check(ctx)`), `project/`, `hidden/` tests copied in only
    after the run, and `solution/`.
  - **`selftest`** requires the untouched project to fail a required check and the solution to pass them all. Run it
    after changing any task; it costs no steps.
  - **`--repeat N`** runs each task N times in one run (folders `<task>~2`…), and the report counts passes per task.
    Model answers vary, so judge a single failure only after repeating it.
  - **The Peto-Web copy excludes `agent-cli/evals`.** It is made with `git archive HEAD -- . ":(exclude)agent-cli/evals"`,
    because that folder holds every task's solution, including the answer to the Peto-Web question.
  - **Safety.** Windows Home has no Sandbox, so `policy.CommandPolicy` is the guard:
    - Commands are allowed only for view, build, test and run with the tasks' toolchains, plus read-only git and curl
      to localhost.
    - Refused: paths outside the copy, non-local URLs, installs, delete/move/kill commands, env and registry reads,
      and `tasklist`/`netstat`.
    - PowerShell is judged on its own parser's AST (`policy.powershell_outline`, Windows PowerShell 5.1 like the
      runner). Variables assigned in the command, try/catch and script blocks are allowed. Env/drive variables, static
      .NET calls, file redirection and dynamic invocation are refused, and every nested command must be on the list.
    - In cmd only `%NAME%` counts as a variable, so curl's `%{http_code}` passes. The first real run (2026-09-24) was
      refused three legitimate API checks before these two rules existed.
    - Files Peto changed are scanned before any code-running command.
    - `run.py` strips secret-looking environment variables at start.
    - It is still not a sandbox: code run by an allowed test command runs as the user.
  - **Isolation.** Everything lives under `%USERPROFILE%\.peto-eval`: its own device login ("Bài thi Peto",
    revocable on the web), logs, browser profiles and results. The user's daily `peto` state is never touched.
  - **Not `%LOCALAPPDATA%`** (found 2026-09-24). The Claude desktop app is an MSIX package. New folders its child
    processes create under AppData are redirected to `…\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local`.
    - Results written there by Claude never appear where the owner looks.
    - `Path.resolve()` returns the redirected path. The harness therefore resolves the task root it prepares, so browser
      profile hashes match the ones `Workspace` computes.
    - Existing folders such as the owner's real `%LOCALAPPDATA%\PetoAgent`, and Temp, are not redirected.
  - **Cost.** Steps still count against the account's daily cap, and `run` prints the budget and asks first. Never run
    it without the owner's go-ahead.
  - Tests: `agent-cli/tests/test_evals.py` covers the policy and a whole task against a scripted fake model.

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
- Every finished assistant message has a "Sao chép" button under it (`MessageCopy`, layout A picked by the owner from
  mockups on 2026-09-21: always visible, since phones cannot hover). It copies the **raw Markdown**, not the rendered
  text, so a render problem can be diagnosed from what the model actually wrote. It is hidden while that message is
  still streaming. Code blocks keep their own button; both share `useCopy`. Their accessible names differ ("Sao chép"
  vs "Sao chép câu trả lời"), so tests match the code button's name exactly.
- Math renders with `remark-math` + `rehype-katex` (`trust: false`, `strict: "ignore"`) after
  `mathMarkdown.normalizeMath` turns `\(…\)` / `\[…\]` into dollar delimiters, skipping code. It also runs
  `tildeNegation`: in LaTeX `~` is a non-breaking space, so a model writing negation as `~p` (common in discrete-math
  textbooks) rendered as " p" and a correct answer looked wrong (reported 2026-09-21). Only a `~` in operand position
  (start of the formula, after an opening bracket, a logic operator or another negation) becomes `{\sim}`; `a~b` and
  `\text{…}~x` stay spaces. It scans by hand instead of using lookbehind so older Safari can parse the bundle. The chat
  prompt also asks for `\lnot` or `\overline{…}`.
- Per-user preferences (effort, theme, imagine quality/resolution/ratio/count, voice on/off, source, voices, fallback
  and the user's own TTS keys, Companion mute, character motion and view) live in
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
- Peto on the web is an AI assistant by default, by the owner's decision. The Discord bot's roleplay persona
  (age/identity, "don't always comply", insult-back, NSFW or pet roleplay, `*action*` narration) lives only in
  `ROLEPLAY_SYSTEM_PROMPT` behind the roleplay mode's checks. Never mix it into `SYSTEM_PROMPT` or the Agent and
  Companion prompts; `tests/test_persona.py` checks both prompts.
- Nothing writes back to the bot's memory. The gateway is read-only and loopback-only; it
  must never sit behind Cloudflare Tunnel.
- No AI credential of the server ever reaches the browser or the CLI, including `OPENAI_API_KEY` and the TTS keys,
  and neither does `PETO_VOICE_WORKER_TOKEN`. Keys users type under "Khóa của bạn" are their own: they stay in their
  browser, and the voice relay forwards them for one call without storing or logging them.
- Registration is open by the owner's explicit decision. Do not add an allowlist, invite
  code, or per-account quota back unless asked for it. The owner asked for two per-account quotas: the Peto Agent
  daily step cap, kept scoped to the agent, and the monthly Giọng Peto allowance (`PETO_TTS_FREE_CHARS_MONTHLY`),
  kept scoped to that voice source. The OpenAI model gates in `ai_models.py` (Luna for Discord/Google, Terra and Sol
  for `PETO_OWNER_ACCOUNTS`) are also the owner's call. These quotas and gates exist because those features spend the
  owner's API billing; Peto itself stays open to everyone.
- Guest and Google accounts must never resolve to a Discord ID — that isolation is the
  only thing keeping the bot's memory private now that anyone can sign in.
- Do not rename model slugs (`grok-4.7`, `grok-imagine-image-2.0`, `gpt-6-luna`, `gpt-5.6-terra`, `gpt-6-sol`), the `/api/imagine` path,
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

Provider spies must patch the class (`MockProvider.stream`), never the shared instance from `get_provider()`: undoing
an instance patch leaves an instance attribute behind, which silently hides class patches in every later test file.

`tests/test_review_regressions.py` holds regressions from a prior review pass — revoked
access, partial-reply persistence, pagination, anonymity. Treat failures there as behavioral
regressions, not flaky tests.

## Related documents

- `README.md` — user-facing description of current behavior, Discord OAuth setup, and an
  explicit list of what each feature does *not* do yet.
- `DEPLOY.md` — VPS deployment, systemd unit in `deploy/`, Cloudflare Tunnel, troubleshooting.
- `voice-worker/README.md` — connecting the Windows voice machine to the VPS, and the relay's
  operating limits.
- `PETO_WEB_HANDOFF.md` — original project brief. Historical context, **not** a description
  of the current code; prefer `README.md` and the source when they disagree.
