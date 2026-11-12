# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Feature notes live in `docs/notes/`, one file per area (table below).** Write a new feature note into the note file
of its area, never into this file. Keep this file under 400 lines: only what every session needs.

## What this is

Peto Web is a private chat UI for Peto, an AI assistant. The name comes from a Discord bot
(`Tracen Jukebox`) in a **separate repository**. This web app is deliberately independent:
its own database, its own xAI token file, its own persona prompt. The only link back to the
bot is a read-only memory gateway (see below).

On 2026-09-17 the owner made the default persona an honest, helpful AI assistant (now `prompts/core.CORE_PROMPT`
plus `prompts/chat.WEB_PROMPT`): it says it is Peto, an AI assistant, addresses users as "bạn", and refuses only
genuinely harmful requests. By the owner's call it never names the model behind it (no Grok or xAI in any prompt), and
`tests/test_persona.py` checks that. The bot's roleplay character survived as an opt-in roleplay mode until 2026-10-18,
when the owner removed it (see the section at the top and "Roleplay mode (removed)"). Peto Agent uses the same core.
Companion has its own persona, `COMPANION_SYSTEM_PROMPT` (see "Companion persona" under "Companion tab and voice
relay").

Stack: FastAPI + SQLite (aiosqlite) backend, React 19 + Vite frontend, xAI Grok via the
Responses API, plus OpenAI's GPT-6 models as a user-selectable option (see "Model choice"). Registration is **open**:
Discord, Google or GitHub — there is no allowlist.

## Where to read before working on an area

Read the area's note file before changing code there. Each file puts current behaviour first, then a dated log
(newest first). `docs/notes/unverified.md` lists what was never tried for real (live models, real keys, real devices).

| Area | Read first |
| --- | --- |
| Web Chat: providers and models, `POST /api/chat`, work log, tools, web search, sources/citations, long context, recovery, prompts, Chat UX, Brain Benchmark | `docs/notes/chat.md` |
| Attachments and readers (PDF/OCR, Word, Excel, logs), generated Word/PDF, Mermaid diagrams, slides, spreadsheets, editing uploaded Excel/Word | `docs/notes/documents.md` |
| Companion: stage, characters and cards, voice relay and sources, hearing, emotions, private notes, web search, MAGIC, Companion settings, own API keys, Minecraft plan | `docs/notes/companion.md` |
| YouTube Player inside Companion and Companion controlling it | `docs/notes/player.md` |
| Imagine (image generation) | `docs/notes/imagine.md` |
| Peto Agent CLI (`agent-cli/`), `/api/agent/step`, TUI, tools, browser, evals, multi-source models | `docs/notes/agent-cli.md` |
| Peto Harness desktop app (ph), `/api/agent/v1` gateway, `/download/` page, desktop auto-update, Agent web search | `docs/notes/agent-gateway.md` |
| Backend layout, ops tools, `/admin` dashboard, configuration, database | `docs/notes/admin-ops.md` |
| Public guides at `/docs/` | `docs/notes/docs-site.md` |
| Static serving and routing, Settings and account menu, Motion setting, frontend conventions | `docs/notes/frontend.md` and `DESIGN.md` |
| Identity and isolation, profile and avatar, Discord memory gateway, Peto's memory | `docs/notes/accounts-memory.md` |

Planning files (gitignored, only on the owner's machine): `PETO_AGENT_PLAN.md` (Agent/CLI), `PETO_COMPANION_PLAN.md`
(Companion; read before any Companion work), `PETO_MINECRAFT_PLAN.md` (nothing built yet).

## Language convention

**Every comment, docstring, log message, error message, and user-facing string in this
codebase is written in Vietnamese.** Keep it that way when adding code — an English error
string would be visibly out of place in the UI. Identifiers, type names and this file stay
in English.

Model instructions are the exception: every system prompt in `backend/prompts/` is English, for every model (Chat,
Agent, Companion). Replies still follow the user's language, defaulting to Vietnamese with full diacritics. Raw user
messages, memory, preferences, project guidance and documentation are never translated. Tool schemas, validation,
user-facing errors and logs stay Vietnamese (Agent tool descriptions are English only for CLIs that declare
`english_tools`). Notes in `docs/notes/` follow the same rule as this file (English), except passages that were
written in Vietnamese, which stay Vietnamese: when moving notes, never translate or rewrite them. Details:
`docs/notes/chat.md` ("Model instructions in English").

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
cd frontend && npm run test:browser              # Chromium PC/mobile, mocked API and checked-in Windows screenshots

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

Short map; the full sections are in the note files named in each line.

- **Two run modes.** Dev is two processes: uvicorn serves the API and Vite serves the UI, proxying `/api`. Production is
  one process: `core/static_files.py` serves `frontend/dist` from the backend (one port for Cloudflare Tunnel, no
  nginx). Its catch-all route must stay registered after every API route (last statement in `main.py`), and it serves
  `index.html` only for declared app paths. Details: `docs/notes/frontend.md`.
- **Backend layout.** `main.py` is the `uvicorn main:app` entry; `core/lifespan.py` owns startup; feature routers and
  services live under `features/`, shared tools under `shared/`, SQLite schema and queries under `storage/`, prompts
  under `prompts/`. See `backend/README.md` and `frontend/README.md`; details in `docs/notes/admin-ops.md`.
- **`owner` is the tenancy key** (`discord:<id>`, `google:<id>`, `github:<id>`, built by `config.owner_key`). Every
  query in `storage/` takes `owner` and filters on it in SQL; another owner's id gives 404. The server never accepts a
  Discord ID from the browser; the session cookie holds only the owner key. Only `discord:` owners reach the Discord
  memory gateway. Details: `docs/notes/accounts-memory.md`.
- **AI provider layer.** `ai/base.py` defines `ChatProvider.stream()`, yielding text or `StreamChunk` values; nothing
  outside `backend/ai/` knows which provider runs. `ai/models.py` holds the model catalog and access rules (Peto/Grok
  for everyone, Luna and Haiku for signed-in accounts, Terra/Sol/Sonnet owner-only in Agent); `get_provider(model)`
  caches one provider per model. Providers raise `ProviderError` with a Vietnamese, user-facing message. Tool loops run
  inside the provider. `PETO_AI_PROVIDER=mock` needs no network. Details: `docs/notes/chat.md`.
- **`POST /api/chat` lifecycle.** Returns SSE (`meta`, `delta`… then `done`, `error` or `stopped`). The whole turn runs
  inside `admission.slot(owner)`, so throttling happens before any message is written; ownership is re-checked inside
  the slot; SQLite writes are shielded from cancellation; failures still persist partial text as `incomplete`; there
  is no automatic retry of a paid turn; Stop is acknowledged through `POST /api/chat/stop`. Background tasks, the
  voice relay queue and the Agent device codes are process-local, so the backend runs as a single process. Details:
  `docs/notes/chat.md` ("Chat request lifecycle").
- **Configuration and database.** Environment variables are read in `core/config.py` (numbers clamped) and documented
  in `.env.example`; the two exceptions are listed in `docs/notes/admin-ops.md`. SQLite via aiosqlite in WAL mode; schema upgrades are manual `PRAGMA table_info` + `ALTER TABLE` at
  startup, with no migration framework. Details: `docs/notes/admin-ops.md`.

## Invariants — do not break these

- **Never** point `PETO_WEB_DB` or `PETO_XAI_TOKEN_PATH` at the Discord bot's files
  (`bot_memory.db`, `.xai_tokens.json`). Separate database, separate tokens, no shared files
  with the bot's production data.
- `prompts/` must not contain real names or Discord IDs of members — `tests/test_persona.py`
  asserts this. Personal context is loaded per account at runtime, not baked into the prompt.
- Peto on the web is an AI assistant, by the owner's decision. The Discord bot's roleplay persona (age/identity,
  "don't always comply", insult-back, NSFW or pet roleplay, `*action*` narration) is not in any web prompt since
  roleplay mode was removed on 2026-10-18. Never add it to the Chat, Agent or Companion prompts;
  `tests/test_persona.py` checks them. Since 2026-10-25 users may write their own Companion persona in a character
  card (see the section at the top); that is their text, the built-in prompts stay as they are, and the fixed under-18
  rule is always appended.
- Nothing writes back to the bot's memory. The gateway is read-only and loopback-only; it
  must never sit behind Cloudflare Tunnel.
- No AI credential of the server ever reaches the browser or the CLI, including `OPENAI_API_KEY` and the TTS keys,
  and neither does `PETO_VOICE_WORKER_TOKEN`. Keys users type under "Khóa của bạn" are their own: they stay in their
  browser, and the voice relay forwards them for one call without storing or logging them.
- Registration is open by the owner's explicit decision. Do not add an allowlist, invite
  code, or per-account quota back unless asked for it. The owner asked for two per-account quotas: the Peto Agent
  daily step cap, kept scoped to the agent, and the monthly Giọng Peto allowance (`PETO_TTS_FREE_CHARS_MONTHLY`),
  kept scoped to that voice source. The OpenAI model gates in `ai/models.py` (Luna for signed-in accounts, Terra and Sol
  for `PETO_OWNER_ACCOUNTS`) are also the owner's call. These quotas and gates exist because those features spend the
  owner's API billing; Peto itself stays open to everyone.
- Google and GitHub accounts must never resolve to a Discord ID — that isolation is the
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

The Brain Benchmark (`backend/evals/`) is described in `docs/notes/chat.md`; Agent evals in `docs/notes/agent-cli.md`.
Never run paid benchmarks or evals without the owner's go-ahead.

## Related documents

- `DESIGN.md` — frontend visual and copy conventions (see "Frontend conventions").
- `README.md` — deliberately short (rewritten 2026-09-30 at the owner's request, from 674 lines): what the project is,
  how to run, configure, test and deploy it, and links. Do not grow it back into a manual: behaviour belongs in this
  file and in `/docs/`.
- `DEPLOY.md` — VPS deployment, systemd unit in `deploy/`, Cloudflare Tunnel, troubleshooting.
- `voice-worker/README.md` — connecting the Windows voice machine to the VPS, and the relay's
  operating limits.
- `PETO_WEB_HANDOFF.md` — original project brief. Historical context, **not** a description
  of the current code; prefer this file and the source when they disagree.
- `docs/notes/` — per-area feature notes moved out of this file on 2026-11-12; `docs/notes/check_migration.py`
  checks that the move lost nothing.
