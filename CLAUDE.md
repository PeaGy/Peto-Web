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
Responses API, plus OpenAI's GPT-5.6 models as a user-selectable option (see "Model choice"). Registration is **open**:
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

### Model choice (Peto and GPT-5.6)

On 2026-09-17 the owner added OpenAI API billing and picked this design from mockups. `ai_models.py` holds the catalog
and the access rules; the server checks them on every chat turn and agent step, never trusting the UI:

- `peto` (Grok through the web's xAI account) for everyone; `luna` (`gpt-5.6-luna`) for Discord and Google accounts,
  on the web and in the CLI; `terra` and `sol` (`gpt-5.6-terra`, `gpt-5.6-sol`) only in the CLI and only for owners
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
`imagine_jobs`, `imagine_images`, `agent_devices`, `agent_usage`, `roleplay_consents`. `users` is the only place mapping
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
voice is on but the voice machine is offline, and the Chat tab's composer styles. Enabling voice,
its status, choosing a voice and "Nghe thử" live in Settings, in `VoiceSettings.tsx`.

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

Speech is generated on the owner's Windows PC, never on the VPS, and reaches listeners through the
VPS in three hops:

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
3. `backend/voice_api.py` serves signed-in users. `GET /api/voice/health` lists the voices only if a
   heartbeat arrived in the last 15 s. `POST /api/voice/speak` accepts `playful-1` or `gentle-2` and
   up to 300 characters, queues a job and waits up to 120 s for the audio: 429 when four jobs are
   already queued or this owner has one, 503 when the worker is offline or reports a failure, 504 on
   timeout. Results must be a RIFF/WAVE body under 8 MB. A listener disconnect removes the job, late
   audio is rejected instead of reaching another listener, and nothing is written to disk.
   `tests/test_voice.py` covers this with fake WAVs.

The queue and heartbeat live in process memory, so the backend must run as a **single** uvicorn
process with a single relay. A restart drops waiting jobs, and a job claimed by a relay that dies
waits out the 120 s timeout. Registration is open, so any signed-in account, guests included, can
use the owner's GPU while the relay runs; stopping the relay stops sharing. Setup and operating
limits are in `voice-worker/README.md`.

`localSpeech.ts` holds markdown → speakable text, chunking and the player, which calls
`/api/voice`; `LocalVoice.tsx` holds `useLocalVoice`, `SpeakButton` and the speaker icons. The
"local" names date from the first design, where the browser called 127.0.0.1 directly. Keep the
`peto-local-voice*` storage keys so saved choices survive, and keep those file names distinct beyond
letter case: on Windows `./LocalVoice` resolves to a `localVoice.ts` before the `.tsx`.

`useLocalVoice` is called once in `App.tsx` and passed to both Companion and `VoiceSettings`, so they
share one enabled flag, probe result and player. `speak()` returns a promise that rejects with a
Vietnamese message, and each caller shows its own error. Companion's speech keys start with
`companion-` so the Settings sample does not change Companion's status line.

- Voice stays off until the user presses "Bật giọng nói" in Settings, and nothing calls
  `/api/voice` before that. Even once enabled, the hook only probes after Companion has been opened
  or while Settings is open, so the Chat tab never calls it. `tests/Companion.test.tsx` asserts both.
- Chunks stay roughly equal (target 150 characters). Generation is only slightly faster than real
  time; the next chunk is requested when the previous one arrives, so it is ready in time only if
  it is not much longer than the one playing. One request at a time also fits the backend's
  one-job-per-owner limit. An aborted request frees that slot only once the backend notices the
  disconnect (it checks every 0.25 s), so a request sent right after an abort can get 429.
- The backend only relays text and WAV bytes. Never add TTS models or their packages to the backend
  or the frontend: `pip install` and `npm ci` on the VPS would ship them to every deployment.

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
  get a yellow notice instead. Caps: 8 mentions, 1000 lines / 60k chars per file, 120k chars per message, 200 entries
  for a directory listing. The `@` completion menu reuses the `/` command menu: `__main__._suggester` chains
  `commands.suggestions` and `mentions.suggest`, and `line_editor.create` takes the combined callable.
- **`update_plan`** renders the model's own task list (`☑ ▶ ☐`) and needs no permission, since it touches nothing. At
  most 10 items; unfinished ones are named in the request's summary line so "xong" cannot hide a half-done plan.
- **Background commands** (`background.py`): `start_command` / `read_command_output` / `stop_command`. `runner.spawn`
  is shared with `run_command`, output is collected by a reader thread into a 256 KB tail buffer, and `read` waits up to
  30 s for new output so one step is worth spending. At most 3 running jobs. They deliberately outlive a request (a dev
  server is the point) but never the session: `__main__.session` stops all of them in a `finally`.
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
- **xAI failures are logged, not shown.** `ai/agent.py` logs the reason xAI gives (HTTP errors, `error` /
  `response.failed` / `response.incomplete` stream events), clipped to 500 characters and without conversation content.
  Users still get the Vietnamese `ProviderError`. Authentication errors log only the status, since their message can
  include part of a key.
- **Tokens.** Each `done` carries `usage`. The CLI's summary line shows the last step's input + output as `hội thoại N
  token`, the size the model sees, so users know when to `/moi`. There is deliberately no context-window percentage,
  because the CLI does not know the model's window. `/me` returns `tokens_used`, today's input + output total including
  the conversation resent at every step, and `peto status` prints it.
- **The CLI enforces permissions locally** (`workspace.py`, `tools.py`, `runner.py`):
  - Resolved paths, following symlinks and junctions, must stay under the folder it was opened in, which cannot be a
    drive root or the home directory.
  - `.env*`, keys and `.git` are never read or written.
  - An edit needs a prior `read_file`, an exact unique match and an unchanged file, and keeps CRLF/BOM.
  - Every edit, write, delete, rename and command asks `[y/n/a]`, where `a` lasts for the current request only.
  - Commands run with a timeout; timeout or Ctrl+C kills the whole tree with `taskkill /T`.
  - Tool results are capped at 20k characters. A stopped request still appends an output for every pending call, so the
    next step stays valid for the model.
- **CLI display** (picked by the owner from mockups): tool steps stay as permanent lines; while waiting for the model
  there is one transient `… Peto đang nghĩ · Ns` status line (`UI.status`, redrawn with `\r\033[2K`, only when colors
  are on); each request ends with one summary line. `ReplyWriter` prints replies line by line so `UI.markdown` can color
  bold, inline code, headings, bullets and fenced code; without colors (piped output, tests) text stays raw.
- **`/resume`.** `history.py` keeps the latest conversation per project folder (keyed by the normalized path, and only
  for the same server) in `sessions/` next to `logs/`, overwritten after every request and pruned after 30 days. It
  holds file contents Peto read, so it stays local. Resuming reruns nothing and clears `Workspace.read_digests`, so any
  edit needs a fresh `read_file`. `/moi` leaves the saved conversation resumable until the new one is saved.
- **Input line with a command menu** (`line_editor.py`, the owner's pick over a plain list printed on `/`). In a Windows
  console the `Bạn ›` prompt reads raw key events with `ReadConsoleInputW`, so typing `/` shows a filtered menu under
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
  mute, character motion and view) live in
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
- No AI credential ever reaches the browser or the CLI, including `OPENAI_API_KEY`, and neither does
  `PETO_VOICE_WORKER_TOKEN`.
- Registration is open by the owner's explicit decision. Do not add an allowlist, invite
  code, or per-account quota back unless asked for it. The Peto Agent daily step cap is the one per-account
  quota the owner asked for; keep it scoped to the agent. The OpenAI model gates in `ai_models.py` (Luna for
  Discord/Google, Terra and Sol for `PETO_OWNER_ACCOUNTS`) are also the owner's call, because those models spend the
  owner's API billing; Peto itself stays open to everyone.
- Guest and Google accounts must never resolve to a Discord ID — that isolation is the
  only thing keeping the bot's memory private now that anyone can sign in.
- Do not rename model slugs (`grok-4.6`, `grok-imagine-image-2.0`, `gpt-5.6-luna`/`-terra`/`-sol`), the `/api/imagine` path,
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
