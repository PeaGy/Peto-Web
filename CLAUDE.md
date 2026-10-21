# CLAUDE.md

## Web Chat request context — stage 2 (2026-10-21)

The owner approved stage 2 after deploying and live-testing stage 1. See
`backend/features/chat/docs/request-context.md` and the four-stage roadmap. Stages 3–4 remain planned.

- `features/chat/request_context.py` binds an immutable Web Chat snapshot only around the main reply, after account,
  conversation/project/model checks and context preparation. It carries request/conversation/project IDs with
  provenance, authorized model selection, actual provider/API model and effective effort, fresh server clock and
  validated-browser/default/invalid-timezone provenance. No owner ID, credentials, raw UA, inferred device or billing.
  Client IDs/preferences never grant permissions. Concurrent requests and cancellation reset the ContextVar.
- `features/chat/capabilities.py` selects one `ToolPlan` per provider round. The exact plan supplies portable native
  schemas, the snapshot's available/disabled/unavailable/unauthorized entries and a dispatch allowlist. Required-search
  first rounds, finalization, side calls, missing file/history scope and GitHub readiness use this same selection.
  A fabricated function call outside that round's plan returns an error without running a handler. Handler-specific
  owner/input/current-connection checks remain mandatory; availability does not prove a tool succeeded.
- GitHub readiness uses local encrypted connection state, not a network probe. Status and dispatch share the same
  refresh/reconnect predicate, including the 60-second refresh window. Connected sessions recheck readiness each
  round and access again before each tool. No repo permission is assumed from merely having a connection.
- File-reading capability reports bounded cached reader states, including unparsed/unreadable; it does not open all
  files or claim they were fully read. History lookup now describes nullable fields and pagination, accepts an empty
  query as chronological reading, bounds SQLite integers and returns actionable validation feedback without arguments.
- Claude's existing native-tool translation is reused for the manifest (including its real web_fetch tool), so it is
  not a second feature table. Volatile snapshot/clock blocks sit after the stable system cache breakpoint. Request
  budgets still validate the final instructions/tools/input every round. Agent/Companion receive no Chat snapshot;
  saved personal memory stays shared under the existing account policy. No CLI version/bundle update is required.
- Tests in `backend/tests/test_chat_request_context.py` use temporary SQLite and fake providers/streams. These verify
  structure, scope, tool enforcement and provider translation, not semantic truthfulness of a deployed model.
  Related regression: 163 passed; full backend: 1,483 passed, 1 skipped (274.90s). After the final malformed-credential
  guard, request-context/GitHub tests: 64 passed. `git diff --check` passed. No commit, deployment or paid API call.

Live check after the owner deployed `0f9ec2d`: Peto/Luna clock/effort/web toggle/capabilities and scoped file search
worked. Haiku's clock completed round 1 but its continuation returned HTTP 400. Current Anthropic docs bind Haiku 5.5
thinking signatures to the entire preceding system/tools/messages prefix; the per-round Chat snapshot changes it.
`ClaudeClient.create` now disables replay of whole thinking/redacted_thinking blocks only when the Web Chat snapshot
is present, retaining all other native blocks, function calls/results and history. No altered signatures, beta flags,
or billed retry; Agent/Companion keep default replay. Tests simulate signature rejection on prefix change, including
redacted thinking. The owner deployed patch `64c3797`; a fresh Haiku/low/web-OFF clock request completed in about
6 seconds without the continuation error. Memory was already restored ON for this follow-up; model/effort/web were
restored to Peto/auto/AUTO afterward. One Luna reply after the earlier failed turn followed that old request instead
of the new file question; recorded for stage 3 recovery work, not diagnosed as a reader bug. Details in `request-context.md`.
Validation of the patch: related tests 153 passed; full backend 1,489 passed, 1 skipped (284.44s); final
Claude/request-context group 66 passed (includes a spoofed heading that must not enable the server-bound behavior).

## Web Chat long context — stage 1 (2026-10-20)

The owner approved a four-stage Web Chat roadmap, starting with long context. The plan and gates are in
`backend/features/chat/docs/roadmap-2026-10-20.md`; implementation details and production limits are in
`backend/features/chat/docs/long-context.md`. Stage 2 is documented above; stages 3–4 remain planned.

- `features/chat/context.py` prepares the exact recent messages under a model/deployment budget and adds a portable
  rolling summary, a bounded first-user anchor, file metadata and explicit unrepresented-message counts. Source
  messages are never replaced. Saved personal memory stays shared Chat/Companion by the existing product policy;
  the Chat summary is independent of its toggle. Companion's summary and Agent's runtime are unchanged.
- `storage/chat_context.py` stores one versioned projection per owner/chat/project, source spans, a character cursor,
  model **service/API-ID**, timestamp and chained digests. Each update validates the read fragments and prior digest
  again under an immediate SQLite transaction. Edits/deletes affecting the covered prefix and project moves
  invalidate it; forks start their own context and conversation deletion cascades. Corrupt v1 caches are rebuilt;
  future schemas are not overwritten. This is summary provenance, not an exactly-once tool journal.
- At most one summary call per incoming turn, through the selected Web model, low effort, tools/web disabled,
  no new retry layer, 16,000 source characters/32 messages per batch, 3,072 output tokens and a default 20-second
  timeout. Structured JSON validation rejects invented source IDs, empty or malformed responses. Cancellation
  propagates. Failure keeps the last good cursor; old chats can retain a backlog explicitly marked as unread.
  Calls spend the provider's normal quota/billing; mock validation does not establish semantic model quality.
- `features/chat/context_budget.py` owns Web limits, separate from Agent execution. Its small catalog snapshots
  already verified API IDs (see CLI context-budget notes), with conservative fallback and JSON overrides by exact
  API-ID. The application input cap defaults to 64,000 estimated tokens. Images are estimated separately from
  base64, with a margin; reserves cover tools/summary/output. `ResponsesProvider` checks the actual portable request
  before **every** provider round. Overflow is explicit and never slices tool call/result protocol. This estimator
  is not provider tokenization or billing, especially for images/encrypted reasoning. Side-call output allowance is
  raised only while the Chat summary budget is bound; existing other side calls keep their 1,024-token ceiling.
- `shared/chat_history_tools.py` registers native `read_chat_history` only when old context is hidden. It is bound
  server-side to owner/chat/current source boundary, returns source IDs, character pagination, original citations,
  file refs and stopped/incomplete state. No cross-chat search or model-supplied ownership/path exists. History is
  reference data, not live instructions. `AttachmentFiles` and document-edit sessions receive bounded metadata from
  the conversation's older uploads and verified generated versions, without loading all old files into the prompt.
- Tests in `tests/test_chat_context.py` use mocked providers/temporary SQLite, covering all three Web selections,
  memory OFF, correction precedence, character cursors, CAS races, fork/edit/delete/project scope, cancellation,
  corrupt cache/migrations, native tool continuation and per-round budgets. No paid/live API test or deployment
  was authorized as part of this implementation. No CLI bundle/version update is needed.

## Multi-source models: M0–M3 (2026-10-20; CLI 0.31.0 source)

Owner handed over Codex's roadmap `agent-cli/docs/provider-integrations-roadmap.md` (Peto source, own API keys, ChatGPT
plan via OAuth, `/connect` and `/models` like OpenCode). M0 decisions are in `agent-cli/docs/provider-integrations-m0.md`:
direct sources run locally in the CLI (not relayed through the VPS like Companion BYOK); shared prompts/schemas will be
generated from pure backend modules into `peto_agent/bundle/` with a parity test (M3); Windows DPAPI via ctypes for
secrets, no plaintext fallback; sessions stay namespaced by the configured Peto server so a session survives a source
switch. ChatGPT plan usage is documented by OpenAI for "open-source and locally hosted apps"; the public repo has no
license, so the owner must license the CLI or file OpenAI's interest form before M5.
M1: `peto_agent/providers/` (`contract.Selection`/`ModelRequest`, `errors.classify`, `peto.PetoSource`,
`gateway.ModelGateway`). Every model call (work, wrapup, compact, title, btw, explore) goes through `Session.models`;
`Session.selection()` is taken once per logical step (retries and the post-compaction retry reuse it; explore once per
run). The Peto source forwards the unchanged body to `/api/agent/step` through the journaling `RuntimeClient`, which pops
the new `source` keyword and records it in `model.started`; nothing new is sent to the server. Error logs gain a shared
`category`. Title still uses model `peto`. `peto_agent.providers` is listed in `pyproject.toml`; the installer test
imports it from the installed wheel. Baseline before changes: CLI 673 passed; after, one full run 696 passed and
backend Agent API/schema/installer 95 passed. All mocked; no live server run.
Owner chose MIT for the CLI (2026-10-20): `agent-cli/LICENSE` (with opencode's MIT notice for ported parts); the wheel
builder writes `License: MIT` and ships `<dist-info>/LICENSE`. The web app and server are not under that licence.
M2: `Selection.connection`, `budget_key` (Peto keeps the server key, others `source:connection:model`) and
`opaque_scope`. `Session.select(source, model, connection=)` refuses while a request runs, keeps the session id, task
state and tool results, and drops opaque items (reasoning, web_search_call, item ids) whenever source, connection or
model changes; resume uses the same rule (`_compatible`). Peto-source sessions still save as history v2; other sources
save as v3 (`SOURCE_VERSION`, JSON and journal snapshot alike) so old CLIs skip them instead of opening them on Peto.
`history.newer_sessions` lets `/resume` report files from newer CLIs without touching them. The gateway journals every
source (`RuntimeClient.journaled`; Peto is `journals_itself`). Tests: `tests/test_model_continuity.py` with a fake
source; full CLI 708 passed in one run.
M3 (own OpenAI API key, CLI 0.31.0 source): `peto connect openai` (getpass, or one stdin line when piped) checks the key
with `GET /v1/models` (no tokens), keeps only catalog `gpt-` slugs, saves the key with DPAPI (`credentials.py`,
`%APPDATA%\PetoAgent\credentials\<id>.bin`, entropy bound to the connection id) and the non-secret profile in
`connections.json` (`connections.py`), then selects the cheapest model (`config.json` `selection`; Peto keeps `model`).
`peto connections`, `peto disconnect <id>`; `/model` lists Peto models (only when `/me` answered) plus direct ones and
switches with `Session.select`. Direct mode needs no Peto login: a token-less `Client` keys sessions by the saved server,
else `default_server.txt`, else `http://localhost` (sessions saved under that key are not visible after a later login to
another server). With a login, startup still reads `/me` with a 5 s timeout and ignores its failure.
`providers/openai_key.py` calls the Responses API directly (`providers/transport.py`: HTTPS or loopback only, no
redirects, threaded SSE reader, size caps; errors carry only status/code/clipped message) and maps events to the CLI
contract with Vietnamese messages and `code` categories (401/403/404/429 quota are not retried; 429 rate limit, 5xx
and drops before output are). Prompts/schemas come from `peto_agent/bundle/`, generated by
`agent-cli/tools/make_bundle.py` from the pure backend modules (`prompts/core|agent|providers.py`,
`features/agent/tools.py` and the new `features/agent/assembly.py`, which `api.py`/`budget.py` now delegate to; 2,240
sampled server contexts produced identical instructions/tools/budgets). `provider_prompt` now takes a service name.
Direct features = CLI features present in the bundle; Peto features stay negotiated (`Session.source_features`). Web
search is off for direct sources; time comes from the local clock with "local machine time" and the real UTC offset.
Title, btw, compact, wrapup and explore use the session's selection (title at low effort); `_observe_steps` keeps the
Peto step counter when a direct `meta` lacks it. Fixed while testing: `assembly.limits` raised when no override was
passed. Tests: `agent-cli/tests/test_direct_source.py` (fake OpenAI server on 127.0.0.1, fake Peto server counting
requests: only the startup `/me`, zero `/step`, also with Peto out of steps or offline; key never in session files,
journal, logs, export, request bodies or env; Ctrl+C; redirects; connect/disconnect; bundle and handler parity) and
`backend/tests/test_agent_bundle.py`. Full CLI 725 passed in one run (242s); backend Agent/prompt/model/
installer 197 passed. No real OpenAI key or paid call was used; live behaviour with a real key is unverified.

## Multi-source models: M5 Continue with ChatGPT (2026-10-21; CLI 0.33.0 source)

The owner approved M5 from an OpenCode "Connect OpenAI" screenshot. Rereading OpenAI's docs corrected M0: the open-source
local path needs no requested client ID; each account registers dynamically (`client_id=dynamic_agent_client`, the
callback returns the issued ID; no client secret). "Request a client ID" is the commercial-partner waitlist. Owner's
picks: verify the RS256 ID token with the standard library instead of adding `cryptography`, and keep OpenAI's exact
English strings ("Continue with ChatGPT", "Use your ChatGPT plan", "Using ChatGPT plan", "Manage usage", "You're using
your ChatGPT plan"/"Got it") with Vietnamese around them.
- `jwt_rs256.py`: verify-only RSASSA-PKCS1-v1_5/SHA-256; recomputes the full EMSA encoding and compares bytes, rejects
  keys under 2048 bits, even exponents, `alg` other than RS256.
- `chatgpt_auth.py`: endpoints from `auth.openai.com/.well-known/openid-configuration`; persistent opaque
  `ext_agent_host_id` (`config.json`); fresh PKCE S256/state/nonce; `Callback` on `127.0.0.1` (port 1455 else any) opened
  before the browser, ignoring other states; code exchange with the issued client ID and the same redirect URI; ID token
  checked against JWKS plus iss, aud, exp (120 s leeway), nonce; plan only with `chatgpt.tokens.use.direct`, otherwise an
  identity-only connection; reauth with client ID, `id_token_hint` (never shown), `login_hint`, rejecting another `sub` or
  client ID; token record (`credentials.save_record`, DPAPI, 64 KB) refreshed serially under a file lock, rotating
  refresh token saved atomically, terminal refresh errors mark `signed_out` and keep the client ID; `revoke` on delete;
  `registrations()` keeps sub → client ID after deletion; `store()` saves or updates by `sub` and lists models
  (`GET /v1/models`, `visibility == "list"`, server order). Tests monkeypatch `ISSUER`/`API_BASE`; no env override.
- `providers/chatgpt.py` subclasses the OpenAI key source (`_payload`/`_failed` hooks added there): field allowlist, no
  `max_output_tokens`, tools wrapped in namespace `peto`, old function calls given the namespace, system-role items
  dropped; `loop.portable()` strips `namespace` when switching sources. Errors follow "Errors and recovery":
  usage limit points to Manage usage (no OAuth loop, no switch to a paid key), 401 before output refreshes once and
  retries. `transport` gained form posts and parses OAuth `error` strings, `detail` and `param`.
- UI: `/connect` → OpenAI shows "Kết nối OpenAI" (Continue with ChatGPT, Khóa API; no Codex legacy rows, which borrow
  Codex's client ID) or the account list (Gói ChatGPT, Khóa API, Đã đăng nhập trước đây); waiting dialog via
  `dialog_busy(on_key=…)` (esc cancels, c copies the URL); one-time welcome; prompt footer "Using ChatGPT plan · Manage
  usage: /usage"; `/usage` separates "Gói ChatGPT" from own keys. `peto connect chatgpt` for the text UI;
  `peto disconnect` revokes. `catalog` and the gateway register `chatgpt-plan`.
- Tests: `tests/test_chatgpt.py` (fake auth+API server on 127.0.0.1, fixed test RSA key signing ID tokens, browser stub
  that calls the callback; `webbrowser.open` is always stubbed). An early run before that stub may have opened one real
  browser tab on the fake loopback URL. Full CLI run 745 passed in one run; backend installer/bundle 9 passed. Not yet
  accepted with a real ChatGPT account, which is M5's completion criterion.

## Multi-source models: M4 `/models`, `/connect`, `/usage` (2026-10-20; CLI 0.32.0 source)

The owner tested `peto connect openai` with a real key, then asked for M4 and, after seeing three mockups, sent OpenCode
2.0.29 screenshots: make it look like OpenCode. `tui/dialog.py` ports OpenCode's `dialog.tsx`, `dialog-select.tsx` and
`dialog-prompt.tsx` (MIT): a centered 60-cell panel a quarter down the screen over the conversation dimmed with black at
150/255, bold title with a clickable "esc", search line with a block cursor, accent-bold category headers, the selected
row filled with primary, "●" on the current item, right-aligned footers, action hints at the bottom, "…" when the list
scrolls, press-twice confirmation (`arm`). `SelectDialog` options marked `searchable=False` (Favorites/Recent copies)
disappear while searching, where the source moves to the right like OpenCode. `ScreenEngine._float` composites a
`Panel(overlay=True)` over the dimmed rows; a click outside is Esc; `guard=False` skips the 0.3 s permission key guard.
`TerminalUI.dialog()` and `dialog_busy()` (slow work such as the key check keeps the panel up; Ctrl+C interrupts).
`model_catalog.py` holds every model row (Peto rows from `/me` at session start, direct rows re-read from
`connections.json` each time), display names (`gpt-6-luna` → "GPT-6 Luna"), categories, and `favorite_models`,
`recent_models` (10), `set_default` in the user-profile `config.json`. `model_dialogs.py`: `/models` (Favorites, Recent 5,
then per source; `ctrl+a` sources, `ctrl+f` favorite, `ctrl+d` set default; asks for an effort when the new model lacks
the current one), `/connect` (Popular: Peto with account, OpenAI with key count; OpenAI with no key goes straight to the
key prompt, else a key list with add, `ctrl+r` rename (`connections.rename`), `ctrl+d` twice delete; after connecting it
opens that key's models), `add_key` (masked prompt, deviation from OpenCode, `secret_problem`, `/v1/models` check under
`dialog_busy`, `connections.next_label`). Following roadmap M4, switching a model changes only the open conversation (it
used to rewrite the default); `/resume` restores the conversation's own model when the catalog still has it; a lost
default prints a yellow notice at start instead of silently switching; deleting the key in use switches with a notice.
`ModelGateway` wraps every stream in `_Counted` (not a generator, so closing an unstarted stream still closes the inner
one) and sums calls/input/output/cached tokens per (source, connection) for `/usage`, which now prints model and source,
today's Peto steps, conversation context, and own-key tokens labelled as provider-reported, not an invoice. The prompt
meta shows the source muted after the model ("GPT-6.1 Sol OpenAI"). New `peto models [--json]` and
`peto models default <name>`; `/models` and `/connect` in `command_catalog.json` (since 0.32.0). ChatGPT stays hidden
until M5. Without dialogs (pipes, classic UI) `/models` prints the list and `/connect` points to `peto connect openai`;
keys never pass through slash commands, input history or session files. Tests: `tests/test_dialogs.py` (dialog render
and keys, overlay on the fake screen, models flow, effort prompt, connect with a fake OpenAI server on 127.0.0.1 with the
key absent from the screen and disk, rename and delete, resume model, lost default) plus updated `test_loop_client`,
`test_direct_source`, `test_line_editor`, `test_mentions` for the new semantics. Final full CLI run: 735 passed in one
run; backend installer/bundle tests 9 passed. Preview frames rendered from the real code: https://claude.ai/artifact/PVSuM2R7r9JJzmdxy7ZR1x. Not
checked in a real Windows Terminal or VS Code, nor with a real key.

## Model-aware context and Sol 6.1 (2026-10-20; CLI 0.30.0 source)

Owner explicitly requested OpenCode-style context budgeting and upgrading 6 Sol to 6.1 Sol. See
`agent-cli/docs/context-budget-0.30.0.md`; reference remains offline OpenCode 2.0.32 commit
`22e771f5893e255ea78fc10557ed3fb98d3a1072` (MIT), no upstream code/scripts executed.
Backend features/agent/budget.py owns verified API-ID context/input/output catalog and deployment caps; /me returns
allowed models' context_limits and context_transport. Negotiated context_budget adds meta budgets, instruction/tools
overhead and fit max_output_tokens. CLI budget.py anchors provider-normalized input+output usage (cache/reasoning
already included), estimates new content with UTF-8 bytes/4 + 15%, and invalidates anchors on model/reset/resume/compact.
Default reserve is 10% or 16k for a sufficiently large window. Current catalog: Grok 4.7 500k; GPT Luna/Terra/Sol 1.05M;
Claude Haiku/Sonnet 5.5 1M. Output deployment caps unchanged. Unknown API IDs use known=false, conservative 200k app
budget; admin PETO_AGENT_CONTEXT_LIMITS JSON overrides context/input/output by actual API ID. Sources are in the doc.
New mode keeps roughly 15k recent tokens (less for small windows), respects tool/signed Claude groups, and can compact
a single exchange whole. Transport still caps 300 items/AGENT_MAX_REQUEST_BYTES, so compact at 240 items/80% bytes
independently of token %. Old servers/clients retain old behavior and exact tool schemas.
Classified context_overflow before any produced content triggers one compact-and-retry of a work request. Server
preflight/provider rejection refunds unproduced steps under existing rules; partial output is not marked recoverable.
Oversized compaction requests flatten only their transport view with explicit clipped-tool/assistant notes, then
shrink at 70/50/35% of the first rejected request, at most three shrinks. User requests are never clipped; unfit fixed
requirements stop rather than discard them. Canonical journal/archive and durable acceptance are preserved.
Model key sol remains stable; label 6.1 Sol, slug gpt-6.1-sol, owner/agent-only and step_cost=4 unchanged. Supported
efforts low/medium/high/xhigh/max (no none/minimal); CLI uses the supported list for saved settings. Provider stays
Responses, other model roles/keys and BYOK/historical slugs unchanged. Optional model_identity in Saved/JSON/journal
lets resume drop stale opaque reasoning when an alias now points to a different model (or old identity is unknown),
while preserving visible conversation/tool results. Same identity retains reasoning; no automatic tool replay.
Validation: final full CLI 673 pass, 237.41s; final estimator refinement 17 focused pass. Initial full had an old-label
fixture failure and a Ctrl+C timing failure; final full passed without relaxing the timing assertion. Backend full
1412 pass/1 skip/1 new fixture failure (wrong zero starting-balance assumption); fixed fixture then all 140 related
API/model/prompt/schema/installer cases pass, final budget/provider-routing recheck 7 pass. No single full-green backend
rerun claimed. Compile/diff checks pass. Tests are mocked, no paid calls, commit/deploy/installed update or game writes.

## Tolerant text/log reader (2026-10-19)

The owner's Minecraft report was valid UTF-8 (75,168 bytes) but rejected before any model call because it contained
seven NULs in nvspcap64.dll version metadata. `features/documents/text_reader.py` now supplies the shared decoder
used by upload validation, excerpts and full attachment search/line reads. Strict UTF-8/BOM UTF-16/UTF-32 decoding;
no Latin-1 fallback or lossy replacement. Sparse C0/C1 controls other than TAB/CR/LF become visible `[U+XXXX]`
markers, with a notice/count. More than 1% controls or 4096 total is rejected. Preserve original uploaded bytes and
line breaks; even short excerpts retain leading/trailing blank lines so line tools and context agree.
`reader.py` keeps `decode_text` as a compatibility import. New text results carry text_format=1, encoding and
normalized_controls. Global reader VERSION stays 3 to avoid invalidating PDF/Word/Excel/OCR caches. Old long-text
excerpts (recognized by their existing "Tệp dài " notice) expire through Chat's bounded legacy re-read path.

Long-log selection prioritizes Caused by/Suppressed/Description/fatal/critical/panic/Traceback, then errors, then
warnings, retaining source order and true line numbers. Oversized candidates are skipped rather than stopping the
search. This is deterministic excerpt selection, not semantic diagnosis; full search/read tools remain available.
No model/provider prompt change, frontend change, new dependency or CLI update. User's actual file passed validation,
process extraction (~366 ms locally, not AI latency), search and read at line 114; 608 lines and original SHA-256
unchanged, all 12 unusual controls made visible. Synthetic fixtures avoid committing the private crash report.
Validation: focused reader/document/attachment tests 67 pass; full backend 1408 pass, 1 skip. Changed Python modules
compile and `git diff --check` passes. Provider tests are mocked; no paid calls, commit, deployment or original-file
changes. Deploy/restart backend for the fix; the local parsing time does not measure model response latency.

## English Agent tool descriptions (2026-10-19; CLI 0.29.1, needs the backend deployed)

The owner asked to translate the Agent tool descriptions, the largest Vietnamese part still resent at every step.
Feature `english_tools`: the server lists it in `/me agent_features`, CLI 0.29.1 declares it in `NEW_FEATURES`, and only
then `tool_schemas`/`explore_schemas` return `_english(...)` copies. Every Vietnamese description in
`backend/features/agent/tools.py` registers its English text beside it through `_en(vi, en)` (the `EN` map), so the
Vietnamese schemas stay byte-identical: all 196,610 checked feature/model combinations matched the pre-change output,
and the 0.29.0 set (Peto and GPT) is now pinned too. Names, parameters, enums, required lists and order are identical;
only description text differs (`test_english_tools_only_changes_description_text`). The literal "(nên chọn)" stays in
`ask_user`, because the eval `PolicyUI` picks the option carrying it. Tool results, CLI notes and Web Chat tool schemas
(documents, attachments, GitHub) are still Vietnamese. Size on the full 0.29 set: descriptions 11,919 → 10,763
characters and 2,520 → 1,788 words; whole schema JSON 22,367 → 21,211 characters (25,868 → 21,224 UTF-8 bytes).
Token counts were not measured (no offline tokenizer, no paid call); the schemas sit in the cached prefix, so the money
saved is smaller than the token count suggests. The translations kept the old "The user must approve" wording even
though 0.28.5 made allow the default permission. Tests: backend `test_agent_tool_features.py` (pins, structure,
coverage, marker) and `test_agent_api.py` (negotiation); CLI `test_fewer_steps.py` and the existing backend/CLI
handler contract test, which now also runs with `english_tools`.

## Durable Agent runtime, inbox and acceptance (2026-10-19; CLI 0.29.0)

Owner approved the three reliability upgrades based on OpenCode and explicitly excluded Execution isolation.
See `agent-cli/docs/durable-runtime-0.29.0.md`. Reference: OpenCode 2.0.32, pinned commit
`22e771f5893e255ea78fc10557ed3fb98d3a1072` (MIT), local `.runtime/references/opencode`; no upstream scripts run.
The earlier continuity section's three follow-ups are implemented in this source version, with the limits below.

- `journal.py`: per-root/server/session SQLite WAL/FULL event log + canonical snapshot, schema version 1. Durable
  physical request intents (including compact/title/btw/explore/wrapup), logical step IDs, `(step, ordinal)` tool
  identities, result/task-state commits before renderer, process lease, interrupted/unknown recovery without replay.
  JSON remains a compatibility export; managed JSON missing its journal and corrupt/future journals fail closed.
  Legacy unmanaged JSON still opens. Rename is metadata-only; delete/retention take the lease, remove DB/WAL and
  leave a tombstone so late callbacks cannot resurrect a deleted session. Active sessions are skipped by retention.
- `observer.py`: presentation exceptions cannot erase results or manufacture failed tools; failing interactive
  methods deny/dismiss rather than grant. KeyboardInterrupt still stops. Rendering remains synchronous and terminal
  close stops the local runtime; this is not a full independent OpenCode Core/UI transport or persistent daemon.
- Terminal input is admitted durably before Enter acknowledgement/draft clear; delivery+transcript is transactional.
  `/pending` explicitly sends or cancels saved text/images; queued slash commands only prefill for another Enter.
  Resume never auto-runs pending input. Captured tool images are included in recovery checkpoints.
- `task_state.py`: goal/plan/artifact hashes/revision/runtime evidence/acceptance survive compaction/resume. Negotiated
  `task_state` adds evidence_id to outcomes and a strict record_acceptance tool; old feature schemas are unchanged.
  Passed requires current real check evidence, not a write/plan/failed check; edits and external artifact changes
  stale prior criteria. Scope is agent-reported, not semantic proof. Model projection is bounded (~14k chars) with
  omitted counts; full current state has 100 evidence rows/30 criteria, prior tool output remains in journal/archive.
  No new permissions, provider retry expansion, OS isolation, frontend change or production DB migration.

Use `pytest tests` from agent-cli, not bare pytest (eval fixture projects intentionally contain failing tests).
Tests use mock models, temporary workspaces and real child-process crashes. No paid model calls, commit/deploy,
installed CLI update or user project/game changes in this source task. Deploy backend then update CLI to 0.29.0
for acceptance negotiation; journal/UI/inbox also work with older backends. No new third-party dependencies.
Final validation: full CLI 656/656 pass; related backend Agent/API/schema/provider/guide/installer 83/83 pass.
Installer test installs the built wheel into a temporary target and runs its CLI; a separate 0.29.0 wheel build
also compiled every packaged Python module. `git diff --check` passes. No live-provider or physical power-loss test.

## English model instructions, provider overlays, no roleplay mode (2026-10-18)

The owner asked for every system prompt in English to save tokens, including the Web Chat assistant and its examples,
for a better structure than one `english.py`, for removing roleplay mode ("we have Companion now"), and to learn how
OpenCode handles prompts per model.
- **`backend/prompts/` is English only and split by role.** `core.py` (`CORE_PROMPT`: identity, address forms,
  accuracy, safety; shared by Chat, Agent and /btw), `chat.py` (`WEB_PROMPT`, `chat_prompt(model)`, search, document
  mode, tool-budget and Grok follow-up texts), `agent.py` (everything Agent), `providers.py` (overlays), `context.py`,
  `diagrams.py`, `companion.py`/`companion_runtime.py` (unchanged). `assistant.py`, `english.py`, `roleplay.py` and
  `routing.py` were deleted; there is no `uses_english` and no `english=` parameter anywhere any more.
- **Every model gets the same base, like OpenCode** (`packages/core/src/session/runner/prompt/system.txt` plus
  `plugin/optimize.ts`, which replaces the base for GPT/Kimi/Meta/Trinity families and appends a short block for Claude).
  Peto chooses by `ai.models` service: `provider_prompt(model, chat=)` adds `OPENAI_PROMPT`/`ANTHROPIC_PROMPT` to every
  turn and `XAI_CHAT_PROMPT` (the translated Web reply examples Grok was tuned with) to Chat only. GPT/Claude never had
  the examples, so they do not pay for them. Tool curation per model already existed (apply_patch and no update_plan
  for GPT).
- **Peto/xAI Web Chat now uses the English prompt** (before: the Vietnamese `SYSTEM_PROMPT`, about twice the
  characters). Rules only the Vietnamese prompt had (teasing limits, no `*action*` narration, story/practice
  roleplay allowed but never sexual, one clarifying question, serious-topic handling) became the `## Conversation`
  section of `WEB_PROMPT`, for every provider. Replies still follow the user's language, default Vietnamese.
- **Other model instructions became English too** (the owner's pick): time/search/GitHub/finalizing blocks, the Agent
  guide (now attached only when recent messages mention Agent/CLI/Peto, on every model; before, Grok and Companion got
  the Vietnamese guide on every turn), docs/project/YouTube wrappers, stopped-turn labels, Companion memory
  extraction/sort/tell/summary prompts (entry titles and details are still written in Vietnamese because the Memory page
  shows them; the Companion thread summary is now written in English since only the model reads it), the title prompt
  and Grok's Excel follow-up nudge. Markers and labels changed with them (`MEMORY_MARKER`, "User:", "Request:",
  `<<< user preferences >>>`…); `ai/mock.py` follows. Tool schemas, tool results (e.g. the GitHub NOTE), attachment
  notices inside user messages, validation errors and UI strings stay Vietnamese.
- **Roleplay mode is gone.** No consent API (`/api/profile/roleplay-consent` removed, `roleplay_confirmed` dropped from
  `/me`, `roleplay_consents` no longer created; old DBs keep the unused table), no `PETO_ROLEPLAY_MAX_HISTORY`, no
  composer toggle/chip or 18+ dialog. `ChatRequest.persona` other than `assistant` gets 400 (`ROLEPLAY_REMOVED`).
  Existing roleplay conversations (`persona='roleplay'`, the owner's pick "Giữ, chỉ xem") stay listed with "· Nhập vai"
  and open read-only like archived chats ("Hội thoại nhập vai cũ chỉ còn để xem" + "Bắt đầu hội thoại mới"); sending,
  branching and model changes return 409 (`conversation_actions.LEGACY_ROLEPLAY`), so their possibly 18+ history never
  reaches any model. Rename, archive and delete still work. Memory never reads them (`MEMORY_SOURCE` unchanged). The
  Discord memory `VOICE_RULE` now always applies. Drafts lost their persona dimension. Brain Benchmark: 28 cases, 34
  turns (two roleplay cases removed); the adapter now also stubs `chat_memory_block` so it never touches a database.
- **Measured** (characters, before per-user blocks): a Grok Chat turn went from the Vietnamese `SYSTEM_PROMPT` (23,836)
  plus the always-attached Vietnamese Agent guide (3,497) to `chat_prompt('peto')` (15,468, examples included; the
  3,002-character English guide only when asked). Luna 13,386, Haiku 13,471. Vietnamese also costs more tokens per
  character, so the token saving is larger; real token counts were not measured and no paid call was made. Grok's live
  answer quality under the English Chat prompt is untested.
- **Tests:** backend 1366 pass; frontend 782/782 after 2026-10-19 (`keeps image generation alive…` had expected "Peto
  đang tạo 1 ảnh…", removed by the GenerationPreview change; it now waits for "Đang gửi yêu cầu…" and the pending tile);
  build passes; a mock-stack browser run checked the read-only old roleplay chat, the plus menu and a normal send.

## Post-GTA continuity improvements (2026-10-17–18; CLI 0.28.6 source)

Owner authorized the post-test priorities and quicker Peto supervision. See `agent-cli/docs/harness-continuity-0.28.6.md`.
No commit/deploy/installed update or game writes in this change. Installed/server version used for live validation: 0.28.5;
the test imported source CLI 0.28.6. Compaction now requires six nonempty ordered sections, at most 8000 characters;
one malformed-summary retry at medium effort, then preserve history. This validates format, not semantic correctness.
continuation.py separately pins bounded tool observations (20 paths, 10 plan rows, 6 recent command/error results),
filters seeded fields and carries no execution grants. Save failure restores in-memory items/context tokens/read state.
read_file/search_files stream UTF-8 through 64 MB; mutation/undo cap stays 1 MB. Search reports skipped files/huge lines.
file_glob.py shares bounded brace expansion for find/search. run_python (negotiated python_exec) executes multiline
code as direct argv through the existing permission/snapshot/output/timeout path; cmd multiline guard stays active.
Eval policy receives actual argv and scans source; default build permissions remain allow, with require_approval for evals.
Validation: full CLI 613 pass / 3 fixture failures in 616 cases; fixed summary/replay fixtures and a midnight-dependent
session-picker test; recheck all four affected modules 62 pass. All 616 cases covered across runs, not a single full-green
run. Final evidence-dedup regression added; 83 related cases pass, covering 617 total CLI cases across runs.
Backend API/schema/prompt/installer 74 pass; old schemas unchanged. Tests use workspace temp dirs, mock models.
Real Peto controlled continuity case: 2.3 MB metadata, synthetic binary fixture, forced compaction then persisted resume;
independent decoder/hash checks confirm 20 old + 5 new, duplicate ID preserved, original catalog unchanged. 13 billed
steps (1 compact + 12 work), 18 agent tools, 86.65s continuation, zero manual approvals. Automatic fixture policy still
checks commands. Runtime artifacts: `.runtime/peto-continuity-20261017/`. Supervisor setup errors and recovery are logged;
do not attribute seeded history to Peto or call this an equal-difficulty GTA benchmark. Server has no python_exec yet,
so model selection of the new Python tool is untested until deploy. Peto still made Windows quoting errors and spent
two extra calls after a passing consumer because verification-reminder logic lacks explicit acceptance results.
Structured acceptance, durable journal/inbox and UI/runtime separation remain follow-up work, not implemented here.

## Default tool permissions (2026-10-17; CLI 0.28.5)

The owner requested OpenCode-style default execution after the supervised GTA test spent about 65 minutes awaiting
approvals (including the conversation interruption). Build-mode commands, background commands and file mutations now
default to allow. This is permission behavior, not an OS sandbox or a complete port of OpenCode's rule engine.
`/permissions [allow|ask|deny]` sets both groups; `/permissions shell|edit allow|ask|deny` sets one. The setting lives
in the user-profile permissions.json `policies` map, keyed by project root; never read policy from the repo or history.
Ask keeps legacy exact s/l grants and request a; deny is checked first and cannot be overridden by those grants.
`/permissions clear` clears remembered grants AND project policy and visibly returns to allow. Ask must be selected
after clear to restore prompts. Malformed/unreadable profile JSON falls back to ask and cannot be silently overwritten.
Grant writes preserve policies; saves use atomic_file. Failed clear/save is reported, not treated as success.
Plan commands still go through legacy approval, and plan file restrictions stay enforced. Browser/MCP/undo retain
their separate approval flows. CLI still renders commands/diffs/results, and read-before-edit/checkpoints/timeout,
Windows multiline-command guards and Ctrl+C still apply. No live Peto call, deployment or installed CLI update is
part of this source change. Permission-specific legacy tests select ask explicitly; default-mode tests use no prompts.
The eval harness sets tools.require_approval=True so PolicyUI/CommandPolicy still evaluates every command/file effect;
this owner-controlled runtime flag is not read from project files or session history, and reset_task preserves it.
Validation: all 590 CLI cases covered successfully across the full run and targeted recheck. The full run had 589 passes
and one new test fixture missing /me; after fixing that fixture, all 58 session/policy/catalog tests pass. Backend API,
prompt and installer tests: 61 pass; final installer/wheel recheck: 5 pass. No paid model calls. Sandbox denied temporary
browser/socket access, so full integration checks ran with dedicated workspace temp directories outside that sandbox.

## Optional per-request step budget (2026-10-17; CLI 0.28.4)

The owner explicitly requested removing the fixed 40-step interruption before the next GTA test. Interactive
Session now defaults to max_steps=None, matching the optional agent.steps check in the pinned OpenCode CLI engine
(`packages/core/src/session/runner/llm.ts`). Only an explicit positive Session(max_steps=N) budget triggers wrapup
and the continue prompt. Evals pass their task budget into that session, never mutate a global loop limit.
Daily account quota, Ctrl+C, retry limits, compaction/context guards, save failures, permissions and repair guards
remain in effect. No .env setting is needed. This source change does not install, deploy or start the GTA task.
Regression coverage runs 45 successful, distinct read tools before completion, quota denial or Ctrl+C, verifies
saved tool results, and checks that an eval still stops at its own budget with a wrapup turn. Model calls are mocked.
Validation: 157 related CLI tests (fewer_steps, harness_boundaries, loop_client, evals) and 5 wheel/install tests pass.

## OpenCode harness comparison (2026-10-17; CLI 0.28.3 source only)

The owner requested an offline clone and detailed harness/function comparison. Reference checkout:
`.runtime/references/opencode`, dev commit `22e771f5893e255ea78fc10557ed3fb98d3a1072`, package 2.0.32, MIT.
Full files, shallow history; no upstream dependencies/scripts executed. See `agent-cli/docs/opencode-reading-map.md`
and `agent-cli/docs/opencode-harness-review-2026-10-17.md`. Treat upstream instructions as reference scoped to that repo.
Source, not old V1 paths or prose alone, is authoritative; current retry/output implementation differs from parts of specs.
0.28.3 adds typed JSON input preflight (tool_input.py), makes history.save return explicit success, stops before further
effects/model steps on failed progress writes, reconciles unanswered calls in old sessions without replay or on-read disk
rewrite (session_protocol.py), and applies the existing 3-failure guard to apply_patch too. Legacy migration keeps its
original if saving fails. Loop finalization settles missing calls in memory as well as in the saved copy.
Main prompts are now saved before their first model request, not only after a model step returns; queued UI inbox data
still needs a durable-inbox design. This does not auto-start or replay any interrupted task.
atomic_file.py uses unique same-directory temporaries and at most 3 short replace retries for Windows errors 5/32/33;
permanent errors still fail. A local stress probe reproduced 117 failures/2000 saves before and 0/2000 after, handling
52 transient denials. The process causing these denials was not identified; do not assert antivirus causation.
570 CLI tests + 5 wheel tests pass; 27 new boundary/contract cases include backend schema/CLI handler compatibility.
No live model call, game modification, installation or VPS deploy in this review. Previously patched installed CLI is 0.28.2.
Keep Windows stdlib runtime and remote auth/quota/provider split. UI/event isolation, durable inbox/journal, per-model context
budget, output codecs and structured acceptance/artifact state remain documented follow-up work, not completed features.

## Terminal read_output crash (2026-10-17, CLI 0.28.2)

See `agent-cli/docs/peto-read-output-crash-2026-10-17.md`. Installed 0.28.0 crashed in TerminalUI.tool_started:
EXPLORE included read_output/read_history but its separate status-label dict omitted both. EXPLORE is now one map
of tool names to status-label builders. Regression tests use actual Tools + TerminalUI for reading/searching saved
output and reading archived history. Unexpected _run exceptions now report error and preserve an interrupted,
protocol-valid saved session before re-raising; never mark a crash done or automatically replay pending tools.
The user's latest assignment session had one unanswered read_output and no source edits. Local repair artifacts
and pre-repair backups are under `.runtime/peto-ui-crash-20261017/`. No live model call or VPS deployment is needed.

## Supervised Peto eval (2026-10-17; local CLI 0.28.1 after the run)

The owner explicitly authorized running Peto and supervising a radio-like task. See
`agent-cli/docs/peto-supervision-2026-10-17.md`. Peto medium on source CLI 0.28.0 passed
`radio-20-bai-3-che-do` unaided: 23 main model calls + 1 compaction = 24 billed steps, 314.1 seconds.
This synthetic spec-provided task is easier than real GTA IV; one pass is not a before/after comparison.
Logs/results are under `.runtime/peto-live-eval-20261017/`; do not print credentials. Temporary copied config is removed.
After the run, 0.28.1 rejects multiline Windows cmd commands in run_command/start_command before approval/execution:
cmd /c silently ignored later lines and returned 0 during the run. Use PowerShell syntax or a script file instead.
Recorder now forwards keyword purpose for wrapup; a separate regression test covers it. No VPS deploy or daily CLI install.

## Agent continuity update (2026-10-17, CLI 0.28.0; local, not deployed)

See `agent-cli/docs/harness-review-2026-10-17.md` for the radio-session evidence and limits of the comparison.
`recall.py` saves visible prefix messages/calls/results before successful compaction to
`sessions/<project>/<id>.archive/`; a failed write keeps the original conversation. It omits provider reasoning,
signatures and image bytes. `request_anchors` retains selected verbatim user requests within 12,000 characters/24
messages; `history.SUMMARY_NOTE` is an internal note, not a real user request. Archived content remains available
through feature-negotiated `read_history(pattern,start_entry,start_character)`, including after resume. No extra
model call for storage/lookup itself; the normal model step selecting a tool still costs quota. Archive limit 64 MB,
cleanup follows session deletion/pruning. Never describe this as recovering already-lost old history.
`check_observations` carries bounded local observations and command outcomes at the end of the Agent prompt;
checked_revision records an attempt, not task success. Prompt/reminder require appropriately scoped independent
consumer/application checks for non-code tasks and preserve user failure feedback in compaction. No model, context
threshold, quota, authorization or repair-budget change. `radio-dung-trong-ung-dung` is an offline MUS1-consumer eval;
grader selftest is not evidence of improved live-model performance. Existing schema feature sets stay unchanged.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

## Language convention

Agent/CLI planning context is recorded in [PETO_AGENT_PLAN.md](PETO_AGENT_PLAN.md).
The clarified direction is a Windows CLI that runs the loop and executes local project tools, with VPS
authentication, step limits and model calls (first version: "Peto Agent (CLI)" below). Docker is optional; web
Work is later scope.
It distinguishes agreed direction from open implementation choices and does not
authorize deployment. Consult it when continuing Agent/CLI discussions or work.

Minecraft planning context (Peto joining the owner's LAN world, from AIRI's Minecraft integration, 2026-09-28) is
recorded in [PETO_MINECRAFT_PLAN.md](PETO_MINECRAFT_PLAN.md) in the same way. Nothing of it is built yet; consult it
before any Minecraft work.

Companion direction is recorded in [PETO_COMPANION_PLAN.md](PETO_COMPANION_PLAN.md) (rewritten 2026-10-13): the AIRI drift
review, what AIRI is building now, the prioritised next steps and the "not doing" list; the original September plan is
kept at its end as history. The owner's calls of 2026-10-13: web first, and a Companion-only settings page at
`/companion/settings/` modelled on AIRI's web Settings, with the Companion group removed from the shared Settings dialog.
The page was built the same day (see "Companion settings page"). Consult the plan before any Companion work. Like the other plan files it is gitignored, so it
exists only on the owner's machine.

**Every comment, docstring, log message, error message, and user-facing string in this
codebase is written in Vietnamese.** Keep it that way when adding code — an English error
string would be visibly out of place in the UI. Identifiers, type names and this file stay
in English.

Model instructions are the explicit exception: since 2026-10-18 every system prompt is English, for every model
(Agent since 2026-10-15). `backend/prompts/` holds them by role (see the section at the top); `chat_prompt(model)` in
`prompts/chat.py` builds Web Chat and `features/agent/api.py` builds Agent (including compaction), both adding the
provider overlay from `prompts/providers.py`. Companion keeps its own English persona. The shared English core keeps the
Peto identity and replies in the user's language, defaulting to Vietnamese with full diacritics. Raw user messages,
memory, preferences, project guidance, skill metadata and documentation are never translated. Tool schemas,
validation, user-facing errors and logs retain Vietnamese, except Agent tool descriptions for CLIs that declare
`english_tools` (0.29.1, see the section at the top). The Agent guide enters Web prompts only for product/Agent
questions (using recent turns for follow-ups); file-tool instructions remain always present to avoid fragile
keyword-based routing. Grok's short Excel-announcement follow-up is restricted to xAI.
Routing and context preservation are covered in `backend/tests/test_prompt_routing.py`; these mocked tests do not
establish live model answer quality or billed token usage.

On 2026-10-09 the owner requested fuller, more readable Web Chat analysis for all providers. It is the
"Explanation and evidence" part of `WEB_PROMPT` (the Vietnamese `ANALYSIS_PRESENTATION_PROMPT` was removed 2026-10-18). Reviews use meaningful headings, real short blockquotes, code excerpts, impact and suggested changes.
Depth follows the task, not the question's length; simple questions and requested summaries stay concise. Numerical
ratings require criteria, and quotations must be real. Agent work summaries and spoken Companion are not
forced into this Web presentation policy. The frontend already supports blockquotes and highlighted code blocks.
After the owner's follow-up sample, reviews additionally require exact passages for consequential file-specific
claims and short usable replacements when proposing edits. Overlapping findings are grouped. A prompt file alone
does not establish missing application authorization, unseen prompt assembly or production readiness; distinguish
observed file facts from checks that require other code or runtime evidence. Do not pad a review with deployment advice.
The owner's next sample exposed missed existing exceptions and silently joined quotations. Reviews must check rules,
conditions and examples already present before recommending additions, distinguish reinforcing repetition from
contradiction, preserve distinct constraints in proposed merges, and mark omissions or quote separate passages separately.
On 2026-10-11 the owner asked why Peto's answers looked shorter than ChatGPT/Claude. The Vietnamese prompt's explanation
examples (asyncio, race condition) were two-sentence answers placed last in `SYSTEM_PROMPT`, contradicting its own depth
rules; they now show only the opening line plus a bracketed outline of the sections that follow (since 2026-10-18 in
English, as the Grok-only `providers.XAI_CHAT_PROMPT`). The owner's manual
test with Grok (one mRNA question at Tự động/Trung bình/Cao) gave similar, already structured answers, so effort routing
was left unchanged. The Brain Benchmark caps output at 1024 tokens, so it cannot measure answer depth as it stands.

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

Chat is split into `features/chat/api.py`, `schemas.py`, `service.py`, `history.py`, and `prompt_context.py`.
Projects live in `features/projects/` and `storage/projects.py`, with `conversations.project_id` migrated at startup.
Project IDs and selected file IDs are owner-checked before chat writes and inside admission; branches retain the project.
Project instructions apply each turn; only explicitly selected files (up to 4, total 32,000 extracted characters) enter
the system context. No automatic history sharing across project chats. PDFs/DOCX/text are cached after upload; project
files are SQLite BLOBs included in normal database backups. Limits: 50 projects per account, 20 files/64 MB per project,
8 MB per file. Deleting a project preserves conversations and their existing attachments, returning chats to recents.
Frontend `features/projects/` owns sidebar folder toggles, the top-left chat project name and move dialog. Recents
fetch unassigned conversations; global search still covers all chats. There is no project overview or shared-file
picker; files are attached directly in chat. Legacy project instructions/files APIs and stored data are preserved.
Projects currently apply to web chat only, not Companion/CLI.
Chat archival uses `conversations.archived` (migrated to 0 for existing rows). Default lists/search/project counts
exclude archived chats; `GET /api/conversations?archived=true` lists only the current owner's archived web chats.
PATCH `archived` retains titles, pin state, project membership, messages, attachments and generated documents.
Settings -> archived conversations supports search, paging, read-only opening, restoration and confirmed permanent
deletion. Restoring returns to the old project, or recents after project deletion. Chat sends/branches reject archived
conversations before admission and recheck after waiting/reading files. Companion is never archived by this API.
Sidebar preloads the first chat page per folder with three concurrent requests. Opening a folder reuses cached or
pending data; background refreshes retain existing rows. Writes refresh affected folders explicitly, including
renaming/deleting chats in inactive projects. Cache and request guards reset at authentication scope changes.
Provider spies patch `features.chat.service.get_provider`; history budget spies patch `features.chat.history`;
migration tests patch `storage.connection.DB_PATH`. Prompt text, API paths, schema/SQL, resource locations and launch
commands were preserved during the move. Tests keep setting fake environment variables before the first config import.

### Two run modes

- **Dev = two processes.** uvicorn serves the API; Vite serves the UI and proxies `/api`.
- **Production = one process.** `static_files.mount()` serves `frontend/dist` from the
  backend itself, so the VPS needs one port for Cloudflare Tunnel and no nginx. It is a
  no-op when `dist` does not exist, which is why dev is unaffected.

Its catch-all route `/{full_path:path}` **must be registered after every API route** — it
is the last statement in `main.py`. Move it earlier and API 404s start returning
`index.html`. The handler also explicitly rejects paths starting with `api/` as a second
line of defense, and blocks path traversal by resolving under `static_dir`.

On 2026-10-09 navigation moved to React Router's BrowserRouter (declarative mode), scoped to the existing App shell.
`app/routes.ts` maps `/`, `/companion`, `/imagine` and `/imagine/<root>/<version>` (plus the `/companion/settings/…` pages
since 2026-10-13); it does not implement history itself.
App and Imagine read router location and use navigate for user actions. Tab switches push only when the view changes;
legacy `/#companion`, `/#imagine` and image hashes replace the current entry, preserving query parameters.
Chat remains mounted, and visited Imagine/Companion stay mounted with their existing active props and account keys
on the outer LazyBoundary. BrowserRouter uses `useTransitions={false}` so urgent image selection cannot get ahead
of a deferred location commit when Back is pressed immediately; existing component animations are unchanged.
Docs retains its separate entry and anchor navigation. FastAPI serves index only for declared app paths, after real
files; missing API paths, assets, unknown Docs articles and other paths remain 404. The catch-all still runs last.
`playwright.routing.config.ts` verifies browser history/F5/deep links against the production build with this real
fallback, using mocked user/AI data and a loopback-only server without database access.

Web Chat now uses `/chat/<conversation-id>`, with `/` for a new chat. A route effect loads messages/settings through
the existing owner-filtered API, including chats outside the recents list and archived read-only chats. Selecting a
chat pushes once; selecting the same chat preserves messages/draft. First-turn SSE metadata replaces the unnamed
entry with its ID; a branch pushes a new entry. Returning from another tab restores the selected Chat URL. Route loads
retain abort/version guards, without remounting Chat. An in-memory snapshot of the one active reply routes stream writes
only to that conversation, so browser history may select another chat without aborting AI or leaking its deltas into
the selected thread; returning while the reply runs uses that snapshot. Late metadata never forces a tab switch.
The single-stream send lock remains. Chat drafts now use `features/chat/useChatDrafts.ts` and `chatDrafts.ts`:
text-only `sessionStorage` entries are keyed by account/conversation; unnamed chats also distinguish project and persona.
Writes debounce 250 ms and flush on scope change, pagehide/beforeunload, hidden document and unmount. Files/previews
stay in memory per draft and are never serialized. New-chat history state stores only owner/project/persona metadata
so F5/Back recover the correct scope, without adding entries for context changes or remounting the composer.
SSE receipt clears only the submitted snapshot, preserving another chat or later changes; pre-receipt failures retain it.
Since 2026-10-10 the Chat textarea remains editable during a reply, letting the user prepare the next message.
Enter/form submit cannot start another turn while streaming; Shift+Enter still inserts a newline, Stop stays available,
and completion never auto-sends the draft. Attachment/model/effort controls retain their existing stream lock.
Chat file drag/drop is handled once by `ChatFileDropZone.tsx` on the existing `.chat-layout` container, including
history, header, composer and the open document panel, excluding Sidebar. A non-interactive overlay dims only
that area and shows a local SVG file cluster and two short Vietnamese lines; no external artwork is fetched.
Only `Files` drags activate it; text/link drags keep their default behavior. Drops reuse `addFiles` for all existing
limits/deduplication and never send a message. Streaming/loading/failed/archived states and open modals block drops.
Leaving the chat, dropping outside, Escape, dragend, blur, hiding the page or changing draft scope clears the overlay.
While Chat is active, accidental file drops on Sidebar/outside are ignored and prevented from navigating to the file;
hidden Chat removes this guard so Imagine's existing drag/drop stays independent. Children are not keyed/remounted.
If the first-turn receipt assigns an ID while the user is still on that unnamed chat, `accept(snapshot, id)` moves
any remaining draft into the new conversation scope, without overwriting a nonempty destination. Background receipts
do not move the selected draft. Tests cover late receipts, next-message send, Stop/errors, F5, Back/Forward and
desktop/mobile browser input with fake APIs only.
Before the server assigns an ID, active-reply selection also checks project/persona so Back between unnamed chat
contexts cannot redirect the wrong entry or display another draft's pending reply.
Logout/confirmed expiry clears all Chat drafts and cached file URLs; a failed auth network check does not erase drafts.
Successful conversation deletion clears its draft; project deletion clears only unnamed project drafts, retaining
drafts of existing conversations. Storage denial/quota errors fall back to memory. Drafts do not sync across devices;
sessionStorage is tab-session storage, not a durable backup. Companion/Imagine persistence is unchanged.
The static fallback also accepts `/chat/<id>` but rejects missing `/chat`, extra segments and paths resembling assets.
It also accepts exactly the Companion settings pages (`_COMPANION_SETTINGS` in `core/static_files.py`, mirroring
`COMPANION_SETTINGS_PATHS` in `app/routes.ts`); any other path under `/companion/settings` is a 404.
Signing in from a Chat deep link records only its same-origin path/query in sessionStorage; the normal OAuth root
callback then replaces that root entry with the requested Chat URL. The pending return is consumed once; auth and
owner checks remain unchanged, with no public sharing or arbitrary redirect target.
Explicit sign-out clears any pending return and replaces the URL with `/` (2026-10-11: switching Google ↔ Discord
from an open chat made the next account land on the previous account's `/chat/<id>`, "Không tìm thấy hội thoại").
A mid-session expiry keeps the URL, so signing back in still returns to that chat.

The index page is not served verbatim: the handler inserts `og:image` (plus alt text)
from `app_identity.get_app_identity()` — the bot's Discord CDN icon, already the absolute
URL Open Graph requires. That keeps the domain out of the build and makes link previews
follow the bot icon. The other preview tags are static in `frontend/index.html`; crawlers
such as Discordbot never run JS, so they must stay in the HTML. Because the home page now
awaits `get_app_identity`, that function must never raise.

### Identity and data isolation

`owner` is the single tenancy key, formatted `discord:<id>` (`config.owner_key`). Every
query in `storage/` takes `owner` and filters on it **in SQL** — there is no "load then check"
path. Knowing someone else's conversation id gets you a 404.

The server never accepts a Discord ID from the browser. `features/accounts/auth.py` exchanges the OAuth code
server-side, calls `/users/@me` itself, and discards the Discord access token immediately
(nothing stored, nothing sent to the client). The session is an `itsdangerous` signed
cookie holding only the owner key.

There are three ways in, all in `features/accounts/auth.py`: Discord, Google and GitHub OAuth.
`owner_key(provider, external_id)` builds every owner; `provider_from_owner` is what
`session_owner` uses to reject a signed cookie carrying a malformed key.

**Guest login was removed on 2026-10-06** (the owner's call): anyone could mint unlimited guest accounts and spend the
web's AI quota, and a per-guest counter could be dodged by clearing cookies. GitHub login replaced the "Khách" button.
- `guest` left `config.PROVIDERS`, so an old `guest:` cookie fails `session_owner` and the visitor is signed out. Agent
  tokens of an owner that no longer parses are refused as expired (`device_auth`).
- GitHub uses its own OAuth App (`GITHUB_LOGIN_CLIENT_ID/SECRET/REDIRECT_URI`), separate from the Kết nối GitHub App
  (`PETO_GITHUB_*`). No scope is requested (public profile only). The owner is `github:<numeric id>`; `login` can change,
  so it is only the username. GitHub reports a bad code with HTTP 200 and an `error` field, so the callback checks the
  body. The token is revoked right after reading `/user` (best effort), and nothing is stored.
- GitHub accounts have the same rights as Google: Luna, Agent CLI, the Giọng Peto allowance. Only the Discord gateway check differs, since only `discord:` owners have a Discord ID.
- `ops/purge_guests.py` deletes old guest data: a dry run by default, `--yes` to delete. Every table with an `owner`
  column, child rows through `ON DELETE CASCADE`, then upload and Imagine files inside `PETO_UPLOAD_DIR` (never outside).
  Tests sign a second account in with `conftest.sign_in` (a fresh `github:` owner) instead of the old guest endpoint.

The allowlist was **deliberately removed** — anyone who can reach the deployment can use
it and spend the server's AI quota. That was the owner's explicit call after being shown
the cost; do not reintroduce a gate unless asked. `tests/test_auth.py` asserts
`config.ALLOWED_DISCORD_IDS` no longer exists so a well-meaning revert gets caught.

Only `discord:` owners carry a Discord ID, so `discord_id_from_owner` returns `""` for
Google and GitHub accounts and `features/chat/prompt_context.py` skips the memory gateway entirely for them. That
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

On 2026-09-17 the owner added OpenAI API billing and picked this design from mockups. `ai/models.py` holds the catalog
and the access rules; the server checks them on every chat turn and agent step, never trusting the UI:

- `peto` (Grok through the web's xAI account) for everyone; `luna` (`gpt-6-luna`) for every signed-in account,
  on the web and in the CLI; `terra` (`gpt-5.6-terra`, until a GPT-6 Terra exists) and `sol` (`gpt-6-sol`) only in the CLI and only for owners
  listed in `PETO_OWNER_ACCOUNTS` (`discord:<id>` or `google:<id>`, bare digits mean Discord). Without `OPENAI_API_KEY`
  the OpenAI choices are hidden (503 if a turn asks for one); under `PETO_AI_PROVIDER=mock` every model uses the mock.
- `get_provider(model)` caches one provider per model. `ai/xai.py` holds `ResponsesProvider`, the tool loop, web search
  and sources shared by `XAIProvider` and `ai/gpt.py`'s `GPTProvider`; subclasses only set the client, model, output
  budget (`PETO_OPENAI_MAX_OUTPUT_TOKENS`, 16000, since reasoning tokens count) and Vietnamese error messages. OpenAI
  reasoning summaries are not requested, because they can require organization verification.
- `POST /api/chat` takes `model` per message, so switching mid-conversation works (history is plain text). Companion must
  stay on `peto` (400). Old roleplay conversations cannot be continued at all (409, see "Roleplay mode (removed)"). Since 2026-10-13 Companion can instead use the user's own API key (`provider` field; see "Companion
  providers"), which never touches the owner's accounts. The title call uses the same model as the first message. `/api/auth/me` returns the account's web
  `models`; `ModelMenu.tsx` sits left of the send button (hidden with fewer than two models), and
  phones show the send button as an arrow only to keep the bar on
  one row.
- The persona rule still holds: whatever model runs, Peto does not name the model behind it.
- Tests patch `features.chat.service.get_provider` with a callable that accepts the model (`lambda model="peto": ...`).
  `tests/test_models.py` covers the access rules, step costs and the OpenAI call shape with fake clients.

On 2026-10-10 Web Chat gained per-conversation `model`/`effort` columns, migrated at startup with `peto`/`auto`
for old conversations. PATCH `/api/conversations/{id}` saves the pair together, separately from other metadata,
with owner, persona, provider access and effort validation; it does not change the recents ordering. Accepted chat
turns also save the UI choice (including `auto`, rather than the resolved effort for that message). Branches copy
the selection, and changing a branch does not change its source. Reads return a valid fallback and a Vietnamese
notice if a model/effort becomes unavailable, without destroying the stored preference on a read.
`getMessages` returns selection metadata; GET `/api/conversations/{id}/settings` supports lightweight refresh on
window focus/visibility return. `useChatSelection` restores selections without remounting the composer or reloading
messages on focus, serializes writes per chat, guards stale replies/account changes, and waits for pending writes
before sending or reopening that chat. Network save failures are visible; successful sends persist the current
choice again. `peto-model`/`peto-effort` now only supply device-local defaults for chats without an ID, updated by
explicit user choices rather than by opening an existing chat. Across devices, the last server write wins; this
is not continuous push synchronization. Tests use temporary databases/fake APIs, including independent browser
contexts, mobile, F5, Back/Forward and delayed writes; no paid provider requests are needed.

Claude was added on 2026-10-08: `haiku` (`claude-haiku-5-5`) is available to every signed-in account on Web and Agent;
`sonnet` (`claude-sonnet-5-5`) is owner-only in Agent, as explicitly chosen by the owner. Both accept
`low/medium/high/xhigh/max`, never `none`; the API receives `thinking.type=adaptive` and `output_config.effort`.
`ANTHROPIC_API_KEY` is a server-only Default workspace key. Missing key hides Claude; mock uses no credentials.
`ai/claude.py` translates the existing internal Responses-shaped items/events to the native Anthropic Messages SDK,
sharing Web's tool loop and Agent's step handling. It never calls an Anthropic Responses endpoint. Full native
assistant blocks (including thinking signatures and server search results) are held in a `reasoning` wrapper beside
portable text/tool items. Re-sending that group restores the exact native blocks; switching models drops the wrapper.
CLI 0.14.2 keeps groups intact during compaction and can resume histories containing web search items.
Web output budget is `PETO_ANTHROPIC_MAX_OUTPUT_TOKENS` (32768); Agent uses
`PETO_ANTHROPIC_AGENT_MAX_OUTPUT_TOKENS` (128000). Basic native web search is capped at five uses per request;
`pause_turn` continues up to three times and sums usage. HTTP failures are sanitized, no SDK retries silently
spend another request, incomplete/disconnected streams never become successful answers. Haiku costs one Agent step,
Sonnet two, multiplied by the existing effort cost; these are Peto quota units, not Anthropic billing prices.
Tests use the real SDK against fake HTTP/SSE, never real keys or billing. Deployment/key activation is separate.
Prompt caching (2026-10-11; before that no request sent `cache_control`, so the admin page showed 0 cached tokens):
`ClaudeClient` sends the system prompt as a cached stable block followed by the time block (`split_time_context`),
because a per-second clock anywhere before a breakpoint makes everything after it uncacheable. A second marker goes on
the last block of the last message, on a copy so caller history is never edited: always for Agent
(`cache_history="always"`), only inside a tool loop for Chat (a single-round turn would only pay the 1.25× write
premium, since the chat clock still changes every turn). Agent instructions end with `agent_time_context`, rounded to
the hour, so steps within an hour reuse the whole cached history; this also helps OpenAI/xAI automatic caching. Cache
reads and writes are reported in `input_tokens_details` (`cached_tokens`, `cache_write_tokens`) and summed over
`pause_turn`. Real cache hit rates still need checking on the admin page after deployment.
On 2026-10-08 the owner's VPS logs showed `ModuleNotFoundError: No module named 'anthropic'` after adding the key:
the service's venv had not installed the new backend requirements. Web and Agent now share a lazy Claude loader
that converts dependency import failures to an actionable Vietnamese provider error. DEPLOY.md gives the exact
venv install/import-check/restart commands; restarting alone never installs dependencies.

### Chat request lifecycle (`POST /api/chat`)

This is the most intricate part of the codebase. The endpoint returns a `StreamingResponse`
of SSE events: `meta` then many `delta` then a terminal `error`, `done`, or `stopped`.

Web Chat sends a fresh `request_id` for each attempt. `POST /api/chat/stop` authenticates the owner, persists
`stopped` in the additive `chat_turns` table and cancels the registered turn, including queue/file-reading waits.
It waits for persistence before acknowledging; an early Stop leaves a tombstone so a late POST cannot start AI.
The client aborts its stream only after confirmation. A failed confirmation remains retryable, never a false Stop.
Disconnects become `interrupted`, timeouts `timeout`, provider failures `error`; startup marks leftover `running`
attempts interrupted. The registry matches the deployment's single backend worker; multiple workers would require
cross-worker cancellation/acknowledgment before changing the worker count.

`history.context_rows` removes explicitly stopped unanswered requests from model context and from `agent_question`.
Partial responses/artifacts and attachments remain reference data; their old question is wrapped as an assistant
historical reference, never a pending user task. Image attachments keep the user role. Titles skip stopped turns.
Retry binds a new attempt to the same question; forks copy prior turn states but reactivate their selected target.
Legacy rows have no explicit Stop state and cannot be retroactively classified. `test_chat_turns.py` verifies actual
provider payloads, persisted labels, owner isolation, early Stop, Retry, forks and disconnect distinction using fakes.

Order of operations inside `event_stream()`, and why:

1. `admission.slot(owner)` wraps the whole turn. Cooldown and queue rejection happen
   **before conversation messages are written**, so a throttled request leaves no orphan
   message (only its attempt record). Cooldown is only recorded for requests actually admitted.
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
6. There is no automatic retry: a turn that timed out or failed may already have spent provider tokens, so it is
   never repeated invisibly (`test_empty_timeout_does_not_repeat_paid_turn`). The UI offers "Thử lại".

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

**Time limits stop a stuck turn, not a busy one** (2026-10-05). Before, `RESPONSE_TIMEOUTS` (180/300/480 s by effort)
capped the whole turn, and an Excel edit was cut at 5 minutes while Peto was still working.
- `RESPONSE_TIMEOUTS` is now the longest silence: time without any chunk from the provider. `TURN_TIMEOUT_SECONDS`
  (`PETO_TURN_TIMEOUT_SECONDS`, 900) caps everything after the uploads are read: every model call and every tool.
- `_stream_reply` reschedules an `asyncio.timeout_at` on every chunk and raises `TurnTimeout(kind="idle" | "turn")`. The
  error message says which limit was hit and for how long. The `chat_timing` outcome stays `timeout`.
- `ResponsesProvider` yields a `pulse` chunk at most every `PULSE_SECONDS` (10) while the service streams events with
  nothing to show (a long tool call being written, raw reasoning). The service forwards it as an SSE comment
  (`: ping`): the browser parser skips blocks without `data:`, and Cloudflare does not close a silent stream. Title
  and memory calls ignore pulses.
- `tests/test_turn_limits.py` covers steady work outliving the silence limit, silence, the turn cap and pulses.

`mode` is `chat` by default; `companion` comes only from the Companion tab. `_resolve_mode`
rejects anything else with a Vietnamese 400. A companion turn is forced to `effort="low"`, searches the web only
when Peto decides to (see "Companion web search"), accepts image attachments only, must use the `peto` model (400
otherwise) unless it brings the user's own key (see "Companion providers"), and skips the title call. `_build_system_prompt` uses `COMPANION_SYSTEM_PROMPT` as the base prompt instead
of the assistant core (see "Companion persona"), then appends the usual agent/docs guide, Discord memory, profile, and
the Companion memory list plus the thread summary (`companion_memory.memory_block`). Conversations store their
`mode` and a turn must match the conversation's mode; `list_conversations` only returns `chat`
ones, and `GET /api/companion` returns the latest `companion` thread with its recent messages.

### Frontend SSE reader

The endpoint is POST, so `EventSource` cannot be used. `frontend/src/shared/api/api.ts` does the framing by
hand: `fetch`, then `response.body.getReader()`, split on a blank line, parse the `data: `
line. If you add an SSE event type, update `ChatEvent` and `ChatHandlers` in `api.ts` as
well as the emitter in `features/chat/service.py`. Blocks without a `data:` line are skipped, which is what lets the
server send `: ping` comments.

### Work log ("Đang làm")

On 2026-10-05 the owner asked for a timer beside "thinking" and a more useful thinking block, pointing at Claude.ai's
"Worked for 5m 12s". They picked "Dòng thời gian" from three live variants; the others were one status line with a
summary ticker, and a phase bar sized by time spent.
- **Why it moved to the server.** The client used to build the list from events. It showed only "Đã làm trong N giây",
  lost the list on reload, and dropped the whole bubble when a turn failed before any text. A timed-out Excel edit left
  nothing to show what Peto had tried.
- **Server-built steps.** `features/chat/work_log.py` (`WorkLog`, chat mode only) turns provider chunks into steps whose
  `start`/`end` are milliseconds from the turn's start:
  - `read`: uploads, with `read_detail` ("5 trang tính · 152 công thức");
  - `think`: from `round` until the first text or tool call, carrying Grok's reasoning summary;
  - `note`: Peto's lead-in sentence before tools;
  - `compose`: Grok writing a long document-tool call;
  - `tool`: its result from the tool's private `_ui` hint ("Đã sửa X · 38 thay đổi", or each refusal);
  - `lookup`, `github` (consecutive reads become one step) and `search`. Consecutive searches, with only think steps
    between them, also become one step ("Đã tìm trên web · 3 lần", sources counted for the turn): on 2026-10-06 the
    owner saw 5–6 identical "Đã tìm trên web" lines.
  - `page`: Claude opening a link from the conversation (`web_fetch`), grouped the same way ("Đã đọc 2 trang · 1 trang
    không đọc được"; all failed is a failed step "Không đọc được trang"). A link icon, not the search globe.
- **Events and storage.**
  - SSE `step` upserts a step by id, and `thinking` carries its `step`.
  - The final `work` event comes right before `done`/`error` and equals what is stored in `messages.work` (JSON, manual
    migration, copied when a conversation is branched). Think steps under 1.5 s with no summary are left out of it.
  - The old events (`reading`, `search`, `file_lookup`…) still go out, for pages loaded before an update and for
    Companion.
- **Provider milestones** (`StreamChunk`):
  - `round`: a model call started;
  - `tool`: a function-call item started. It is preceded by `note` when the call already streamed text; `note` also
    comes at the round's end as a fallback;
  - `tool_result`: built from the tool's `_ui` hint, which is popped before the result goes to the model.
- **Lead-in notes.**
  - Text written before a tool call (up to `NOTE_LIMIT`, 600 characters) moves from the answer into the log. The service
    drops it from `collected` and sends `replace {text}` with what remains of the answer.
  - Longer text is real content: it stays in the answer with a paragraph break.
  - The prompt asks Peto for one short sentence before multi-step tool work, followed by the call in the same response.
  - `replace` now drops only the current call's draft, so text from earlier calls is never lost.
  - **Drafts before a web search** (2026-10-07). On every search start, `ResponsesProvider` sends `replace` for the text
    written since the previous search. Before this, only the first search in a call did, so a lead-in written between
    two searches stayed in the answer, glued to what followed ("phân tích.Ad gửi link"). In Chat, a draft of up to
    `NOTE_LIMIT` becomes a `note` step; a longer one is dropped as before. Companion still drops its draft.
- **Announce, then stop** (2026-10-05, the owner's re-run of the Excel test at effort "Thấp"). Grok thought for 46 s,
  wrote "Peto sửa lại từ file gốc, không đụng sheet Quy_dinh." and ended the turn without a tool call, so no file came
  back and no error showed. It was not a truncation: xAI's `max_output_tokens` counts visible text only, and a cut
  response arrives as `response.incomplete`, which raises.
  - The prompt now ties the lead-in to the call and forbids ending a turn with only the announcement.
  - Safety net in `ResponsesProvider`: one nudge per turn (`FOLLOW_UP`). It needs an editable workbook in the chat, a
    message that asks for an edit (`documents.tools.asks_edit`, accented words such as "sửa", "điền", "gộp"), and a
    round that ends with at most `FOLLOW_UP_CHARS` (300) characters, no tool call and no document tool yet this turn.
  - The follow-up round sends no `round` chunk, so the chat side still treats the announcement as the current draft.
    If Grok then calls a tool, the announcement and the follow-up's own text become the note.
  - The follow-up's own text is held. Without a tool call it is dropped when short ("XONG") and kept when long (an
    error list the user asked to approve first), and the original answer stands.
  - Tests: `tests/test_follow_up.py`, with a fake Responses client and an end-to-end chat edit.
- **UI** (`WorkTimeline.tsx`; never a `workLog.ts` beside a `WorkLog.tsx`: the `LocalVoice` problem below).
  - **While running:** the header reads "Đang làm m:ss" on the client clock (`workStartedAt`), and every step has its own
    time.
  - **Think steps are one line** (the owner's call after the first real run on 2026-10-05: Grok's summary came as dozens
    of Vietnamese paragraphs, "Đang kiểm tra từng dòng nhân viên…", and the open step filled the screen). While running,
    the line is the latest thought (`latestThought`: the last `**heading**`, else the last paragraph), cut with an
    ellipsis by CSS. Once done it reads "Đã suy nghĩ". A click opens the whole summary in a 240 px scroll box, and a step
    closes again when it finishes. `ThinkStep` toggles from its own state on the summary click, because jsdom does not
    open `<details>` on a click.
  - **Notes and refusals:** notes are plain text; refusals are listed in red. The tool's hint line to the model ("Sửa
    công thức, hoặc bọc IFERROR…") is not shown as a refusal.
  - **Open or closed:** the block collapses when answer text appears, and again when the turn ends, even if the user
    opened it meanwhile. A turn that stopped before any text stays open.
  - **Finished:** "Đã làm trong 3 phút 18 giây". A stopped turn reads "Đã dừng sau …", with "Đã dừng khi …" on the
    unfinished step.
  - **No final `work` event** (Stop, lost connection): `closeWork` closes the steps on the client clock.
  - **Stopped turns** (2026-10-08, the owner asked for Grok's look). After Stop, once the server has accepted the
    message, the bubble always stays, even when empty. Explicit Stop now persists `stopped` through backend turn state,
    so F5 preserves the label and Retry action.
    It shows an italic "Đã dừng theo yêu cầu của bạn." and an action row with Sao chép (when there is text), "Thử lại"
    (last turn only) and a "Đã dừng" label. The notice above the composer remains only for a stop that came before
    the server stores the question, when the draft is still in the box. The Stop acknowledgment can recover a stored
    question even when its `meta` event never arrived.
  - **Retrying in place.** "Thử lại" and editing the last question both send `branch_message_id`. That always forked a
    new conversation version, so Stop and then resend left two chats with the same title (reported 2026-10-08).
    `conversation_actions.retry_in_place` now handles the case where the target is the last user message and everything
    after it is an unfinished assistant reply with no artifacts. It deletes that reply, updates the question's text, keeps
    its attachments and answers in the same conversation. Anything else still forks
    (`test_resending_a_stopped_last_question_stays_in_the_same_conversation`).
  - **Failed turn with no text:** the bubble is kept as `local` (not stored), and App skips it when matching stored ids
    by position.
- **Mock:** `__suaexcel__` shows the whole flow (note, compose, edit result), `__suynghi__` streams a long
  multi-paragraph summary like the real one, and `__slow__` shows the running clock.
- **Tests:** `backend/tests/test_work_log.py`, frontend `WorkTimeline.test.tsx`, `App.test.tsx` and `api.test.ts`.

### Tool calling

The tool loop lives **inside the provider** (`ai/xai.py`), not in the route. The provider
sends `TOOL_SCHEMAS`, runs the loop itself with `store=false` (conversation state is kept
in the `input` array rather than on xAI servers), and yields only assistant text upward.
Limits: `MAX_TOOL_ROUNDS = 3`, `MAX_TOOL_CALLS = 8`; when GitHub tools are available,
`MAX_GITHUB_TOOL_ROUNDS = 12` and `MAX_GITHUB_TOOL_CALLS = 30` apply across the turn's tools, and a conversation with an
editable workbook gets `MAX_WORKBOOK_TOOL_ROUNDS = 8` and `MAX_WORKBOOK_TOOL_CALLS = 16` (the larger limits win).
These are ceilings, not a target or a guarantee of reading an entire repository; the model can finish earlier.
The final model request disables all tools and asks it to summarize available results and disclose missing data.
Calls beyond the count limit receive a not-executed result; they never run. A provider that still calls tools on
the final request raises a clear error instead of looping. The existing per-turn timeout still applies.

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

If a native search item fails after a completed search in the same turn supplied valid sources,
`ResponsesProvider` closes that stream and uses one remaining tool round to summarize without any tools
(an empty `tools` list, omitting `tool_choice`). xAI rejects even `tool_choice=none` with no tools;
this also applies to normal tool-budget finalization. It keeps completed search/message/reasoning items and drops the interrupted round's
draft, failed items and unexecuted function calls. The final instructions disclose the supplemental lookup
failure and distinguish unread/unverified gaps; URLs alone are not page contents. No successful sources,
timeouts, connection errors or failure of the summarizing call still follow the existing error handling.
This is a bounded summary call, not a retry of the failed search; all normal chat timeout/output limits remain.

**Links the user sends** (2026-10-11). The owner noticed Peto analysed a YouTube link while Luna and Haiku only
searched around it. Per the providers' docs, xAI's web search browses pages itself, OpenAI's can `open_page` on reasoning
models, and Peto gave Claude only `web_search`. No provider documents video understanding; nothing here watches videos.
- `shared/youtube.py`: for YouTube links in the last three user messages (watch, youtu.be, shorts, live, embed; exact
  hosts only, at most three), `_build_system_prompt` adds title and channel from the fixed public oEmbed endpoint, for
  every model and mode. No redirects, 3 s timeout, 64 KB cap, cached a day (failures 10 minutes); any failure adds
  nothing. Titles are JSON-quoted data; the block forbids describing unseen scenes and reproducing lyrics.
- Claude Chat also gets `web_fetch_20250910` (`max_uses` 3, `max_content_tokens` 20,000; no fee beyond tokens; Claude
  can only fetch URLs already in the conversation). Not in Agent: the CLI browser asks per domain and a server-side
  fetch would bypass it. A fetched page becomes a `web_search_call` item with action `fetch`, so it shows as a source
  card and is not counted as a billed search; a failed fetch (JS-only page, blocked) adds no item and the turn goes on.
  `ClaudeClient` emits `peto.page_fetch.started` / `.failed`, and the provider turns those and completed fetch items
  into `StreamChunk("page", fetching|fetched|failed)`, the work log's `page` step. The SSE `search` event keeps only
  `searching`/`completed` for pages loaded before the update.

`shared/web_search.py` validates HTTP(S) source URLs, removes duplicates and bounds the list.
Extract sources from tool outputs or URL annotations, never by scraping model prose
for links. Persist them in `messages.sources`, return them in history, and include them
as clearly marked old references in the next model input. Frontend `WebSources.tsx`
renders source links without downloading favicons; SSE `search` and `sources` events
flow through `api.ts` and stay separate from `delta` and `thinking`.
Source cards use bundled SVG icons for YouTube (red) and GitHub, with a globe for other hosts.
Recognition uses the actual hostname, including YouTube short/mobile URLs and GitHub subdomains;
titles, URL paths and lookalike domains cannot select a brand icon. The outer source pill shows
a brand only when every source belongs to that service, otherwise it keeps the globe.
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

`shared/attachments.py` validates by **magic bytes first**, then declared MIME / extension. A file
claiming to be an image but failing `sniff_image_mime` is rejected outright. Images become
data URLs for the model. `features/documents/reader.py` reads PDF text with page labels, DOCX body
paragraphs/tables, and UTF-8/UTF-16 text in a cancellable AnyIO worker process. `features/documents/ocr.py`
renders pages without native text with PDFium in cancellable workers (4 MP/4096 px output; checks source images
before rendering, 20 MP/image, 40 MP/page, 2000 objects and 8 form nesting levels) and feeds PNG through
stdin to local Tesseract (`vie+eng`, installed separately; see backend/README.md). Required languages are checked
before new OCR; do not silently accept Tesseract's fallback when only one language loads. OCR has a global two-page limiter,
one CPU thread per engine, 8 scanned pages/file, 30s total including queue/render time and 8s/page; subprocess
output is capped and cancellation closes/kills the engine. Native text survives OCR errors/timeouts. Labels keep
original page numbers and identify OCR; notices expose read/total counts and accuracy limitations.
Missing/disabled OCR and encrypted/broken/oversized documents retain honest reading status.
Do not promise PDF image/layout understanding, complete Word page layout, native Word charts or legacy .doc support.

**Word uploads** (`features/documents/word_reader.py`, 2026-10-06). The owner's Word uses are solving math exercises sent
as .docx and writing school reports. The old reader took only `w:t`, so every Word equation (Alt+=, OMML) vanished:
"Rút gọn A = (x+1)/(x²−1)" reached Peto as "Rút gọn biểu thức sau:". The owner's own exercise survived only because its
formulas were typed as Unicode math italics with combining overlines.
- **Equations** become LaTeX (`math/omml_in.py`): `$…$` inline, `$$…$$` for `m:oMathPara`. Fractions, roots, scripts,
  n-ary operators, functions and limits, accents, bars, delimiters (cases, matrices, binomials), equation arrays, group
  characters, boxes and phantoms are mapped; math alphanumerics such as 𝑥 go back to `x`, ℝ to `\mathbb{R}`.
- **Numbering labels.** Word's automatic labels (a), b), 1.1., •) are not text, so Peto never saw which sub-question was
  c). `Numbering` follows numbering.xml and paragraph styles like Word: counters per abstractNum, deeper levels restart,
  `startOverride` restarts a list on its first use, `numStyleLink` is followed once, bullets in Symbol/Wingdings read as •.
- **Symbol font.** Old worksheets typed Greek and operators in the Symbol font ("x Î A" for x ∈ A); runs in that font and
  `w:sym` are mapped through the Adobe Symbol table (`math/symbols.SYMBOL_FONT`).
- **Embedded pictures** (`word_images.py`, 2026-10-11) follow body relationships and retain `[Hình N trong tệp]`
  numbers. Raster pictures are normalized with Pillow in the reader process, respecting DrawingML crop/rotation;
  no external links or orphan media are loaded. At most the first 8 references are attempted, with 10 MiB/20 MP
  source limits, 2048 px maximum edge, 1 MiB/output and 4 MiB total. Unsupported/broken/omitted pictures remain
  explicitly unread; headers, footers, native charts and vector media are not rendered as Word pages.
  Chat history sends selected pictures through the existing shared Responses/Claude image pipeline, labelled with
  filename and figure number. The existing `MAX_HISTORY_IMAGES` budget (default 4) is shared with standalone images,
  preferring recent messages; omitted pictures are identified in model context. Word figures do not consume the
  standalone "Ảnh N" numbering used by generated documents. Selected project DOCX files use the same pipeline.
- **Marked, not read:** native charts (`[Biểu đồ N trong tệp]`) and MathType/Equation 3.0 OLE objects
  (`[Công thức MathType N: Peto không đọc được]`). These and unread pictures make status `partial`, with `truncated`
  false unless text was cut, so history does not suggest attachment text tools to recover images. The notice asks
  for a screenshot. Text boxes are read once (only the `mc:Choice` of an AlternateContent); tracked deletions are skipped.
- **Cache.** Word results carry `word_format` (`WORD_FORMAT` 3). Older Word reads are re-read lazily from the original
  file, including selected project files, without changing visible attachments. Normalized `embedded_images` stay
  in the internal document cache for follow-up turns; `public_document` exposes counts, never bitmap/data URLs.
  `formulas`, `formulas_unread`, `images`, `images_prepared` and `images_unread` are public.
- **Tests:** `tests/test_word_reader.py`, `tests/test_word_images.py`; provider tests use mocks, not paid API calls.

**Excel uploads** (`features/documents/workbook_reader.py`, 2026-10-04, the owner's next step after `create_spreadsheet`).
`.xlsx` and `.xlsm` are accepted as attachments (magic bytes `PK`, counted as media like PDF/Word). An OLE container
(`CFB_MAGIC`: legacy `.xls` or a password-protected workbook) and `.xls` are refused at upload with a Vietnamese hint
to save as `.xlsx`.
- **No new dependency.** Parsing uses `zipfile` and defusedxml `iterparse` (DTD forbidden), streaming each part through
  `_Limited` (48 MB per part, 8 MB for workbook/styles/rels; declared total 192 MB, 5000 entries). Reading stops at
  50,000 rows per sheet, 256 columns, 400,000 cells, 30 sheets and 200,000 shared strings, and the notice says what was
  skipped. It runs in the document reader's worker process under the same timeout. Macros never run, formulas are
  never recalculated: values are the results Excel stored.
- **Text for the model**, one row per line so the attachment tools work: a workbook line (sheet list, chart sheets,
  visible defined names), then per sheet a header (area, row count, hidden), merged ranges, formulas grouped into
  copied-down/copied-right runs by relative pattern (`relative_pattern`), then `Hàng N | A: … | B: …`.
  - Values use the `create_spreadsheet` cell syntax: machine numbers, percents rounded to the format's decimals, ISO
    dates (1900 and 1904 systems), `TRUE`/`FALSE`, error codes. So Peto can rebuild an uploaded workbook with the tool;
    the prompt says colours, custom formats and charts of the original are lost.
  - Shared formulas are expanded by shifting relative references (`shift_formula`); formulas without a stored result
    show `(chưa có kết quả)` and are counted in the notice.
  - **What the owner's planted-error test exposed** (2026-10-05, `bang_test_loi_luong_diem.xlsx` against Claude.ai's
    answer key). Peto missed three planted errors only because the text hid them; all three were fixed that day:
    - Only 10 merges were listed, and the bad `E10:F10` was the 11th. `MAX_MERGES_SHOWN` is now 100.
    - `_cell_text` stripped spaces, so "Võ Thị Em " and " Bùi Lan" looked clean. Now an empty text, text with spaces
      at either end, and text starting with `"` are written in double quotes (inner quotes doubled, as in formula
      strings). One workbook line explains the quotes, and each sheet head lists the padded cells (up to 30).
    - Excel stores a formula returning "" as `t="str"` with an empty `<v>`, which ElementTree reads as no value. Every
      `IF(…,"",…)` therefore showed `(chưa có kết quả)` and counted as "made by other software". It now shows `""`.
      An empty `<v>` on a number cell (XlsxWriter's way to force a recalc) still counts as uncached, and
      `workbook_grid` marks pending cells by the same rule (`Cell.has_value`).
- **Long workbooks** use `workbook_reader.condense`, not the log condenser: shape-collapsing would erase data rows,
  which all look alike. It keeps every header and formula line and, per sheet, head and tail rows (totals live at the
  end), with `[… bỏ qua dòng a–b của tệp (hàng Excel x–y) …]` markers that cite the full text's line numbers for
  `read_attachment_lines`.
- **Charts, tables, pivot tables and cell notes** (2026-10-05) are read by `workbook_parts.py`: classic and `chartEx`
  charts with their series ranges and cached values, drawings' text boxes, Excel Tables, pivot table layouts, legacy
  notes and threaded comments with their authors (at most 30 charts, 40 text boxes and 200 notes). Chart sheets get a
  `[Trang biểu đồ "X"]` block. `SHEET_FORMAT` (3 since the fixes above) is stored in the cache, so older cached
  workbooks are re-read lazily.
- `public_document` exposes `sheets`, `sheets_read` and `rows`; the chat shows "· N trang tính" (or `k/N`). The composer
  shows a note about what Excel reading covers. Excel error codes count as signal lines for the log condenser too.
- **Tests:** `tests/test_workbook_reader.py` (XlsxWriter-built workbooks plus hand-built packages for shared formulas,
  missing addresses, DTDs and oversized parts), frontend `DocumentReading.test.tsx` and an Excel case in `App.test.tsx`.

The `attachments.document` JSON cache stores text plus version/status/notice and counts.
Version 3 caches OCR text per page privately; tools reuse it when the engine signature matches. Old cache versions
are lazily reread; a changed engine path/mtime, enabled flag, languages or page limit triggers rereading scanned
files on follow-up. Disabling/uninstalling OCR preserves already cached OCR text; fully cached scans require no engine
process even for tools. Adding language data or retrying transient failures without a settings change requires reupload.
`_public_attachment` exposes only the status metadata, never native/OCR text, engine settings or disk paths. Read new
documents inside admission, before shielded writes; emit `reading` SSE without treating it
as acceptance. `meta` acknowledges persistence. Legacy files are lazily cached with an
owner-filtered UPDATE, at most MAX_ATTACHMENTS total reads per turn including new files.
`_to_chat_messages` applies MAX_DOCUMENT_CONTEXT_CHARS, newest message first and shared
between files in that message. Always tell the model when text is missing/truncated.
PDF parsing has page/decompression/time limits; DOCX ZIP/XML has size limits and rejects
DTD/external entities. Dependencies: pinned pypdf and defusedxml in requirements.txt.

**Long files** (2026-09-29, both levels picked by the owner after "a long log, and Peto read only a little of it").
Before this, a text file kept only its first 80,000 characters, so the errors at the end of a log never reached Peto.
- **Condensed excerpt.** `document_reader.condense_text` keeps a text file over `MAX_TEXT_EXCERPT_CHARS` in three
  parts: the start (15%), error/warning blocks from the middle (`SIGNAL`, 2 lines of context each, one block per line
  shape, up to 35%), and the end (the rest). It cuts only at line boundaries.
  - Runs of 5+ lines of the same shape (digits and hex ignored) collapse into first, "[… N dòng cùng dạng …]", last.
  - Each block opens with "[Dòng a–b]" in real line numbers. Files of 20 lines or fewer keep a head and tail by
    characters instead.
  - `VERSION` went to 2, so old cached excerpts are re-read lazily.
  - The notice is shown to users under "Đọc được một phần", so it names no tools.
- **Tools** (`shared/attachment_tools.py`): `search_attachment` (plain case- and diacritic-insensitive text, alternatives
  split by " | ", never regex) and `read_attachment_lines` (at most 400 lines).
  - They work on the whole file, re-read from disk. Text is decoded as is; PDF and Word go through
    `read_full_document`, still bounded by the page cap and the timeout.
  - Only files in the owner-filtered rows of this turn (`AttachmentFiles(rows)`, chat mode) can be opened, by the stored
    path. Results are capped (40 matches, 16,000 characters) and carry `DATA_NOTE`.
  - `ai/xai.py` offers them only when the conversation has files, and emits `file_lookup` / `file_lookup_done` chunks.
    Each lookup becomes a `lookup` step of the work log (see "Work log").
  - `_to_chat_messages` tells the model the tool names and the file name whenever an excerpt is partial.
  - The mock answers `__timtep__:<query>` by searching the newest file.
- **anyio re-runs the parent's `__main__` file** in the reader's worker process. A dev launcher script without an
  `if __name__ == "__main__":` guard around `uvicorn.run` starts a second server there, and every read then fails as
  "Bộ đọc tài liệu đang gặp lỗi" (hit on 2026-09-29 with a scratch launcher; `uvicorn main:app` is safe).
- **Tests:** `tests/test_attachment_tools.py` (excerpt, tools, provider loop with a fake client, chat API);
  `frontend/tests/api.test.ts` and `App.test.tsx` for the event and the work log.

Only the `MAX_HISTORY_IMAGES` (default 4) most recent images are re-sent to the model;
older ones degrade to a text placeholder. This is computed twice — in
`features.chat.history._to_chat_messages` (which decides what to read off disk) and in
`ai/xai._recent_image_keys` (which decides what to send). Keep them consistent.

### Documents in chat (`create_document`)

`features/documents/tools.py` gives the Chat tab (not Companion or the agent) a `create_document` tool. The model sends a title and
Markdown; `document_jobs.build_files` renders a PDF (ReportLab, `pdf_out.py` behind `document_export.render_pdf`) and a DOCX
(python-docx, `docx_out.py` behind `render_docx`), `storage/documents.py` keeps them per owner, and the card shows page 1
of the PDF (pypdfium2). The DOCX preview is that PDF, so a feature must exist in both renderers or the preview misleads.
`export.py` keeps what both share: Markdown → blocks, the math glue, column widths and font registration. The four styles
and the cover page are under "Styles and cover" below.

On 2026-09-30 the owner picked a Word/PDF upgrade as the first step of the document roadmap. Mermaid diagrams in chat
came second, PowerPoint third and Excel fourth (sections below).
- **Real lists.** Every Markdown list gets its own Word numbering definition (`_numbering_level`), so numbers restart per
  list, honour `start`, and Word renumbers when the user edits. Nested ordered lists go 1. → a. → i., bullets • → –.
  The PDF draws the same labels (`list_label`) at the same hanging indents (`list_indent`). Later paragraphs of an item
  carry no number.
- **Images.** A line `![caption](anh-N)` inserts the Nth image the user sent in this conversation (`features/documents/images.py`),
  with the caption below it.
  - Only that owner's images of that conversation, filtered in SQL and read from the stored path. Any other image URL
    stays text (`[Ảnh: …]`) and is never fetched.
  - Images are shrunk to 1600 px: PNG for transparency, screenshots and GIFs, JPEG for photos. At most 12 per document;
    images over 40 megapixels are refused before decoding.
  - "Ảnh N" counts the conversation's images by `created_at, rowid`. `db._attach_files` puts the same `number` on each
    image, `ai/xai.build_input_payload` labels it `[Ảnh N: name]` for the model, and `conversation_actions.fork` copies
    images in that order, so a new version keeps the numbers.
  - The tool refuses a number that does not exist, so the model can fix it. A hand-edited draft shows text instead.
- **Contents.** A line `[TOC]` (or `[Mục lục]`) outside lists and quotes becomes "Mục lục" with headings of levels 1–3,
  followed by a page break.
  - PDF: ReportLab's `TableOfContents` with real page numbers (`multiBuild`). Every heading also becomes a PDF bookmark.
  - DOCX: a TOC field marked dirty. Word asks to update fields on open, then fills in page numbers; other viewers show
    the heading list written into the field. The tool result tells Peto to mention that prompt.
- **Word styles.** python-docx's template gives Title and Heading styles theme fonts (`asciiTheme`), which beat the font
  name set on them: Word showed Calibri instead of Times New Roman or Arial, and a blue rule under the title. `render_docx`
  strips the theme attributes and the rule, and matches heading sizes and spacing to the PDF.
- **Render queue.** `document_jobs.RenderQueue` still renders one document at a time per process (small VPS). Later
  requests wait in a short line instead of failing at once as the old lock did: 4 waiting at most, 30 s for the tool,
  15 s for exports, 10 s for preview pages.
- **Formulas** (2026-10-06, step 2 of the owner's Word plan). Before, the tool said "Chưa hỗ trợ LaTeX" and a math
  solution printed `$\bar{x}$` raw, so the owner copied answers from the chat, which turned overlines into "xˉ".
  - **Extraction first.** `math/markdown.extract` swaps `$…$`, `$$…$$`, `\(…\)` and `\[…\]` for private-use placeholders
    before markdown-it runs: a display formula continued on a line starting with "+ " would otherwise become a bullet,
    and Markdown eats the backslash of `\(`. Code spans and fences are skipped. Dollar rules follow Pandoc ("giá $5 và $10"
    is not math); `~p` in operand position is negation, as in the chat's `tildeNegation`.
  - **One tree, two renderers.** `math/latex.py` parses a fixed command set (tables in `math/symbols.py`) into nodes and
    refuses anything else with a Vietnamese message naming the formula, so Peto rewrites it and calls again.
    `math/omml_out.py` writes native Word equations: Cambria Math runs, `\text` in the document font, child order per the
    OMML schema. `aligned` and `cases` are `m:m` matrices with justified columns, since alignment marks inside `m:eqArr`
    are unverified; primes stay plain characters as in Word.
  - **PDF** (`math/layout.py`): a TeX-style layout with the bundled STIX Two Math (OFL; the MATH table constants are
    copied into `C`). Italic letters use the Unicode math alphanumerics; tall delimiters, radicals, braces and wide
    accents are vector paths, because ReportLab cannot reach the font's size variants.
    - Inline formulas sit in an `<img>` slot of the formula's size (`assets/math-slot.png`, `valign` = −depth).
      `attach_math` tags each slot's ImageReader with its box, and `MathCanvas.drawImage` (`math_canvas`) draws vector
      math there.
    - Body styles use `autoLeading="max"`, so tall inline fractions push lines apart. Display formulas are a flowable,
      shrunk to fit, with `\tag` at the right.
    - Plain-text symbols Tinos lacks (≤, ∈, →) are drawn in STIX via `<font>` instead of failing the PDF.
  - Limits: 600 formulas, 4,000 characters and 3,000 nodes per formula. Tables now allow 12 columns (a 4-variable
    truth table has 9).
  - Neither Word nor LibreOffice is installed here, so the OMML was checked by round trips (`omml_out` → `omml_in`) and
    schema order. The owner then opened a sample DOCX in Word: the equations display and can be edited.
- **Styles and cover** (step 3 of the owner's Word plan). The owner found Peto's reports "non, chưa chỉnh chu": US Letter,
  Arial, no cover page, a title printed twice. They have no school-specific rules. On 2026-10-06 they saw three live
  mockups (https://claude.ai/artifact/R79UV3ASRLWUd49j79ZvzR) and kept all three:
  - **Khung đôi** (`classic`, the default) for đồ án tốt nghiệp and khóa luận.
  - **Dải màu** (`band`) for báo cáo môn học and đồ án nhóm.
  - **Tối giản** (`minimal`) for tiểu luận, lời giải and simple documents.

  `essay` stays for nghị luận. The prompt picks a style by document type and follows the user when they name one.
  - **Shared standard** (`themes.py`). Every style uses the usual Vietnamese school layout: A4, Times New Roman 13, 1.5
    line spacing, justified, 1 cm first-line indent, margins top 2, bottom 2, left 3, right 2 cm. A frozen `Theme` holds
    only what differs:
    - heading sizes, caps, italics and colour;
    - the title block when there is no cover;
    - tables (`grid`, `band`, `booktabs`) and code boxes (`box`, `bar`, `rules`);
    - captions, header (none, `split`, `title`), footer and cover.
  - **Old `report` documents** keep their stored files; anything rendered now (a revision, or exporting a hand-edited
    version) uses `classic` (`ALIASES`). The API still accepts `report`; the tool offers only the four, and new manual
    drafts send `classic`.
  - **PDF fonts.** Tinos and Cousine are bundled (OFL, metric-compatible with Times New Roman and Courier New), so line
    breaks and page numbers almost match Word. Documents no longer use Noto; the files stay in `assets/fonts`.
  - **Cover data** (`cover.py`). It is a `--- … ---` block of `khóa: giá trị` lines at the very start of the Markdown, so
    the user can fix a school name or MSSV in "Sửa nội dung" without asking Peto.
    - Keys are matched unaccented, with English aliases. The cover keys are: `trường`, `khoa`, `cơ quan`, `loại`, `môn`,
      `đề tài`, `phụ đề`, `giảng viên` (or `GVHD`), `nhóm`, `lớp`, `nơi`, `ngày` and `logo: anh-N`.
    - `thành viên` is a list of `- Tên | MSSV | ghi chú` lines, 15 at most.
    - An unknown key is refused with the allowed list, so the model fixes the call. A block that is not at the start, or
      never closes, is ordinary content.
    - Missing fields print dotted blanks (`DOTS`) for the user to fill. A missing date is the current month in
      `DEFAULT_TIMEZONE`. The prompt forbids inventing a school, instructor, members or MSSV.
  - **Word cover** (`docx_out.py`).
    - Word cannot push text to the page foot, so the cover is a borderless three-row layout table with exact row heights:
      the school block at the top, the title mid-page, the people at the bottom.
    - Each style draws its own frame:
      - `classic`: a double frame as a page border on the first page only (`w:pgBorders display="firstPage"`);
      - `band`: a navy rectangle anchored to the page (`wps` inside `mc:AlternateContent` with a VML fallback, behind the
        text);
      - `minimal`: rules made of paragraph borders.
    - The cover page has no header or footer. Elements python-docx lacks are inserted in schema order (`_insert`),
      because Word calls a file damaged when children are out of order.
  - **PDF cover** (`pdf_out.py`). It is painted straight onto page 1 (`onFirstPage`), and the text flow starts on page 2.
  - **Title.** An opening heading equal to the title, or the only heading at its level (`# Lời giải bài tập 5` followed
    by `## Bài 1`), becomes the title block instead of printing twice (`body_blocks`). The remaining headings are
    renumbered from level 1. Without a cover, page 1 has no running header.
  - **Captions and slots.**
    - A paragraph "Bảng: tên" right above a table becomes "Bảng N. tên" ("Bảng N: tên" in `band`), kept with the table.
    - Captioned images become "Hình N. …".
    - `![chú thích](khung-anh)` leaves a dashed 5.4 cm frame reading "Chỗ dán ảnh chụp màn hình", with its Hình number,
      where the user pastes a screenshot in Word (30 per document).
  - **Tables.** Column widths come from the visible text (`column_widths`): never narrower than the longest word, and
    math counted by the symbols it shows. Header rows repeat on every page.
  - **Page breaks.** Both renderers now break pages the same way.
    - Tables of up to `SHORT_TABLE_ROWS` (12) rows never split. Word gets this from rows that keep with the next one and
      `cantSplit`; the PDF from a KeepTogether. Longer tables split between rows.
    - In the PDF, headings and long-table captions stay with the start of the next block, as Word's "keep with next"
      does. This is `_KeepStart`, plugged in through the template's `handle_keepWithNext`.
    - ReportLab's own grouping caused two problems. It moved a heading together with a whole long paragraph or table to
      the next page, which left up to half a page blank. It also never grouped a heading with a following KeepTogether,
      so a heading before a short table or an image could end up alone at the bottom of a page.
    - The group now moves only when the space left cannot hold the heading plus the next block's own first split: two
      lines of a paragraph, or the header and first row of a table.
  - **Word contents.** The TOC field is still marked dirty, so Word offers to update it. `build_files` (and `export_file`
    for hand-edited versions that have a `[TOC]` line) now renders the PDF first and passes its heading pages
    (`toc_pages`) to the DOCX. Viewers that never update fields (phones, Google Docs) therefore show real page numbers
    with dot leaders.
  - **Mock.** `__baocao__` (or `__baocao__:band`, `:minimal`) creates a sample report with placeholder names.
  - **Not yet checked in real Word:** the band rectangle, the first-page border, the cover heights and the pre-filled
    contents.
  - **Tests:** `tests/test_document_themes.py`.
- **Small fixes that day.** The essay header said "Nghị luận xã hội" on every essay (now the title). Table cells and
  code lines took the essay's first-line indent and justification.
- **Not done:** charts and images from Imagine (the user attaches them). Editing an uploaded Word file in place is
  "Editing uploaded Word files" below.
- **Tests:** `tests/test_document_features.py`, `test_document_export.py`, `test_document_artifacts.py`,
  `test_document_math.py`.

### Diagrams in chat (Mermaid)

The second step of the document roadmap. On 2026-09-30 the owner picked "Thẻ bên phải" from mockups: a ```mermaid block
in a Chat reply becomes a card in the bubble (`DiagramCard.tsx`: thumbnail, title, kind), and clicking it opens the
diagram large in a panel on the right (`DiagramPanel.tsx`), where the document panel sits.
- **Mermaid 11, not 12.** 12 (released 2026-09-10) needs Safari 17.4+ and bundles the heavier ELK layout by default.
  `diagrams.renderDiagram` imports it dynamically, so it loads only once a reply has a diagram. The panel is its own
  `preloadable` chunk (`diagramPanelLazy.ts`), warmed when the pointer enters a card.
- **Rendering.** `mermaid.initialize` is global, so renders queue one at a time: a light-theme export must not leak into
  a dark card.
  - `securityLevel: "strict"`: the code is written by the model, which a web page can steer, so no HTML, links or click
    handlers.
  - `htmlLabels: false`: labels are SVG text, not `foreignObject` HTML, which taints the canvas and breaks PNG and PDF.
  - Colours come from the app's tokens (`PALETTE`), including `rowOdd`/`rowEven`. Left unset, Mermaid 11 derives ERD rows
    from the primary colour, which gave pale rows with unreadable text on the dark theme.
  - `useDiagramTheme` follows `data-theme`. A theme change re-renders and keeps the old picture until the new one is
    ready.
- **While a reply streams** the card only says "Đang vẽ sơ đồ…" (`pending`), because half-written code would flash
  syntax errors. Code Mermaid rejects shows a Vietnamese note and the code.
- **`components` in `ChatMessage` must stay memoized** (`useMemo` on `writing`). An inline object gave react-markdown new
  component types on every render, which remounted every card (re-running Mermaid) and reset code-block copy buttons.
- **Title and kind.** The title is `title:` in the block's `---` front matter; the kind comes from the first keyword.
  Mermaid has no activity or use case diagram, so Peto draws them with `stateDiagram-v2`, `swimlane-beta` and
  `flowchart` and starts the title with "Sơ đồ hoạt động: " or "Sơ đồ use case: ". `NAMED_KINDS` reads the kind from that
  prefix, and `kindNote` avoids "Sơ đồ tuần tự · Sơ đồ tuần tự".
- **Swimlanes.** Mermaid 11.17 ships `swimlane-beta`: flowchart syntax, each `subgraph` a lane, laid out as real lanes.
  draw.io's import turns it into its own lane shapes (both checked on 2026-09-30).
  - Vertical lanes only: `LR` routed arrows in long loops around the whole diagram.
  - A node declared outside every lane gets an extra lane with no name, so the prompt puts every node, start and end
    included, inside its lane. Cross-lane arrows go after the last `end`: a node lands in the first lane that mentions
    it, so an arrow written inside one lane pulls the node it points to into that lane.
  - The lane header row sits where Mermaid puts the title, so `renderDiagram` raises `flowchart.titleTopMargin` to
    `LANE_TITLE_MARGIN` for these diagrams.
  - UML symbols come from Mermaid 11's shapes: `sm-circ` start, `fr-circ` end, `fork` bars, `{}` decisions. `themeCSS`
    fills the start dot and the end's inner dot with the line colour; by default they took the node fill and the pale
    border colour. The second rule skips nodes with text, so a labelled double circle `((( )))` keeps its fill.
  - It is a beta: recheck it (and the prompt) after any Mermaid update. The lock file pins 11.17.2.
- **Panel.**
  - Drag to pan; zoom with the wheel (a non-passive listener, since React's is passive), a pinch, or + − 0 and arrows.
    "Vừa khung" fits the diagram above the zoom controls. A "Mã" tab shows the code with a copy button.
  - ‹ › and "N / M" walk the conversation's diagrams. `diagramCodes` in `App.tsx` collects them with `diagramBlocks`,
    which reads fences as Markdown does (`~~~`, longer fences, blocks in lists, an unclosed last block) and skips the
    reply still streaming. `normalizeDiagram` makes a card's code (from the hast tree) equal the list's (from raw text).
  - It reuses the document panel's `<dialog>` and classes: `show()` beside the chat, `showModal()` over the screen at
    1100px and below. Opening a diagram closes the document panel. Switching conversations, Ctrl+Alt+B and the document
    panel's button close the diagram.
- **Downloads** ("Tải", `diagramExport.ts`) always render the light theme, so a PNG pasted into Word is not a black
  block. PNG at 2×, SVG as rendered, and PDF: a 3× JPEG on one A4 page (portrait or landscape by shape, 36 pt margin),
  written by `pdfFromJpeg` without a library. Canvases stay under 16 M pixels, since iPhone Safari draws a blank image
  above about 16.7 M.
- **draw.io.** The "draw.io" link is `https://app.diagrams.net/#create=` plus the JSON that draw.io's own tool
  (@drawio/mcp) builds: `{type: "mermaid", compressed, data}`, with `data` the base64 of deflate-raw of
  `encodeURIComponent(code)`, or the raw code when `CompressionStream` is missing. draw.io turns it into editable shapes,
  which is the way to manual layout and a vector PDF.
  - **Keep the URL free of query parameters.** With any of them (that tool adds `grid`, `pv`, `border`, `edit`), draw.io
    asked "Tất cả mọi thay đổi sẽ mất!" right after opening, and "Loại bỏ" threw the diagram away. Checked in headless
    Edge on 2026-09-30.
- **Prompt.** A `WEB_PLATFORM_PROMPT` line tells Peto that diagrams, unlike pictures, are drawn right in the reply, never
  in Tạo ảnh. The detailed `persona.DIAGRAM_PROMPT` (front-matter titles, IDs and quoting, class, sequence, activity, use
  case, ERD) is appended only on Chat turns whose recent user messages mention diagrams
  (`build_diagram_guide`, unaccented keywords), so other turns pay nothing for it. Its rules come from real Mermaid 11
  errors: `<<choice>>`, `<<fork>>` and `<<join>>` states declared after their first use render as plain boxes, and
  parentheses in an unquoted `[ ]` label are a syntax error.
- **Not done:** use case diagrams (Mermaid has none; Peto approximates them with a flowchart), and diagrams inside
  `create_document` files (the user can download the PNG and attach it).
- **Tests.**
  - `frontend/tests/diagrams.test.ts`: kinds and titles, fences, the PDF's structure and xref offsets, the draw.io
    payload round trip.
  - `DiagramPanel.test.tsx` mocks `mermaid`: cards, the panel, the download menu, the draw.io link, sharing the space
    with the document panel, pending and error cards, re-rendering on a theme change.
  - `backend/tests/test_diagrams.py`: the guide's keywords and where it is appended. The mock answers `__sodo__` with a
    class, a sequence, an activity and a swimlane diagram (`DIAGRAM_SAMPLE`). Its chunker now streams whitespace
    exactly; it used to drop the spaces after each chunk, which broke code indentation.

### Presentations in chat (`create_presentation`)

The third step of the document roadmap, built on 2026-10-04. The owner liked all three styles from live mockups
(`frontend/prototypes/slides`, deleted after the pick) and chose to keep them all: Gọn sáng (`clean`, default), Học thuật
(`academic`) and Đậm nét (`bold`). Peto picks one by context and follows the user when they name one. There is no manual
slide editor in v1, also the owner's call: changes go through chat and create a new version.
- **Tool.** `features/documents/slides/spec.py` holds the strict schema. A deck has a title, a theme and up to 25
  slides in seven layouts: cover, agenda, bullets, two_columns, image_text, table, chart.
  - Every field of every layout is present and null when unused.
  - Tables and charts are flat `table_*` / `chart_*` fields, not nullable nested objects, because not every provider
    accepts `anyOf` in strict mode.
  - `normalize` cleans the text and checks limits per layout. Its errors name the slide ("Slide 3 (bullets): …"), so
    the model can fix the call and try again.
  - `DocumentSession.present` mirrors `create`: at most two artifacts per turn, idempotent, rejects unaccented
    Vietnamese, and takes images only from this conversation's `[Ảnh N]`.
- **One layout, two renderers.** `layout.py` turns each slide into positioned shapes (`scene.py`, points on a 960×540
  slide). `pptx_out.py` (python-pptx) and `pdf_out.py` (ReportLab) only draw those shapes, so the preview matches the
  download.
  - **Metrics.** Text is wrapped with real font metrics. The PPTX names Arial and Times New Roman; measuring and the
    PDF use the bundled Liberation Sans and Serif. Their widths match exactly (checked 2026-10-04), so line breaks
    match PowerPoint.
  - **No Georgia.** It lacks precomposed glyphs such as "ố" and broke Vietnamese accents in the first mockup.
  - **Shrink, then refuse.** Text shrinks within a size range. If it still doesn't fit, `SlideOverflow` asks the
    model to shorten the slide or split it.
- **PPTX details.**
  - Titles sit in the slide's real title placeholder (outline view, screen readers), raised above shapes drawn
    before it.
  - Bullets are real PowerPoint bullets (`a:buChar`). Text boxes have zero insets and exact line spacing, slide
    numbers are `slidenum` fields, and runs carry `lang="vi-VN"`.
  - Tables use the "No Style, No Grid" table style with explicit borders.
  - Charts are native (column, bar, line, pie). Their value axis is fixed by `nice_axis` and shared with the preview.
    Bar charts reverse their data so the first category is on top.
  - The file's theme gets the style's fonts and accent colours, and the layouts of python-pptx's 4:3 template are
    widened, so slides the user adds still fit.
  - Speaker notes go to each slide's notes page.
- **Storage and API.**
  - The content is the normalized deck as compact JSON. History hands it back to the model, which is how "sửa slide
    3" works.
  - Decks store their file in `document_assets.pptx`, a new nullable column added by manual migration; `docx` is
    empty for decks.
  - Export serves `pptx` and `pdf`. A `docx` export of a deck returns 400, and so does a manual `versions` edit.
  - The conversation fork copies assets with an explicit column list. Its old positional insert would have broken
    with the new column.
- **UI.**
  - The card shows the whole first slide with a "Xem slide · N slide" chip, and "Tải PDF" replaces "Sửa nội dung".
  - The panel pages by "Slide N / M" and shows that slide's notes below it (`slideNotes`).
- **Mock.** `__slide__` or `__slide__:academic` creates a six-slide sample (`slide_sample`).
- **Not done:**
  - manual slide editing;
  - notes pages in the PDF;
  - transitions;
  - images from Imagine or the web;
  - a check in real PowerPoint: none is installed on this PC, so the custom XML was only checked against the
    schema's element order.
- **Tests:** `backend/tests/test_presentations.py`, frontend `DocumentArtifactCard.test.tsx` and `DocumentPanel.test.tsx`.

### Spreadsheets in chat (`create_spreadsheet`)

The fourth step of the document roadmap, built on 2026-10-04. The owner picked "Lưới Excel" from three live variants
(`frontend/prototypes/sheets`, deleted after the pick; the others were print pages like Word/PDF and a reading table
with formulas per column). The card shows a light mini grid of the first sheet; the panel shows an Excel-like grid.
- **Tool.** `features/documents/sheets/spec.py` holds the strict schema. A workbook has a title and 1–5 sheets, and each
  sheet is one table at A1: row 1 holds the headers, `rows[0]` is row 2, and the optional total row follows the last
  data row. This fixed addressing is what lets the model write correct formulas.
  - Columns have a format (text, number, percent, vnd, usd, date) and optional decimals. Cells are strings: text,
    machine numbers, `8%`, ISO dates or formulas.
  - `parse_cell` refuses malformed numbers (`1.500.000`, `7,5`), percents without `%` and non-ISO dates, naming the
    cell. Words in number columns (`Vắng`) stay text.
  - Limits: 20 columns, 300 data rows, 4000 cells, 4 charts per sheet and 8 per workbook; pies at most 10 rows.
  - `DocumentSession.tabulate` mirrors `present`: two artifacts per turn, idempotent, rejects unaccented Vietnamese.
    Its result carries `results` (total-row values, `view.summary`), so Peto quotes computed numbers instead of
    redoing the arithmetic.
- **Formulas** (`formula.py`, `engine.py`). Formulas are tokenized and parsed into a tree, never evaluated as code.
  - Only the functions in `FUNCTIONS` are accepted: Excel 2007-era names, so no `_xlfn.` prefix is needed. `;`
    separators become `,` when no `,` is present, smart quotes are normalized, and the canonical text (uppercase names
    and references, quoted sheet names) is what the file and the stored JSON hold.
  - XlsxWriter stores 0 as each formula's cached result, so phone previewers and LibreOffice (which by default does
    not recalculate Excel files) would show 0. `engine.compute` evaluates every formula by Excel's rules (coercion,
    15-significant-digit rounding and comparison, COUNTIF criteria with wildcards, 1900 date serials from 01/03/1900)
    in topological order, so long chains never recurse. The writer stores the results, and XlsxWriter's
    `fullCalcOnLoad` makes Excel recalculate on open.
  - Any error result, a cycle, a reference outside the table or to an unknown sheet is refused with the cell, the
    formula and a hint, so the model fixes it (IFERROR when an error is intended).
  - Approximate VLOOKUP/HLOOKUP/MATCH on unsorted or mixed data is refused (`#UNSORTED`, never written to a file):
    Excel's binary search gives unpredictable results there. Range arithmetic (`A2:A9*B2:B9`) is refused too;
    SUMPRODUCT and SUMIFS cover it.
  - Whole-column references are lazy: functions walk only the used area and count blank cells arithmetically, so
    COUNTBLANK(A:A) matches Excel.
- **File** (`xlsx_out.py`, `view.py`).
  - The header row is tinted with a teal rule, frozen, with autofilter. Data rows are banded by conditional formatting,
    which survives sorting. The total row is bold.
  - Number formats such as `#,##0 "₫"` follow the user's locale in Excel; the grid always shows Vietnamese style
    (`view.display`). Column widths come from display lengths, with room for the filter button, capped at 50 with wrap.
  - Print setup: A4, fit to width, repeated header row, the sheet title in the page header, page numbers in the footer.
  - Charts are native (column, bar, line, pie), anchored right of the table (8 columns or fewer) or below it. Their
    value axes are fixed by `view.nice_axis`, shared with the grid's SVG charts.
- **Storage and API.**
  - The content is the normalized workbook as compact JSON with canonical formulas. History hands it back to the
    model for revisions.
  - Files live in `document_assets.xlsx`, a new nullable column added by manual migration. `docx`, `pdf` and `preview`
    are empty, and `pages` is the sheet count.
  - `GET /api/documents/{id}/sheet?version=` recomputes the grid from the stored content (display strings, formulas,
    widths, charts). Export serves only `xlsx`, preview returns 404, a manual `versions` edit returns 400, and the
    conversation fork copies `xlsx`.
- **UI.**
  - `SheetPreview.tsx` (main chunk): `useSheet` fetches `/sheet` per card, with no cache shared across accounts. The
    card shows the first rows as a light mini grid and counts formulas and charts.
  - `SheetView.tsx` (lazy, `sheetViewLazy.ts`): formula bar (name box, formula, value chip, "Công thức" toggle or
    Ctrl+`), sticky letters, row numbers and header row, arrow keys and Enter to move, sheet tabs. It opens on the first
    formula cell; only keyboard moves scroll, so opening never hides column A. `SheetChart.tsx` draws the charts as SVG
    at their anchor cells, measured after layout.
  - Opening a workbook from its card collapses the panel's file list once, to give the grid room.
- **Mock.** `__excel__` (grade book with statistics and two charts) and `__excel__:chitieu` (dates, VND, SUMIF,
  percent, pie).
- **Not done:**
  - conditional formatting rules, merged title rows, PDF export, manual cell editing;
  - array formulas and newer functions (XLOOKUP, IFS, TEXT…);
  - a check in real Excel or LibreOffice: neither is installed on this PC, so the XML was inspected instead.
- **Tests:** `backend/tests/test_spreadsheets.py`, frontend `DocumentArtifactCard.test.tsx` and `DocumentPanel.test.tsx`
  (`tests/sheetFixture.ts`).

### Editing uploaded Excel files (`edit_spreadsheet`)

Built on 2026-10-05, after Excel uploads could only be read. Peto edits the user's own file and keeps everything it
does not touch. The upload never changes; each edit is a new version.
- **No openpyxl.** It drops cached formula results, sparklines and other `x14` extensions, and drawings it does not
  understand. `features/documents/workbook_edit/` patches the package surgically instead.
  - lxml for small parts, so namespace declarations such as `mc:Ignorable` survive.
  - A regex row/cell parser for `sheetData` keeps untouched rows byte-identical.
  - The rest of a sheet is a skeleton (`before` + `<sheetData peto-sheet-data="1"/>` + `after`), parsed only when
    something outside the cells changes.
- **Operations** (`ops.py`, strict `SCHEMA`): set, fill (formulas copied like drag-fill), clear, format, insert/delete
  rows and columns, merge/unmerge, add/rename sheet. At most 40 changes per call; each uses the coordinates the previous
  one left. New formulas may only use `sheets.formula.FUNCTIONS`.
  - Guards refuse what Excel refuses: writing inside a merged range, a pivot table, part of an array formula, a Table's
    totals row, a protected sheet. `merge` refuses to discard data (Excel keeps only the top-left value) and partial
    overlaps; `unmerge` drops every merge touching the range.
  - Inserting or deleting rewrites references with Excel's rules (`refs.py`: quoted and Unicode sheet names, 3D,
    external and structured references, defined names). Merges, CF/DV ranges, charts, drawing anchors, notes, Tables,
    pivot caches and print areas move too. Inserting right above a total row also widens its SUMs, and charts over the
    same block, which Excel itself does not.
  - Writing next to a Table grows it; calculated columns fill; renaming a header updates the Table and structured
    references.
- **A batch is atomic, but every refusal comes back at once** (up to `MAX_PROBLEMS`, 8). Until 2026-10-05 only the
  first error was reported, so a workbook with several errors cost one 1–2 minute round per error. The tool result
  says nothing was written and asks for the whole list again.
- **Recalculation** (`recalc.py`): changes propagate through dependents (whole columns, other sheets, defined names)
  and are evaluated with `sheets/engine`. New formulas that evaluate to an error or form a cycle are refused, as in
  `create_spreadsheet`. Existing formulas Peto cannot compute lose their cached value rather than keep a stale one.
  `fullCalcOnLoad` is set and `calcChain.xml` dropped, so Excel recalculates on open.
- **Chart caches** (`chart_cache.py`, 2026-10-05). Excel redraws charts from cells on open, but phone viewers and the
  reader use the numbers cached in the chart. The owner's edited grade book still read "Giỏi 1, Khá 0" from its chart
  after the count cells became 2 and 2. Series (`numRef`/`strRef`, single-level chartEx `lvl`) whose range touches a
  cell written or recalculated in this edit (`Report.cells`), or a sheet that had rows or columns inserted or deleted,
  are re-read from the cells. Other charts stay byte-identical. Defined names, multi-area and whole-column ranges keep
  their old cache.
- **Storage and API.**
  - Edits run in a worker process (`to_process`, 45 s, behind the render queue).
  - Each success is a `style='workbook'` document version holding the xlsx; an upload becomes a new document. At most
    `MAX_EDITS_PER_TURN` (4) saved edits per turn.
  - **One card per file per turn** (the owner's first real run on 2026-10-05 left three cards for one file). Editing
    the same file again in a turn passes the earlier edit's lines and changed cells to the worker (`carried`).
    - `Session.carry` keeps them, and later inserts, deletes and renames in the new edit move them. A line whose area
      was deleted says so.
    - The new version's change list and tinted cells therefore cover the whole turn.
    - `DocumentSession._turn_edits` puts the new card in place of the earlier one, and the page replaces a card with
      the same id.
    - The model still gets only that call's lines (`new_lines`), and `change_count` gives the card its full total.
  - The content holds the change lines ("Thay đổi:"), "Ô đã sửa: …" and a 40,000-character readout, so follow-ups and
    the attachment tools see the new file.
  - `/sheet` returns `workbook_grid.grid`: 500 rows × 60 columns per sheet, Vietnamese number formats, theme colours,
    charts drawn from the live ranges. `.xlsm` downloads keep the macro MIME type and `vbaProject.bin` byte for byte.
- **UI** ("Nhật ký thay đổi", picked by the owner from live variants on 2026-10-05).
  - The card lists the first changes.
  - The panel puts the change list on top; clicking one selects its area. Below are a formula bar ("Peto vừa sửa",
    "Excel tính khi mở tệp") and a grid in the app's theme with changed cells tinted.
- **Mock:** `__suaexcel__` edits the newest workbook of the conversation.
- **Not done:**
  - new charts, conditional formatting, sorting and filters, images;
  - a check in real Excel (none on this PC).
- **Tests:** `backend/tests/test_workbook_edit.py` and `test_turn_limits.py`, frontend `DocumentArtifactCard.test.tsx`
  (`tests/workbookFixture.ts`).

### Editing uploaded Word files (`edit_document`)

Step 4 of the owner's Word plan, built 2026-10-12. Their use: a teacher's exercise file (Đại số Bool, hồi quy…) where
answers go right under each question, with real equations, truth tables and Karnaugh maps. Before this they pasted Peto's
chat answer into Word, which broke overlines into "xˉ".
- **Tracked changes, author "Peto"** (the owner's pick over plain text or bold answers). Every insertion is `w:ins`, every
  removal `w:del` with `w:delText`, so the user reviews in Word and uses Accept All or Reject. Revision ids continue
  after the largest `w:id` in the file. Replacing or deleting Peto's own earlier insertion removes it outright, as Word
  does for your own tracked text, so revising an answer never stacks two layers of marks.
- **Package** (`features/documents/word_edit/package.py`): only `word/document.xml` is rewritten (lxml, keeps namespace
  declarations for `mc:Ignorable`); every other part is copied byte for byte with its name, order, date and compression.
  Same size limits as the reader; DTDs, encrypted/OLE (.doc) and Strict Open XML files are refused with a hint.
- **Operations** (`ops.py`, strict schema, at most 30 per call, atomic, up to 8 refusals reported at once):
  `insert_after` (Markdown content, parsed by `export.parse_blocks`: paragraphs, lists written as text labels, Markdown
  tables, `$…$`/`$$…$$` as native OMML through `math/omml_out`), `replace` (one paragraph), `delete` (paragraph or table)
  and `fill_cell` (row/column by grid position, honouring `gridSpan`, refusing `vMerge` continuations).
  - Targets are the reader's own numbers: `word_reader.numbered_blocks` is shared by `read_body` and the editor, and every
    target in one call refers to the file before that call. Repeated inserts after one target keep their order;
    deletions run last.
  - Paragraphs or cells holding equations, pictures, fields, footnotes, text boxes or section breaks cannot be replaced
    or deleted (Peto inserts a new paragraph instead); Peto's own insertions inside them do not count.
  - Inserted text takes font, size and language from the target paragraph, or the nearest paragraphs that set them,
    never bold/italic/colour. Tables get single borders, a header row (`tblHeader`), widths from `export.column_widths`
    and the page's text width. An empty Peto paragraph separates two adjacent tables (Word would merge them) and follows
    a table that would otherwise end the body.
  - The reader now numbers empty tables too (`[Bảng N]` / `(bảng trống: R hàng × C cột)`) so Peto can fill a blank
    answer grid; a file with nothing but empty tables still reads as no text. `WORD_FORMAT` is 4.
- **Storage.** Each success is a `style='wordedit'` version (`docx` asset, `pages` 0, no PDF/preview: no Word on the
  server to lay pages out). Content holds the change lines, a "Mã dấu sửa của từng thay đổi" line (each change's first
  and last revision id) and a 40,000-character reread with the new numbers, which Peto reads next turn. The same
  card-per-file-per-turn merging as Excel applies; `MAX_EDITS_PER_TURN` is shared.
- **API.** Export serves only `docx` (pdf 400); manual `versions` edits 400; `/preview` 404.
  `GET /api/documents/{id}/word?version=` (`preview.py`) rebuilds blocks from the stored file: parts marked ins/del,
  equations as LaTeX, Word numbering labels, per-block revision ids, and the change list with its id ranges.
- **UI** ("Nhật ký", picked by the owner 2026-10-12 from three live variants; the others were a white Word-like page with
  a markup/final toggle, and a diff of only the changed spots). The card (`WordEditArtifactCard`) lists the first changes
  ("Đoạn 5 · Chèn 1 bảng"). The panel (`WordView.tsx`, lazy, KaTeX) puts the clickable change list above the content in
  the app theme: inserted blocks tinted with `--sheet-accent`, deletions struck in `--danger`. A change jumps to the
  blocks whose revision ids fall in its range, so it stays right on later versions that still carry earlier marks.
- **Prompt.** Both cores tell Peto to use `edit_document` only when asked to write into the file, to put a whole
  exercise in one call, and to say it cannot draw circuits or figures into the file. `asks_edit` also matches "chèn",
  "làm bài", "giải bài"… for the Grok follow-up nudge.
- **Mock:** `__suaword__` inserts a sample answer (paragraph with an equation, and a table) after Đoạn 1 of the newest
  Word file.
- **Checked in real Word by the owner (2026-10-12):** insertions, including equations (`w:ins` wrapping `m:oMath`), show
  as tracked insertions, the deletion is struck, and Accept All leaves a clean file. That check also found "F_{\min}"
  drawn as "Fmin□": `omml_out` wrote a function name with no argument as `m:func` with an empty `m:e`, which Word shows
  as an empty slot. A bare function name is now a plain upright run (this also fixes `create_document`).
- **Tests:** `backend/tests/test_word_edit.py`, frontend `DocumentArtifactCard.test.tsx` and `DocumentPanel.test.tsx`.

### Imagine (image generation)

**Gallery generation UX (owner request, 2026-10-15):** `GenerationPreview` keeps the chosen ratio and tile positions
from pending to decoded final images. Auto uses a neutral square unless a pending reference's ratio is available;
read that ratio from the displayed source, never eagerly download reference images across historical jobs.
The provisional Auto frame does not claim an output size.
Subtle grain/dots indicate activity only: never show invented percent or fake intermediate AI images. Pause motion
for queued jobs, failed polling, inactive Imagine or a hidden document; honour `data-motion="reduced"`.
Image download/decode failures offer an image-only retry, never another generation POST.
“Tạo thêm” is an explicit new billed batch using the original prompt, count, quality, resolution, ratio and ordered
source snapshots, independent of the current composer draft. It reuses the existing in-flight lock, background job
and uncertain-receipt recovery, never retries an unknown job automatically, and does not create an edit-history child.
“Dùng lại mô tả” restores count too. Welcome templates only fill the draft; keep edit suggestions/reference guidance
removed as previously requested. No provider streaming-preview, video, removal or enhancement capability is implied.

For UI polish, apply the owner's selected `emil-design-eng` and `mobile-native` skills when available
(source: https://github.com/emilkowalski/skills). Keep the owner's Grok screenshots and interaction requests
authoritative. Use the existing motion tokens/press feedback; gate hover by pointer capability, retain
keyboard focus, keep touch inputs at least 16px, and preserve pinch zoom and canvas gestures. Do not add
navigation rails or decorative motion by default. `break-ui` is installed for explicit UI stress reviews.
Emulated mobile tests do not certify Safari keyboard, safe areas, or physical touch feel.

Fully separated from chat: its own router (`features/imagine/api.py`), its own REST call to
`/v1/images/generations` (`ai/imagine.py`), its own `imagine_jobs` / `imagine_images`
tables. Chat **intentionally has no image-generation tool**, so Peto never draws when the
user was just talking.

The current frontend submits `background: true` with a unique `request_id`. The API persists a queued job and
its sources before returning 202, then generates and saves the result independently of the HTTP connection.
`GET /api/imagine/{id}` tracks queued/running/complete/failed/unknown; the frontend resumes polling after reload.
Status reads, workspace history and library reads bypass cache and have a 10-second abortable deadline,
including reading the JSON body. This only cancels the read, never the background AI job. Polling accepts each
job as soon as its response arrives, independently of other stalled/failed reads, then retries transient read
failures without another POST. A completed edit updates history and selects its image only if that root is still
open; closing the viewer must not reopen it on a late result. Sort pending IDs so reordering history does not
restart polling. The library, workspace, status and receipt GET APIs send `Cache-Control: private, no-store`;
image files retain their existing cache policy. Clear the connection notice when no jobs are pending.
`GET /api/imagine/requests/{request_id}` recovers a lost POST response without submitting again. The owner-scoped
`imagine_requests` ledger keeps a fingerprint and job ID even after deletion, so duplicate requests cannot generate
a second billed batch. Conflicting reuse is 409; a deleted original request is 410. An uncertain POST receipt lives
in sessionStorage until checked. No automatic paid retry happens on timeout, restart or lost provider response.

The runner uses the existing `admission` limiter under `imagine:<owner>` and the batch timeout. SQLite serializes
acceptance, allowing one active image job per owner and at most `MAX_CONCURRENT + MAX_QUEUE` accepted image jobs.
Run the backend as a **single process**, as already required by voice: its background tasks are process-local.
Startup marks orphan queued/running rows unknown, and graceful shutdown cancels tracked tasks without replay.
Outputs are only exposed when complete; partial save failure removes them while retaining source snapshots and
an error state. Old clients may still omit `background` and use the original synchronous response/rollback behavior.

Edits accept up to five ordered `source_images: [{data: base64} | {image_id: owned_id}]`; the old mutually exclusive
`source_image` / `source_image_id` fields remain accepted, but cannot be mixed with the new list. PNG/JPEG/WebP
sources are decoded with Pillow and bounded at 8 MiB each (configurable), 16 MiB combined, and 40 MP each.
The Imagine POST route caps the raw JSON body at 24 MiB before parsing, including chunked requests. Sources are
copied per job with explicit `position`, `parent_image_id` and `parent_job_id`, so deleting a prior output never
breaks later edits. Provider JSON uses `image` for one source and `images` for multiple; no multipart API is used.
The API returns both ordered `source_images` and legacy `source_image` (first source). All 15 fixed xAI ratios plus
auto are accepted. Paid provider calls have not been used to verify the current account's multi-image support.

The composer copies Grok's Imagine at the owner's request. Chips above the box pick Nhanh/Chi tiết, the
count and the ratio (`StudioMenu.tsx`, a popover reusing the `.effort-options` classes). The box holds the
source-image button, 1K/2K where Grok has Image/Video, and a round send button whose accessible name stays
"Tạo ảnh"/"Sửa ảnh". Desktop always shows all of it. Below the 720px breakpoint `.studio-dock` floats over
the gallery and collapses to a bar (a library button showing the newest image, a one-line prompt, an options
button) until the prompt is focused or the options button is pressed. A tap outside or a submit collapses it
and blurs the prompt so the phone keyboard hides.

Reference edits use a compact strip of thumbnail attachments. Do not restore the reference-count guidance,
"Gợi ý chỉnh sửa" section, suggestion buttons or their explanatory text: the owner explicitly removed them.
Desktop thumbnails are 56px with a remove button; numbered badges and an accessible first-source action
appear only for multiple sources. File names stay in tooltips instead of large text cards. Reordering
or removing a reference that renumbers others shows a dismissible reminder to check numbered references in
the prompt. Ratio options include purpose hints. The preview's "Thêm làm tham chiếu" appends the viewed
image to the current draft; "Dùng ảnh này" replaces the draft's sources with the viewed image and fills its
prompt from the saved job. It keeps the viewer and large canvas open, replaces the chip/single edit field
with the shared studio composer, and focuses the prompt. Attachments appear above the text; existing
quality/count/ratio controls sit in its footer, and no request is made until Send. The right panel's ratio
and palette prompt actions operate on this same draft. The suspended library must not render another
composer at the same time, to avoid duplicate input IDs and competing refs. `MeasuredImage.tsx` reads actual
natural dimensions after loading for library tiles, previews and comparison panes; it hides previous-image
metadata when the URL changes, rather than guessing dimensions from requested resolution or aspect ratio.

`ImagineLibrary.tsx` opens as a non-modal `<dialog>` within Imagine on desktop, beside the existing app
sidebar; on mobile it remains a full-screen modal. The real sidebar stays usable and can collapse/expand
in both the desktop library and viewer. The gallery behind either view is hidden from keyboard navigation.
It shows output tiles, searches
loaded prompts ignoring Vietnamese diacritics via a top search toggle, and offers medium/small square tiles
(localStorage), All/Liked tabs and created/edited filters. Desktop tiles stay bounded to 240–360px (medium) or
180–240px (small), even with only one image; mobile retains 2/3 columns. Selection/download/delete actions
live in the top bar. Neither library nor viewer adds its own left sidebar/rail. The extra reference-slot guidance row is removed; limits remain enforced by the reference action. The same composer moves into the library, then hides during selection; a ResizeObserver
keeps the last grid row clear of its floating dock. The API returns 40 jobs per page; `before=<last-job-id>` loads earlier jobs with a stable created_at/id order.
The composer appends uploads/paste/drop sources and selected library images (in selection order), with remove and
"Đặt làm ảnh đầu" controls. "Dùng lại mô tả" restores every source. `ImageComparison.tsx` compares a selectable
source and output side by side without stretching. `EditHistory.tsx` follows saved parent links lazily when opened,
including parents outside the current page, and keeps snapshot fallbacks if an ancestor was deleted. A normal click opens the viewer; "Chọn" or a 500 ms long press enters multi-selection. The click generated by releasing a long press is suppressed only for that tile, with an expiry; moving to scroll or cancelling the pointer cancels the timer. Right click opens a per-image menu without entering selection. Selection can share (Web Share with files, hidden when
unsupported), download or delete. Deletion is per image: `DELETE /api/imagine/images/{id}` removes one output
and deletes the job, source image included, once no output is left. `PUT /api/imagine/images/{id}/like` stores
`imagine_images.liked`. Source images of edits cannot be deleted or liked on their own. The heart button lives
in `ImageWorkspace.tsx`, a desktop viewer inside Imagine beside the real app sidebar (modal on mobile):
a fitted image and wide edit prompt in the central area, existing tools across the top of the right
details/action panel (above the image on mobile), zoom/panel toggles, navigation, and side-by-side
comparison in the central stage. `imageTools.ts` implements local normalized crop and vector brush/eraser
strokes with Canvas, extracts a four-color palette, and encodes a new PNG source without overwriting the
stored original. Undo keeps the original plus at most five recent PNG versions in memory; closing/reloading
loses these local drafts, which are labelled as unsaved. Download/reference/edit uses the working PNG;
unchanged images keep their saved ID. A modified reference obeys the existing 5-source, 8 MiB each/16 MiB
aggregate limits. Palette presets only append an editable prompt; no provider request occurs before Send.

The owner's latest desktop screenshots supersede the earlier interpretation of the left tool strip:
info/palette/crop/brush belong in a horizontal row at the top of the right panel. Keep the actual Peto
sidebar visible and usable; never create another navigation sidebar or hide it with a desktop modal.
Back sits at the top-left of the main area, zoom at the top-right. The composer is centered below the
canvas, up to 760px of usable width in an 800px dock regardless of portrait width. Photos retain their aspect ratio and
fit the available height, with extra top clearance when the central area is narrow. Collapsing the right
panel leaves a 60px rail (72px with a coarse pointer) with the existing aspect/reference/share/like/download actions, and an expand
button; it does not add unavailable Grok actions. The full panel groups actions at its bottom. The reaction
row has like/download only: no X social action or duplicate close button. Back closes the viewer. Mobile gives the
image more height and scrolls the detail panel below; the body grid must use `minmax(0,1fr)` to prevent
its controls expanding beyond narrow screens. Opening the viewer suspends the library dialog without
resetting its search/filter state; Back/Escape restores it. Saved versions now appear in an 80px
rail beside the real sidebar, with 64px thumbnails, independent scrolling and overflow arrows.
The rail contains the selected root image and its persisted edits, never sibling outputs from `job.images`.
On mobile it becomes a horizontal strip. Do not animate version selection or wheel zoom.
`imagine_jobs.root_image_id` groups edit jobs under one original output; `edit_parent_image_id` retains
branch ancestry and `edit_kind` distinguishes AI/crop/brush. Existing rows keep NULL roots and their previous
independent library behavior. `/api/imagine` lists roots plus a separate `active_edits` recovery field; children
stay out of the library/gallery/sidebar. Workspace GET resolves an owner-scoped root and its child jobs.
Confirming a crop persists a new file/job with an idempotency receipt, without an AI call. Brush Apply now
requests an AI edit on both desktop and mobile; legacy brush PNG revisions remain readable. Reference uploads
viewed as sources keep temporary crop drafts; applying their brush sketch requests an AI result. Unapplied strokes/prompts remain drafts.
Deleting a root deletes its child jobs/files and preserves request tombstones; active AI/local saves block root
deletion. Source copies used by independent jobs remain independent. Every lookup/mutation filters by owner.
Viewer URLs use `/imagine/<root-image-id>/<version-image-id>` with browser Back/Forward and reload recovery;
the previous `/#imagine/<root-image-id>/<version-image-id>` links remain supported.
These are authenticated workspace links, not public sharing links. Keep dialog opening dependent on initial
library loading as well as the selected image; deep links can resolve before the dialog exists in the DOM.
Mouse-wheel input within the single-image canvas changes its fitted zoom from 50% to 800%, using a
non-passive native listener. Normalize pixel/line/page wheel deltas and keep the image point under the
pointer in place along scrollable axes. Ignore browser zoom modifiers, horizontal scrolling, active brush
strokes and the comparison view. Clicking the percentage restores 100% (the existing fitted scale) and
clears the canvas scroll offsets; plus/minus retain their 25-point steps. Do not animate wheel zoom.
Library and viewer inherit the project's body font, including native buttons, inputs and selects.
Desktop controls are 38px high; viewer panel text is 14px, metadata 12px, and edit text 16px in a
60px-high composer. The panel is bounded to 280–360px. Keep touch targets at least 44px and touch
input text at least 16px. Escape dismisses one library layer at a time; cancellation of the nested delete
confirmation must not also cancel the selection. Resizing across the desktop/mobile boundary switches
dialog modes without clearing the open library's filters.
The mobile library uses a dedicated fullscreen layout: close/select at the top, edge-to-edge tiles,
and a bottom search/filter dock. Compact defaults to three square columns; Wide uses two columns and
the loaded image's natural aspect ratio. Persist mobile density separately from desktop density.
Use explicit max-content grid rows so opening the selection dock never compresses the thumbnails.
Tap views an image; a 500ms hold enters selection and selects it. Suppress the release click and native
touch context menu. Pointer movement/cancel and a second touch anywhere cancel the pending hold; keep
native vertical scrolling and pinch available. Selection shows a top-right check only on picked images,
with the existing share/download/reference/delete actions at the bottom. Hide the dock with zero picks.
Do not mount the generation composer in the mobile library or add an unavailable Tag action.
Mobile controls have 44px targets, search text is 16px, and the header/footer honor all safe-area insets.
Enable viewport-fit=cover only while this mobile library is visible, restoring the previous viewport meta
when it closes or yields to the viewer, so other screens keep their existing viewport behavior.
The mobile image workspace follows the owner's Grok recording (2026-10-08): the image is centered,
small version thumbnails scroll horizontally above the bottom actions, and the direct edit input stays
compact. Render the original thumbnail even before it has edits. Entering tools replaces that dock with
a tool row, horizontal palette presets, or a floating vertical brush-size slider. Collapse the size/color
controls when a stroke starts; keep undo, redo and eraser available. Mobile send always requests one
AI edit, including stroke-only submissions: send the annotated PNG with the selected parent image ID.
Without typed text, use a Vietnamese instruction to turn the sketch into matching image details and
preserve the subject/composition. Crop confirmation still saves PNG versions locally on the server;
do not route brush Apply or mobile send to that endpoint.
Use a separate bottom sheet for metadata, fitted zoom, aspect ratio, comparison and reference actions;
it supports backdrop/Escape dismissal, focus trapping/restoration, and dragging its handle down to close.
Use a non-passive touchstart listener only on custom drag surfaces (drawing canvas, crop box, sheet
handle) to suppress compatibility taps. Do not cancel native scrolling on the version/palette tracks.
The crop overlay takes focus and makes the underlying mobile workspace inert until it closes.
Keep the mobile viewer layout intact. Pending edits cover PNG preparation, the in-flight HTTP request and
the actual pending job for the blurred image, dotted overlay, pending thumbnail and "Đang tạo…" label;
do not wait for the POST receipt to show progress or use timers that fake success. A rejected submission
restores the editable sketch; uncertain requests still require receipt checking before another send.
New results still belong to their root only.
Desktop brush follows the owner's latest Grok references (2026-10-08). Brush size, eraser/color and Style
live in the right panel; sketch undo/redo/delete sit over the canvas next to the existing zoom controls.
Entering brush hides the central composer before drawing. Once there are strokes, redo history, typed text,
or an explicit style, the right panel replaces its usual bottom actions with a prompt, Apply and Reset.
Typing, the first stroke, and pending updates must not resize/reposition the fitted image; reserve a fixed
40px dock for status below it. Reset clears sketch/redo/prompt/style without a request or saved version.
Style defaults to preserving the original. Manga, Illustration, Painting and Realistic (Vietnamese UI labels)
append an aesthetic instruction to the existing edit prompt only on Apply; never send on selection or add
an unsupported provider `style` field. Official xAI image editing docs describe prompt-based style transfer:
https://docs.x.ai/developers/model-capabilities/images/editing . The four consumer dropdown choices come
from the owner's screenshots; the docs do not specify the consumer drawing tool's internal implementation.
Desktop pending blur applies to both the source image and annotation canvas. Clip the white moving dot
overlay to the picture bounds; only animate transform/opacity, never image layout/filter. The dots continue
from PNG preparation through HTTP acknowledgement and job polling, with disabled editing controls and a
pending version thumbnail. Reduced motion keeps static dots/status instead. Always include the root thumbnail
on desktop too, so the first edit doesn't insert a new rail and shrink the image. Failed sends preserve the
sketch, prompt and style. Keep the uncertain-request receipt checks and parent/root grouping unchanged.
Desktop-specific styles live in `features/imagine/imageWorkspaceDesktop.css`; use project fonts and existing
38px controls. The style menu reuses StudioMenu, with focus restoration without scrolling and Escape closing
just the menu. Do not describe annotated reference uploads as a dedicated mask/inpaint implementation.
Mobile styles live in `features/imagine/imageWorkspaceMobile.css`. Sheet transitions use transform/opacity
(260ms entrance, 160ms exit), tool entrance is 180–220ms, and explicit tool layout changes use a 220ms FLIP
transform captured before the action and measured at the final fitted size before paint. Never restart
picture animations for polling, metadata sheets, color popovers, keystrokes or viewport measurements.
The brush color popover overlays the dock; closing it during a stroke must not resize/move the image.
Measure only nonzero stage dimensions and skip identical measurements; keep an unloaded image hidden
until its real fit is known. Move viewport-fit setup to the viewer lifecycle so selecting a version does
not restore/reapply the viewport meta. Focus restoration uses preventScroll, and thumbnail auto-scroll
only scrolls its own track, never dialog/canvas ancestors. Version navigation and wheel zoom remain instant.
Keyboard actions and reduced motion skip
these transitions. Honor viewport-fit/safe areas, 44px touch targets and 16px inputs; use visualViewport
height/offset for keyboards that shrink only the visible viewport, without resizing during browser pinch.
Chromium emulation covers gestures/layout/animation, but physical-phone keyboard, safe-area and touch
feel still need hardware verification.
The viewer's direct edit field sends one edit result; its "Dùng ảnh này" composer uses the existing studio
controls and request path. Both use
the existing background/idempotency/uncertain-request path, without issuing a request just to attach an image.
Edits submitted from the viewer remain there while pending and select the saved result on completion.
No segmentation, AI mask/inpainting guarantee, transparent-background removal, video or tag manager is
implemented here; do not add placeholder buttons that pretend those features are available.

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
  USD per million), reread on mtime/size change. Missing cached tokens price as uncached and are flagged. The owner's
  xAI login is a subscription, so Grok is deliberately left unpriced ("chưa có giá"). An optional `long_context`
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

### User profile (Settings → Hồ sơ)

`features/accounts/profile.py` stores a self-written profile per owner in `user_profiles` — kept apart
from `users`, which is overwritten from Discord/Google/GitHub on every login: full name, what
Peto should call them, an occupation code from a fixed server-side list, and free-form
instructions (1500 chars). `features.chat.prompt_context._build_system_prompt` re-reads it on **every** turn and
appends `persona.build_profile_context` after the memory block, so an edit applies to the
very next message. Instructions are fenced with `USER_INSTRUCTIONS_START/END`, copies of
those markers are stripped from user text, and the block states it cannot override the
rules above it. Validation errors are Vietnamese 400s, not Pydantic's English 422s.

`ProfileSettings.tsx` ties labels to inputs with `htmlFor` instead of wrapping them:
every `<label>` is `user-select: none` for tap handling, and iOS Safari can refuse to
edit inputs nested inside such an element.

Profile occupations and connector status filters use the existing accessible voice dropdown,
now shared at `frontend/src/shared/ui/Dropdown.tsx` (re-exported by `voiceUi.tsx`). Settings
use compact transparent triggers and scrollable menus, with keyboard navigation and Escape
closing the menu before the dialog. `ProfileAvatar.tsx` provides Upload / Restore default actions.
Authenticated `PUT/GET/DELETE /api/profile/avatar` accepts one PNG/JPEG/WebP, up to 10 MiB and
16 million pixels; Pillow validates, applies EXIF orientation, crops to 512px square PNG and
strips metadata. `storage/avatars.py` stores one image BLOB per owner in `user_avatars`, included
in existing SQLite backups. Original provider photos stay in `users.avatar_url`; later logins
do not overwrite the custom image. Both `/api/auth/me` and `/api/profile` return the effective
avatar URL and `custom_avatar`. Restoring default deletes only the custom image. Avatar reads
use the authenticated owner and private/no-store responses; a version in the URL refreshes
all visible avatars immediately. Tests cover validation, isolation, login persistence and reset.

`/api/auth/me` also returns the profile's `nickname`, so the empty-state greeting can use
it on first paint without a second request or a visible name swap. The greeting line
comes from `frontend/src/features/chat/timeGreeting.ts`: a few lines per time-of-day slot on the
**browser** clock (unlike chat, which trusts the server clock), re-picked when the tab
becomes visible again in a new slot or day.

### Settings and the account menu

On 2026-09-29 the owner asked for a compact account row and menu like ChatGPT's and a settings panel like Claude's, then
picked "Từng mục" from three live variants (the repo's `prototype` skill). The other two were one scrolling page with a
scrollspy list, and grouped cards with coloured icons.

- **Account row** (`.account`, bottom of the sidebar): a 24px avatar, the display name and one line under it
  (`accountSubtitle`). That line is `@username` for Discord, "Google" for Google accounts (their username is the display
  name) and `@login · GitHub` for GitHub. There is no gear: the row opens the menu, not Settings.
  - The first version left 26px above the name and 18px below it, and the owner found the bottom "taller". It is now
    tight like ChatGPT's: 6px between the list and the row (`.sidebar-section + .sidebar-foot`) and 6px under it.
  - The conversation list and the image library fade over their last 20px (with as much bottom padding), so a
    half-cut row never sits on the account row.
- **Account menu** (`AccountMenu.tsx`): the account (opens Tài khoản), Hồ sơ, Cài đặt, Hướng dẫn (`/docs/` in a new
  tab) and Đăng xuất (disabled while a reply streams).
  - It is fixed-positioned above the row and rendered outside the sidebar, because the sidebar clips overflow. With the
    sidebar collapsed to 64px it widens to 248px, to the right.
  - Focus goes to the first item. Arrows, Home and End move; Esc closes and refocuses the row; a pointerdown outside,
    Tab or a resize closes.
  - It fades out for 110 ms before unmounting, with a timer fallback: jsdom and hidden windows fire no animationend.
- **Dialog** (`SettingsDialog.tsx`, still a `<dialog>` opened with `showModal` in a layout effect). A 216px list of
  sections sits on the left and one section shows on the right. The sections are Giao diện, Hồ sơ, Trí nhớ, Tài khoản,
  Hội thoại đã lưu trữ, Peto Agent and Kết nối. App keeps a `SettingsView` of `{open, section, page}`.
  - **No Companion group since 2026-10-13.** Nhân vật, Giọng nói and Tra web moved to the Companion settings page (see
    "Companion settings page"). Trí nhớ stays here and also appears there.
  - **Opening.** "Cài đặt" in the menu opens Giao diện, "Hồ sơ" opens Hồ sơ and the account item opens Tài khoản.
  - **Focus.** On open, focus goes to the current section's item (on a phone page, to the back button). After opening
    from the menu, closing refocuses the account row (`settingsReturn`), since the menu item is gone.
  - **Mounting.** Visited sections stay mounted and are only hidden, so an unsaved Hồ sơ edit survives switching
    sections. `render(section, active)` passes `active` (dialog open, section shown) as each component's `open` prop.
    Sections therefore load their data when shown.
  - **Close button.** It has its own `.settings-close`. The shared `.dialog-close` × still belongs to the other
    dialogs (Nhân vật, Bối cảnh, model check, Beat Sync, documents, the Imagine lightbox). Commit 33d52a4 deleted it
    together with the old settings CSS, and those buttons fell back to the browser's grey box until it was restored.
  - **Phones.** Below 720px the dialog fills the screen. The list of sections comes first; picking one slides its page
    in from the right, iOS style, with a back button. This uses `data-motion` push/pop and is skipped under reduced
    motion. `data-page` on the dialog says which screen shows.
- **Rows** (`settingsUi.tsx`):
  - `SettingsRow` puts the label and description on the left and the control on the right, with hairlines between rows.
    `SettingsGroup` groups rows under an optional small title.
  - `Segmented` is made of real radio inputs, so arrow keys and `.checked` work; the theme choice uses icons.
    `SettingsSwitch` and `SettingsIcon` complete the set.
  - Section components render straight into these rows, without their own heading: the dialog shows the section title.
    On phones, inputs and dropdowns drop under their label, while switches stay on the right.
- **Tests:**
  - `App.test.tsx` has a "Menu tài khoản và hộp Cài đặt" group.
  - The settings helpers in `Companion.test.tsx` and `Hearing.test.tsx` open settings the way a user does: Trí nhớ
    through the account row, the menu and the section; voice, hearing and web search through the gear in the Companion
    chat column, then Mô-đun, then the page.

### Roleplay mode (removed 2026-10-18)

From 2026-09 a conversation could be started in roleplay mode (`persona='roleplay'`, the Discord bot's persona,
18+ self-confirmation in `roleplay_consents`, a longer history, Peto model only). The owner removed it on 2026-10-18
because Companion covers that need. Now:
- New chats are always the assistant; a request with another `persona` gets 400 `ROLEPLAY_REMOVED`.
- Old roleplay conversations stay listed ("· Nhập vai") and readable. `App.tsx` treats them like archived chats
  (`readOnly`): the composer is replaced by "Hội thoại nhập vai cũ chỉ còn để xem" and "Bắt đầu hội thoại mới", and
  message actions are disabled. The server refuses sends, branches and model changes with 409 `LEGACY_ROLEPLAY`
  (`features/chat/conversations.py`), so their history never reaches Grok, GPT or Claude. Rename, archive, delete work.
- Memory never reads them (`storage/memory.MEMORY_SOURCE` keeps `persona = 'assistant'`).
- Tests: `backend/tests/test_roleplay.py`, the "Hội thoại nhập vai cũ" group in `frontend/tests/App.test.tsx`.

### Discord memory gateway

`features/accounts/discord_memory.py` calls the bot's gateway over loopback. It is **one-way, read-only, and
fails soft** — any error, bad JSON, wrong token or unreachable host returns `EMPTY` and chat
continues normally. It re-queries every turn and never caches, because the gateway also
reports the user's anonymity status; a cached snapshot could surface memory a user just
disabled. `PETO_MEMORY_CACHE_TTL` is kept only for config compatibility and does nothing.

Disabled unless both `PETO_MEMORY_GATEWAY_URL` and `PETO_MEMORY_GATEWAY_TOKEN` are set;
half-configured setups log a warning at startup rather than failing silently.

The bot writes its summary in its roleplay voice. On 2026-10-11 the owner's Discord account got assistant replies
(Grok and Luna) that called itself "Peto" and the owner "ad", with an empty profile; the same question from their
Google account (no gateway) did not. A first rule forbade taking any form of address from the summary; the owner found
it too rigid the same day (they wrote "peto không nhớ ad hả" and Peto still answered with "bạn"). They want Peto to
adapt the way Claude's memory does, and to follow changes asked for in chat or in Settings. Now:
- The assistant core (`prompts/core.py`) mirrors the user: default "mình"/"bạn",
  but when the user calls themselves or Peto something else ("ad", "anh"…; "Peto", "em"…), Peto answers with that pair.
  The latest request, in chat or in the profile, wins. Only forms of address change, never personality or character.
- `prompts/context.VOICE_RULE` (only when there is a summary) lets Peto use the forms of address the summary shows
  when the current conversation and the profile say nothing else, and forbids the character's voice, personality and
  actions.
- Lasting changes come from the web's own memory, now shared by Chat and Companion (see "Memory (Brain)"): its
  extraction records how the user wants to be addressed, so a change said in chat carries over to later conversations,
  for every account type. Settings → Hồ sơ still works and the latest request wins.

### Companion tab and voice relay

**Product direction (owner reaffirmed 2026-10-01):** Companion strongly follows Project AIRI. Use
[AIRI overview](https://airi.moeru.ai/docs/en/docs/overview/) and [upstream repository](https://github.com/moeru-ai/airi)
as the primary references when proposing or implementing Companion work. Ground feature comparisons in the relevant
upstream documentation/code and distinguish implemented features from roadmap/WIP items. Prioritize AIRI-style
Ears/Mouth/Body/Brain interaction and the web/mobile stage experience. History navigation is a supporting improvement;
voice interaction and character presence should drive the Companion roadmap. Adapt to Peto's current stack and retain
the owner's existing choices for the stage, short English replies, microphone defaults and optional web search.
Since 2026-10-13 the web comes first (AIRI's `apps/stage-web` and the shared `packages/stage-pages`/`stage-ui` code, not its
desktop-only features). The next steps and the AIRI comparison live in `PETO_COMPANION_PLAN.md`.

`Companion.tsx` is mounted alongside Chat like `Imagine.tsx` (an `active` prop, kept alive once
visited) and owns one continuous thread from `GET /api/companion`; "Bắt đầu lại" deletes it. It
sends `mode: "companion"`, speaks stable sentences as they arrive unless muted, and stops speaking when the
tab is left.

**Companion persona** (`prompts/companion.py`). Since 2026-09-27 (commit 64097d5) Companion has its own base prompt,
`COMPANION_SYSTEM_PROMPT`, instead of a short addition to the assistant core; `COMPANION_PROMPT` is only an alias kept for
imports. On 2026-09-29 (commit 40203b7) the owner rewrote it: Peto is an adult virtual girl and AI companion, warm and a
little mischievous. Light affection (virtual hugs, kisses, flirting) is allowed without AI disclaimers; pressure,
exclusivity, jealousy, guilt and fostering dependency are forbidden. Real help comes first for serious questions. Replies
are always in English and written for the ear: no Markdown, lists, emoji or `*action*` stage directions. It never names
the model behind it, and never claims capabilities Peto Web does not give it. The prompt also defines the EMOTION and
PRIVATE NOTES markers (sections below). This persona is the owner's own Companion character, separate from the Discord
bot's roleplay character (whose web roleplay mode was removed on 2026-10-18). `tests/test_persona.py` checks only that this
prompt does not name Grok/xAI.

On desktop the layout is a stage on the left and a ~380px chat column on the right. The stage holds
the character and the model's credit line. The owner added an animated three-dot thinking bubble on
2026-10-02; other text and controls remain in the chat column. The chat column carries the speaking status, the mute toggle, "Bắt đầu lại", a notice when
voice is on but the chosen source cannot speak (`voice.problem`), the mic button and its panel (see "Hearing" below), and
the Chat tab's composer styles. Enabling
voice, choosing a source and a voice, and "Nghe thử" live on the Giọng nói page of the Companion settings page, in
`VoiceSettings.tsx` (see "Voice sources"
below).

The default character is the Live2D sample Hiyori; users can import their own Live2D or VRM models (see "Companion
characters, scenes and Beat Sync"). `Live2DStage.tsx` is lazy-loaded and mounted only while Companion is active,
and renders Hiyori from `public/characters`, or an imported model from IndexedDB, with PixiJS 6 and
`pixi-live2d-display/cubism4`. The model path, mouth parameter and head height live in
`characterConfig.ts`; licensing notes are in `frontend/CHARACTER.md`. Because the stage has no
controls, the view changes by gesture: wheel or pinch zooms around the pointer, dragging pans (with the
middle mouse button at the owner's request, or one finger on a touchscreen), double-click resets, and the view is
saved in `localStorage`. The pure math (zoom, pan limits, look
direction, wheel steps) lives in `characterView.ts` with its own tests.

When motion is allowed the model plays its `Idle` motions, breathes, blinks and turns toward the
pointer anywhere on the page; otherwise it holds its pose. "Nhân vật cử động" (since 2026-10-14 the first row of the
Chuyển động block on Cài đặt Companion → Nhân vật) picks `system` ("Theo cài đặt chung", the default) or `always`. Since 2026-10-13 `system` follows the web's
Cài đặt → Giao diện → Chuyển động (default "Mượt", so characters move) instead of the OS. Before that it followed
`prefers-reduced-motion`, and Windows with Animation effects off reports reduced motion, which is why the owner asked
for the "Luôn cử động" override. The
mouth follows the audio that is actually playing (`voiceActivity.ts` reads a 20 ms loudness
envelope against `currentTime`). PCM16 WAV takes the direct path; other browser-supported formats
use `OfflineAudioContext.decodeAudioData` without rerouting or delaying playback. Decoding is serialized,
bounded to 8 MB encoded / 120 s decoded / 8 channels, and stale results are ignored. An unavailable decoder
or unsupported codec leaves speech playback intact and lip sync at zero. `VoiceMouthBlend` gives Live2D
and VRM the same time-based attack/release at 24/30/60 FPS; pause, waiting and stop immediately close the
speech-driven mouth. Authored emotion mouth baselines remain independent.

Companion presence (2026-10-02) adapts AIRI's `packages/stage-ui-live2d/src/components/scenes/live2d/presence-bubble.vue`
and `packages/stage-shared/src/presence-bubble/{placement,follow}.ts`: the renderer updates a shared DOM bubble each frame,
anchored to the head, preferring above and switching sides with hysteresis when space runs out. Live2D uses a
Head/Face hit areas where available, otherwise adapts AIRI's `head-anchor.ts` to identify drawables moved by head
angles once before showing the model. Probing restores parameters; subsequent frames read only selected bounds.
Models without a head rig retain a face-height fallback; VRM projects its head bone. A damped spring follows
the animated head with slight lag/overshoot, substepped at 120 Hz, with stabilized placement decisions.
It follows pan/zoom, never receives input, hides with unavailable/offscreen characters and on stop/end/tab exit,
and uses static dots when the web reduces motion unless the owner selects "Luôn cử động". Generation controls it independently of speech playback.
Character settings include per-model `composerGaze` (default true, including old saved preferences). Only actual
typing in a focused desktop composer attracts eyes/head for 3 s after the latest keystroke; blur, send and inactivity release attention.
Both renderers restore the previous pointer/idle behavior with a 0.45 s release time constant, retaining gaze
ownership until settled so idle/pointer cannot snap the head back. The switch is independent of cursor tracking
and respects the existing system/always motion preference. Recognized speech and old drafts never trigger it.
Typing the next draft during generation/playback still attracts gaze without changing the body phase or lip sync.

Companion phase 2 (2026-10-02) coordinates Body with Ears and Mouth:
- `useCompanionActivity` prioritizes actual playback, generation/waiting, then hearing/typing attention.
  A manual keystroke holds listening attention for 3 s; an unsent or recognized draft alone never holds it.
  Hearing `speaking` and `transcribing` both hold attention, but opening a silent microphone does not.
- `LocalVoicePlayer` publishes `playing` only after media `playing` or a fulfilled `play()` promise.
  `buffering` covers gaps between chunks and media waiting. The body holds its speaking pose for 350 ms,
  then thinks until playback resumes; the mouth follows media independently and stays closed during gaps.
- Completion, failures and stop dispose media callbacks, envelope tracking and object URLs, and abort any
  prefetched synthesis request. Late play/decode callbacks cannot change a newer speech session.
- Switching character stops the old speech and clears its expression. Leaving the tab keeps the existing
  reply request behavior but stops playback and unmounts the renderer. Mobile stage layout, opt-in microphone,
  auto-send, motion preferences and frame-rate limits are preserved.
- Regression coverage: activity, audio envelopes, speech lifecycle, both renderers and Companion unit tests;
  browser tests record/decode a local Opus sample with real media playback and exercise UI lifecycle at
  desktop/mobile sizes. External providers and speech recognition are mocked, with no paid calls.
  The hearing browser test uses a synthetic looping PCM16 fixture instead of Chromium's intermittent
  fake microphone beep, so its AudioWorklet meter check is deterministic on Windows.

VRM characters (`VRMStage.tsx`) got the missing items of AIRI's Body list on 2026-09-28, at the owner's pick:
- **Idle eyes.** After 3 s without pointer movement the eyes glance around (`IdleEyes`, as in Live2D).
  - The glance is an angle around the head (`IDLE_YAW`, `IDLE_PITCH`). VRM bone look-at turns the eyes only about 10°
    for a 90° gaze, so small offsets would not show.
  - The head follows a little only when motion is allowed. The eyes still glance under reduced motion, as the Live2D
    test (`idle eyes override motion eye values even with … reduced motion on`) has pinned since 2026-09-23.
- **Blinks.** `Blinker` blinks at random gaps of 1.5–6 s, sometimes twice in a row, and only when motion is allowed.
  Before, VRM blinked every 4.3 s exactly.
- **Checking it.** On 2026-09-28 the owner's VRoid model was checked in headless Edge. This machine's Windows has
  animation effects off, so headless Edge reports reduced motion too. Emulate `prefers-reduced-motion: no-preference`
  (`Emulation.setEmulatedMedia`) to see blinks. Since 2026-10-13 this only matters when Chuyển động is "Theo máy": by
  default the web ignores the OS setting.

Phones get AIRI's mobile look instead, at the owner's request. Below `COMPACT_QUERY` (the same 720px
breakpoint as the CSS) the character fills the screen in a fixed frame (`compactHeight` and
`compactTop` in `characterConfig.ts`). The header, messages and a pill composer float over it in
translucent `--stage-*` colours defined on `.companion`. Zoom, drag and double-click are ignored
there; since 2026-10-15 the size and position are set on Cài đặt Companion → Nhân vật instead (see "Companion character
page"). A finger held on the screen acts as the pointer, and the character looks at it until
the finger lifts. `index.html` sets `interactive-widget=resizes-content`, so on Chrome for Android the
keyboard shrinks the layout instead of panning the page away. That shrink keeps the message list's scroll position,
which used to hide the newest reply behind the keyboard (the owner saw the middle of the thread on 2026-09-27). A
ResizeObserver in `Companion.tsx` now pins the list to its bottom on every resize, unless the user has scrolled up.
Check it in a pane that is really drawing: a hidden browser skips ResizeObserver callbacks and scroll events. The compact frame keeps the tallest stage
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
3. `backend/features/voice/api.py` serves signed-in users. `GET /api/voice/health` reports `home.online` (a
   heartbeat in the last 15 s) and lists the home voices in `voices` only then. `POST /api/voice/speak`
   with `playful-1` or `gentle-2` and up to 300 characters queues a job and waits up to 120 s for the audio: 429 when four jobs are
   already queued or this owner has one, 503 when the worker is offline or reports a failure, 504 on
   timeout. Results must be a RIFF/WAVE body under 8 MB. A listener disconnect removes the job, late
   audio is rejected instead of reaching another listener, and nothing is written to disk.
   `tests/test_voice.py` covers this with fake WAVs.

The queue and heartbeat live in process memory, so the backend must run as a **single** uvicorn
process with a single relay. A restart drops waiting jobs, and a job claimed by a relay that dies
waits out the 120 s timeout. Registration is open, so any signed-in account can
use the owner's GPU while the relay runs; stopping the relay stops sharing. Setup and operating
limits are in `voice-worker/README.md`.

**Voice sources** (option A, picked by the owner from mockups on 2026-09-24, modelled on AIRI's "official provider plus
your own key"). The Giọng nói page of the Companion settings page shows the sources as cards in two groups, and the card picked is the source
Companion speaks with:

- **Giọng Peto** (`official`): the voices in `speech_cloud.catalog()` (StepFun, plus OpenAI or Qwen Cloud when
  enabled), called with the owner's keys. Each Discord, Google or GitHub account gets `PETO_TTS_FREE_CHARS_MONTHLY`
  characters (5000) a month, counted in `voice_usage` by `PETO_DEFAULT_TIMEZONE` month (`voice.MEMBERS`; guests got 403
  until guest login was removed). `db.take_voice_chars` checks and adds in one statement before
  the call, a failed line gives its characters back, and `X-Peto-Voice-Used` returns the new total. A used-up
  allowance is a 429 with `X-Peto-Quota: exhausted`, which, like 502/503/504, lets `/speak` switch to the request's
  `fallback` voice. The shared USD ceiling (`PETO_TTS_MONTHLY_USD`, `speech_budget`) still applies on top.
- **Máy nhà của Peto** (`home`): the relay above.
- **Khóa của bạn**: since 2026-10-13 the keys are entered on Cài đặt Companion → Nhà cung cấp (see "Companion
  providers"); the Giọng nói page only picks the source, model and voice. Eight providers in `voiceProviders.ts` (OpenAI,
  ElevenLabs, Azure Speech, Google Gemini, MiniMax,
  Alibaba Cloud, StepFun, any OpenAI-compatible server). Keys stay in that browser's `localStorage` (`peto-voice-keys`)
  and bill the user's own account. The browser calls the provider directly, except StepFun (it blocks browser calls,
  checked 2026-09-24) and Alibaba Cloud (Qwen answers with an audio URL the browser cannot fetch, and CosyVoice is a
  WebSocket that needs the key in a header). Those two go through `POST /api/voice/relay` with the key in
  `X-Voice-Key`: used for that one call, never stored, logged or charged to the owner. Voice and
  model ids must match `[\w.\- ]{1,64}`, and the region must be a key of `QWEN_ENDPOINTS`. All audio becomes WAV PCM16
  (`audioBytesToWav`, `normalizeWav`) along the existing provider paths; lip sync also accepts other
  browser-decodable audio now, without changing those provider request formats.
  On 2026-09-24 the owner tried Azure Speech with a real key: "Nghe thử" and Companion both spoke. The other seven
  are still untested with real keys; their request shapes follow each provider's docs from that day.

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

Every picker on the Giọng nói and Nghe pages of the Companion settings page and in the Micro panel is `Dropdown` from `voiceUi.tsx`, never a native
`<select>` or `<datalist>`. The owner reported on 2026-09-25 that the datalist popup stayed where it was while
Settings scrolled, since the browser draws it as a separate window, and asked for AIRI's behaviour.
- **Placement.** The list sits in the page right under the field (`position: absolute`), so it moves with the field. It
  flips above when there is not enough room below the nearest clipping ancestor, and it re-checks on every scroll
  (a capture listener on `window`) and on resize.
- **Variants.** There are two: select-only (a `role="combobox"` button) and `editable` (an input that filters
  suggestions as you type and still accepts any id).
- **Keyboard.** Arrow keys, Home and End, Enter, type-ahead, and Esc. Esc stops propagation, so it closes only the list
  and not the Settings dialog or the Micro panel.
- **Labels.** `Field` gives its label the id `${id}-label`, which names the listbox.
- **Tests.** `tests/voiceUi.test.tsx` covers the flip and scroll behaviour with mocked rects.

**Alibaba Cloud card: Qwen-TTS and CosyVoice.** The owner liked AIRI's Alibaba voices (龙婉, 龙硕, Stella…) and on
2026-09-25 picked option A from mockups: one card, one Alibaba key, a Model dropdown, like AIRI. The provider id stays
`qwen`, so saved keys survive the rename.
- **Models.** Each model has its own voice set in `KeyProvider.modelInfo`: `qwen3-tts-flash` (48 voices, Vietnamese notes
  translated from the Qwen Cloud voice list), `cosyvoice-v2` (default) and `cosyvoice-v3-flash`.
  - `suggestedVoices`, `defaultVoiceOf` and `voiceNoteOf` pick the set for the current model.
  - Switching models keeps the voice only if the new model has it. Otherwise it falls back to that model's default.
- **Why not v1.** AIRI reaches CosyVoice v1 through its own unspeech proxy. Alibaba shuts v1 down on 2026-10-10.
  - v2 keeps 18 of AIRI's 20 voices as `<id>_v2` (龙彤 and 龙祥 are v1-only) at ¥2 per 10,000 characters.
  - v3 Flash keeps 14 of them as `<id>_v3` at ¥1.
  - Prices are from the China account's model pages, checked 2026-09-25.
- **Voice lists.** `cosyVoices.ts` holds the official China-account voice tables from that day: 100 v2 and 80 v3 Flash
  voices.
  - Only voices that speak English are kept, since Companion replies in English.
  - Voices are grouped by Alibaba's scenes, with Vietnamese notes. Labels are the Chinese name plus a romanisation of
    the id ("龙婉 · Long Wan").
  - The editable voice field shows that label while not being edited, and the raw id while being edited.
- **Relay.** `speech_cloud._cosyvoice` speaks Alibaba's WebSocket protocol:
  - `run-task` with `format: pcm`, 24 kHz and `language_hints: ["en"]`; then `continue-task` and `finish-task` once
    `task-started` arrives. Binary frames are collected until `task-finished`, and the PCM is wrapped as WAV.
  - `task-failed` codes and handshake statuses map to the same Vietnamese messages as the HTTP relays (`relay_error`).
    Alibaba's error text never reaches the user.
  - `websockets` is imported lazily and pinned `>=14` in `requirements.txt`, so an old install breaks only CosyVoice.
    A dedicated logger at WARNING keeps websockets from logging the handshake headers, which include the key.
  - `tests/test_voice_sources.py` runs it against a fake WebSocket server on 127.0.0.1.
  - Nothing has been tried with a real key yet.

**Hearing (Peto nghe, "Ears")**. This is option A, picked by the owner from mockups on 2026-09-24 (AIRI's mic button).
- **UI.** A mic button sits at the left of the Companion composer. Clicking it starts listening and opens the "Micro"
  panel above the composer: a big toggle, a level meter, "Tự gửi", the microphone select and a link to the Nghe page
  of the Companion settings page (`/companion/settings/modules/hearing`). The panel sits inside the chat column, never on the stage, and closes when listening stops. On phones
  (below 720px) a compact status bar above the pill composer replaces it. It all runs in the browser; the backend has no
  part in it.
- **Store.** `hearingEngine.ts` is a module store, like `musicVibe.ts`, shared by Companion and Settings. It holds:
  - the settings, under the `peto-hearing-*` keys;
  - the phase: `off` / `starting` / `waiting` / `speaking` / `transcribing` / `paused`;
  - interim text;
  - a separate level store, so the meter's ~20 updates a second re-render only the meter.
- **Where text goes.** Companion registers a sink (`setHearingSink`) that appends each final sentence to its draft
  (`joinSpeech`). "Nghe thử" in Settings uses a test sink and never touches the draft. The mic opens only on a click, and
  leaving the Companion tab stops listening.
- **Sources.** The first is "Có sẵn trong trình duyệt": the Web Speech API in `browserSpeech.ts`.
  - Interim results show live in the composer, which is read-only while they stream.
  - Browser hearing starts synchronously on the mic click, before opening the optional volume meter, preserving user
    activation. The phase stays `starting` until recognition `onstart`; an unacknowledged start fails after 10 seconds.
    Meter capture failures leave recognition running. Both use the default microphone; the mic selector is disabled
    for this source without erasing the selected device saved for key sources. Two separate captures still exist:
    volume alone is not proof of successful recognition.
  - Speech events or at least 300 ms of audio above 0.01 RMS arm an 8-second no-text notice. This is a diagnostic
    heuristic, not model VAD. Silence alone does not arm it; new words clear it. No-speech notices remain visible in
    Settings while listening. Source availability only claims API support, not a proven working service.
  - All callbacks reject stopped/replaced recognition instances. Intentional mic toggles retain interim words as
    editable draft text; automatic tab cleanup and reply pauses discard them. Unexpected session end/network errors
    retain partial text without auto-send; later finalized speech cannot auto-send that draft until it is manually
    edited or sent. While interim text is displayed, Enter/send cannot drop it by sending only
    the previous draft. Default auto-send and pause choices are unchanged.
  - Chrome ends continuous sessions after silence, so sessions restart. Five sessions in a row that end within a
    second of starting stop with an error; restarts wait 300 ms and stop clears every pending timer.

  The others are the seven key providers in `hearingProviders.ts`: Groq, Azure, OpenAI, Deepgram, ElevenLabs, Gemini and
  OpenAI-compatible servers.
  - The browser calls them directly (CORS checked 2026-09-24).
  - Keys share the Mouth's `peto-voice-keys` store through `voiceProviders.getKeyConfigs` / `updateKeyConfig` /
    `useKeyConfigs`. That store is one snapshot keyed by the raw localStorage string, so saving a key in one tab never
    drops a key entered in the other.
  - `sttModel` is kept apart from the TTS `model`.
- **Recording for key sources.** `hearingCapture.ts` calls getUserMedia with echo cancellation and runs the AudioWorklet
  `hearingWorklet.js`, which batches 2048 frames. The worklet is imported with `?url&no-inline`: Vite otherwise inlines
  files under 4 KB as `data:` URLs, which not every browser loads as a worklet.
- **Cutting sentences.** `hearingAudio.Segmenter` works on volume, with no VAD model:
  - 90 ms of loud audio starts a sentence and 800 ms of quiet ends it;
  - it keeps 300 ms of audio from before the start, caps a sentence at 30 s, and drops blips under 250 ms of speech;
  - sensitivity 0..100 maps to a threshold of -20..-60 dBFS.

  Each sentence becomes WAV PCM16, 16 kHz mono, and sentences are transcribed in order.
- **Errors.** Auth, billing and bad-model errors (`HearingError.fatal`) stop listening. Rate limits and network errors
  show a notice and listening continues.
- **Cách nghe.** "Luôn nghe" (default) or "Giữ để nói"; see "Push to Talk" below.
- **Switches.** "Tạm không nghe khi Peto đang nói" is on by default. It pauses listening while a reply streams or Peto
  speaks, so Peto does not transcribe itself through the speakers, and resumes afterwards. "Tự gửi" is off by default,
  the owner's call, as in AIRI. It sends 700 ms after a heard sentence, and only text that came from hearing: typing
  cancels the pending send.
- **Not done:**
  - official hearing on the owner's key with an allowance;
  - Whisper on the home machine;
  - a model-based VAD;
  - Discord voice. That would live in the bot repo, and since March 2026 Discord requires DAVE end-to-end encryption for
    voice.
- **Tests:** `hearingAudio.test.ts`, `hearingProviders.test.ts`, `browserSpeech.test.ts` and `Hearing.test.tsx` (a fake
  SpeechRecognition and a mocked `hearingCapture`). `browser-tests/hearing.spec.ts` exercises real Chromium microphone
  capture/AudioWorklet with a fake audio device, mocked recognition and blocked external requests on PC/mobile.
  This validates text delivery/lifecycle, not a real browser recognition service or the owner's physical microphone.
  On 2026-09-24 real Edge with Chromium's fake microphone showed the worklet delivering levels.
  No provider has been tried with a real key yet.
- **File names.** `hearingEngine.ts` and `HearingControls.tsx` are deliberately not `hearing.ts` / `Hearing.tsx`: those
  differ only by case, which is the `LocalVoice` problem below.

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

Companion phase 3 (2026-10-02) reduces the wait before speech and coordinates turn cancellation:
- Chat `meta.voice_stream` explicitly allows early speech only for Companion with web search off. Missing/false
  capability uses completed-reply playback, so older servers and search drafts remain safe.
- `StreamSpeechText` buffers incomplete sentences, decimal numbers, common abbreviations and open fenced code;
  `SpeechQueue` feeds the same player used for replay. Final completion flushes the tail without replaying the whole
  response. Speech still needs a ready, enabled voice and an unmuted, active Companion.
- One audio segment plays at a time, with only one synthesis request prefetched. Stop aborts generation, playback,
  pending synthesis and queue waits. Version/controller guards discard late callbacks. Leaving the tab, muting or
  changing character suppresses automatic speech for the rest of that turn.
- The composer accepts drafts during generation. Delayed server acceptance clears only the draft that was sent;
  newer edits survive. During generation, use Dừng before sending the next turn. While only speech remains,
  Gửi can start the next turn and cancels the previous speech.
- Hearing resumes only if it was enabled and still wanted. Auto-send requires a finalized draft, the waiting hearing
  phase and no reply/speech; speaking again or editing postpones/cancels it. Pausing key-based hearing aborts queued
  and in-flight transcriptions and discards their late results after resume.
- Regression tests cover sentence boundaries, player cancellation, Companion draft/turn isolation, hearing
  resume/auto-send and PC/mobile streaming browser flows using fake services.

Companion long-session recovery (2026-10-02):
- Hidden pages, `pagehide` and offline events stop hearing, including Settings tests. Interim text is retained as
  an editable, non-final draft in its original sink; returning/going online never reopens the microphone or auto-sends it.
  Late permission/capture/transcription callbacks are rejected by the session generation. Starts require a visible,
  online page. Leaving the in-app Companion tab retains its existing cleanup behavior.
- Track end or suspended/interrupted AudioContext disposes key-source capture and reports a restart notice; a failed
  optional browser meter does not stop native recognition. Capture shutdown is idempotent and removes event listeners.
- Key transcription retains at most three segments, including the active request, and each request times out at 30 s.
  Overflow is reported without allocating another WAV; timeout is recoverable. Synthesis times out at 45 s, and media
  playback aborts after 20 s without progress. Cancellation resolves waits even when a provider ignores its signal.
- Background/offline speech stops immediately, discards prefetched audio and suppresses automatic speech for that turn.
  Background text generation is retained; reconnect uses the existing history recovery and never resends a chat.
- Coverage: lifecycle/capture/player/Companion unit regressions, 40 mocked capture cycles and 30 actual Chromium
  capture cycles per PC/mobile project. Hidden-page/lock behavior is simulated; physical Android/iOS lock and live
  browser recognition/provider services still require device trials.

Optional spoken barge-in (2026-10-02) is "Cho phép nói chen" on the Nghe page of the Companion settings page:
- Off by default. Enabling it neither starts the microphone nor enables auto-send. While enabled, the existing
  pause-while-speaking preference is preserved but temporarily overridden; its switch is disabled with an explanation.
  Turning barge-in off restores that choice. No extra controls or panels are added to the stage.
- Browser hearing uses native speech-start events, with non-empty recognition text as a fallback. The volume meter
  never triggers browser barge-in. Key-based hearing uses the existing RMS segmenter with a 250 ms onset instead of
  90 ms to reject short clicks; it retains pre-roll and the current recording/transcription rather than restarting it.
  This is an amplitude detector, not a model-based VAD or speaker classifier.
- Only active Companion hearing can interrupt. Settings' Nghe thử and stale microphone sessions cannot interrupt
  chat, and voice samples from Settings are excluded. New speech cancels Companion generation, current audio and
  queued synthesis and clears the spoken expression, while preserving typed/interim words and the same listener.
  Already received reply text remains; late SSE/audio callbacks cannot overwrite the new turn. Speech remaining after
  generation completes is interruptible too. Final words enter the draft and auto-send follows its existing setting.
- Recommend headphones: capture requests browser echo cancellation, but speaker playback may still be detected as
  new speech and cause false interruption. Do not claim reliable full duplex or verified automatic barge-in in AIRI.
  Unit tests and `browser-tests/companion-barge-in.spec.ts` cover cancellation, draft retention, noise guards,
  default settings and PC/mobile flows with simulated speech/services; physical microphones/providers need real trials.

Push to Talk ("Giữ để nói", 2026-10-13, after AIRI PR #2729) is the "Cách nghe" choice on the Nghe page:
- **Pick.** The owner chose "Bật rồi giữ" from three live mockups (the others: the mic button as the hold control with no
  arming step, and a messaging-app recorder where an empty composer's Send becomes a mic with slide-to-cancel). Testing the
  mockup, they found that clicking the mic then pressing Space only toggled it, because the button kept focus; so Space on
  the armed mic button and pressing and holding it with the mouse or a finger also talk, and a quick click still disarms.
- **Setting.** `HearingSettings.mode` is `always` (default, as in AIRI) or `hold`, in `peto-hearing-mode`. With `hold`, the
  pause-while-speaking and barge-in rows are hidden: the microphone only opens during a hold.
- **Engine** (`hearingEngine.ts`). In hold mode `startListening()` only arms (`phase: "ready"`, no capture). `beginHold()`
  must run inside the key or pointer event, because browser recognition needs the user activation; `endHold()` returns
  `short` under `MIN_HOLD_MS` (300, a cancel) and otherwise finishes; `cancelHold()` drops it (Esc), and blur, hidden page,
  pagehide and offline cancel it keeping interim words as an unfinalized draft. `MAX_HOLD_MS` (60 s) ends a stuck hold.
  - Browser source: one recognition per hold; release calls the new `BrowserSpeechSession.finish(done)`, which uses
    `stop()` (not `abort()`), treats leftover interim text as final because the user said they were done, and never
    restarts. A 3 s safety timer takes the interim text if the browser never ends the session. The level meter opens after
    recognition starts.
  - Key sources: the whole hold is one recording (no silence segmenter), sent once on release; a hold with under 150 ms
    above the sensitivity threshold sends nothing and shows a hint.
  - `onHoldStart` on the sink: starting a hold always stops Peto's speech and reply, like barge-in without its switch.
  - `hint` in the state is a short message that clears itself (`flashHearingHint`).
- **UI** (`HearingControls.tsx`). Arming does not open the Micro popover. Desktop shows `HoldControls`' strip above the
  composer ("Giữ Space hay micro để nói", then "Đang nghe" with levels and a timer, Tự gửi switch); phones (720px) show a
  large "Giữ để nói" button and a Tự gửi pill instead, and `HearingBar` is hidden. `MicButton` focuses itself after arming
  (except on coarse pointers, where the tooltip would cover the pill) so the next Space is a hold. Companion's window
  listener follows AIRI's `KEY_OWNER_SELECTOR` (`SPACE_OWNERS`) and also ignores Space while a `dialog` is open.
- **Auto-send** in hold mode fires as soon as the phase is back to `ready` after a release, with no 700 ms wait.
- **Tests:** `Hearing.test.tsx` (Space, Esc, blur, the armed mic button, Groq one-file recording, the settings row),
  `browserSpeech.test.ts` (`finish`), `browser-tests/hearing.spec.ts` (real capture only during a hold, PC Space and phone
  pad). Not checked on a physical phone or with a real recognition service; the first syllable can be lost while the
  microphone opens, which neither Peto nor AIRI has measured.

Companion images (2026-10-02), following the owner's AIRI desktop/mobile references:
- The image button sits immediately left of the mic on desktop, and as a small separate round button left of the pill
  composer on mobile. Thumbnail previews with remove buttons stay inside the composer; no stage panels or camera/screen
  capture are added. The file picker, clipboard paste and drop accept JPEG/PNG/WebP/GIF, up to 4 images. Following
  AIRI's `packages/stage-ui/src/components/scenarios/chat/composables/use-chat-images.ts`, source files may be up to
  20 MB; `prepareCompanionImage.ts` reduces non-GIF images to at most 1920 px on the longest edge, preserving aspect
  ratio and PNG/WebP transparency. JPEG uses quality 0.85; if the encoded file still exceeds 3 MB the edge decreases
  by 20% per attempt. Small images and GIF animation are retained. Prepared images total at most 3 MB per turn.
  Local originals are never modified; previews and provider uploads use the prepared file. Unreadable images fail
  locally. `useCompanionImages.ts` reserves pending slots, prevents sending before preparation completes, discards
  late batches after reset/unmount, and owns/revokes the draft object URLs on remove/accept/reset/unmount.
- Sending accepts images with or without text. A finalized microphone question sends the selected images with it;
  selecting/removing an image cancels any pending auto-send, and interim speech cannot be sent prematurely.
- The server keeps the existing magic-byte validation, account ownership, attachment persistence and recent-image
  context limits. Non-image files remain rejected in Companion. Image input reaches the existing provider vision
  payload, not OCR or a new image service. Reopening Companion shows the saved images; clicking opens the image.
- Encoding and delayed acknowledgments preserve newer draft text/images. Only image IDs included in the acknowledged
  turn are cleared. Failed/unaccepted sends retain their draft, and cancellation before encoding completes cannot
  dispatch a late request. Optimistic message images use separate data URLs before draft URLs are revoked.
- `Companion.test.tsx`, `Hearing.test.tsx`, chat API tests and `browser-tests/companion-images.spec.ts` cover lifecycle,
  microphone questions, provider payload/history, ownership/deletion and desktop/mobile layout with fake services.

Companion timing diagnostics (2026-10-02) live on the Chẩn đoán page of the Companion settings page ("Kiểm tra tốc độ
Companion", shown open since 2026-10-13; before that it was a collapsed section under Settings → Giọng nói). `companionTiming.ts` keeps at most five in-memory records containing source IDs,
input kind, search flag and monotonic `performance.now()` milestones only; it stores no message, audio or key and
does not add requests. Reload/unmount or Xóa kết quả đo clears them and invalidates pending updates.
- Hearing supplies provider-confirmed end/finalization timestamps. Browser end can arrive after final text, or never
  arrive; key-based hearing marks end when the existing silence segmenter closes a segment. These are detector events,
  not a precise physical end-of-speech measurement. The last finalized sentence supplies the voice draft timestamps;
  manual edits discard them. Missing/reversed intervals are unavailable rather than guessed.
- Turns mark send, first visible text, first speakable sentence, synthesis request, actual playback and reply completion.
  Search replacement discards draft milestones. Stop/error freezes a record; late callbacks cannot alter it or a new
  turn. Player cancellation from settings also marks stopped. A completed text-only turn never claims audio playback.
- UI separates recognition, user/auto-send wait, first text, sentence/search wait, synthesis-to-playback and total wait.
  It shows the voice source selected at send, not a claim about the fallback voice ultimately used. No model/network
  latency claim is made from these client-observed combined intervals. AIRI-style stage layout and microphone defaults
  remain unchanged. Coverage includes store guards, real hooks with fake services and PC/mobile Settings/browser flows.

- Voice stays off until the user turns on the "Bật giọng nói" switch on the Giọng nói page, and nothing calls
  `/api/voice` before that. Even once enabled, the hook only probes after Companion (or its settings page, which is
  part of the Companion tab) has been opened, so the Chat tab never calls it. `tests/Companion.test.tsx` asserts both.
- Chunks stay roughly equal (target 150 characters). Generation is only slightly faster than real
  time; the next chunk is requested when the previous one arrives, so it is ready in time only if
  it is not much longer than the one playing. One request at a time also fits the backend's
  one-job-per-owner limit. An aborted request frees that slot only once the backend notices the
  disconnect (it checks every 0.25 s), so a request sent right after an abort can get 429.
- The backend only relays text and audio, or calls TTS APIs over HTTP. Never add TTS models or their packages to the
  backend or the frontend: `pip install` and `npm ci` on the VPS would ship them to every deployment.

### Memory (Brain)

The first Brain feature, picked by the owner from mockups on 2026-09-27 for Companion. It has its own section in
Settings, "Trí nhớ", and is on by default.

On 2026-10-11 the owner asked for Peto to adapt the way Claude's memory does (forms of address, preferences), and chose:
one memory **shared** by Chat and Companion, roleplay Chat **never read or written** (roleplay mode is gone since
2026-10-18; old roleplay chats stay excluded), **on by default**. The same day
they found Companion's "Peto vừa ghi nhớ: … · Xem" line under replies redundant, and it was removed (with its polling);
memories are seen only in Settings → Trí nhớ. Table and API names keep their `companion_` prefix.

**Entries in three sections** (2026-10-15). The owner sent screenshots of Claude's Settings → Memory (You, Topics,
Areas; each entry a title, a one-line summary, "Updated" date and bullet details; a box at the bottom to tell Claude what
to change) and picked "Như Claude" from three live variants (the others: entries opening in place with × per bullet,
and a two-column list/detail). Claude's help pages only document "Topics" and saving during the chat; the three
sections come from the owner's screenshots. Before this, memory was up to 50 one-line notes.
- **Storage.** `companion_memory_entries` (`storage/memory.py`): `section` (`you` "Bạn", `topic` "Chủ đề", `area`
  "Lĩnh vực"), `slot`, `title`, `summary`, `details` (JSON list of short sentences). `you` holds exactly two fixed entries
  by `slot` (`style` "Cách trả lời", `profile` "Hồ sơ"; unique per owner, title not editable); `area` is one entry per
  project, subject or job. Limits (`features/companion/memory.py`): 20 entries, 12 details each, 150 characters per
  detail, at most 3 new entries per run, `MEMORY_BUDGET` 8000 characters told to the model.
- **Old notes.** At startup `init_db` moves each owner's rows of the old `companion_memories` table into one entry with
  slot `legacy` ("Ghi nhớ cũ", up to 60 details) and empties that table. `sort_legacy` then makes one call
  (`SORT_MARKER`) that distributes them into entries and deletes the legacy entry; it runs before the next background
  memory run, or in the background of `GET /api/companion/memory` (which then reports `sorting: true`; the page polls
  every 4 s, at most 10 times). A failed or unparsable sort keeps the notes and waits `SORT_RETRY_SECONDS` (600).
- **Concurrency.** Every model-driven write of an owner (background run, sort, tell) holds `_lock(owner)`. Patches carry
  the entry's `updated_at` at read time (`_seen`) and `apply_memory_changes` skips entries changed since, so a manual edit
  made while the model was thinking is never overwritten.

- **When it runs.** After a complete Companion or Chat turn (`remembers` in
  `features/chat/service.py`), the service marks the owner pending before `done`. It then runs
  `companion_memory.remember(owner)` in the response's background task, so the reply and voice are never delayed. Runs
  for the same owner are coalesced (`_running` / `_again`). Each run is one extra small `peto` call: `MEMORY_MARKER` in
  its system prompt; the current entries are listed as `[id] section · title — summary` plus `  - detail` lines, and the
  model returns `{"entries": [{"id", "details" (the whole new list), "summary"?, "title"?} | {"section", "title",
  "summary", "details"}], "remove": [ids]}`. It is skipped when the new user text is under `MIN_NEW_CHARS`.
  The extraction prompt asks for forms of address ("Tự xưng là ad, gọi Peto là Peto") and preferred answer style in
  "Cách trả lời", updating old details instead of leaving contradictions, opening a new entry only when nothing fits,
  and never homework or document contents. `_talk` marks `--- Companion ---` / `--- Trò chuyện ---` when the new
  messages span several conversations.
- **"Bảo Peto…" (`tell`).** `POST /api/companion/memory/tell` (`{text, entry_id?}`, up to 500 characters) is one small
  call (`TELL_MARKER` in the message) that applies the user's request with the same JSON. It answers `message` (built by
  `describe`: "Đã thêm vào “Hồ sơ”.", "Đã bỏ khỏi …", "Đã thêm mục … vào nhóm Lĩnh vực." …), `changes` (`id`, `kind`
  new/add/remove/update/delete, `fresh` indices to highlight) and the new list. 409 while memory is off, 503 when the
  site disabled it, 404 for an entry that is not the owner's, 502 when the model call fails (nothing changes, the box
  keeps the text). Sensitive data is still refused.
- **What it reads.** A message-id cursor in `companion_memory_state` decides this:
  - On first use the cursor starts at the latest user message, so history from before memory existed is never mined.
  - Turning memory back on moves it to the latest message, so what was said while it was off is never read.
  - Only the owner's own messages are read, filtered in SQL by `storage/memory.MEMORY_SOURCE` (Companion, plus Chat
    with persona `assistant`; `memory_messages_after`). Old roleplay chats never enter. It has nothing to do with the Discord
    bot's memory.
  - The startup migration that added `companion_memory_state.chat` moved every existing cursor past all current
    messages, so Chat history from before the change is never mined; `since` (the Companion summary floor) is
    unchanged.
- **Summary of older talk.** The other half of the proposal the owner agreed to: each Companion thread keeps a short
  summary of what has scrolled out of the `PETO_MAX_HISTORY` window (`companion_summaries`, one row per conversation).
  - Once `SUMMARY_BATCH` (10) messages have left the window unsummarized, the same background task makes one more
    small call (`SUMMARY_MARKER`) that folds up to 40 of the oldest into the summary. `_build_system_prompt` appends
    `persona.build_companion_summary` after the notes, fenced by `COMPANION_SUMMARY_START/END`.
  - It follows the list's rules. It is written and used only while memory is on. It never covers messages at or below
    `companion_memory_state.since`: that is where memory started, or was last switched back on
    (`ensure_memory_state`, `set_memory_enabled`).
  - Deleting an entry, "Xóa hết", or a user action that drops a detail (a manual edit, or telling Peto to forget)
    blanks every summary and moves its `upto` past all current messages (`_forget_summaries`, `forget_summaries`). A
    single fact cannot be cut out of a summary, and Settings promises that a deleted line is forgotten. The cost is lost
    context, never a deleted fact coming back. Background model edits do not blank it.
  - `save_companion_summary` saves only if `upto` is unchanged since it was read, so a delete that lands while the model
    is writing drops the result. `delete_conversation` removes the row, so "Bắt đầu lại" deletes it too.
- **Validation** (`parse_changes`, `new_entry`). Lists only; details cut at 150 characters, case-insensitive
  duplicates dropped; unknown ids and bad sections ignored. A new `you` entry must map to a slot (`slot_for`: "trả lời",
  "hồ sơ"…); a new entry whose slot or title already exists is merged into it; an entry whose details become empty is
  deleted. `apply_memory_changes` applies everything in one transaction.
- **Prompt.** On Companion turns (`memory_block`) and Chat turns (`chat_memory_block`), `_build_system_prompt`
  appends `build_companion_memory` after the profile block: one `### You · Hồ sơ: summary` heading per entry (section
  names in English since 2026-10-18, titles and details as stored) with its details, You first, then the most recently
  updated. Past
  `MEMORY_BLOCK_BUDGET` (9000) the remaining entries keep only their heading. Plain strings (the Brain Benchmark) still
  render as single lines. It is fenced by `COMPANION_MEMORY_START/END` (copies are stripped) and labelled as possibly
  outdated data, not instructions. Stored titles and details are never translated.
- **API.** `features/companion/memory_api.py`:
  - `GET /api/companion/memory` returns `available`, `enabled`, `pending`, `sorting`, `limit` (entries) and `memories`
    (`id`, `section`, `title`, `summary`, `details`, `fixed`, `legacy`, dates). `pending` (set by `mark_pending` before
    `done`, true for 30 s or while a run is going) fed the removed "Peto vừa ghi nhớ" line; no page reads it now.
  - `PUT /settings` turns memory on or off.
  - `POST /tell` as above. `PATCH /{id}` edits title (not for fixed entries), summary or details (1–12). `POST` recreates
    an entry (the Hoàn tác button; 409 for a taken slot or a full memory).
  - `DELETE /{id}` deletes one entry; another owner's id gives 404 on every route.
  - `DELETE` clears all memories.
  - `PETO_COMPANION_MEMORY=false` turns the feature off for everyone (`PUT` and `tell` then return 503).
- **UI** (`MemorySettings.tsx`, `memory.css`; also the Trí nhớ page of the Companion settings page, where each group is a
  card).
  - List: the switch, then SettingsGroups "Bạn", "Chủ đề", "Lĩnh vực" (and "Chưa xếp mục" for the legacy entry), rows
    sorted by title (`localeCompare` vi) with title, summary and "Cập nhật hôm nay/hôm qua/14 thg 10"; Sửa and Xóa
    appear on hover or focus (space reserved, so nothing shifts). Phones show title and summary with a chevron only.
    Footer "N/20 mục · M ý" with "Xóa hết" (inline confirmation). A sticky box at the bottom ("Ví dụ: Con mèo của mình
    tên Mơ") sends `tell`; its result shows as a toast with "Xem", which opens the entry with the new details tinted.
  - Detail: "← Trí nhớ", the section, the title (focused), Sửa and Xóa, "Cập nhật lần cuối", "Tóm tắt", "Chi tiết", and a
    sticky "Bảo Peto đổi hay bỏ điều gì" box for that entry. Sửa edits title (not fixed), summary and one detail per
    line. Esc steps back (stop editing, then back to the list) without closing the Settings dialog; focus never drops to
    the body, which would let the next Esc close the dialog.
  - Deleting is immediate; the toast's "Hoàn tác" recreates the entry with `POST`. Errors roll back and show the
    server's Vietnamese message; the tell box keeps its text on failure.
  - The section reloads whenever it becomes the one shown. Nothing polls the memory after a turn. The first load shows
    `LoadingIndicator` ("Đang tải trí nhớ") in place of the whole section, as Kết nối does; while old notes are being
    sorted, a bordered line with the icon variant says "Peto đang xếp các ghi nhớ cũ vào từng mục…". A bare "Đang tải…"
    line was there before and the owner found it unprofessional (2026-10-15).
  - "Bắt đầu lại" deletes the thread, never the memories. Its dialog re-fetches the list when it opens and, when
    memories exist, says they are kept and where to delete them.
- **Tests.**
  - `backend/tests/test_companion_memory.py`. In a conversation the mock (`ai/mock._memory_changes`) answers
    `__nho__:text` (adds to Hồ sơ), `__sua__:id:text` (replaces an entry's details), `__quen__:id` (deletes) and
    `__muc__:section:title:text` (new entry); a sort puts every old note into Hồ sơ; a tell starting with "bỏ", "quên"
    or "xóa" drops details sharing a word, anything else is added to the entry (or Hồ sơ). A summary call becomes the
    old summary plus the user lines it was given. The summary tests shrink the window with
    `features.chat.service.MAX_HISTORY_MESSAGES` and `companion_memory.SUMMARY_BATCH` (both 4).
  - Provider spies must filter out `MEMORY_MARKER` and `SUMMARY_MARKER` as well as `TITLE_MARKER`.
  - Chat sharing, roleplay exclusion, the upgrade migrations, legacy sorting, tell, manual edits, undo and the
    `_seen` guard are covered there too.
  - Frontend: `MemorySettings.test.tsx`, and in `Companion.test.tsx` the absence of a notice and the reset dialog.
  - Real model behaviour (how well Grok sorts and routes notes) has not been checked; only the mock has run.

### Companion private notes

On 2026-09-27 the owner tried "pick a number from 1-9 and remember it". Peto said it had picked one and judged
guesses ("No, that wasn't it"), then admitted it never had a number. The model keeps nothing between turns except the
conversation text. The owner picked option A from two: a hidden note (`features/companion/private_notes.py`), rather than only telling
Peto to be honest and swap roles.

- **Prompt.** The PRIVATE NOTES section of `COMPANION_SYSTEM_PROMPT` tells Peto to write a game secret once in
  `<private>...</private>`. That is the one exception to "plain spoken text". Peto must never claim a secret choice
  that is not in an earlier note, and answers guesses only from the note.
- **Storage.** The reply is stored raw, note included, and `_to_chat_messages` sends it back to the model as it is.
- **Stream.** `NoteFilter` removes notes from Companion `delta` events and keeps back a tail that may be the start of a
  tag cut between chunks. `flush` releases that tail at the end of the reply. An unclosed note hides the rest of the
  reply.
- **History.** `_public_message(row, companion=True)` strips notes for `GET /api/companion`. `GET
  /api/conversations/{id}/messages` does the same for Companion threads. The browser, the voice and the copy of the
  reply therefore never see a note.
- **Edge cases.** A reply that is only a note counts as no answer and is not saved (`_visible`), so no empty bubble
  appears. Memory extraction strips notes. The summary keeps them, so a game that outlives the history window keeps
  its secret.
- **Scope.** Only Companion threads are filtered. A Chat reply can contain a literal `<private>` in XML code, and
  must not lose it.
- **Tests.** `tests/test_private_notes.py` feeds the filter at every chunk size and every split point. The mock answers
  `__bimat__:x`, a reply hiding x, and `__doan__`, which reads back the latest note from the history it was sent.

### Companion emotions (Brain)

The second Brain feature. The owner picked from mockups on 2026-09-27: the card layout (B), AIRI's nine emotions, and
initially one emotion per reply, expanded to spoken-segment expressions on 2026-10-02, then restored to one per reply
on 2026-10-05 because rapid face changes looked unnatural in short replies. Before this, Hiyori never changed expression: the sample model ships no expression files, and the
keyword guess (`replyEmotion`) almost never matched once the Companion prompt banned emoji.

- **The model picks.**
  - The EMOTION section of `COMPANION_SYSTEM_PROMPT` asks for exactly one AIRI-style marker at the start of every reply,
    choosing the emotion for the whole reply and keeping it throughout:
    `<|EMOTE_HAPPY|>`, `SAD`, `ANGRY`, `THINK`, `SURPRISED`, `AWKWARD`, `QUESTION`, `CURIOUS` or `NEUTRAL`.
  - ANGRY is meant as mild sulking, never hostility.
  - Private notes and the marker are the two exceptions to "plain spoken text".
- **Stream.** `emotion_tags.MarkerFilter` runs after `NoteFilter` on Companion replies:
  - It removes every `<|...|>` marker from `delta` events, and holds back a marker cut between chunks (up to
    `MAX_MARKER_CHARS`).
  - Only the first recognized marker emits an SSE `emotion` with its UTF-16 offset in public text, interleaved with
    `delta` in source order. Extra and unknown markers are stripped without changing expression. Split markers and
    emoji preserve positions. Replacement filters inherit the turn's first emotion, preventing a second event.
  - Both filters share `reply_spacing.Spacing`. A reply never starts or ends with whitespace, and the whitespace on
    both sides of a removed note or marker merges into one gap: the side with more line breaks, otherwise one space.
    Whitespace away from a removed part stays as the model wrote it. The bubble is `pre-wrap`, and before 2026-09-28
    only spaces merged, so a reply opening with a note and a blank line streamed as a bubble with two empty lines at the
    top (history trimmed them, so a reload hid it).
  - Each module's `strip` runs its filter over the whole text, so history equals the stream character for character.
    The tests compare them exactly at every cut point, never after collapsing whitespace, which is how the blank lines
    slipped through before.
  - The reply is stored raw, marker included, so the model keeps seeing its own habit.
- **History and helpers.**
  - `_public_message(companion=True)` strips markers and returns first `emotion` plus a single `emotion_cues` entry at
    offset zero for the whole reply, including old stored replies with multiple markers, without a schema migration.
    After replacement the saved reply is prefixed with the turn's first marker if needed to keep replay consistent.
  - `_visible` strips notes and markers.
  - Memory and summary input (`companion_memory._talk`) never contain markers.
  - Chat replies are left untouched.
- **Timing (`Companion.tsx`).**
  - `cue()` sets `stageEmotion` (`{emotion, key}`; the key makes two equal emotions in a row count as new).
  - With a ready, unmuted voice, the first offset-based cue waits for actual playback. Prefetch, final text completion
    and buffering cannot change the face. Companion ignores additional emotion events, including those from older
    servers. `StreamSpeechText` carries the same emotion through all queued chunks without restarting the face.
    Completed-reply/replay playback keeps normal chunk limits; replay normalizes old multiple cues to one at zero.
    Muted/unavailable voice uses the first text-time cue; old servers without offsets retain immediate cues.
    Replace clears draft offsets and retains the original first emotion for the whole turn, matching persistence.
    Stopped/replaced speech cannot update the next turn's expression or finalize its timing diagnostic.
  - The face holds while Peto speaks. It is released 1.5 s after speech ends, or 6 s after the reply when nothing is
    read aloud.
  - Tracking begins during voice loading, so a failure before playback still releases the face. Buffering
    keeps the same reply's expression. An ending old speech session cannot schedule a release over a new
    streamed reply's cue; a new cue always cancels the previous release timer.
  - A reply without a marker falls back to `replyEmotion`.
- **Faces.** `characterExpressions.faceSource` decides per emotion:
  - **Auto** (no mapping): an expression file whose name matches, otherwise the built-in face.
  - **Mapping values:** a file id, `@builtin` (`BUILTIN_FACE`), or `''` for none. A mapped file the model no longer
    has falls back to the built-in face.
- **Built-in faces** (`builtinFaces.ts`) are Cubism standard parameters in three kinds:
  - `set` blends toward a value, `scale` multiplies eye openness so blinking survives, and `add` adds head angles so
    pointer tracking survives.
  - `mouthOpen` holds the mouth slightly open when silent; lip sync takes the larger value.
  - `FaceBlend` cross-fades (in ~0.15 s, out ~0.5 s). `Live2DStage` applies the face in `beforeModelUpdate`, after the
    idle-eye blend and before the additive head sway.
  - The values were tuned on real renders of Hiyori. Her ranges: mouth form -2..1 with a default of 1 (she already
    smiles), eye open 0..1.2, cheek -1..1.
  - Her brows sit under the bangs, so the faces differ through eyes, mouth, cheeks and head angle. Angles under ~15°
    barely show on her.
  - Happy closes the eyes fully (eye open 0 plus eye smile gives "^ ^"). At 30% open the owner read it as squinting
    (2026-09-28).
- **VRM.** `VRM_EMOTIONS` maps onto the VRM presets (happy, sad, angry, surprised, relaxed) plus a head roll, and uses a
  model's own expression when it defines one with the emotion's name. `vrmFace` returns the weights, the roll and the
  mouth baseline.
  On 2026-10-11 the owner requested gentler VRM faces: happy/sad use 0.7 and surprised 0.8, matching AIRI's
  `packages/stage-ui-three/src/composables/vrm/expression.ts`; angry was already 0.7. FaceBlend timing, mouth baselines,
  other emotions and Live2D presets stay unchanged. The model's native overrideBlink/overrideMouth rules still apply;
  lower weights may leave more room for blink/lip sync but do not guarantee that for every imported model.
  `browser-tests/companion-vrm.spec.ts` is an opt-in real-render check using `PETO_VRM_SAMPLE_PATH`, with API mocks
  and a local silent WAV. It compares old/new weights on the same real VRM, reads applied mesh morphs and captures
  face previews; the inspection hook and old-weight substitution exist only in test network responses.
- **Picker** (`ExpressionPicker.tsx`, layout B).
  - Nine cards in a 3×3 grid, the on/off switch, and the selected card's source: the shared `Dropdown` for Live2D,
    plain text for VRM.
  - A card sends `previewExpression(id, emotion)`. The stage holds the face for 6 s even when the switch is off.
  - It is the Biểu cảm block of Cài đặt Companion → Nhân vật, beside the page's own stage, so the face shows live.
    Until 2026-10-14 it sat in a dialog covering the stage, and the stage photographed the head for the picker
    (`publishSnapshot`, `faceThumbnail`); that pipeline was removed with the dialog.
- **Checking faces.** A hidden browser pane draws no frames, so the face never moves there. Real renders were captured
  with headless Edge over the DevTools protocol, with a temporary profile and a debug build that exposes `show` on
  `window`. That hook must never reach the source.
- **Tests.**
  - `backend/tests/test_emotion_tags.py`: the filter at every cut point, event order, notes plus a marker, the Chat
    tab. The mock prefixes `<|EMOTE_X|>` for `__camxuc__:x`.
  - Frontend: `builtinFaces.test.ts`, `characterExpressions.test.ts`, `ExpressionPicker.test.tsx`,
    `Live2DStage.test.tsx` (built-in face), `VRMStage.test.tsx`, `api.test.ts`, and `Companion.test.tsx`
    (stubbed stage reading the `emotion` prop).

### Companion web search

On 2026-09-28 the owner decided Companion should only gain features AIRI has, and picked AIRI's web-search module from
the list, with option C from mockups: the page shows no sources.

- **Switch, off by default.** Later on 2026-09-28 a Companion reply on the owner's phone was slow. The owner then picked
  a switch in Settings → "Tra web" (option A, like AIRI's Modules → Web Search; since 2026-10-13 it is the Tra web page
  under Mô-đun of the Companion settings page),
  off by default as in AIRI.
  - `companionSearch.ts` keeps it per browser (`peto-companion-web-search`); `SearchSettings.tsx` renders it.
  - Companion sends `off` unless the switch is on.
- **Server.** With the switch on, a Companion turn uses `web_search="auto"`, so Peto decides when to search.
  - A page sending `on` gets `auto`; there is no forced search in Companion. `off` keeps search off.
  - `PETO_WEB_SEARCH_ENABLED=false` still turns search off for everyone.
- **Telling a search from a slow model.** `journalctl -u peto-web` has one `chat_timing` line per turn (`first_text_ms`,
  `total_ms`, `search`). Each model call also logs a `model_usage` line (`elapsed_ms`, `reasoning_tokens`,
  `search_calls_seen`). `search_calls_seen` counts the search calls in xAI's own output, so it catches a search even if
  the page never showed "Đang tra web…".
- **Spoken instructions.**
  - `_stream_reply(spoken=True)` sets `web_search.spoken_reply`, a ContextVar like `document_tools.current_session`,
    and `search_context` then returns `SPOKEN_SEARCH_CONTEXT`. No provider signature changed.
  - The chat text asks for Vietnamese answers with source links. The spoken one keeps English speech with no links or
    citation marks, asks for one quick query, and says where facts came from in plain words.
- **Replace.** When Peto writes before deciding to search, the provider drops that draft (`replace`), and Companion
  clears the bubble in `onReplace`.
  - That draft often held only the emotion marker. `event_stream` therefore remembers the turn's first emotion.
  - If the text after the search has no marker or starts with a different emotion, the stored reply gets the first
    marker back, so a replayed message keeps the same face for the whole reply.
- **Page.** While searching, the header status and the pending bubble say "Đang tra web…" (`searching`, from
  `onSearch`). Sources still stream and are stored with the message, but Companion never renders them.
- **Tests.**
  - `test_web_search.py` checks the instructions through the real provider with a fake client, and the replace path.
  - `Companion.test.tsx` checks the status and bubble, the cleared draft, that no source is shown, and the switch (off
    by default, `auto` once on).
  - The mock provider never fakes a search (`test_mock_does_not_fabricate_search_results`). The real-render check on
    2026-09-28 therefore used a scratch server that patched the mock.
  - Not yet tried with real Grok.

### Companion characters, scenes and Beat Sync

All three run in the browser only. Nothing goes through the backend, and nothing syncs across devices. Clearing site
data deletes them.

- **Character library** (`characters/characterLibrary.ts`, `useCharacters.ts`, `CharacterPicker.tsx`).
  - **Where it opens.** Since 2026-10-14 the library is the "Chọn nhân vật" dialog (AIRI's ModelSelectorDialog) of the
    Cài đặt Companion → Nhân vật page (see "Companion character page"). It only selects, imports, renames and deletes;
    picking a card or finishing an import closes it so the new character shows on the page's stage. The character name
    in the Companion header ("Đổi nhân vật"), the person button beside the stage, "Nhân vật" in the phone sidebar and
    the settings home card all open that page.
  - **Storage.** Hiyori is built in. Users can add up to 20 of their own models, saved in IndexedDB `peto-characters`
    (stores `models` and `assets`). The selected id lives in `peto-selected-character`; a missing id falls back to
    Hiyori, and a `storage` event keeps tabs in sync. Card thumbnails are captured from the rendered canvas
    (`characterThumbnail`).
  - **Actions.** Users can rename or delete their own models. Deleting removes only the library copy, never the
    user's original files.
- **Import** (`characterImport.ts`, loaded on demand).
  - **Live2D** comes as a ZIP (unpacked with fflate) or a folder (`webkitdirectory`).
    - It needs exactly one `.model3.json` (Cubism 3+) and a `MOC3` magic header.
    - Limits: 1–16 textures, at most 100 expressions and 200 motions.
    - Only files referenced from `.model3.json` are imported. Paths that are absolute, contain control characters or
      `: ? # %`, climb out of the package with `..`, or repeat another path (ignoring case) are refused. Inside a ZIP,
      `__MACOSX/` entries and hidden dot-files are skipped.
    - `CharacterImportReview.tsx` lists motions, expressions, textures, physics and any warnings first; any error
      blocks the import.
  - **VRM** is a single `.vrm` file. The GLB header and the VRM extension are checked, external `uri` references are
    refused, and the name and author are read from the model's metadata. It is rendered with `@pixiv/three-vrm`.
  - **Limits** (`characterLimits.ts`, raised by the owner on 2026-10-11): 200 MB per import, 400 MB unpacked, 128 MB
    per file, 4 MB per JSON file, 512 files.
- **Per-character settings**, the blocks of the Nhân vật page (`CharacterSections.tsx`).
  - **Live2D:**
    - "Cách chuyển động": Hiện tại or MAGIC (`MotionDriverPicker.tsx`, see "Companion MAGIC motion");
    - the idle motion: "auto" (random `Idle` group), off, or one looped motion file, in `peto-idle-motion:<id>`;
    - switches for cursor tracking, idle eyes, breathing, physics and composer gaze, all on by default, in
      `peto-character-effects:<id>`. Physics is disabled when the model declares none. `withCharacterEffects` skips
      only those additive effects for a frame and leaves motions, blinks, pose and lip sync alone;
    - size and position, the expression picker and Beat Sync.
  - **VRM:** composer gaze and the expression picker only (no size, position or Beat Sync).
- **Render quality** (`renderQuality.ts`, `stageQuality` in `companionMotion.ts`). On desktop it is fixed at 30 FPS and
  up to 1.5× resolution. Below the 720px breakpoint it defaults to 24 FPS at 1×; the "Hiển thị trên điện thoại" block
  of the Nhân vật page (shown on phones only) can raise it to 60 FPS and up to 2× (`peto-mobile-render-quality`), for both Live2D and VRM.
- **Scenes** (`CompanionScenes.tsx`, `sceneLibrary.ts`; built 2026-09-23). A background picture behind the stage and chat
  column (`.companion-with-scene`).
  - **Where it opens.** The "Bối cảnh" dialog opens from the image button beside the stage, or "Bối cảnh" in the phone
    sidebar (App's `sceneRequest` counter; on the settings page that sidebar item opens the Bối cảnh page instead). The
    Bối cảnh page of the Companion settings page shows the same `SceneEditor`. A `peto-scene-change` event keeps every
    `useCompanionScene` instance in step, since Companion stays mounted while its settings page is open; it reloads the
    stored images only when images were added or removed.
  - **Backgrounds.** Three are built in: `dark` (the default, no picture) and two of Project AIRI's backgrounds in
    `public/scenes/airi/` (MIT, `AIRI-LICENSE.txt`). Users can upload PNG/JPEG/WebP/AVIF files up to 12 MB and 32
    megapixels. Uploads are stored unchanged as Blobs in IndexedDB `peto-scenes` and shared by every character.
  - **Per character.** Each character remembers its background, darkening (0–80%, default 20) and blur (0–20 px) in
    `peto-scene:<character id>`. Deleting the selected upload falls back to `dark`.
- **Beat Sync** (`musicVibe.ts`, `beatMotion.ts`, `MusicVibePicker.tsx`; built 2026-09-22). The character bobs its
  head to music. This is Live2D only; `VRMStage` does not use it.
  - **Audio source.** `getDisplayMedia` asks the user to share a tab with its audio. The video track is ignored, and
    the source must have audio. It works only where display capture and AudioWorklet exist, in practice desktop
    Chrome/Edge.
  - **Analysis.** Beats come from the `@nekopaw/tempora` analyser worklet, with AIRI's looser defaults (warmup,
    adaptive threshold and spectral flux off). `BeatPulse` adapts AIRI's sway trajectory and beat spring (MIT,
    `public/vendor/beat-sync/`).
  - **Motion.** It adds yaw, pitch and roll to the head angles, scaled by `CompanionMotion`'s `musicWeight` so
    conversation poses take precedence. It moves only when character motion is allowed.
  - **Saved settings.** Strength (default 50%) and analyser parameters are kept per character in
    `peto-beat-sync:<id>`.
  - **Lifecycle.** Capture always needs a fresh click and is never restarted automatically. It stops when the shared
    track ends, the model changes, or the user leaves the Companion tab or signs out (`leaveMusicVibe`, run when the
    Live2D stage or the settings page unmounts). Opening the Companion settings page unmounts the stage but keeps
    sharing, so the Nhún theo nhạc page works. Closing the panel keeps it running. Audio is analysed on the device and never uploaded.
- **Tests:** frontend `characterLibrary`, `characterImport`, `CharacterImportReview`, `CharacterPickerImport`,
  `characterEffects`, `sceneLibrary`, `musicVibe`, `beatMotion` and `MusicVibePicker`.

### Companion MAGIC motion (`characters/magic/`)

AIRI PR #2376 (v0.12.0-beta.5): "Markovian Animation Generator with Illusory Conditioning", procedural Live2D motion AIRI
calls "Neuro-sama like (aka Neuro bump)". Surveyed 2026-10-13 (notes in `PETO_COMPANION_PLAN.md` §4); the owner tried a
live mockup with four variants and on 2026-10-14 chose: add it, default stays "Hiện tại" (AIRI's default is Universal),
keep the mouth-form switch.
- **Setting.** Per Live2D character in Cài đặt Companion → Nhân vật → Chuyển động → "Cách chuyển động: Hiện tại / MAGIC"
  (AIRI: Settings → Models →
  Animation → Motion driver). `magicSettings.ts` stores `{driver, profile, viewTarget, mouthForm}` in
  `peto-character-magic:<id>` with a change event, like `characterEffects.ts`. Profiles: Hào hứng (`excited`, AIRI's
  "Speaking / excited", the default profile), Bình thản (`calm`, "Idle / calm") and Theo lúc nói (`speech`, Peto's own:
  calm while waiting, blending to excited while `voicePlaying()` or activity `speaking`; AIRI makes the user pick one).
  "Mắt nhìn thẳng" is AIRI's force-view-target (eyes counter the head); "MAGIC điều khiển dáng miệng" off keeps the model's
  default `ParamMouthForm` (AIRI always drives it). With MAGIC the idle motion select, cursor tracking and idle eyes are
  disabled, as in AIRI; composer gaze, breathing, physics, blink, emotions, lip sync and Beat Sync stay.
- **Model** (`magicModel.ts`): AIRI's VAR only (production AIRI never uses AR-HMM): ridge regression on the last 20 frames
  at 30 Hz, duplicate channels folded, generation = prediction + a residual drawn from the recording × 1.15, clamped to the
  recording's range, seeded random (mulberry32). Algorithms unchanged, comments translated; MIT notice in
  `AIRI-LICENSE.txt` beside it.
- **Data.** `idle-calm.json` and `speaking-excited.json` are AIRI's two recordings already resampled to 30 Hz (what AIRI fits
  on) and rounded to 4 decimals: 137 + 132 KB, 17 + 21 KB gzipped, versus AIRI's 49 + 65 KB. `magicProfiles.ts` imports them
  and fits both; `loadMagic()` reaches it through a dynamic import (a 42 KB gzipped chunk) only when a character uses MAGIC,
  caching the fit for the page. Fitting both takes about 60–190 ms in the browser on the owner's PC.
- **Runtime** (`magicMotion.ts`): `MagicSource` generates 30 Hz frames on the stage's own clock (AIRI uses a separate
  requestAnimationFrame loop) through AIRI's output filter (cutoff 0.0575, smoothing 0.8) and drops generated mouth opening;
  `MagicRuntime` runs both profiles, blends them (0.35 s in, 0.9 s out), applies the view target and AIRI's spring
  (follow 1, inertia 0.6, 1/120 s substeps), and takes or releases control over ~0.3 s (`owned`).
- **Live2DStage.** `start()` awaits `prepareMagic()` before the first frame, so the Companion loading screen covers the fit;
  a later switch loads it on the fly. `magicWriter` writes in `afterMotionUpdate` (before physics, like AIRI's "final" motion
  plugin, so hair follows the head): head ×30°, body ×10°, eye balls, mouth form, honouring an imported model's
  `live2dControls` mappings for head and eyes. Squint multiplies eye openness in `beforeModelUpdate` after blinking, then the
  emotion face is applied on top (so Vui still smiles and closes the eyes). Values written before `saveParameters` persist
  into the next frame, so on release a parameter no motion rewrote eases back to the model default instead of freezing
  (the prototype had left Hiyori's mouth stuck). `magicOffset` shifts the whole model (AIRI: ±20 px across, ±40 px down).
  Reduced motion (unless "Luôn cử động") keeps MAGIC off. A failed chunk shows "Chưa tải được MAGIC…" and keeps the old
  motion.
- **Not done:** VRM (AIRI has none either); AIRI's motion workbench (recording, keyframe editor, gamepad) and custom
  datasets; checks on a physical phone. Lip sync with MAGIC was checked in headless Edge with a muted fake voice.
- **Tests:** `tests/magic.test.ts` (fit, determinism, ranges, real datasets, filter, runtime, writer release and mappings,
  settings), `CharacterSections.test.tsx` and `Live2DStage.test.tsx` MAGIC cases.

### Companion settings page (`/companion/settings/`)

Built 2026-10-13. The owner picked the "Thẻ AIRI" variant from three live mockups (the others were a settings column
beside the stage, and a two-column page with an overview). Plan and AIRI reading notes: `PETO_COMPANION_PLAN.md`.
- **Routes.**
  - `app/routes.ts` (`CompanionSettingsPage`, `companionSettingsRoute`, `companionSettingsPage`) defines:
    - `/companion/settings/`;
    - `character` (see "Companion character page");
    - `modules`, `modules/brain`, `modules/voice`, `modules/hearing`, `modules/web-search` and `modules/beat-sync`;
    - `providers` and `providers/<id>` (see "Companion providers");
    - `scene`, `memory` and `diagnostics`.
  - Each works with or without a trailing slash. `appView` maps them to `companion`, so the sidebar keeps Companion
    selected.
  - The backend fallback accepts exactly these paths.
  - `tests/routes.test.ts`, `backend/tests/test_static_files.py` and `browser-tests/routing.spec.ts` cover deep links,
    F5, Back/Forward and 404s.
- **App wiring.**
  - On these paths App renders the lazy `features/companion/settings/CompanionSettings.tsx`, and Companion stays mounted
    with `active=false`. As when leaving the tab, speech stops, the stage unmounts and the microphone closes; a reply
    that is streaming keeps going.
  - Entry points:
    - the gear "Cài đặt Companion" in the Companion chat column header (`onOpenSettings`);
    - the Micro panel link, which opens the Nghe page.
  - Navigation:
    - Sidebar "Companion" returns to `/companion`.
    - Each page's back button goes to its parent; the home page's back button returns to `/companion`.
- **Layout** (after AIRI's `stage-layouts/settings.vue`, `page-header.vue`, `icon-item.vue` and `ripple-grid`).
  - One centred column, at most 1040px wide, with a sticky header: back button, the parent page's name small above, and
    the page title at 30px.
  - The home page is a list of large cards: Nhân vật, Nhà cung cấp, Mô-đun, Bối cảnh, Trí nhớ, Chẩn đoán. Each card has
    a title, one description line and a large faded icon.
  - Mô-đun is a two-column grid: Bộ não, Giọng nói, Nghe, Tra web, Nhún theo nhạc.
    - A green dot means "on now": voice enabled, microphone listening, web search on, Beat Sync sharing.
    - Each card also has a one-line status.
  - Leaf pages reuse the existing components: `VoiceSettings` (now without tabs), `HearingSettings`, `SearchSettings`,
    `BeatSyncBody`, `SceneEditor`, `MemorySettings` and `CompanionTimingPanel`. Each `SettingsGroup` is styled as a card
    with a large grey title.
  - Palette: scoped `--cs-*` tokens, using the Companion teal already allowed for on/selected states.
  - Icons are drawn locally (`settingsIcons.tsx`). AIRI's Solar icon set was not copied; its licence has not been
    checked.
- **Motion** (owner, 2026-10-13: smooth by default even when the OS asks for reduced motion).
  - The header title slides in over 250ms.
  - Cards rise with a ripple delay from the card clicked last: 70ms per grid step, 260ms each.
  - On hover (fine pointers only): a teal sweep (transform/opacity), the dotted pattern grows stronger, and the icon
    scales and tilts.
  - A giant faded icon rotates in at the bottom right.
  - `:root[data-motion="reduced"]` keeps only the fades: users choose "Giảm" in Cài đặt → Giao diện → Chuyển động.
  - Focus moves to the page title on every page change.
- **Tests:**
  - `Companion.test.tsx`: the gear, levels, Back, the back buttons, focus, the Nhân vật page from the header and the
    card, and a deep link to Trí nhớ.
  - `App.test.tsx`: the shared dialog has no Companion group.
  - `Hearing.test.tsx`: the Micro panel link and leaving the page stopping a test listen.
  - Playwright: `companion-barge-in`, `companion-stream` and `routing`.

### Companion character page (`/companion/settings/character`)

Built 2026-10-14. The owner asked for AIRI's Settings → Models layout "vì có nhân vật nằm ở giữa để dễ xem những gì đã
thay đổi", picked "Như AIRI" from three live variants (the others: editing in place where the chat column swaps for the
settings, and a three-column page with the library always visible), and had AIRI's "We support both 2D and 3D models"
callout dropped as cramped and unneeded.
- **Layout** (`settings/CharacterPage.tsx`, after AIRI's `pages/settings/models/index.vue` and `model-settings/`). The
  settings page header, then a panel on the left (`clamp(340px, 31%, 440px)`): "Chọn nhân vật" with the current name and
  format, the blocks, a footnote. The page's own `Live2DStage`/`VRMStage` fills the rest and centres the character there
  (Companion's stage is unmounted on settings pages). No scene background, as on AIRI's page. Phones: header, a sticky
  44dvh stage, then the blocks scroll under it, so the character stays in view.
- **Blocks** (`characters/CharacterSections.tsx`, AIRI's collapsible `Section`s; Kích thước và vị trí open first):
  - Kích thước và vị trí (AIRI: Scale And Position): Thu phóng, Ngang, Dọc sliders with reset buttons and "Về vừa khung".
    They write the same per-model view as wheel/drag on the stage; `writeCharacterView(view, id, source)` now dispatches
    `peto-character-view-change` and `watchCharacterView` listens, so the stage moves at once and the sliders follow
    wheel and drag. When only the zoom changes, `Live2DStage` zooms around the head (`zoomAt` at the head point) and
    writes the new pan back. VRM: a note.
  - **Phones** (owner's correction, 2026-10-15): size and position are adjustable on phones too, only here, since the
    phone stage still takes no pinch or drag. The phone view is stored apart from the desktop one
    (`peto-character-view-compact:<id>`; `readCharacterView`/`writeCharacterView` take a `compact` flag and events carry
    it), because the phone frame is an upper-body close-up and the desktop a full body. On phones `Live2DStage`
    measures pan in units of the frame height (horizontal: `PHONE_ASPECT`, 9 : 19.5, of it), so the 44dvh preview
    places the character exactly as the full-screen Companion stage does, only smaller, and the keyboard never moves
    it. Crossing 720px saves any pending view and switches to the other frame's view.
  - Chuyển động (AIRI: Animation): "Nhân vật cử động", MAGIC (`MotionDriverPicker`), idle motion, the effect switches.
  - Biểu cảm (`ExpressionPicker`), Nhún theo nhạc (`BeatSyncBody`, Live2D only) and, on phones only, Hiển thị trên điện
    thoại (render quality).
  - Collapsing animates `grid-template-rows` 0fr → 1fr (240 ms); content is `inert` while closed and may overflow only
    once open, so dropdowns are not clipped.
  - Not ported: AIRI's "Extract colors from model" (Peto has no model-derived theme colour) and the manual parameter
    sliders of "Model Parameters".
- **Removed with the old dialog:** `IdleMotionPicker.tsx`, the Beat Sync dialog (`MusicVibePicker`'s default export)
  and the face snapshot pipeline (`publishSnapshot`, `watchSnapshots`, `faceThumbnail`). App no longer holds
  `characterPickerOpen`; `openCharacters` navigates to the page.
- **Tests:** `CharacterSections.test.tsx`, `CharacterPickerImport.test.tsx`, `Live2DStage.test.tsx` (view sync and
  head-anchored zoom), `Companion.test.tsx` (header and card entry, stage beside the blocks), route tests, Playwright
  `routing`, `companion-presence`, and the opt-in `companion-vrm` / `companion-live2d-controls`.

### Companion providers (own API keys, `/companion/settings/providers`)

Built 2026-10-13. The owner asked for AIRI's Settings → Providers so users can bring their own API keys, and picked the
"Như AIRI" variant from three live mockups (the others: keys inside each module page like Giọng nói, and one "Khóa API"
page per company). Their calls the same day:
- Own keys change only Companion's brain; the Chat tab stays Peto, Luna, Haiku.
- Own-key turns neither read nor write memory, because AIRI's memory is still work in progress. Chat history is still
  stored.
- Web search uses the provider's own search where it has one (xAI, OpenAI, Anthropic, Gemini). Otherwise the user enters
  a Tavily key on the Tra web page, as in AIRI's Web Search module.
- The first batch is xAI, Anthropic, OpenAI, DeepSeek, Ollama (the ollama.com cloud, the owner's pick; the server cannot
  reach Ollama on the user's machine), Google Gemini, Azure OpenAI and Mistral.

**Backend** (`ai/byok.py`, `features/companion/providers_api.py`).
- `ChatRequest.provider` (`{id, model, endpoint?}`) is accepted only in Companion (400 elsewhere). The key comes in
  `X-Peto-Provider-Key`, the Tavily key in `X-Peto-Search-Key`; both live only for that turn and are never stored or
  logged, like the voice relay's `X-Voice-Key`. `byok.choose` validates the id, model and key (printable ASCII, 8–512
  characters) before anything is stored.
- The server only calls a fixed list of hosts. Azure OpenAI accepts only `https://<name>.openai.azure.com` (or
  `cognitiveservices.azure.com`, `services.ai.azure.com`) and calls `<endpoint>/openai/v1`. This keeps users from using the
  server to reach arbitrary addresses.
- Provider kinds:
  - xAI and OpenAI: a keyed `ResponsesProvider` subclass. `send_reasoning` drops `reasoning` and the encrypted reasoning
    include for models that reject them: OpenAI outside `o*`/`gpt-5`/`gpt-6`, and xAI outside `XAI_MODEL` and
    `grok-3-mini`.
  - Anthropic: `ClaudeProvider` with the user's SDK client. `ClaudeClient(adaptive=False)` skips adaptive thinking for
    models older than generation 5.
  - Gemini: the native `streamGenerateContent` API (SSE), with `google_search` grounding when search is on. The key is
    sent in `x-goog-api-key`, never in the URL. The OpenAI-compatible layer has no search.
  - DeepSeek, Mistral and Azure OpenAI: `ChatCompletionsProvider`.
  - Ollama cloud: `OllamaProvider` on `/api/chat` with NDJSON.
  - Both share `_ToolLoopProvider`: up to 3 tool rounds with the time tool and, with a Tavily key, a `web_search`
    function backed by `api.tavily.com`. Text written before a tool call becomes a `replace` draft, like Grok's.
  - DeepSeek and Ollama get image labels instead of images.
  - No SDK retries. HTTP failures map to Vietnamese messages (key refused, quota, rate limit, unknown model, provider
    down); provider text is only logged, clipped.
- A Tavily provider without a Tavily key forces `web_search="off"`, so early speech still works.
- `remembers` is false for own-key turns, and `_build_system_prompt(memory=False)` drops the Discord memory, the memory
  list and the thread summary. `messages.provider` (new column, `''` for Peto) marks both messages of the turn.
  `memory_messages_after` and `messages_before_window` skip marked rows, so a later Peto turn never mines them.
- Usage events use service `byok`, model `byok:<id>` and slug `byok/<id>/<model>` (`usage_service` and `usage_slug` on the
  provider). The admin page therefore never prices them as owner cost, even when the model name matches a priced slug.
- `POST /api/companion/providers/check` (authenticated, `no-store`) lists models with the user's key to verify it.
  Results are filtered to chat models. Azure returns an empty list; the user types the deployment name. Ollama's tag list
  may not prove the key; a bad key then fails on the first turn.
- Mock mode (`PETO_AI_PROVIDER=mock`): own-key turns use `MockProvider("byok:<id>:<model>")`, and the check returns sample
  models (a key containing `__sai__` is refused).

**Frontend.**
- Catalogue: `features/companion/providers/catalog.ts` mirrors `PROVIDERS`.
- Keys share the `peto-voice-keys` store by provider id, so one OpenAI or Gemini key serves the brain, voice and hearing.
  `KeyConfig` gained `endpoint` and `deployment`.
- Brain store: `providers/brain.ts`.
  - `peto-companion-brain` holds `{provider, model}`; Peto when absent.
  - `peto-provider-models` holds the model list from the last successful check.
  - A provider is "connected" only after a check with the current key. Editing or forgetting the key clears that list and
    resets the brain to Peto.
  - `brainRequest(search)` builds the turn's `provider`, key and, only for Tavily providers with search on, the Tavily
    key. `sendMessage` sends the keys as headers.
- Pages (`settings/ProvidersPages.tsx`):
  - `/companion/settings/providers`: intro box, tabs Bộ não / Giọng nói / Nghe, a price filter (not on Giọng nói, whose
    catalogue has no free-tier data), and AIRI-style cards with a status foot (Đã kết nối, Chưa kiểm tra, Chưa có khóa,
    Không cần khóa).
  - `/companion/settings/providers/<id>`: key fields, Kiểm tra kết nối for brain providers, and where the key is used.
  - `/companion/settings/modules/brain`: provider and model dropdowns plus the own-key notice.
  - Tra web: `TavilySection`.
  - Giọng nói and Nghe no longer show key inputs. `KeyLink` reads "Đã có khóa X · Sửa ở Nhà cung cấp" and opens the
    provider page. Model and voice choices stay there.
- Routes: `COMPANION_PROVIDER_IDS` in `app/routes.ts` (`companionProviderRoute`, `companionProviderId`) matches the
  catalogue (a test compares them) and `_COMPANION_PROVIDERS` in `core/static_files.py`.
- Companion's status line under the character's name adds the provider ("Trả lời ngắn bằng tiếng Anh · DeepSeek").
- **Tests:**
  - `backend/tests/test_byok.py`: turns, validation, memory exclusion, the check endpoint, request shapes over
    `httpx.MockTransport`, Tavily, Gemini, Ollama, error messages and usage labels.
  - `frontend/tests/Providers.test.tsx`.
  - Updated key tests in `Companion.test.tsx` and `Hearing.test.tsx`.
  - Browser: `browser-tests/companion-providers.spec.ts` and `routing.spec.ts`.
- **Not checked:** none of the eight providers or Tavily has been called with a real key; request shapes follow each
  provider's docs as of 2026-10-13.

### Motion setting (Cài đặt → Giao diện → Chuyển động)

Built 2026-10-13, after the owner asked for smooth motion across the web "dù máy đã bật giảm chuyển động". Users who
dislike it reduce it here, like Claude's Appearance → Motion.
- **Choices** (`peto-motion`, `MOTIONS` in `app/preferences.tsx`):
  - "Mượt" (`full`, the default) animates even when the OS asks for reduced motion;
  - "Theo máy" (`system`) follows `prefers-reduced-motion` live;
  - "Giảm" (`reduced`).
- **How it is applied.**
  - The resolved value is `<html data-motion="full|reduced">`. The inline script in `index.html` sets it before React
    runs, so nothing flashes (it runs on /docs too), and `usePreferencesPersistence` keeps it current.
  - `shared/motion.ts` exposes `readMotionChoice`, `resolveMotion`, `applyMotion`, `isReducedMotion` and
    `useReducedMotion`; the last one watches the attribute with a MutationObserver.
- **What follows it.**
  - App CSS: all 25 former `@media (prefers-reduced-motion: reduce)` blocks became `:root[data-motion="reduced"] …`
    rules.
  - JS:
    - the composer's first-send FLIP;
    - phone Settings page slides;
    - the Imagine viewer FLIP;
    - Live2D and VRM "Theo cài đặt chung";
    - the Docs default.
  - The loading logo is still exempt.
- **Tests and checks.**
  - Unit tests: `tests/motion.test.tsx` and an `App.test.tsx` case; Live2D and VRM tests mock `isReducedMotion`.
  - Playwright: `playwright.config.ts` emulates an OS that reduces motion, and `mockPeto` sets `peto-motion=system`, so
    screenshots keep their old meaning. `browser-tests/motion.spec.ts` checks the default and "Giảm" across F5.

### Peto Agent (CLI)

`agent-cli/` is a stdlib-only Python CLI (`peto`) that runs on the user's machine. **The CLI owns the loop**: it
sends the whole conversation to `POST /api/agent/step`, the backend makes exactly one model call and streams `meta` /
`thinking` / `delta` / `done{output, usage}` / `error`, and the CLI runs the requested tools locally and sends their
results in the next step. The server stores no conversation (`store=False`), and the xAI credential never leaves it.

- **Login** is a device-code flow in `features/agent/api.py`. `device/start` returns a `XXXX-XXXX` code; the user opens
  `/?agent_code=…`, where `AgentConnectDialog.tsx` keeps the code in `sessionStorage` across OAuth redirects; `POST
  device/{code}` allows or denies; `device/token` hands the CLI a `peto_…` token exactly once. The fixed routes must stay
  declared before `/device/{user_code}`. Pending codes live in RAM for 10 minutes, so this needs the single-process
  backend, like the voice relay. Only the token's SHA-256 is stored (`agent_devices`), and tokens unused for
  `PETO_AGENT_TOKEN_IDLE_DAYS` stop working. Settings → Peto Agent (`AgentSettings.tsx`) lists and revokes devices.
- **Every signed-in account can use the agent** (Discord, Google, GitHub). Guests could not until guest login was
  removed; `device_auth` still refuses a token whose owner no longer parses.
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
  are always the server's: `english.CORE_PROMPT` + `english.agent_prompt(…)` + the search prompt for the current setting + time
  context + project/OS line. Tool schemas are server-owned (`features/agent/tools.py`). `ai/agent.py` holds the xAI call and a mock that runs a scripted `__demo__` task (read
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
  - An edit needs a prior `read_file`, a unique match and an unchanged file, and keeps CRLF/BOM. Since 0.18.0, with
    the server's `edit_v2`, the match may be approximate under strict rules the owner approved on 2026-10-12; see the
    0.18.0 bullet under "Redesign after OpenCode".
  - From 0.28.5, edits and commands default to allow; `/permissions` can set allow/ask/deny per project, separately
    for shell and edit. In ask mode, edits, writes, deletes, renames and commands ask `[y/n/a]`, where `a` lasts for the current request only.
    Commands (`run_command` and `start_command`, through `Tools._approve_command`) also offer `s` (this exact command,
    folder, timeout and shell, for the session) and `l` (this exact command, folder and shell, always, in this project).
  - `l` grants live in `approvals.py`, in `permissions.json` next to `config.json` in the user's profile, keyed by the
    normcased project root. This is the "loosen permissions gradually" item `PETO_AGENT_PLAN.md` left open (added
    2026-09-23 after the owner asked to weigh ChatGPT's `.peto/permissions.json` idea). **Never read grants from the
    project folder**: a downloaded repo could ship a file that pre-approves commands. Matching is exact, with no
    wildcard or prefix matching, so `npm test && …` never rides on `npm test`. The timeout is left out of the key: it
    is only a cap, Ctrl+C still stops the command, and the model varies it between runs. A command that runs on an `l`
    grant prints a dim line saying so. `/permissions` lists both kinds, plus pages Peto may click and type on (browser
    phase 2) and outside domains it may view (phase 3). `/permissions clear` drops grants and policy, returning to allow.
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
- **Redesign after OpenCode (in progress since 2026-10-12).** The owner asked to redo everything seen in the terminal
  after OpenCode (MIT, https://github.com/anomalyco/opencode): display, tool behaviour and a concise reply voice.
  Owner's picks after real xterm.js mockups (https://claude.ai/artifact/2PGMSbJruX1EedZUk6quZ2):
  - **Inline with a fixed footer** (like `opencode mini`), not OpenCode's full-screen view, picked first. Superseded
    by the full screen in 0.19.0 (below). There is no sidebar.
  - **No painted background.** Only panels get a background: user messages, tool blocks, the prompt. The terminal's
    own background shows elsewhere. Theme colours are OpenCode's `opencode` theme with Peto's rose as primary.
  - **Paste collapsing unchanged:** 4+ lines or 1000+ characters.
  - **Show context use**, so users know when to `/compact` and when compaction runs by itself. The figure is measured
    against the CLI's own automatic-compaction threshold (`loop.py`: 180 items or 200,000 characters), not the
    model's window, so no server change is needed.

  Phases:
  - 0.15.0: tools and the loop emit structured events; same look.
  - 0.16.0: the OpenCode look.
  - 0.17.x: the footer engine.
  - 0.18.0: tool behaviour, behind new `features`.
  - 0.19.0: the full screen, replacing the inline footer as the default.
  - Voice: backend prompts, measured with evals first.

  Tolerant edit matching relaxes "exact unique match" and needs the owner's separate approval. Until 0.16.0 ships,
  the bullets below describe the current look.

  **0.15.0 (done 2026-10-12): structured events.** `peto_agent/events.py` defines the events, and handlers no longer
  build display strings.
  - Every tool method carries `@tool`, and MCP handlers go through `Tools._evented`. A call emits `ui.tool_started` and
    `ui.tool_finished(ToolDone)`, including direct calls such as `/init`'s `list_files` and tests.
  - `ToolDone.result` is exactly what the model receives. `meta` is display-only and never sent: `refused`, `raised`
    (with `message`), `read_only`, `done`, `plan`, `base`, and the screenshot `path`.
  - Before approval a handler calls `ui.preview(kind, body)` for a diff, command, move or MCP call. Questions go through
    `ui.ask(Permission)`; the y/n/a/s/l semantics are unchanged.
  - Other events: `ui.notice`, `ui.search`, `ui.request_finished(RequestEnd)`, `ui.tool_progress(call_id, …)`.
  - The loop sets `tools.call_id` before each call instead of passing a new argument, so the evals `Recorder` wrapper
    keeps working.
  - `UI` in `ui.py` turns these events back into the exact old lines, so all 334 tests pass. `PolicyUI` is unchanged,
    because the legacy `preview`/`ask` still call `diff`/`command`/`page_permission`.
  - Server `thinking` events now reach `ReplyWriter.think` (still not drawn) and tick the "đang nghĩ · Ns" clock, which
    used to freeze while summaries streamed.
  - `format_duration`/`format_tokens` moved to `formats.py`; `loop` re-exports them.
  - Tests: `agent-cli/tests/test_events.py`.

  **0.16.0 (done 2026-10-12): the OpenCode look, still inline.**
  - **Which UI runs.** `__main__.create_ui` picks `tui.view.TerminalUI` when stdout is a VT terminal.
    `PETO_AGENT_UI=classic` forces the old `ui.UI`, which also serves pipes, files, tests and `PolicyUI`. The old
    colored `UI` path and `line_editor.layout` are now used only by tests.
  - **Modules (`peto_agent/tui/`).**
    - `theme.py`: OpenCode `opencode` tokens with an MIT attribution, rose primary, `PETO_AGENT_THEME=light`. Glyphs
      fall back to ASCII-ish ones outside Windows Terminal and VS Code, where conhost/Consolas may lack Braille and
      some symbols.
    - `text.py`: spans, cell width, wrap.
    - `highlight.py`: regex highlighting, no parser.
    - `markdown.py`: streaming blocks; tables are drawn once complete.
    - `diff.py`: line-number gutter; split into two columns above 120 cells.
    - `prompt.py`: the prompt frame, passed to `LineEditor.read(frame=…)`. Suggestions show above the box. On submit
      the box becomes the user-message panel in scrollback.
    - `view.py`: `TerminalUI` and `TerminalReply`.
  - **Behaviour.**
    - Consecutive read/list/search calls stay in `_group` and print as one "→ Đã xem: …" line when other output starts.
    - Edits and commands print as panel blocks. The diff in an edit block is capped at 40 rows; `/diff` shows all.
    - The permission panel is drawn transiently at the bottom and answered with ←/→ + Enter. Esc means n, letters work,
      and v/PgDn pages the diff. Keys arriving within 300 ms of opening are ignored. The panel is erased after the
      answer.
    - Without raw keys (`editor` is None), the panel prints statically and the answer is typed.
    - Thinking shows only as "+ Đã nghĩ: <last bold heading> · Ns"; `/suynghi` (new command) also prints the summary.
    - The request ends with "▣ Peto · <model> · <time> · … · N% tới lúc tự tóm tắt".
    - The prompt footer adds "ngữ cảnh N% tới lúc tự tóm tắt", from `Session.context_share()` against `COMPACT_ITEMS`
      and `COMPACT_CHARS`.
  - **Packaging.** `pyproject` lists `peto_agent.tui`. `install.build_wheel` maps dotted names to folders and dedupes
    files.
  - **Checking.**
    - `agent-cli/tests/test_tui.py` checks that no row reaches the last column at 40–160 columns, plus grouping,
      blocks, panel keys, the prompt frame and NO_COLOR.
    - Visual check: a scratch script ran the real `TerminalUI` and `Tools` (real edit, real `py -m unittest`) with a
      fake console, and the ANSI was replayed in xterm.js. Real Windows Terminal, conhost and VS Code typing (Unikey)
      still need the owner's check.

  **0.17.0 (done 2026-10-12): fixed footer.** The owner kept "chân cố định" after being told that Claude Code is
  inline, not full-screen. That was outdated (see 0.19.0); since 0.19.0 this engine runs only with
  `PETO_AGENT_UI=inline`.
  - **Engine** (`tui/footer.py`, `FooterEngine`). `__main__.session` calls `ui.start_footer()` after the header and
    `stop_footer()` in its `finally`.
    - The console stays raw for the whole session (`WindowsConsole.ensure_raw()` re-applies it every second, since child
      processes share the console).
    - One input thread waits with `WindowsConsole.wait(100)` and feeds keys to the shared `EditorState`.
    - All output goes through `TerminalUI.write` → `engine.commit`: erase the footer, write lines, redraw the footer, in
      one write wrapped in `?2026`. No DECSTBM.
  - **Footer contents.**
    - Above the prompt: queued messages ("↳ Chờ gửi"), the spinner status and the running plan item ("▶ … (k/n)").
    - Busy: the prompt placeholder and footer line change; the footer line becomes "esc lần nữa để dừng" after one
      Esc.
  - **Keys and requests.**
    - Enter while busy queues the message; `take()` returns queued messages before waiting.
    - Ctrl+C or Esc Esc while busy calls `signal.raise_signal(SIGINT)`, so the main thread gets the usual
      `KeyboardInterrupt` and `runner` still kills the process tree.
    - Ctrl+C on an idle prompt clears text, or exits when the prompt is empty.
    - Permission questions and `wait_for_user` replace the prompt via `engine.ask(render, handle)`. They share
      `TerminalUI._chooser` with the pre-engine panel, ignore keys for 300 ms, and keep the draft. `/diff` prints the
      whole diff.
  - **Resize.** The erase assumes one line per footer row even after a width shrink. Assuming reflow made ConPTY
    erase two committed lines in a test. A shrink may now leave a stray "┃" row above; history is never erased.
  - **Tests.**
    - `tests/test_footer.py` with `tests/vt.py`, a minimal terminal emulator. It checks that every committed line
      reaches scrollback once and in order with the footer at the bottom, plus queueing, Ctrl+C/Esc, the panel and stop.
    - A scratch ConPTY driver ran real `python -m peto_agent` against a fake local server with scripted keys, replayed
      in xterm.js. It covered typing while busy, the queued message auto-sending, arrow-key approval, Esc Esc and
      Ctrl+C stopping a request without exiting, Ctrl+C exiting from idle, and resizing 100→70→50→90→100 columns.

  **0.18.0 (done 2026-10-12): tool behaviour like OpenCode.** It needs the backend deployed. Old CLIs keep
  byte-identical schemas.
  - **Handshake.** `/api/agent/me` returns `agent_features`. The CLI (`__main__`, and `evals/run.py`) declares
    `NEW_FEATURES` only when they are listed there. Results are built by the CLI while descriptions come from the
    server, so a new CLI on an old server stays on the old behaviour.
  - **Schema pins.** `backend/tests/test_agent_tool_features.py` pins the sha256 of every shipped feature set. New
    variants replace tools in place, and `find_files` is appended last to keep the prefix cache.
  - **`explore_v2`.**
    - `read_file` content is `cat -n` style (`f"{n:>6}\t"`), and so are `@` mentions.
    - `search_files` returns `{files: [{path, matches: [{line, text}]}], total, truncated}`, newest file first.
    - The new `find_files(pattern, path)` uses its own glob translation (`tools.glob_regex`: `**`, `*`, `?`, `[!x]`,
      case-insensitive). It goes through `iter_files`, so it honours ignores, and returns at most 100 results, newest
      first.
    - Prompts: `AGENT_EXPLORE_PROMPT` in Vietnamese and English.
  - **`edit_v2`** (owner-approved).
    - `edit_file` gains `replace_all`. `edit_match.find` tries, in order: exact, then stripping line-number prefixes,
      then line-trimmed, then whitespace-normalised lines. There is no character-distance fuzzing.
    - Every strategy still needs a unique match; `replace_all` covers exact matches only. Ambiguity names up to 8
      line numbers.
    - On an approximate match, `reindent` maps each old_text line's indentation to the file's (longest prefix).
    - The result carries `match` and `replacements`, and the permission panel and edit block say "khớp gần đúng: …".
    - Read-before-edit, the digest check, CRLF/BOM and the checkpoint are unchanged.
    - Prompt: `AGENT_EDIT_PROMPT`.
  - **Loop guard (CLI only).** The third identical call (same name and canonical arguments, no file revision in
    between) asks `Permission("loop")`.
    - Polling and browser tools are exempt (`LOOP_EXEMPT`).
    - A refusal returns an error telling Peto to change approach. `PolicyUI` refuses with a reason, by the owner's
      pick.
  - **Tests.** `agent-cli/tests/test_tools_v2.py`, two `test_tui.py` cases, and feature negotiation in
    `test_loop_client.py`.

  **0.19.0 (done 2026-10-12): full screen, like Claude Code.**
  - **Why it changed.** The owner saw that their Claude Code (v2.1.278) draws on the alternate screen, pins the prompt
    at the bottom and leaves the terminal clean on exit. That is Claude Code's fullscreen renderer
    (https://code.claude.com/docs/en/fullscreen), the default for users who started after 2026-05-06. They asked for
    that, and saw 0.17's footer leave stacked prompt boxes when the VS Code panel was resized (xterm.js reflows the old
    footer rows). They picked Claude Code's layout (header at top, prompt at bottom) over opencode's centred home, and
    mouse capture.
  - **Engine** (`tui/screen.py`, `ScreenEngine`, a `FooterEngine` subclass that keeps its input thread, queue, panel
    and stop keys).
    - `?1049h` on start, `?1049l` on stop, after clearing the alternate screen. `__main__.session` now starts it before
      the header. Exit prints nothing except "Đã dừng N lệnh nền", shown after leaving.
    - The transcript is a list of `Entry` objects holding a build function, cached per width. On resize everything
      reflows: `TerminalUI._emit`/`_out` take builders, which capture the preview at emit time. Text written directly
      becomes a `TextEntry` (`text.parse_ansi`). The header picks its mascot size at draw time. A streaming reply is
      one entry re-rendered from its Markdown source.
    - Each frame rewrites only changed rows, each from column 1 followed by EL. Claude Code's docs say ConPTY mangles
      sparse cell writes. `PETO_AGENT_FULL_REPAINT=1` rewrites every row.
  - **Scrolling.**
    - Wheel 3 lines, PgUp/PgDn half a screen, Ctrl+Home/End.
    - The anchor is (entry, line) so new output does not move a scrolled view. The last transcript row shows
      "↓ còn N dòng bên dưới".
    - Sending a message or a permission question returns to the bottom.
  - **Mouse** (`line_editor.WindowsConsole`, `mouse` flag).
    - Raw mode adds `ENABLE_MOUSE_INPUT | ENABLE_WINDOW_INPUT | ENABLE_EXTENDED_FLAGS` and drops QuickEdit.
    - Checked through ConPTY on 2026-10-12: wheel, press, drag and release arrive as `MOUSE_EVENT` records in screen
      cells, so no VT input parsing is needed. Hover moves are dropped.
    - Drag selects and copies on release (`tui/clipboard.py`, CF_UNICODETEXT), and a double click copies a word.
    - Ctrl+C with a selection copies instead of stopping. Shift+drag keeps native selection.
    - Ctrl+click opens a URL or existing path, except in VS Code, which handles links itself. Ctrl+L redraws.
  - **Tests and checks.**
    - `agent-cli/tests/test_screen.py`. `tests/vt.py` gained `?1049`, CUP and `2J`.
    - A scratch ConPTY run of real `python -m peto_agent` (typing, permission, wheel, resize 100→70→50→90→100, exit)
      was replayed in xterm.js.
    - xterm.js's WebGL addon (headless) kept stale panel backgrounds on the main screen after a resize followed by
      leaving the alternate screen. A minimal sequence without peto does the same, the buffer itself is clean, and
      the DOM renderer shows nothing. Whether real VS Code shows it needs the owner's check.

  **Voice (in progress 2026-10-12, backend only).**
  - **Prompts.** `AGENT_PROMPT` gained "## Cách trả lời" and the English prompt "## Replies", replacing "gọn và đi
    thẳng vào việc", "Xong việc thì tóm tắt ngắn…" and "Finish with changes…". The rules:
    - no plan announcement before tools; `update_plan` for multi-step work;
    - silence between tool calls, or one sentence when the cause is found;
    - result first, usually 1–4 prose lines, bullets for several changes;
    - no closing offers;
    - code questions answered in the first sentence with `path:line`, explanations complete;
    - after the CLI's "Kiểm tra sau sửa" reminder, only what is new.
  - **Measurement.**
    - `evals/harness.voice` measures final reply lines and characters (excluding code), text between tool calls,
      filler openers, closing offers, `path:line` references and output tokens. It works from recorded steps, so it
      costs nothing. `report.md` has a "Giọng trả lời" section; `run.py compare A B` lines up two runs.
    - Baseline 2026-10-12 (Peto, medium, CLI 0.19.0, prompts before the change): 10/10 passed, 70 turns, 28k output
      tokens. Every task opened with "Mình sẽ xem…"; 20 turns carried 2,360 characters of narration between tools.
      Final replies averaged 5.6 lines / 582 characters; no closing offers; 3 `path:line` references.
    - The CLI stays unchanged between runs so only the prompt differs.
    - After the change (same day, deployed): still 10/10, 70 → 68 turns, output tokens 28k → 26k, final replies
      5.6 → 4.1 lines and 582 → 492 characters, narration 2,360 → 1,984 characters. The fix tasks shortened most
      (sua-api 12 → 4 lines); question answers kept their evidence.
    - The opening announcement did not change: Grok dropped "sẽ" ("Mình xem cấu trúc…"). `harness.PREAMBLE` was
      widened to catch that, giving 10 → 10. The rule was then sharpened: when tools are needed, the first turn holds
      tool calls only, and nothing announces the next step.
    - Third run (2026-10-13, deployed, CLI 0.21.0): still 10/10, 70 turns, 25k output tokens, final replies 4.0 lines,
      narration 1,887 characters, `path:line` 6 → 11. The opener did not move (10 → 10): Grok still writes "Mình sẽ
      xem…" in the first turn, and `WEB_PLATFORM_PROMPT`'s lead-in rule is not part of the Agent prompt, so nothing
      contradicts it. Two prompt versions have failed on this; it looks like Grok's habit. Peto asked no `ask_user`
      question on these clear tasks.
    - **6 Luna, same day, same tasks** (the owner allowed the OpenAI spend): 10/10, 96 turns, 16k output tokens, final
      replies 3.3 lines, no narration and no openers, 18 `path:line` references. `apply_patch` ran 8 times with no
      error, editing several files per call. 29 of the 96 turns held only an `update_plan` call (Peto: 1 of 70), and
      `tran-ngang-dien-thoai` hit the task's 14-turn cap with no final reply because of them.
    - **Fix, CLI 0.21.1 + prompts.** Both prompts now say to send `update_plan` in the same turn as the next step's
      tools and the final all-done update with the final answer. The CLI ends a request when a step has reply text and
      only `update_plan` calls that leave nothing undone (`result.left == 0`), still applying the "Kiểm tra sau sửa"
      reminder (`Session._remind_to_check`) and steers. Text with an unfinished plan (Grok's lead-in) continues as
      before.
    - **Luna rerun (2026-10-14, 0.21.1 deployed):** 10/10, 90 turns, 15k output tokens, `apply_patch` 8/8 again. The
      fix did nothing: still 29 turns held only `update_plan` (9 plans made alone in the first turn, the rest marking
      items done), and `test-do-tren-windows` hit the 14-turn cap. Luna never puts text and tool calls in one turn, so
      the CLI's early end never fired: it sends the final all-done update alone, then answers in the next turn.
    - **Owner's call (2026-10-14): GPT models get no `update_plan`.** `tool_schemas(…, patch_model=True)` drops it for
      every feature set, and GPT steps use `english.AGENT_PROMPT_NO_PLAN` (the plan sentences cut out; import fails if
      they no longer match). Peto and Claude keep the tool and the prompt. Pinned non-GPT schema hashes are unchanged.
      `test_gpt_models_get_no_update_plan_tool_or_prompt` covers it.
    - **Measured the same day after deploy** (`20261014-170204-luna-medium`): 10/10, turns 90 → 67, input tokens
      1.25M → 0.93M, output 15k, no task at the turn cap. Final replies 3.1 lines; `path:line` 11 → 19.
      `apply_patch` 8 successes plus one refusal ("read before editing"), after which Luna read the file and
      patched again.
  **Features from opencode, 0.20.0 (done 2026-10-12, CLI only).**
  The owner asked to mine opencode (commit `bcf23b6`) for useful features and picked six. 0.20.0 has four of them;
  0.21.0 adds the rest with the backend.
  - **Inbox** (`Session._inbox`). Before each next step, and at the start of a request, it adds user-role items.
    - A **steer**: Enter while Peto works goes into `FooterEngine.steers` and shows as "↳ Nhắn thêm". Slash commands
      still wait in `queued` ("↳ Chờ chạy"). The steer is added as `history.STEER_NOTE` + text.
      - If the model was about to stop, the loop runs one more step to read it.
      - Leftover steers become the next request.
    - A **plan-mode note** whenever `ui.mode` changed since the last announcement (`PLAN_ON_NOTE`/`PLAN_OFF_NOTE`).
    - A **job note** (`JOB_NOTE`) for each background job that exited by itself (`Jobs.finished`). A job is not
      reported if Peto stopped it or already saw the exit via `read_command_output`.
    - Notes start with `[Peto Agent]` or `[Tự động]`; `history.recap` and `first_title` skip them.
  - **Plan mode.**
    - Shift+Tab arrives as `Key("backtab")` (Tab with SHIFT through ConPTY). Shift+Tab or `/plan` toggles `ui.mode`.
    - The prompt shows "Lập kế hoạch" in `secondary` (`prompt.frame(accent=)`) plus a footer hint.
    - `Tools.call` refuses `PLAN_BLOCKED` (file changes, browser actions) with `PLAN_REFUSAL`. Commands still ask.
  - **Sessions** (`history` v2): `sessions/<project key>/<id>.json` with `title`; the old single file migrates on
    first read. At most 50 per project, 30 days.
    - `Session.save()` assigns the id. `/new` (`reset`) starts a new id and keeps the old file.
    - `/resume` opens the only session directly, otherwise `ui.choose` (TUI `_list_chooser`). `/resume N` opens one
      directly.
  - **English command names.** `command_catalog.json` items gained `aliases`; `commands.canonical` maps old names and
    the menu suggests new names when old ones are typed. The renames are `/new`, `/exit`, `/remember`, `/browser
    [clear]`, `/thinking`, `/plan`, and `/effort low|medium|high`.
    - `features/agent/guide.py` keyword aliases follow the new names.
    - Backend errors say "Gõ /new (bản cũ: /moi)".
  - **Tests.**
    - `tests/test_inbox.py`, `tests/test_sessions.py`, and new cases in `test_screen.py`.
    - A ConPTY run of real `peto` against a scripted fake server confirmed: a steer reaching step 2, Shift+Tab
      (`\x1b[Z`) blocking an edit, the `/resume` list with two sessions, and a job exit reported in the next step.
  **Features from opencode, 0.21.0 (done 2026-10-12, needs the backend deployed).** New `features` (`question`,
  `patch`, `title`, `steer`, `jobs_notify`, `plan_mode`) are listed in `/me agent_features` and declared by the CLI only
  when listed, as in 0.18. Schema hashes of earlier feature sets are unchanged; `test_agent_tool_features.py` pins them.
  - **Model-named sessions.** After a session's first completed request, `Session._name_conversation` runs a background
    thread that posts `context.purpose = "title"` with `model: "peto"`, `effort: "low"` (1 step): up to 2,000 characters
    of the first user message and 1,000 of the reply (`TITLE_SOURCE_CHARS`). The server treats `title` like `compact`
    (`SPECIAL_PURPOSES`: no tools, `TITLE_PROMPT`, usage purpose `side`, `done` carries the purpose). The CLI keeps the
    first-message title on failure, writes the new title under `_save_lock`, names a session once, and the eval
    harness sets `auto_title = False`. A title arriving after `/new` or `/resume` goes to the old file
    (`history.rename`). The title call goes to xAI even when the session uses OpenAI or Claude; the
    README says so.
  - **`ask_user`** (feature `question`, appended last to keep the cached prefix): 1–3 questions with a ≤12-character
    header, 2–4 options with descriptions and `multiple`. `AGENT_QUESTION_PROMPT` (Vietnamese and English) limits it to
    real user decisions and forbids asking for permissions the CLI already asks. `Tools.ask_user` validates and calls
    `ui.questions`; Esc returns `dismissed` with a note to choose sensibly and say so. It is in `LOOP_EXEMPT` and allowed
    in plan mode. The TUI panel (`_question_chooser`) takes ↑/↓/Enter, digits, Space for multi-select and a "✎ Tự trả
    lời…" row with inline typing (on a multi-select question the typed answer joins the checked options; the pencil is
    `theme.glyphs["write"]`, `>` on old consoles); the classic UI reads numbers, comma lists or free text. `PolicyUI.questions` picks the
    "(nên chọn)" option, else the first, and records a `question` request.
  - **`apply_patch`** (feature `patch`, OpenAI models only: `api._patch_model`). `tool_schemas(features,
    patch_model=True)` puts `apply_patch` in `edit_file`'s slot and drops `write_file`; `delete_file`/`move_file` stay.
    `AGENT_PATCH_PROMPT` is English only, since only OpenAI gets it. `peto_agent/patch.py` ports opencode's
    `util/src/patch.ts` (MIT) with the strict matching approved for `edit_v2`: exact, then trailing spaces, then both
    ends; a hunk must match once unless an `@@` context line anchors it. `Tools.apply_patch` applies `edit_file`'s rules
    per file (read first and unchanged, add only to a missing file, move only to a free destination), computes every
    file before writing, asks once (`Permission("patch")`, per-file diffs) and records checkpoints, so `/undo` reverts
    the whole patch. One failing hunk writes nothing. An update that also moves counts its own changed lines in the
    result, while the request summary counts it like `move_file` (old path deleted, new path created).
  - **Prompts for 0.20.0's features:** `agent_inbox_prompt(features, english=)` explains steer notes, job notes (do not
    poll `read_command_output` just to wait) and plan-mode notes, only for CLIs that declare them.
  - Old command names in server messages now name the new ones ("/effort medium", "Gõ /new (bản cũ: /moi)").
  - In full screen, `TerminalUI.line` (slash-command notices, `/help`) now starts at column PAD + 3, aligned with
    replies and tool rows, keeping each line's own extra indent.
  - **Tests:** `agent-cli/tests/test_patch.py`, `test_question.py`; backend `test_agent_tool_features.py` (pins,
    patch only for OpenAI, prompts) and `test_agent_api.py` (title purpose). A ConPTY run of real `peto` against a
    fake server listing the new features checked the two-question panel (arrows, multi-select plus a typed answer), a
    three-file patch (update, update+move, add) approved once, and `/resume` listing two model-named sessions.
    `test_evals.py` runs a whole task with a fake GPT that asks a question and fixes the bug with `apply_patch`;
    `PolicyUI` records a patch approval with every file it touches. The real Luna run is in the Voice bullet above.
  - **CLI 0.19.1.** Grok cites code as ```` ```21:24:src/main.c ````. `tui/markdown.CITATION` labels such a block
    `src/main.c:21-24` and highlights it by the file extension; before this the label was just "21". The harness
    counts these blocks as `path:line` references.

  **Features from opencode, round two: 0.22.0 (done 2026-10-14, CLI only).** The owner sent opencode 2.0.29 screenshots
  and a video, named `/update`, a `/resume` that brings back the whole conversation and the animation beside "esc
  interrupt", and picked more from opencode's TUI (commit `bcf23b6`): a better session list, `/btw`, `/timeline` and
  `/fork`, `/editor`, the title on top, `/export`. Plan: phase A = 0.22.0 (below, no server change); phase B = 0.23.0
  with the backend (`/btw`, `/editor`, `/export`; see the 0.23.0 bullet below). The owner deployed phase A on 2026-10-14.
  - **Scanner** (`tui/scanner.py`, port of opencode `ui/spinner.ts`, MIT). 8 cells, `■`/`⬝` (`■`/`·` on old consoles),
    forward 8, hold 9, back 7, rest 30 frames of 40 ms; 6-step trail (1, 0.9 brightened 15%, then 0.65^(i−1)), inactive
    cells 0.6 fading to 0.3 during holds. Terminals have no alpha, so `trail_colors` pre-blends with `theme.bg`;
    `primary` in build mode, `secondary` in plan mode. It sits before both busy footer lines ("esc esc hoặc ctrl+c
    dừng", "esc lần nữa…"); the Braille spinner on the status line stays. The full screen waits 40 ms per key poll while
    busy (`SCAN_TICK_MS`), inline keeps 100 ms. As in opencode, the cells are all dark for about half of each 2.2 s
    cycle; the ConPTY run drew 13 distinct frames.
  - **Title bar and tab.** `ScreenEngine._title_rows` adds one fixed row on top once the session has a title (bold title
    on the panel colour, folder name muted on the right); mouse rows are offset by `_head`. `Session._announce_title`
    feeds `ui.set_session_title` on `run_task`, the title thread, `reset`, `resume`; `ui.tab_title(state)` gives
    "Peto · đang làm · <title>".
  - **`/resume` replays the conversation** (`transcript.events` → `TerminalUI.replay`): user and steer panels, replies
    through `TerminalReply`, tool blocks through the live `tool_finished` with a preview rebuilt from the arguments
    (edit snippet with `Diff(numbered=False)`, since results store no line numbers; created files; `patch.parse` chunks;
    command; plan). Thinking and page screenshots were never saved. The classic UI keeps the old recap. `/new`,
    `/resume` and `/fork` clear the screen first (`ScreenEngine.clear`, header redrawn).
  - **Session dialog** (`TerminalUI.choose_session`/`_session_chooser`, after `dialog-session-list.tsx`): fold-based
    search, day groups, Ctrl+R inline rename, Ctrl+D twice to delete (`history.delete`, refused for the open session).
    `Saved` is frozen, so a rename replaces the list item (`dataclasses.replace`); the chooser works on its own copy.
    `history.rename` keeps `saved_at`. `line_editor.translate` now returns `Key("ctrl", letter)` for control characters.
  - **`/timeline` and `/fork`** (`__main__._timeline`/`_fork`): the user's messages (`transcript.is_user`, steers
    marked); Nhảy tới (`ui.jump_to` → `ScreenEngine.jump`, via `_user_entries` keyed by `id(item)` holding the item to
    guard id reuse), Chép, or Tách. A fork saves the old session, opens a new id with the items before the message,
    titles it "<old> (nhánh)" and prefills the message (`ui.prefill`; the classic UI prints it). Files are not reverted.
  - **`/update`** (`updater.py`, after `dialog-update.tsx`): only when `sys.prefix` is the install venv
    (`PETO_AGENT_INSTALL_DIR` or `%LOCALAPPDATA%\PetoAgent\venv`); otherwise it prints the `irm` command. It runs
    `$env:PETO_AGENT_UPDATING='1'; & { irm '<server>/install.ps1' | iex }` through `runner.run` (PowerShell, 600 s,
    Ctrl+C stops the tree) and shows it as a command block. `install.ps1` skips its "Bước tiếp theo" lines when
    `PETO_AGENT_UPDATING` is set (needs the backend deployed; an old server's script still prints them). "Mở lại ngay"
    saves, leaves the full screen, stops jobs and the browser, then `subprocess.call([bin\peto.exe, "--resume", id])`
    and exits with its code. `--resume` is a hidden argument accepting only `history.valid_id` ids.
  - **PowerShell output was losing Vietnamese** (found by the `/update` ConPTY run, true of every `run_command` with
    `shell=powershell` since it existed): Windows PowerShell 5.1 writes to a pipe in the console's legacy code page, so
    "Cài đặt" came back "C?i ?t", lossy. `runner.spawn` now prefixes `POWERSHELL_UTF8` (`[Console]::OutputEncoding` to
    UTF-8 without BOM), except for commands starting with `using`, which must come first. Grant keys and the eval
    policy still see the original command.
  - **Tests:** `test_scanner.py`, `test_transcript.py`, `test_update.py`, new cases in `test_screen.py` (replay, title
    bar, jump, session dialog, prefill), `test_sessions.py` (delete, rename keeps the time, `valid_id`, fork, timeline),
    `test_runner.py` (PowerShell Vietnamese). A ConPTY run installed peto for real with `install.ps1` into a temp
    `PETO_AGENT_INSTALL_DIR` from a fake server serving the real template and wheel, then drove the installed
    `peto.exe`: scanner, title bar, `/timeline` jump, `/fork`, the session dialog (search, Ctrl+D on the open session),
    replay, and `/update` reinstalling and reopening the same conversation in a new process (exit 0), replayed in
    xterm.js. Real Windows Terminal/VS Code still need the owner's look.

  **Phase B: 0.23.0 (done 2026-10-14, needs the backend deployed).**
  - **`/btw`** (after opencode `feature-plugins/prompt/btw.tsx`; Claude Code has the same). Server: feature `btw` in
    `FEATURES`, `"btw"` in `SPECIAL_PURPOSES` (no tools, no web search, usage purpose `side`, normal step cost of the
    model and effort). `_btw_instructions` is `CORE_PROMPT` + `provider_prompt` + `BTW_PROMPT` + time (English for
    every model since 2026-10-15); not the Agent working prompt. CLI:
    `Session.side_question` sends a snapshot (`efficient_input` of the items, pending calls given `PENDING_RESULT`, the
    question last) with the current model at `low`, reads `meta` for the step count, and never touches `items`, the
    session file or the log; `done` must carry `purpose: "btw"` or it reports an old server.
    - **Asking while Peto works is the point**, so the screen engine handles it, not the command loop:
      `FooterEngine.side` (set in `session()` to `__main__._aside`) sees every submitted text under the engine lock and
      claims `/btw` before steers/queued. `TerminalUI.ask_aside` starts a `peto-btw` thread and lists the question
      above the prompt as "⠋ /btw …" (`side_pending`, animated) until the answer arrives. A bare `/btw` keeps "/btw "
      in the prompt with `BTW_HINT`; an old server keeps the text with a notice. The classic UI handles `/btw` in the
      loop (`_btw`, synchronous, printed).
    - **The box** (`TerminalUI._side_box`): Markdown with the panel background, at most 60% of the screen,
      ↑/↓/PgUp/PgDn/Home/End scroll, `c` copies (through the engine's copy hook, so tests never touch the real
      clipboard), Esc/Enter/q close. Secondary-colour bar, unlike permission panels.
    - **Panels now queue:** `FooterEngine.ask` waits until no other panel is open (a permission question and a btw
      answer never overlap), and the 300 ms key guard counts from when the panel actually shows. `Panel.on_interrupt`
      makes Ctrl+C close the btw box instead of stopping Peto, and `ScreenEngine.ask` does not jump to the bottom for
      it. There is no way to cancel a pending btw; exiting peto drops it.
  - **`/editor [text]`** (`external_editor.py`): `VISUAL`, `EDITOR`, `code --wait` inside VS Code's terminal, else
    `notepad.exe` (`vi` elsewhere). The program is resolved first (`shutil.which` or an existing path), because
    `cmd /c` reports an unknown command as exit code 1 like any failure. It runs `<cmd> "<temp .md>"` with
    `shell=True`, reads back with `utf-8-sig`, deletes the file, and returns None for empty or unchanged text.
    `FooterEngine.suspended()` (and `TerminalUI.suspended`) stops the input thread and raw mode, leaves the alternate
    screen, prints "Đang soạn trong …", then restarts and redraws everything; `_suspended` blocks every draw and keeps a
    btw box waiting meanwhile, so nothing paints over a terminal editor. The text goes into the prompt via `ui.prefill`,
    unsent.
  - **`/export`** (`export.py`, from `transcript.events`): header (title, date, model, folder, a note that file contents,
    command output and images are left out), `## Bạn` / `## Peto` sections, steers as their own heading, job notes in
    italics, the compaction summary as a blockquote, and one bullet per tool (`tool_lines`: read, edit with +/−, patch
    files, `$`/`PS>` command → exit code, plan as a checklist, ask_user answers, browser actions, refusals as "— không
    xong: …"). `save` writes `peto-<slug>-<yyyymmdd>.md` at the project root with mode `x`, adding `-2`, `-3`…, never
    overwriting. The other choice copies through `ui.copy` (the classic UI cannot).
  - **Tests:** backend `test_agent_api.py` (btw purpose, persona, English for Luna, step cost), feature set in
    `test_agent_tool_features.py`; CLI `test_btw.py` (snapshot and pending calls against a fake server, old server,
    the text UI, the waiting line and box while busy, Ctrl+C, a bare `/btw`, queuing behind an open chooser,
    scrolling), `test_editor.py` (editor choice, a fake Python editor, failures, the full screen stepping aside and a
    btw box waiting for it), `test_export.py`. A ConPTY run of real `peto` from source against a fake server checked
    `/btw` asked while Peto was thinking (waiting line, then the box, Esc), `/editor` with a fake editor through
    `EDITOR` (prompt prefilled on return) and `/export` writing the file; replayed in xterm.js. The "c" key was not
    pressed there, since ConPTY uses the machine's real clipboard.

  **Mouse, 0.24.0 (done 2026-10-14, CLI only).** The owner asked for opencode's clicking (permission buttons, the
  thinking line, "Jump to latest") and picked everything offered: every chooser, expanding cut blocks, clicking their
  own message, the `/` menu, hover highlighting like opencode, and thinking opening in place.
  - **Targets** (`tui/text.py`): `Target(key, run, hover, look)` stored in the span style as `"act"` by `clickable`;
    `render` ignores it. `key` is stable across rebuilds so hover survives redraws. `run` returns a `Key` to feed the
    engine as if typed (choosers select the row and press Enter/Space/Esc, so clicks share the keyboard path and the
    300 ms panel guard) or None. `hover` moves a chooser's selection (opencode's onMouseMove); `look` is "underline",
    "bg" (`theme.hover`, #2c2c2c dark / #dcdcdc light; `element` was too close to `panel` to see) or "".
  - **Engine.** `Frame.source` and `FooterEngine._footer_source` keep the footer as `Line`s. `ScreenEngine._compose`
    records the drawn line of every screen row in `_hits` (title row None, transcript rows cropped, the overlay, footer
    rows) and paints the hovered target (`_paint` → `hovered`). `WindowsConsole._mouse` now reports button-less moves
    as `Key("mouse", "move")`, once per cell; `_run` redraws only when a key changed something (moves that keep the
    same target return False) and still ticks animations. Press records the target and cell, a drag off the cell turns
    it into a text selection, release on the same target runs it; a double click on a target is a second click, not a
    word copy. The wheel clears the hover.
  - **Where** (`tui/view.py` unless noted): "+ Đã nghĩ" (`TerminalReply._commit_thought`, "−" when open; `/thinking`
    still opens all), "↓ còn N dòng bên dưới" (`_overlay` → `_to_latest`), "Đã xem" groups (one row per read/search when
    open), long diffs (`_cut`: "… còn N dòng · bấm để xem đủ" / "▴ thu gọn"; the inline UI keeps "/diff để xem đủ"),
    command output ("(N dòng trước đó · bấm để xem đủ)"), permission buttons (`_panel(pick=…)`), list, session and
    question choosers (rows; `esc`/`enter` hints), the btw box hints, and `/` suggestions (`prompt._menu_target`: Enter,
    or Tab for `has_options` / the new `takes_text`, from "<" in the catalog usage; Tab now adds the space for those
    too). Expandable blocks keep `{"open", "entry"}` and `_toggle` rebuilds just that entry.
  - **Your message:** `commit_user` builds the panel with a "bg" target only once `link_user_entry` has tied it to a
    conversation item (slash-command echoes stay inert). Idle: `_message_clicked` stores `clicked_message`, marks the
    engine busy and queues "/timeline", whose `_timeline` takes it (`take_clicked`) and opens Chép / Tách hội thoại từ
    đây directly (no Nhảy tới). While Peto works it only copies, with a toast (`ScreenEngine.notify`), since forking must
    wait.
  - **Tests:** `test_mouse.py` (hit testing and hover painting, thinking, a drag that must select, jump, groups, diff
    and output, permission hover and click, list rows and the esc hint, the 300 ms guard, question options and the btw
    box, message click idle/busy and inert echoes, `_timeline` with a clicked item, the `/` menu), the move key in
    `test_screen.py`. A ConPTY run of real `peto` sent SGR mouse sequences (`\x1b[<35;x;yM` moves, `\x1b[<0;x;yM`/`m`
    clicks), located text with a lenient copy of `tests/vt.py` (ConPTY writes the last column), and checked hover on
    the thinking line, a permission button and the message panel, opening thinking, clicking Cho phép (the edit was
    applied), jump to latest, the message menu, and the `/` menu; replayed in xterm.js. The fix of a pre-existing race in
    `test_footer.py` (reading the screen before the redraw) came out of the full run.

  **From opencode's core, 0.25.0 (done 2026-10-15, needs the backend deployed).** The owner asked whether opencode's
  backend/harness (`packages/core/src` at `bcf23b6`: `session/runner/step.ts`, `retry.ts`, `max-steps.ts`,
  `compaction.ts`, `snapshot.ts`, `revert.ts`, `tool-output.ts`, `plugin/agent.ts`) was worth learning from. Matched
  against their own `%LOCALAPPDATA%\PetoAgent\logs` (48 files, 79 requests, 693 tool calls): 88/269 reads cut at 160
  lines (half of them files of ~186 lines, 19 re-read later), 11 edits refused for "read first", 10/68 commands changing
  files that `/undo` cannot see, 4 command outputs losing their middle, 2 manual `/retry`, a 39-step request. They picked
  all eight items; 0.25.0 has six, 0.26.0 (snapshots) and 0.27.0 (explore subagent) follow. New features `read_more`,
  `output_files`, `wrapup`, `user_guide`; the 0.21–0.24 schema and its GPT variant are now pinned too, and the
  Vietnamese instructions of old feature sets stay byte-identical (empty parts are still joined).
  - **Bigger reads** (`read_more`): `read_file` reads up to 1000 lines, cut at a line boundary past 32,000 characters (a
    longer single line is cut with a note). `_READ_V3` replaces the schema in place when `explore_v2` is also declared.
    `prompts/agent.AGENT_PROMPT_READ_MORE` and `english.agent_prompt(plan=, read_more=)` swap the "targeted ranges"
    sentence, checked at import like `AGENT_PROMPT_NO_PLAN`. `loop.cap_result(…, READ_BOUNDED_KEYS)` no longer cuts read
    content at 20,000 characters. Reason: each extra step resends the whole conversation, far more than a few hundred
    lines.
  - **Refusal with content** (CLI only): `Tools._require_read` replaces the "read first" errors of `edit_file`,
    `write_file` (overwriting) and `apply_patch`. An unread or changed file raises `UnreadFile` (error + `current`, the
    `read_file` view centred 40 lines above where `old_text` or the patch's first chunk matches, else from the top); the
    file counts as read. Further edits of it in the same step are refused (`_unread_refused`, reset by `start_step` and by
    an explicit `read_file`). A patch attaches at most two files, writes nothing, and once one file is unread skips every
    other check so another error cannot hide the attached content. The UI shows a yellow notice (`raised="unread"`).
  - **Automatic retry** (`loop._step` → `_attempt`, `RETRY_WAITS` 2/5/10 s, Ctrl+C stops): ApiError 0/502/503/504 before
    any SSE event, or an `error` event with `"retryable": true`. The server sets that only when the step was refunded
    (nothing produced) and the failure is transient: `ProviderError.retryable` in `ai/agent.py` (rate limit, connection,
    5xx, stream cut before `done`, `response.failed`, not completed; Claude already had it) or `queue_full`. A drop after
    text keeps `/retry`. Tests that meant the `/retry` path now use status 408.
  - **Full output** (`output_files`, `outputs.py`): `runner.run(spool=True)` and background jobs write the whole stream to
    `%LOCALAPPDATA%\PetoAgent\outputs\out_<12 hex>.log` (20 MB cap, 7 days, pruned at session start). Kept only when the
    result was cut (run) or a read was cut or lost bytes (job, else deleted at `stop_all`); the result gains `output_id`.
    `read_output(output_id, pattern, start_line, end_line)` is appended last: regex search (40 matches) or 400 lines, no
    permission. `AGENT_OUTPUT_PROMPT` explains it; `run_command`'s schema is unchanged.
  - **Wrap-up turn** (`wrapup`): when an explicit `Session(max_steps=N)` budget is reached, the CLI sends
    `context.purpose = "wrapup"` (since 0.28.4 interactive sessions have no default step ceiling)
    (`Session._wrap_up`); the reply is shown and appended, then the old "gõ làm tiếp" line. Server: normal `_instructions`
    with `extra=WRAPUP_PROMPT` placed before the time block (cache prefix), normal step cost, `agent_step(final=True)`:
    xAI gets `tools=[]` (it rejects `tool_choice` none without tools), OpenAI and Claude keep the tools with `tool_choice`
    none (Claude `{"type": "none"}`, allowed with adaptive thinking), no web search. Claude's behaviour with a real key is
    unchecked.
  - **Shared AGENTS.md** (`user_guide`, `user_guide.py`): `%APPDATA%\PetoAgent\AGENTS.md` (`config.home()`), 32,000
    characters, read every step and sent as `context.user_guidance`; never from the project. The server wraps it with
    `USER_GUIDANCE_PROMPT` before the project guidance (project conventions win, the conversation wins over both), capped
    at 40,000. `/guide` picks the shared file or the project's AGENTS.md and edits it in the `/editor` editor
    (`user_guide.TEMPLATE` for a new shared file); like `/remember`, writes skip the checkpoint and drop the read digest.
  - **Tests:** backend `test_agent_tool_features.py` (pins, read_more, read_output, prompts, byte-identical old
    instructions, user guidance), `test_agent_api.py` (wrapup, mock wrapup, retryable only when refunded),
    `test_models.py` (final turn per service, retryable mapping), `test_claude.py` (tool_choice none); CLI
    `test_fewer_steps.py`, `test_outputs_guide.py`, and updated read-first assertions in five older files.

  **Project snapshots, 0.26.0 (done 2026-10-15, CLI only; ships together with 0.25.0, nothing committed between).**
  After opencode's `snapshot.ts`/`revert.ts`, for the 10/68 file-changing commands `/undo` could not see.
  - **`snapshot.py`:** a hidden git repository per project in `%LOCALAPPDATA%\PetoAgent\snapshots\<key>`, git run with
    `--git-dir` there and `--work-tree` the project, plus `-c` overrides (no autocrlf, quotepath, fsmonitor, hooks,
    gc.auto). Never touches the project's `.git`, never checks out. Works in non-git folders; needs `git` on PATH
    (`shutil.which`), else disabled with one notice. `info/exclude` holds `SKIPPED_DIRS` and `BLOCKED_FILE_PATTERNS`, so
    `.env` and keys are never copied; the project's `.gitignore` applies; files over 2 MB and symlinks are dropped.
    `capture()` = `ls-files --others --modified --deleted --exclude-standard`, `update-index --add --remove`
    (`HASH_TIMEOUT` 120 s, other calls 20 s), `write-tree`; any error disables it for the session. `changed`,
    `contents` (one `cat-file --batch`), `has`. `maintain()` runs `gc --prune=30.days.ago` daily in a thread and
    deletes repositories unused for 30 days. Measured on Peto-Web: first capture 7–10 s, later ones 0.3–0.45 s.
  - **Commands:** `Tools.run_command` captures before and after (also after Ctrl+C) and `_record_command` diffs them:
    changed files go into the checkpoint through `Checkpoint.record_command` (`Change.source` "command"; a file Peto
    edited earlier keeps its first `before`), their read digests are dropped, the result gains `files_changed`
    (≤20, plus `files_changed_total`), the command block shows "đổi N tệp" and `RequestEnd.command_files` adds "lệnh
    đổi N tệp". More than 200 files or 12 MB is not recorded (notice). Background jobs are not covered.
  - **Checkpoint:** binary content allowed for "command"/"restore" entries, `source` and `commands_covered` persisted;
    `/diff` labels "· do lệnh", shows binary sizes, and keeps the old "lệnh terminal" warning only when commands ran
    uncovered.
  - **Restore to a message** (`Session._mark_request` captures at each request start in a thread; tools that change files
    wait for it via `Tools.wait_snapshot`/`CHANGES_FILES`, and `_run` joins it before the final save). Marks are
    `history.fingerprint` (content hash + count of identical earlier items) → tree, saved as `snapshots` in the session
    file and kept through resume and fork. The message menu (`/timeline`, clicking a message) offers "Khôi phục tệp về
    lúc trước tin này"; `/fork` asks "Khôi phục cả tệp về lúc trước tin đó?" (default no). `Session.restore_files` lists
    the files, asks via `ui.choose`, applies through `Checkpoint.undo` on Change(tree, now), then stores the inverse as
    the checkpoint so `/undo` brings back the pre-restore state, and tells Peto with a user note.
  - **Tests:** `test_snapshot.py` (excludes, the project's own git untouched, a command creating/changing/deleting a
    binary file and undo, Peto edit then command, refusal after a user edit, no git, restore and undo of the restore,
    marks through save/resume, the message menu); `conftest.py` sets `PETO_AGENT_NO_SNAPSHOTS` for every other test. A
    ConPTY run of real `peto` checked a Python command creating, changing and deleting files, `/diff`, `/undo`, a
    second request, clicking the first message → restore → `/undo`, with the file states verified at each step.

  **Explore subagent, 0.27.0 (done 2026-10-15, needs the backend deployed; ships with 0.25.0 and 0.26.0).** After
  opencode's `plugin/agent.ts` (`PROMPT_EXPLORE`) and `tool/plugin/subagent.ts`. The owner picked the session's own
  model at low effort.
  - **Server:** feature `subagent` appends `explore(task, depth)` last (`depth` enum quick/medium/thorough, caps 4/8/15
    in `EXPLORE_DEPTHS`) and adds `AGENT_SUBAGENT_PROMPT` (vi/en: when to use it, the subagent's reads are not Peto's,
    write a complete task, every child step costs quota). A step with `context.purpose = "explore"` (only with the
    feature) gets `explore_schemas` (the session's own read_file/list/search/find variants, nothing else) and
    `_explore_instructions`: persona core + `EXPLORE_PROMPT` + explore tool notes + search prompt + project and user
    guidance + time, no Agent working prompt; `context.final` adds `EXPLORE_FINAL_PROMPT` and `agent_step(final=True)`.
    Normal step cost and usage purpose; `done` carries `purpose: "explore"`.
  - **CLI** (`subagent.py`): `Tools.explore` (refused without the feature) calls `Session._explore` → `subagent.run`: its
    own `items` (only the task), its own `Workspace` (separate read digests), a `Tools` limited to the four read tools
    with a `_ChildUI` that turns each call into `ui.explore_progress` lines and collects actions and files read. Steps
    use the session's model, `low` effort (or the model's first supported), and `Session._step_context` plus
    `purpose`/`final`; the last allowed step is final, calls outside the list or after it get an error result. The
    result is `{summary (≤8000), steps, files_read}` (plus `error` "Agent con dừng giữa chừng: …" on a server or network
    failure); `_actions` goes to `meta`. Ctrl+C propagates and stops the request. Logged as `explore`.
  - **UI:** TUI status "… Khám phá · Đọc app.py" while it runs, then a clickable "◇ Khám phá <task> · N bước · đọc K tệp"
    row that opens the actions and the summary (`_explore_lines`); the classic UI prints one dim line per action and a
    closing line. `/export` writes "Khám phá (N bước): task".
  - **Tests:** backend `test_agent_tool_features.py` (schema, read-only subset, prompt), `test_agent_api.py` (explore
    step tools, instructions, final, old CLIs); CLI `test_subagent.py` (separate context and reads, final step and
    refused tools, error result, Ctrl+C, old server) and a `test_mouse.py` case for the block.

  **English Agent instructions (2026-10-15, backend only).** The owner asked for the Agent system prompt in English to
  cut tokens, since Vietnamese costs more tokens per character and the instructions are resent at every step. Luna and
  Claude already used `prompts/english.py`; now Peto/xAI does too, for every purpose (steps, wrapup, explore, /btw,
  title, compaction) and every CLI version. `prompts/agent.py` (the Vietnamese copies) was removed, and the inbox lines
  moved to `english.agent_inbox_prompt` (since 2026-10-18 `english.py` is split, and the English Agent text lives in a
  new `prompts/agent.py`; see the section at the top). Replies still follow the user's language, defaulting to Vietnamese (the
  English core says so), and the core still forbids naming the model behind Peto. Measured on the 0.27 feature set:
  Peto's instructions went from 15,786 characters (3,344 words, 3,109 non-ASCII characters) to 13,231 (2,047 words).
  Before the change, the first step of each eval task cost Peto about 11,450 input tokens and Luna (English, other
  tokenizer) about 10,520. Tool schema descriptions stayed Vietnamese (about 19,800 characters, the larger part of
  each step) until CLI 0.29.1's `english_tools` (see the section at the top); CLI notes stay Vietnamese, such as "[Người dùng nhắn thêm…]"; the prompts quote those markers verbatim. Grok's
  reply voice under the English prompt has not been measured with evals yet.
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
  `peto status` (since 0.22.0 an install.ps1 copy says "Gõ /update" instead; see the 0.22.0 bullet). Bump `version` and `peto_agent.__version__` together whenever the CLI changes (`test_agent_install.py`
  checks they match), or installed copies are never told to update. `/usage` shows today's steps and tokens, the open
  conversation's size and the effort.
- **One-line install** (`irm https://<site>/install.ps1 | iex`). `features/agent/install.py` serves `GET /install.ps1`, which is
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
  `build_agent_guide` goes right after the base prompt on chat and Companion turns whose recent user messages mention
  Agent, CLI or Peto (every model; since 2026-10-18 no turn gets it unconditionally), before the per-user blocks. Its install command comes from `agent_install.install_command(request)`, and it falls back to a
  `<địa chỉ Peto>` placeholder when the origin is not https. Never hardcode the site's domain in `prompts/`: it would
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

### Peto Docs (`/docs/`)

Public Vietnamese guides, no sign-in. `main.tsx` mounts `Docs.tsx` instead of the app for `/docs` and `/docs/*`. The
backend serves the same `index.html` there with the article's title and description (`core/static_files.py`), and
`/api/docs` returns the articles (`features/docs/api.py`; content in `backend/docs_content/articles.json`, see its README).
Since 2026-09-29 every `/docs` page also carries the `og.png` link preview, through the same `with_preview` as the home
page (the bot avatar when no public https origin is known).

**Peto answers from the docs.** `_build_system_prompt` appends `docs_api.context(...)` of the last 3 user messages on every
Chat and Companion turn (not the Agent CLI).
- It attaches at most 2 articles, whole, with their `/docs/<slug>/` links. It never copies the user's text.
- An article counts only when the text contains its whole title, or one of its keywords as a whole phrase (unaccented,
  whole words). A one-word keyword counts only if it starts with `/` or is in `DISTINCT_WORDS`; other single words only
  serve the docs site's search box. Longer matches rank higher.
- Before 2026-09-29 a message needed "Peto", "Agent"… to get any article, and single syllables of the body picked it
  ("nói" pulled "Giọng nói"). The owner approved the change.
- Keywords live in `articles.json` (the generated pages set theirs in `pages()`); `docs_content/README.md` says how to
  write them. `tests/test_docs_api.py` pins questions that must find their article and everyday questions (literature,
  physics, code) that must find none.

- **Text for readers without JavaScript** (2026-10-06). Peto's own web search found the docs pages empty, since React
  draws the article. `core/static_files.py` now adds `features/docs/snapshot.noscript` before `</body>`: the article
  as escaped HTML (a small Markdown subset; links only to `/…` or https) plus the list of all articles, inside
  `<noscript>`, so browsers ignore it. Article pages also link their Markdown (`/api/docs/<slug>.md`). There is no
  `robots.txt` or sitemap on purpose: the owner does not want the site promoted to search engines yet.
- **FastAPI's own API docs are off** (`docs_url`, `redoc_url` and `openapi_url` are `None` in `main.py`). Its Swagger page
  answered `/docs` without the trailing slash, so only `/docs/` reached the guide (reported 2026-09-28).
  `test_static_files.py` checks both spellings on the real app.
- **Design.** On 2026-09-28 the owner picked "Bàn làm việc" from three live variants (the repo's `prototype` skill), and
  asked for the look of AIRI's docs on top (airi.moeru.ai/docs; source in `moeru-ai/airi`, `docs/.vitepress`).
  - **Header.** Transparent at the top of an article; once scrolled, the background at 90% plus an 8 px blur, over
    500 ms, as in AIRI's `Layout.vue`. The home page keeps it frosted. The group tab bar below does the same at 80%.
  - **Home** (`DocsHome.tsx`). Peto's art with a pink and a violet silhouette behind it (the same image as a CSS mask),
    plus a pattern tile (`docs-assets/pattern.svg`, a mask tinted by CSS) that drifts diagonally. The text and the three
    layers follow the mouse with the offsets of AIRI's `ParallaxCover.vue`. CSS transitions (1.2 s, outSine) stand in
    for anime.js: each move starts from where the layer is.
  - **Character size** (2026-09-29, the owner asked for it "bigger and wider, like AIRI"). AIRI's cover is landscape;
    Peto's is portrait, so growing it only pushes the face down.
    - The art sits in `.docs-stage`, the space left under the buttons, which is a size container. Its top (hair) tucks
      behind the glass buttons as in AIRI: 9% of its width, at most 80 px.
    - Its width follows the screen (58vw) but shrinks to keep the chin 40 px above the bottom (`338cqh - 135px` and
      `259cqh + 104px`). There is **no px cap**, so like AIRI the character keeps its on-screen size at any browser zoom.
      A 1000 px cap made it shrink at 25% zoom (the owner caught it).
    - `.docs-cover` must keep the image's aspect ratio (`aspect-ratio`, `align-self: flex-start`). The silhouettes are
      `contain` masks sized to that box. A box stretched to the stage's height drew them off the character, again seen
      at 25% zoom.
    - Desktop screens under 780 px high get a tighter title block.
    - The glass buttons dim the art behind them (`--docs-glass-filter`, `brightness(0.72)`), and the slogan has a halo,
      so text over the hair stays readable.
    - Check zoom levels with headless Edge: CSS viewport = physical size / (Windows scale × zoom), and the device scale
      factor = Windows scale × zoom.
  - **Reader** (`DocsReader.tsx`). Group tabs, the group's articles, the article, then the outline (scrollspy) and
    community links. A violet-pink glow sits at the top (`.docs-glow`, gradients, no image). Phones get a "Danh mục"
    drawer (`<dialog>`).
  - **Search** is a combobox in the header (Ctrl K). It ignores diacritics and opens the matching `##` section.
- **Motion.** Once pressed, the header switch decides (`peto-docs-motion`). Until then the docs follow Peto's "Nhân vật
  cử động" (`peto-character-motion`; same origin, so the app setting carries over). Its default ("Theo cài đặt chung")
  follows the web's Chuyển động setting (`data-motion`, set by `index.html` on /docs too). That default is "Mượt", so
  the docs animate even on the owner's Windows with Animation effects off. Before 2026-10-13 it followed
  `prefers-reduced-motion`. Everything that moves sits under `.docs-motion`; without it only opacity fades remain.
- **Assets.** `peto-hero.webp` (263 KB) and `logo.webp` (7 KB) replaced 2.2 MB of PNGs on 2026-09-28. They were made
  with Pillow from the originals, which stay in git history (commit 2ffde96).
- **Names.** Never add a `docs.ts`: Windows resolves `./Docs` to it before `Docs.tsx` (the `LocalVoice` problem above).
  Shared code lives in `docsShared.tsx`.
- **CSS resets sit inside `:where(.docs)`**, so any component class beats them. A plain `.docs a` reset once hid the
  "Mở Peto" label and the track of a switch that is off.
- **Checking it.** A hidden browser pane draws nothing. Use headless Edge with a temporary profile, and emulate
  `prefers-reduced-motion: no-preference`. A capture right after opening something can catch the first frame of its
  fade: a see-through search panel on 2026-09-28 was only that.
- **Tests:** `frontend/tests/Docs.test.tsx`, `backend/tests/test_docs_api.py`, `test_static_files.py`.

## Frontend conventions

- **Visual details live in [DESIGN.md](DESIGN.md)** (English for agents; written 2026-10-11 from the existing CSS):
  colour tokens and the few allowed hard-coded colours, type scale, radii, control heights, breakpoints,
  press/focus/hover/motion rules, the two menu families, select and dialog rules, Vietnamese UI copy (old-style tone
  marks such as xóa, hủy; `…`) and a pre-ship checklist. Read it before frontend work; when code deliberately departs
  from it, update it in the same commit. The same day the owner approved a cleanup of its listed inconsistencies:
  - Action menus (account, conversation/project, avatar, diagram download) share `.popup-menu` in
    `shared/ui/menu.css` on the `--menu-*` tokens. Conversation/project menus gained a separator and a trash icon on
    the delete item, which uses `--danger` instead of `#ef7777`.
  - Appearance-only `:hover` rules moved into `@media (hover: hover) and (pointer: fine)`, so taps no longer leave
    rows highlighted on phones; reveal-on-hover rules keep their focus and touch fallbacks.
  - `button:disabled` moved to `base.css`; unused `.settings-select` and `.conv-delete` CSS was removed.
  - A second pass the same day followed the owner's Grok screenshots:
    - Button hints use the shared `TooltipLayer` (`data-tip`, `data-tip-kbd`, `data-tip-side`) instead of native
      `title`.
    - Ctrl+K opens history search.
    - Hover fills the background (`--panel-3` on `--panel-2` buttons) instead of flashing the border.
    - Bordered inputs share `.text-field`; the archive search was drawn black with the browser focus ring.
    - Every native `<select>` became `Dropdown` (new `ariaLabel`/`className` props, `compact` variant).
    - The Micro row's long note was removed.
- **Stale-response guarding.** Async loads use a monotonically increasing `useRef` counter
  (`loadVersion`, `listVersion`, `authVersion`) plus an `AbortController`; results are
  discarded unless the version still matches. Follow this pattern for any new fetch — fast
  conversation switching is a tested scenario.
- **Offline notice.** `useReplyRecovery` shows "Bạn đang ngoại tuyến" from `navigator.onLine`, which Chrome on Android
  can leave false while the network works (the owner's phone, 2026-10-06, even after F5). While it says offline, the
  hook fetches `/api/auth/me` at once and every 10 s, and any response clears the notice. Playwright still answers
  mocked routes under `setOffline`, so `recovery.spec.ts` aborts that route while offline.
- **Draft preservation.** The composer keeps text and files until the server acknowledges
  the message (the `meta` event). Stop, error and disconnect all keep the draft.
- Modals are native `<dialog>` with `showModal()`; `tests/setup.ts` polyfills those methods
  for jsdom.
- An empty chat puts greeting + composer together mid-screen on desktop
  (`.chat.empty-state`); phones keep the composer docked. Only the **first send** slides
  the composer down (FLIP via `element.animate` in `App.tsx`); opening a conversation or
  starting a new one switches instantly on purpose — those are frequent navigation.
- Code blocks only colour the grammars registered in `markdownCode.ts` (with their aliases), and `CODE_LABELS` in
  `features/chat/ChatMessage.tsx` holds the display names. Anything else renders as plain text under an uppercased tag, so a new language
  needs a grammar import **and** a label. Each grammar costs bundle size; add ones Peto actually answers with.
  `markdownCode.ts` walks the tree with lowlight's core itself instead of using `rehype-highlight`, because that
  package always imports lowlight's `common` set, even when given `languages`. The build carried 63 grammars instead
  of 26 until 2026-09-27. A ```mermaid block never reaches `CodeBlock`: `ChatMessage`'s `pre` turns it into a
  `DiagramCard` (see "Diagrams in chat").
- Every finished assistant message has a "Sao chép" button under it (`MessageCopy`, layout A picked by the owner from
  mockups on 2026-09-21: always visible, since phones cannot hover). It copies the **raw Markdown**, not the rendered
  text, so a render problem can be diagnosed from what the model actually wrote. It is hidden while that message is
  still streaming. Code blocks keep their own button; both share `useCopy`. Their accessible names differ ("Sao chép"
  vs "Sao chép câu trả lời"), so tests match the code button's name exactly.
- Math renders with `remark-math` + `rehype-katex` (`trust: false`, `strict: "ignore"`, in `markdownMath.ts`) after
  `mathMarkdown.normalizeMath` turns `\(…\)` / `\[…\]` into dollar delimiters, skipping code. It also runs
  `tildeNegation`: in LaTeX `~` is a non-breaking space, so a model writing negation as `~p` (common in discrete-math
  textbooks) rendered as " p" and a correct answer looked wrong (reported 2026-09-21). Only a `~` in operand position
  (start of the formula, after an opening bracket, a logic operator or another negation) becomes `{\sim}`; `a~b` and
  `\text{…}~x` stay spaces. It scans by hand instead of using lookbehind so older Safari can parse the bundle. The chat
  prompt also asks for `\lnot` or `\overline{…}`.
- Per-user preferences (effort, theme, imagine quality/resolution/ratio/count, voice on/off, source, voices, fallback
  and the user's own TTS/STT keys, hearing source/mic/language/sensitivity/auto-send, Companion mute and web search,
  character motion and view, web motion `peto-motion`) live in
  `localStorage` behind try/catch helpers. In-flight Imagine state lives in component state,
  so it survives switching tabs but not a page reload.
- Frontend code is grouped under `src/app`, `src/features` and `src/shared`; see `frontend/README.md` for ownership,
  CSS order and import rules. `app/App.tsx` owns chat state and the app shell; `app/Sidebar.tsx`, `app/LoginScreen.tsx`
  and `features/chat/ChatMessage.tsx` own their presentation. `Imagine.tsx` and `Companion.tsx` are mounted alongside
  it and receive an `active` prop rather than being unmounted — that is what keeps a running generation
  alive when the user switches back to Chat.
- Settings → "Giao diện" contains the theme selector and Chuyển động. Since 2026-10-13 the shared Settings dialog has no Companion
  group: character motion, voice, hearing, web search, Beat Sync, scenes and diagnostics are on `/companion/settings/`
  (character motion on its Nhân vật page). Saved selections and motion values are unchanged.
- Settings → "Kết nối" manages per-owner GitHub App connections (`features/connectors/`, `storage/connectors.py`).
  Configure the five `PETO_GITHUB_*` / `PETO_CONNECTOR_SECRET` variables described in
  `backend/features/connectors/README.md`; no live connection exists until that setup and user consent are complete.
  Tokens/refresh tokens and PKCE verifiers are encrypted with a separate persistent secret; OAuth state is single-use,
  expires in ten minutes, and is bound to both owner and Peto session. Disconnect removes local credentials and pending
  consent, not the remote app installation or existing chat excerpts. Never pass tokens to the frontend/model or log them.
  Only chat receives request-scoped, read-only GitHub tools (repo listing/files and Actions runs/jobs/logs); title and
  Companion calls do not. Progress uses `connector_lookup` SSE, and sources use the existing source cards. Remote content
  is untrusted data, result sizes are bounded, and log download redirects never receive the GitHub Authorization header.
  The initial catalog contains GitHub only; Google Drive and custom MCP are not implemented.
- **What the first load carries.** On 2026-09-27 the owner picked "make the page load faster, especially on phones".
  The entry chunk (then 1.1 MB, 340 KB gzipped) was cut to what the chat screen needs:
  - **Separate chunks.** The chat entry is about 290 KB, plus React at about 190 KB. Everything else loads in its own
    chunk:
    - Imagine, Companion, and the Settings sections (Profile, character motion, Giọng nói, Peto Agent) load on first
      open, through `preloadable.tsx`.
    - Math (`markdownMath.ts`, KaTeX with its CSS) and code colouring (`markdownCode.ts`) load only once a message has
      `$` or a ```/~~~ fence (`markdownExtras.useMarkdownPlugins`). Until then that message shows plain text, and only
      messages that need the chunk re-render when it arrives.
    - Mermaid loads only when a reply has a ```mermaid block, and the diagram panel on its first open.
    - Keep every `import()` in its own arrow function (`loaders` in `markdownExtras.ts`). With both imports in one
      conditional expression, the build preloaded only one branch's dependencies, and KaTeX's CSS never loaded. The
      hidden MathML then showed as duplicated text (caught in a real-browser check on 2026-09-27; jsdom applies no CSS,
      so the tests cannot see it).
  - **Warming.** Hovering or focusing a nav button warms its chunk. Four seconds after sign-in, while idle, all three
    views are warmed, except with Save-Data or 2G. `preloadable` renders a warmed component directly, because
    `React.lazy` suspends on first render even for a loaded module, and React then holds the fallback for about 300 ms.
    Each instance keeps whichever way it first rendered, so the element type never switches mid-life and state
    survives.
  - **LazyBoundary.** It wraps every lazy part, so a chunk that fails to load shows "Tải lại trang" in that spot
    instead of blanking the whole app. This happens when a deploy has removed the old hashed files, since the build
    empties `dist`.
  - **Where these live.** Settings sections render on their first visit (`SettingsDialog` keeps the visited set), each
    in its own `Suspense`, so "Giao diện" never waits for the voice chunk. Keep the icons the sidebar needs in
    `app/navigationIcons.tsx`, independent of lazy feature modules.
  - **React chunk.** `vite.config.ts` puts React in its own chunk (`codeSplitting.groups`), so a deploy changes only
    the app chunk's hash and returning visitors keep React cached. Never widen that group to all of `node_modules`,
    or KaTeX, highlight.js and three.js would be pulled into the first load.
  - **Branded loading.** `shared/ui/LoadingIndicator.tsx` uses the existing `/docs-assets/logo.webp`, gentle logo motion
    and an indeterminate rose bar. Its stylesheet loads with the main entry so the first lazy fallback and auth wait
    share the same full-screen treatment; the logo is preloaded in `index.html`. Panel/icon variants cover conversation,
    view, settings and image waits. Saved light/dark themes are respected. At the owner's request, loading animations
    remain active even with reduced motion enabled, without delaying readiness or fabricating percentage progress.
    The screen caption is "Loading". Companion keeps this screen until its saved character selection and history
    finish loading and the Live2D/VRM renderer has drawn the first frame. The stage remains measurable underneath;
    the stage/chat reveal together, including re-entry and character changes. Model errors release the loading screen
    to the existing retry UI; a retry reports loading again. Renderer callbacks are ignored after disposal.
    Imagine likewise keeps the full-screen loading through its module and initial library request, without an
    intermediate gallery loader/composer frame. Library failure reveals the existing retry UI; retries retain drafts.
    Its dock is measured in a layout effect after loading and when the view becomes active. Docs article/search
    loading text remains unchanged; only the initial Docs module uses the shared splash screen.
  - **Auth preload.** `index.html` preloads `/api/auth/me` (`as="fetch" crossorigin`), and `getAuthState`'s plain
    `fetch` reuses it. This was checked in Chromium: one request, initiator `link`, no console warning.
  - **Measured.** Cold load on an emulated mid-range phone (Lighthouse's slow 4G, 4× CPU, five runs) went from
    2.63 s to 1.36 s until the composer appears. A first open of Imagine, Companion or Settings takes about 45 ms once
    warmed, and about 0.33 s before that.
  - **Tests.** `tests/lazyParts.ts` preloads the lazy modules in `beforeAll`, so their first transform does not land
    inside a test's timeout. Tests look for lazily rendered content with `findBy…`. `vitest.config.ts` raises
    `testTimeout` to 15 s, and `tests/setup.ts` raises testing-library's `asyncUtilTimeout` to 3 s: under a fully
    parallel run, a few heavy tests passed 5 s without being wrong.
- The composer is `Composer.tsx`, presentational only: draft text, the file list and the send
  flow stay in `App.tsx` because they hang off the draft-preservation rule; just the drag
  state is local to it. `files.tsx` holds what the composer and the message bubbles share
  (`DraftFile`, `formatSize`, `FileGlyph`) so `Composer.tsx` never imports from `App.tsx`
  and no import cycle can form.
- `MessageAttachments.tsx` presents sent Chat attachments above and outside the user text bubble. Image thumbnails
  have reserved square dimensions and wrap within the message width; document cards stack vertically with a file
  icon, full accessible filename, type, size and download link. Ordinary successfully read files have no
  "Đã đọc chữ" confirmation line; partial/failed reading and OCR retain their expandable notices. The
  `chat-user-message` class applies only to user messages with attachments, preserving text-only and Companion
  bubble geometry. This presentation is shared by optimistic messages, server receipts and restored history;
  upload limits, the composer and the payload are unchanged. `MessageAttachments.test.tsx` and the mocked
  `browser-tests/chat-attachments.spec.ts` cover mixed attachments, long filenames, maximum file count, receipt
  layout stability, editing, refresh, themes and desktop/mobile layout without paid API calls.
- Clicking a Chat image opens `ChatImageViewer.tsx`, a native modal over the current chat, without changing the URL
  or browser history. Close/Escape restores the trigger's focus without scrolling. The viewer provides original
  image downloads, fit-to-window and 25–800% zoom presets, wheel zoom, mouse drag, two-pointer pinch/pan, and
  a compact percentage-only `ImageZoomMenu.tsx` using the Chat menu styles. It has no visible gesture hints or
  native select; fit is a separate menu item. Escape dismisses the menu before the viewer, with keyboard focus
  feedback only when using the keyboard, and the popup stays scrollable in mobile landscape. The viewer also has
  previous/next controls for images in that message. `imageView.ts` keeps the point under the pointer/pinch center
  anchored and bounds panning; transforms have no transitions so gestures track directly. Pointer ownership is
  limited to the viewer stage; browser zoom remains available elsewhere. Opening a preview during upload keeps
  the modal and zoom when metadata replaces the temporary image URL. Unit tests and the mocked browser suite
  `chat-image-viewer.spec.ts` cover geometry, focus, downloads, unchanged history/drafts/scroll, image failures and
  Chromium touch input; this does not substitute for testing touch feel on physical Android/iOS hardware.
- The desktop sidebar has an unobtrusive right-edge resize separator (`useSidebarResize.ts`). Dragging tracks the
  pointer without a width transition from 64px to 420px, fades labels with the dragged width, and leaves 360px
  for the main view. Release at/below 128px commits the existing collapsed state; otherwise it settles to a
  220–420px expanded width. Collapsing preserves `peto-sidebar-width` for button expansion; dragging out from
  the rail also works. Preferences are saved only on release. Arrow keys/Home/End resize/collapse it;
  double-click restores 260px. Mobile keeps its existing fixed drawer size.
  Chat/Imagine scroll containers extend 6px toward the edge while preserving content padding, leaving a gap
  between the native scrollbar and the separator. Resizing does not touch chat state, drafts, routes or history.

## Invariants — do not break these

- **Never** point `PETO_WEB_DB` or `PETO_XAI_TOKEN_PATH` at the Discord bot's files
  (`bot_memory.db`, `.xai_tokens.json`). Separate database, separate tokens, no shared files
  with the bot's production data.
- `prompts/` must not contain real names or Discord IDs of members — `tests/test_persona.py`
  asserts this. Personal context is loaded per account at runtime, not baked into the prompt.
- Peto on the web is an AI assistant, by the owner's decision. The Discord bot's roleplay persona (age/identity,
  "don't always comply", insult-back, NSFW or pet roleplay, `*action*` narration) is not in any web prompt since
  roleplay mode was removed on 2026-10-18. Never add it to the Chat, Agent or Companion prompts;
  `tests/test_persona.py` checks them.
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

`backend/evals/README.md` documents Peto Brain Benchmark v1 (28 synthetic Chat/Companion cases, 34 turns; two roleplay
cases left with the mode on 2026-10-18).
Run `python -m evals` from backend. Default mock ignores dotenv/credentials; live requires explicit `--mode live
--allow-paid`, uses bounded requests/tokens and disables SDK retries/tools. It reuses prompt composition, providers
and Companion filters with fake account/memory reads, never initializes the real database or modifies production
prompts/model defaults. Tests in `tests/test_brain_evals.py` use only fixtures and mocked HTTP. Mock results are
harness checks, not model-quality measurements. Results and blind human grading live in gitignored `benchmark-output/`.
Agent continues to use its existing CLI eval suite; do not silently run paid benchmarks during tests or CI.

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

- `DESIGN.md` — frontend visual and copy conventions (see "Frontend conventions").
- `README.md` — deliberately short (rewritten 2026-09-30 at the owner's request, from 674 lines): what the project is,
  how to run, configure, test and deploy it, and links. Do not grow it back into a manual: behaviour belongs in this
  file and in `/docs/`.
- `DEPLOY.md` — VPS deployment, systemd unit in `deploy/`, Cloudflare Tunnel, troubleshooting.
- `voice-worker/README.md` — connecting the Windows voice machine to the VPS, and the relay's
  operating limits.
- `PETO_WEB_HANDOFF.md` — original project brief. Historical context, **not** a description
  of the current code; prefer this file and the source when they disagree.
