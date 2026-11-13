# Web Chat notes

Scope: Web Chat: providers and models, the `POST /api/chat` lifecycle, work log, tools, web search, sources and citations, long context, recovery, prompts and Chat UX.

Moved out of `CLAUDE.md` on 2026-11-12 (G0.2). Write new notes for this area here, not in `CLAUDE.md`. Current behaviour comes first, then the dated log, newest first.

# Current behavior

### Chat modules, projects and archival (from "Backend layout", 2026-10-01)

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

### Chat routes and drafts (from "Two run modes")

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
Since 2026-11-12 Chat turns follow "Web Chat stable prefix (G1.1)" in the dated log instead: no clock or snapshot in
system, a history breakpoint even in one-round turns, and Haiku thinking replayed while its prefix is unchanged.
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
Since 2026-11-12 (G1.1) a Chat turn freezes this time block once per turn into the runtime block after the user's
message instead of the system prompt; Companion and other turns still append it to the system prompt.

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

### Model instructions in English (from "Language convention")

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

### Web Chat analysis presentation (from "Language convention")

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

### Peto Brain Benchmark (from "Testing")

`backend/evals/README.md` documents Peto Brain Benchmark v1 (28 synthetic Chat/Companion cases, 34 turns; two roleplay
cases left with the mode on 2026-10-18).
Run `python -m evals` from backend. Default mock ignores dotenv/credentials; live requires explicit `--mode live
--allow-paid`, uses bounded requests/tokens and disables SDK retries/tools. It reuses prompt composition, providers
and Companion filters with fake account/memory reads, never initializes the real database or modifies production
prompts/model defaults. Tests in `tests/test_brain_evals.py` use only fixtures and mocked HTTP. Mock results are
harness checks, not model-quality measurements. Results and blind human grading live in gitignored `benchmark-output/`.
Agent continues to use its existing CLI eval suite; do not silently run paid benchmarks during tests or CI.

`--suite chat-core` (G2.1) runs the personality, reassess, log and stage-4 datasets together (13 cases, 16 turns per
model) on Peto, Luna and Haiku with each model's Chat output cap instead of 1024 tokens, prints a request/token (and,
with `--rates`, USD) ceiling before running, and adds per-model time-to-first-text and cache columns. Details in
`backend/evals/README.md`, "Bộ `chat-core`".

# Dated log (newest first)

## Intentional empty replies are not errors (2026-11-13, committed on branch `silent-reply`, not deployed)

The owner sent "intelligent test: do not reply"; sometimes Chat showed "Peto chưa trả lời được lượt này". Reproduced on
the real app: Grok finished normally (`complete=True`, 253 output tokens, all reasoning) and wrote no text, so the turn
ended `outcome=empty`. ChatGPT shows such a reply as blank; Claude.ai always writes at least ".". The owner chose a
middle way: a Chat turn whose provider finished without raising but wrote nothing is complete, and the reply shows a
muted line "Peto không viết gì cho lượt này." (`.message-silent`), with regenerate still available.
- `service.py`: in Chat mode an empty visible reply after a normal finish sets `complete = silent = True`;
  `chat_turns.persist(..., allow_empty=True)` keeps it `complete` instead of turning empty into `error`. Real failures
  (provider errors, timeouts, stops, incomplete responses) raise before this point and are unchanged. Companion is
  unchanged: an empty or notes-only reply is still "not answered".
- `history._to_chat_messages` drops assistant rows that are empty with no attachments, artifacts or sources, so no
  service receives an empty text block (Anthropic rejects those); the history shows two user messages in a row.
- No prompt change, so no cache reset.
- Tests: `tests/test_silent_reply.py` (empty normal reply completes and is left out of the next turn's history;
  Companion still errors; a provider error is still an error), `frontend/tests/silentReply.test.tsx`.
- Real-app check after deploying `35e24ac` (Grok, three tries): twice Grok wrote a short English line narrating its
  decision ("The user asked me not to reply. I will respect that."), once it wrote nothing: no error any more, but the
  muted line only appeared after a reload. Cause: `App.tsx` treated a finished reply with no text as browser-only
  (`local`), so `ChatMessage` did not consider it complete. Fix (branch `silent-reply-live`): a completed reply that has a
  server message id counts as stored even when empty; `App.test.tsx` covers it (fails without the fix, checked).

## Real-app check of G1.2/G1.3, and turns no longer wait for the summary lock (G1.3b) (2026-11-13, committed on branch `g1.3b-no-lock-wait`, not deployed)

Checked on the real app (`5afb4af`, Grok, low effort, web off) with a conversation of ~9,400-character messages:
- Turns 1–7 read 78–89% from the cache. Turn 8 crossed the 64,000-token budget (estimated 50,745 the turn before):
  the window cut once (real input 40,212 → 24,620, `chat_windows.start_id` saved) and that turn read 5% because the
  history reader tool joined `tools` when older messages became hidden. Turns 9–11 kept the same cut and fingerprint
  and read 81%, 84%, 86%.
- G1.3: every turn's first text came after 2.8–4.1 s, including the cut turn; the summary ran after the reply (11.8–13.1 s
  each, one 16,000-character batch per turn) and its cursor reached the cut after two turns.
- Found: the per-conversation lock was shared, so a turn sent right after a reply waited for that reply's background
  summary (`prepare_ms` 1,876 instead of ~150). Fix: the Chat turn (`summarize_now=False`) no longer takes the lock, since
  it only reads the saved summary; only summary runs take it. `compact` runs `prepare(..., save_window=False)`: it computes
  the cut the same way but never saves it, so the turn is the only writer of `chat_windows` and the two cannot overwrite
  each other; the next turn (one more message) cuts at the same place or later, so the summary cursor stays before it.
- Tests (`test_chat_window.py`): a turn completes while another task holds the conversation lock (fails with the old
  locking, checked); a background summary never moves the window and stays before the next turn's cut.

## Chat summary after the reply (G1.3) (2026-11-13, committed on branch `g1.3-background-summary`, not deployed)

Audit package G1.3. Before it, `context.prepare` called the summary model inside the turn, before the first text, when
older messages had piled up; a long conversation could wait up to `PETO_CHAT_SUMMARY_TIMEOUT_SECONDS` (20) first.
- The chat service now calls `prepare(..., summarize_now=False)`: the turn uses the summary already saved, and the part
  not yet summarized is reported as unrepresented in the envelope, as it already was after a failed summary.
  `Prepared.summary_due` says a summary would have run.
- After a completed turn, the response's background task (with titles and memory) calls `context.compact`, which reloads
  the latest messages and runs the same `prepare` with the summary (same per-conversation lock, same CAS save). It never
  raises. Stopped or failed turns run no summary. Direct callers of `prepare` keep the old default (`summarize_now=True`).
- With G1.2 the cut moves rarely, so this runs rarely; the turn that moves the cut answers without the newest summary
  and the next turn has it.
- Tests (`test_chat_context.py`): no summary before the first reply text and exactly one after (fails with the old
  in-turn call, checked); a stopped turn runs no summary before or after and keeps the cursor (replaces the old "stop
  during compaction" test, since the turn no longer compacts); `compact` never raises. The CAS, cursor, failure and
  timeout tests are unchanged and pass.

## Budget-based history window with a kept cut (G1.2) (2026-11-13, committed on branch `g1.2-budget-window`, not deployed)

Audit package G1.2. Before it, Chat sent the 20 most recent messages verbatim (`PETO_MAX_HISTORY`), so every turn past
20 messages pushed the oldest one out and the request prefix changed on every turn: no long conversation could read the
prompt cache, and only 10 exchanges were ever sent verbatim while the budget allows 64,000 tokens.
- Chat now loads up to `PETO_CHAT_MAX_HISTORY` messages (default 200, 20–1000; Companion keeps `PETO_MAX_HISTORY` = 20,
  and the Companion summary window called after Chat turns still gets 20). `context._window` sends every message from the
  saved cut (`chat_windows.start_id`, one row per conversation, owner-scoped, cascades with the conversation) if it fits
  the budget (`policy(model)['input']` minus the existing reserve) and the cap.
- When either is exceeded it cuts the front in one block, at the start of a user message, to at most half of the budget
  left for history and half the cap (binary search over user-message starts), and saves the new cut. Later turns keep it,
  so the earlier request stays a prefix, until the next overflow. The first time the cap is reached without a cut it saves
  the current first message as the cut, so the window does not slide with "the newest N".
- A saved cut newer than the latest message (after a retry or a branch shortened the conversation) is ignored. The rolling
  summary, the anchor, the small-gap expansion (fewer than `MIN_BATCH` messages kept verbatim instead of summarized) and
  the unrepresented counts work as before on the new boundary; the summary now runs only when the cut moves.
- Tests: `tests/test_chat_window.py` (60 short messages all sent with no summary; an over-budget conversation cuts once and
  keeps the same cut, with each turn's history a prefix of the next, for five turns; the message cap cuts to half and
  keeps it; a stale cut is ignored; owner scope). `test_chat_context.py` and the envelope test in
  `test_chat_prefix_stability.py` now shrink `CHAT_MAX_HISTORY`. Backend: 2,133 passed, 1 skipped.
- Cost: conversations of 21–200 short messages now send all of them (was 20), mostly from the cache after G1.1.
  The summary still runs before the reply when the cut moves (moved after the reply by G1.3, same day).

## Grok replays its runtime blocks (G1.1c) (2026-11-13, committed on branch `g1.1c-grok-runtime-replay`, not deployed)

Real-app check of G1.1b on 2026-11-13: Haiku and Luna read 87–93% of each later turn from the cache with a stable
fingerprint, but Grok read exactly 1,152 tokens on every turn, also with web search off, while Peto Agent on Grok reads
about 83%. Probed with real xAI requests from the VPS (the owner allowed xAI usage): sending the app's exact request
twice read about 5,900 tokens 4/4 times, so no parameter is at fault, and 1,152 is xAI's own shared preamble. What
breaks it: Grok reuses the cache only when the whole previous request is a prefix of the next one. The runtime block
was a part of the current user message (xAI has no documented trailing system item, see G1.1) and was gone from that
message in the next turn's history: 3/3 trials read 1,152. Keeping the block verbatim in the history read about 6,000
in 8/9 trials. OpenAI and Anthropic match partial prefixes, so they were not affected.
- `messages.runtime` (TEXT, added at startup, written only by the server) holds the fenced runtime block that `ai/xai.py`
  appended to that user message. `_place_runtime(first=True)` records it in `RequestContext.sent`; the chat service saves
  it after the turn (`set_message_runtime`, owner-scoped, overwritten when the same message is sent again).
- For Grok Chat turns the service loads the blocks (`message_runtimes`) into the history rows, except for the current
  message, and `build_input_payload`'s caller re-appends each one to its user message after `neutralize`, so the
  replayed text is byte-identical. `context.prepare` does the same for older rows it reloads. Luna and Haiku keep their
  runtime as a separate item and never replay. The history `ChatMessage` carries it as `runtime`, which the context budget
  counts.
- `RUNTIME_PLACEMENT_PROMPT` now says earlier blocks, including ones kept with earlier user messages, are outdated.
- Stored with each user message from then on: the clock, request/conversation ids, model and effort, the self-reported
  OS/browser family, any keyword guides and the summary envelope of that turn. Deleted with the conversation; not shown
  by the conversation API.
- Tests: `test_grok_turn_request_is_a_whole_prefix_of_the_next` (all three models; fails for Grok without the replay,
  checked), `test_grok_retry_of_the_same_message_sends_one_fresh_block`, and the spoofing test now accepts replayed
  genuine blocks from earlier turns.
- Not covered: the history window and summary still move the prefix when they shift (G1.2, G1.3); messages from before
  this change have no stored block, so an existing conversation catches up after its next turn.

## Keyword blocks out of the cached prefix (G1.1b) (2026-11-13, committed on branch `g1.1b-keyword-blocks`, not deployed)

Found by the owner's real-app check of G1.1 on 2026-11-13 (`b588d2c` deployed). Turns 2 and 3 of a Luna and a Haiku
conversation read the cache (Luna 15,365 and 15,577 tokens, Haiku 19,181 and 24,600, about 90% of the input), so G1.1
works. Turn 4 of both read 0. Not effort (the owner kept one level per conversation) and not memory (no
`memory_changes` in the journal). Replaying the owner's own messages through the builders showed the cause: the
Peto Agent guide (`features/agent/guide.py`) matched the bare word "peto" in the last three user messages, so
"peto sẽ tạo bao nhiêu form?" added about 4,000 characters to the system prompt, which changes the whole prefix.
The diagram guide, the `/docs/` context and the YouTube link titles were switched the same way. A first attachment in a
conversation also changes the prefix once (three attachment tools join `tools`); that is left as it is.
- `prompt_context.keyword_guides(question, mode, install_command)` builds those four blocks. Chat turns call
  `_build_system_prompt(..., guides=False)` and pass the blocks to `RequestContext.guides`; `runtime()` puts them after
  the clock, before the summary envelope and the snapshot, with `neutralize` applied (YouTube titles are outside text).
  Companion, the evals adapter and direct callers keep the default `guides=True` (unchanged requests). The context
  budget still counts the guides (`prepare` gets the system prompt plus the guides; the system prompt sent is without
  them).
- The Agent trigger no longer matches "peto" alone: `agent`, `cli`, `harness`, `peto login|logout|status|update|--version`
  and the slash commands do.
- `usage_events.prefix_hash` (column added at startup): 8 hex characters of SHA-256 over `instructions` + `tools` of each
  Responses call, recorded by `ai/xai.py` for every provider. No text. `python -m ops.cache_check [--hours N] [--db PATH]`
  prints recent Chat calls (time, model, effort, input, cache read/write, ratio, fingerprint) read-only and marks
  "phần đầu đổi" when a model's fingerprint changes from its previous call.
- Tests: `test_keyword_guides_ride_in_the_runtime_block_not_the_prefix` (all three models; fails on the old placement,
  checked), `test_prefix_fingerprint_is_recorded_per_call`, trigger cases in `test_agent_guide.py`,
  `tests/test_ops_cache_check.py`; `test_chat.py` and `test_youtube.py` now read the guides from the runtime block.
- Known limits: other per-request toggles still live in the system prompt (document mode, a project's instructions, the
  log-reading prompt when the first text file arrives), and `/admin` does not show the fingerprint.

## LIVE eval suite `chat-core` (G2.1) (2026-11-12, committed on branch `g2.1-live-eval-suite`, not run live)

Audit package G2.1. `python -m evals {plan,run} --suite chat-core` (`evals/schema.SUITES`): the four existing Chat
datasets, default models `peto luna haiku`, 48 turns, default `--max-calls 60`, `--timeout 300`.
- Output cap: `Settings.output_cap(model)` is `context_budget.policy(model)['output']` (8,192 / 16,000 / 32,768 by
  default), lowered by `--max-output-tokens`. Without tools the Responses provider still clamps output to
  `side_output_cap` (1,024); `adapter.output_caps` patches that name in `ai.xai` for the duration of a suite run in the
  CLI process only, and `CallBudget.claim` checks each request against the model's cap. Runs without `--suite` are
  unchanged (128–1,024, 90 s, 32,768 kept characters).
- `adapter.estimate` (printed by `plan` and `run`, stored as `results.json` `estimate`): per model, turns × cap for
  output, Chat's byte/3 × 1.15 estimator for the known input and a ceiling that assumes every earlier reply hits the
  cap, clipped to `--max-input-chars`; the hard output bound is `max_calls` × the largest cap; USD only with `--rates`
  and without cache discounts.
- `report.summarize` adds `first_text` per group, `cache_read_ratio`, and `models` (per-model first text, tokens, cache,
  USD); `report.md` gains "Theo model" and the stored estimate. The manifest lists every dataset with its SHA-256.
- Not the app's request: the clock stays in the system prompt, no `<peto_runtime>` block or `prompt_cache_key`, tools
  off. Nobody has run it live; the owner runs `--mode live --allow-paid` on the VPS after approving the spend.
- Tests: 5 new in `tests/test_brain_evals.py` (suite load and caps, estimate maths, lifted cap reaching the fake OpenAI
  and Anthropic SDKs while a plain run still sends 1,024, CLI plan + mock run of all 48 turns, cache ratio unknowns).

## Web Chat stable prefix (G1.1) (2026-11-12, committed on the worktree branch, not deployed)

Audit package G1.1, approved by the owner. Before it, every per-turn value sat in `instructions`/system ahead of the
history (second-resolution clock, the request snapshot with clock and `round`, the summary envelope, the finalizing
note), so no Chat turn could read the cached history or attachments. Now, for Chat turns only (`request_context.current`):
- `instructions`/system and `tools` are identical across turns and tool rounds: the system prompt, search rules, the
  GitHub prompt from the turn's start, the code prompt and one new sentence, `prompts/chat.RUNTIME_PLACEMENT_PROMPT`.
- The clock, the summary envelope (`Prepared.note`, no longer added to the prompt) and the snapshot are frozen once per
  turn (`RequestContext.clock`, `history_note`; `round` removed) into one runtime block wrapped in `<peto_runtime>`
  tags, placed after the current user message. Placement follows each service's docs: OpenAI, a `developer` item (Responses
  input roles; the caching guide moves dynamic content to later messages); Anthropic, a mid-conversation `role: "system"`
  message (documented for Haiku 5.5, no beta header, must follow a user turn); xAI, whose docs do not say a trailing
  system/developer item is supported, a separate fenced part of the current user message (as in xAI's prompt-caching
  cookbook). Input is append-only: a round whose manifest differs (required-web first round over, GitHub revoked,
  finalizing, search fallback) appends a re-rendered snapshot (same text, same frozen clock), then the finalizing or
  search-fallback note; xAI appends those as user items. The newest block is current; three rounds with an unchanged
  manifest carry exactly one snapshot.
- Server blocks are recognised by position and by the server-made `ServerBlock` type, never by heading:
  `request_context.split_context` is gone, `claude.cached_system` no longer splits on the snapshot heading, and Claude
  accepts `role: "system"` only from a `ServerBlock`.
- Follow-up fix the same day: on xAI the genuine block is only a part of a user-role message, so roles alone do not
  prove origin. In Chat turns `request_context.neutralize` turns the `<` of any `peto_runtime` tag (any case, any
  spacing) into `&lt;` in all text not made by the server: the system prompt part with profile, memory and project
  documents, every text part of history (user and assistant messages, attachment labels and excerpts, cited sources),
  the summary envelope inside the runtime block, and every `function_call_output` the server builds. It is
  deterministic, so prefixes stay byte-identical; stored data is unchanged; non-Chat requests are untouched. Tests:
  lookalike tags in a message, an attached text file and a round-two tool result for all three models, plus a stable
  prefix with a tagged history message (12 tests; backend 2,103 passed, 1 skipped).
- Known limits: xAI's native web search results (and Claude's server-side search/fetch blocks) are produced inside
  the service and replayed as returned, so they cannot be filtered; only the prompt sentence covers them. The model's
  own output items replayed within a turn are not filtered either. There is no automatic fallback if a service rejects
  the new placement in production: the way back is to revert the G1.1 commits and restart the backend.
- Claude: `cache_control` on the last block of the old history even in one-round turns (plus the stable system block and,
  in a tool loop, the last block). Haiku thinking is replayed again, but only when the system, tools and earlier
  messages match the request that produced it (`anthropic_prefix` digest, ignoring `cache_control` as the
  preserved-thinking docs allow); a changed prefix (for example the required-web round's tool list) still drops it.
- xAI receives `prompt_cache_key` = `peto-chat-` + SHA-256 of the conversation ID (documented for Responses as
  `x-grok-conv-id`); OpenAI gets none, because its docs say GPT-5.6+ routes the cache without one.
- Companion, Agent, BYOK and side calls are unchanged: `tests/test_unchanged_requests.py` compares them with requests
  recorded from `62f7b3b`, except that Claude system text containing the snapshot heading is no longer split out.
- Tests: `tests/test_chat_prefix_stability.py` (byte-stable prefix over three turns and three rounds with a moving fake
  clock, envelope placement, spoofing, `cached_tokens` still recorded), the fake Anthropic service in `test_claude.py`
  now applies the documented prefix check, and 14 existing tests had assertions moved to the new location (two test
  helpers now read the newest runtime block instead of `instructions`). Backend: 2,091 passed, 1 skipped. The 20-message
  window and summary timing are unchanged (G1.2, G1.3). Real-model checks are in `unverified.md`.

## Seven Grok-inspired Web Chat UX improvements (2026-10-27, complete locally, committed `348d7ca`, not deployed)

Owner authorized all seven, staged in `backend/features/chat/docs/grok-chat-ux-plan.md`, from clean HEAD `3695600`.
That HEAD already includes the Sources work below; do not roll back committed Companion/Imagine changes.
Research reused observed Grok UI and public JS with REA, not guessed backend behavior; no paid calls during implementation.
- Table icon copy (HTML + plain CSV) and UTF-8 CSV download, formula-safe cells; copy omits rendered citation badges
  but preserves literal markers in code/links/user text. Code Collapse/Expand (>5 lines), Wrap/Unwrap (>90 desktop,
  >50 narrow); full code copy; stable Markdown component identities preserve state on final metadata/stream completion.
- Assistant actions: circular icons for Copy/Regenerate/real variant navigation/More. More has local Markdown export
  with sources and honest "In / lưu PDF" browser print; safe rebuilt print document, no app chrome or remote images.
- Select complete stored assistant prose → "Thêm vào câu hỏi", draft quote strip/remove/jump. Reject user/live/
  incomplete/cross-message/control selections; cap 2,000 UTF-16 chars in UI. Backend `quoted_source {message_id,text}`
  validates owner/same Web Chat, keeps raw question separate, injects quoted reference only in user history, invalidates
  covered summaries on quote mutation, remaps IDs on fork. Companion `quote_id` stays independent.
- Search has desktop list+preview, Arrow/Enter/Escape and mobile preview/Open/Back focus. New scoped read-only
  `/api/conversations/{id}/preview` returns last12/tot24k chars (SQL bounded), no files/work/provider/LLM calls;
  frontend abort/stale guards, cache8/dialog, remount by account, escaped Markdown/no image fetching.
- Completed Regenerate uses existing branch protocol, preserves original. Additive `chat_message_lineage` records
  explicit question/response origins, dedups inherited prefix copies, prefers current copy, scoped owner/mode/project/
  archive/branch_group. Public-only `reply_variants {index,choices}` (latest200 questions/max20 variants), ID-based
  navigation and scroll/focus; no content-equality heuristics for legacy. Different text or quote always forks.
- Plaintext paste >50,000 UTF-16 chars becomes a local unique `pasted-text.txt`; uses ordinary attachment limits,
  bounded escaped preview, remove, Undo preserving selection/caret and refusing to overwrite later edits. Rejected
  attachments fall back to native paste. Draft text/quote persist per session scope; File objects still memory-only.
- Additive startup schema: `messages.quoted_source`, `chat_message_lineage`, `chat_turns.model/effort` and quote
  summary invalidation trigger. Prefix copies preserve provider/source/work/artifact state. No new dependencies/env.
- Validation final runs: backend26 + regression165 passed (distinct); frontend App131 + other13files218 passed
  (distinct); browser44 passed (Chromium desktop + phone emulation, dark/light, Sources/citations, branches/F5,
  keyboard/IME/focus, attachments/draft/stop; external requests blocked). Production build/typecheck passed,
  whitespace check clean. No claim of whole-repo run, physical phone, screen reader, Safari or live provider/VPS test.
- Screenshot evidence outside repo: `grok-chat-ux-implementation/` in the current visualization artifact root.
  Full plan documents exact tests, reconstruction limits and Before/After review. Owner will commit/deploy;
  rebuild frontend + restart backend (startup migration), no `.env` changes.

## Web Chat sources panel from Grok (2026-10-26, committed `3695600`, not deployed)

Owner authorized all four stages; make it as close to Grok as possible. Started clean at `e96fd91`, preserving
the committed Companion changes below. Reopened the logged-in Grok chat, inspected Sources UI/DOM, and statically
analyzed three observed public JS bundles with REA (partial scope, no claim about Grok backend). No paid model calls.
- `work.web` v1 stores a display-only source registry (200 URL/40 native calls/256 KiB), query membership and optional
  producer plaintext snippets. `source_activity` SSE upserts by native provider/round/call ID. Existing 30-source
  context/citation list stays unchanged; this catalogue never goes into model input. Missing query/ID uses truthful
  ungrouped fallback. Claude enrichment is separate from `_portable_output`, preserving native replay equality.
- Web Chat only: backend `shared/source_activity.py`, xai/Claude adapters, WorkLog/service, chat_turns/history;
  frontend `sourceActivity.ts`, `SourceIcon`, `WebSources`, `SourcesPanel`, `sources.css`, App/API/closeWork integration.
  Desktop right panel, narrow-screen 85dvh sheet; query groups collapsed, favicon pill, optional snippet, dark/light,
  keyboard/focus, exclusive document/diagram panels, close on chat/view change and question revision.
- Related backend runs 108 passed + 43 passed (overlapping), final owned hardening30/pipeline5 passed; frontend
  19 + 148 passed, final UI/API/stage4 rerun31 and trigger13 passed; final browser run24 passed; production build passed.
  No whole-repository rerun claim, new live provider acceptance, physical phone or screen-reader verification.
- Favicon Google S2 gets public hostname only/no-referrer, local YouTube/GitHub SVG and globe fallback. No raw HTML.
  Keep neighboring control shape/hover/focus/touch styling consistent, as the owner explicitly requested.
- Plan/reference/contract/test notes: `backend/features/chat/docs/sources-panel-plan.md`, `source-activity.md`.
  Deploy requires backend restart + frontend build/reload; no env or DB migration. Owner will commit/deploy.

## User-message copy action (2026-10-25)

Web Chat user bubbles now have an icon-only copy button immediately after Edit. It copies the original message
content (including real URLs/Markdown), reuses the existing clipboard hook, and shows only a checkmark on success
for 2.2 seconds. Accessible state labels remain; no visible label, tooltip or toast on this button. Empty text and
the active editor show no copy action. Copy remains available while branching/edit actions are disabled.
Frontend-only; rebuild frontend for deployment.
Validation: existing clipboard component cases 3 passed, build/diff check passed. Inspected mocked-app desktop/mobile
emulation: original raw text/URLs copied, no visible text/tooltip, success reset, blocked clipboard does not show
success, keyboard Space retries. Clipboard and APIs were mocked; no real-phone or production acceptance claimed.

## Web Chat citation rendering (2026-10-25)

Owner reported raw `[web:21]`/`[web:26]` in answers. Audit/contract/deployment:
`backend/features/chat/docs/citation-rendering.md`. Sources already carried URL/title through SSE/history, but
normalizers dropped IDs/annotation spans and Markdown had no inline citation renderer. No repo code generated the
raw web markers; no live payload from that exact GTA5 turn was captured. Never map marker numbers to array indices.
- `shared/web_search.citation_ids` keeps bounded explicit aliases and IDs proven by a native annotation's exact
  marker span. Optional `citation_ids` survives provider/SSE/JSON persistence/read/frontend normalization; old rows
  remain valid. URL dedup unions aliases. Unsupported/missing/ambiguous mapping remains unlinked; old lost IDs cannot
  be reconstructed from URL order. Source limit remains 30, 24 aliases/URL; cited sources keep priority.
- Claude Web Chat emits URL-hash `src:` markers at native citation deltas. Original Anthropic native content/signature
  handling is preserved; calls without Web Chat snapshot (Agent/Companion/standalone) keep plain-text behavior.
- Assistant-only remark AST plugin renders grouped inline badges, supports existing native Markdown citation links
  and mapped OpenAI markers, hides incomplete streaming syntax, keeps code/user/link text literal. Unknown references
  show pending/unknown, never guessed links. Existing expandable source footer and access evidence stay intact.
- Use React text, bounded HTTP(S) URLs without credentials/control/backslash, no raw HTML/eval. Inline badges reuse
  TooltipLayer for title/URL and keyboard focus; long tooltip wraps. No new provider params, dependency or DB migration.
- Tests use synthetic providers/native HTTP, temporary SQLite and local browser mocks; no paid call/commit/deploy.
  Rebuild frontend and restart backend; reload existing tabs. Physical-phone and model-quality acceptance remain separate.
- Validation: full backend 1,841 passed/1 skipped (497.42s); full frontend 1,009 passed (153.06s); final bounded-group
  citation/source/API rerun 33 passed; related stage-4 browser 10 passed, citation desktop/mobile-emulation 2 passed
  with long-URL tooltip bounds, keyboard, mocked source click and F5. Build/diff checks passed; inspected both screenshots.

## Web Chat link chips (2026-10-25)

The owner showed Claude's composer turning a pasted YouTube link into its title and a GitHub link into "owner/repo",
and approved chips above the textarea plus short labels in sent messages. Frontend only; committed `5aa22f9`.
- Pasting exactly one http(s) URL (no spaces, no credentials, at most 2048 characters) becomes a chip in the attachment
  row (`Composer.tsx` onPaste); mixed text pastes normally, duplicates are ignored, at most `MAX_DRAFT_LINKS` (8).
- `features/chat/draftLinks.ts`: links live in the draft string after the private-use `LINK_MARK` (U+E000), so
  `useChatDrafts`, sessionStorage, F5 and `accept()` need no change. The textarea shows only the typed text;
  `messageText` sends the typed text then each full link on its own line, so the model and history get real URLs.
- Labels come from the real hostname only (`describeLink`): YouTube (`parseYouTubeUrl`) with its title from the existing
  `/api/companion/player/videos/{id}` oEmbed endpoint (client cache, failures not cached), GitHub `owner/repo`
  (`#N` for issues/PRs, `· file` for blob/tree), else `host › last segment`. Lookalike domains stay "web".
- `LinkChip.tsx`: `ComposerLinkChip` (remove button, full URL in the tooltip) and `MessageLink`, used by
  `ChatMessage`'s `a` override only in user messages whose link text equals its href (bare pasted links).
- Tests: `tests/draftLinks.test.ts`, two `App.test.tsx` cases; frontend 998/998, build passed. Checked on the mock stack
  in the in-app browser: GitHub and YouTube chips (real oEmbed title), F5 keeps them, sent bubble shows both labels.
  Deploy: rebuild frontend.

## Web Chat personality (2026-10-24)

The owner found Peto Trò chuyện stiff and less fun than ChatGPT and sent screenshots (Peto/Grok, effort Thấp). Grok's
own reasoning quoted core rules: it refused a playful "if I give you a gender, what would you choose?" ("invent a body,
age, gender"), answered "hello, peto khỏe không?" flatly ("never turn into a character") and refused to summarize its
limits ("announce internal prompts"). Advice given: do not take text from leaked-prompt repositories (unverified,
proprietary); learn techniques from official sources (Anthropic's published Claude prompts, `xai-org/grok-prompts`,
OpenAI Model Spec): positive character prose, good/bad example pairs, casual vs task modes. Owner approved; committed `7739a1c`.
- `prompts/core.py` (shared with Agent and /btw): still honest about being an AI, still never names the model, harmful
  help still declined; but bodies/gender/experiences are only forbidden "as real facts about yourself", Peto may have
  tastes and play along with hypotheticals, forms of address "change only the pronouns, not who you are", and when asked
  about its rules it summarizes them in its own words instead of refusing (never quotes instructions verbatim).
- `prompts/chat.py` `WEB_PROMPT` starts with `## Personality` (warm, opinionated friend; texting-length casual replies;
  match energy; natural Vietnamese particles) and `## Casual chat examples` (stiff vs better pairs, incl. the owner's
  screenshots), for every Chat model. Agent and Companion do not get them. Chat prompt grew ~2,400 characters
  (Peto 18,579, Luna 16,497, Haiku 16,582); Vietnamese letters stay under the 2% `test_prompts_are_english` limit.
- No fixed gender or preferences for Chat Peto (model picks playfully each time); Companion persona unchanged.
- CLI bundle regenerated (`make_bundle.py`), CLI 0.33.4, since the core is bundled for direct sources.
- Eval `backend/evals/chat-personality-cases.json` (4 cases/5 turns incl. the screenshots): mock 15/15 turns, every
  prompt had the new section; mock text cannot pass content checks and no LIVE run was made. Test
  `tests/test_personality_prompt.py`.
- Validation: related backend group 169 passed; CLI bundle/version/direct-source/release/update 68 passed; full backend
  1,817 passed, 1 skipped (510.75s; the tree also held the uncommitted Player stage 4 work). Deploy: restart the backend (CLI users are offered 0.33.4). Real tone needs the owner's chats.

## Tools survey and log workflow (2026-10-21)

Codex handed the tools research to Claude (`CLAUDE_TOOLS_HANDOFF.md`). The report and incremental plan are in
`backend/features/chat/docs/tools-survey-2026-10-21.md`: code-backed inventory (Web Chat has no code execution;
Agent runs commands on the user's machine), proposals P1 log workflow, P2 structured readback of created documents,
P3 provider code execution. Code execution findings: Haiku 5.5 is documented for `code_execution_*` (Files API is
workspace-scoped, no ZDR, minimum 5 minutes billed); xAI is unverified over Peto's Grok-CLI OAuth and documents no
output files. Two paid probes are written up, not run. Proposals are approved one at a time.

The owner approved P1 only (no paid eval). Implemented locally, committed `c10e717`, not deployed:
- `prompts/chat.LOG_PROMPT` (English, ~1,900 chars): reading status first, one combined `search_attachment` before
  firm conclusions, root failure, suspects ranked by evidence (named in the root error/failing config > top frame
  owner > merely present), real line numbers, confidence labels, no private log data in web search.
- Attached only in Chat when the conversation's stored files include a `TEXT_MIMES` file
  (`prompt_context.has_text_files`, from `file_index` fetched before the prompt in `service.py`), never from user
  wording. It sits before profile/memory blocks, so it stays in the cached prefix. Pasted logs, PDF/Word logs and
  Companion do not get it.
- `search_attachment` description adds a cause-chain query example. `reader.ROOT_SIGNAL` adds mixin failure patterns:
  a synthetic modpack log with 100–400 distinct earlier errors dropped the only line naming the mod from the excerpt;
  now kept. `TEXT_FORMAT` unchanged, so stored excerpts are not re-read.
- Tests: `tests/test_log_workflow.py` (6, synthetic logs only; the excerpt case fails with the old pattern). Eval:
  `evals/chat-log-cases.json` (3 cases); the eval prompt builder passes `text_files` like the app. Mock run for
  Peto/Luna/Haiku completed 9/9 turns with the guide in every prompt; mock text cannot pass content checks and no LIVE
  run was made. Related backend group: 264 passed; full backend 1,578 passed, 1 skipped (348.63s); diff check passed.
  Deploy = restart the backend after the owner commits; no frontend, migration, `.env` or CLI change.
  The owner committed and deployed P1 (`c10e717`).

P2 approved after that deploy; implemented locally, committed `e33fa18`. `features/documents/readback.py` builds a bounded
`check` (under 2,000 characters) from the rendered content, returned by `create_document` (title shown, level 1–2
headings, words, tables, formulas, images, image slots, TOC, pages, `cover.blank` for dotted cover lines) and
`create_presentation` (slide number/layout/title, `without_notes`, images, tables, charts). Tool instructions ask Peto to
compare with the request and name missing parts. The deck instruction no longer always claims every slide has speaker
notes. A readback failure only drops `check`. No UI, storage, tool schema or system prompt change; spreadsheet and edit
tools already return results/changes. Tests: `tests/test_document_readback.py` (7, including the provider tool loop).
Structure only, not content correctness; real-model use of `check` is untested. Document test group 252 passed; full
backend 1,585 passed, 1 skipped (381.64s); diff check passed. Deploy = restart the backend after commit.
The owner committed and deployed P2 (`e33fa18`).

Phase 3a prep (not run against any provider): `backend/ops/code_execution_probe.py haiku|xai` defaults to a dry run on
fake responses shaped after the docs; only `--allow-paid` calls the real API with the machine's credentials (max 2
requests, 2,048 output tokens each). Haiku: `code_execution_20260521` with Chat's adaptive/low thinking, synthetic CSV,
chart in `$OUTPUT_DIR`, one `pause_turn` continuation with the same container, then download, delete and verify 404.
xAI: `code_interpreter` with `store:false`, then resends the items to test acceptance; it uses the stored OAuth token
or `XAI_API_KEY` and never refreshes (a refresh could invalidate the running backend's in-memory refresh token).
Evidence JSON goes to `.runtime/probes/` with hashed container/file IDs and secrets scrubbed. This dev machine has no
Anthropic key and an expired xAI token, so paid runs belong on the VPS after deploy, only on the owner's go-ahead.
Tests: `tests/test_code_execution_probe.py` (8), with ops tests 36 passed.

The owner ran both paid probes once on the VPS (2026-10-21; survey section 4e has the details). Both passed:
- Haiku: one request, 6.6 s; block order `server_tool_use(bash_code_execution)` → `bash_code_execution_tool_result`
  → text; `container` only in `message_delta`; PNG downloaded (C2PA makes it larger than in the container), deleted,
  then 404. `usage.server_tool_use` has no `code_execution_requests`, so Peto must count result blocks itself. About
  6,400 input tokens are the tool's own declaration.
- xAI: works over Peto's OAuth; events `response.code_interpreter_call.*` and `response.code_interpreter_call_code.*`;
  items `{code, outputs: [{type: "logs", logs: "<JSON with stdout/stderr/exit_code/command_timed_out>"}]}`; resending
  items with `store:false` is accepted; usage reports `server_side_tool_usage_details.code_interpreter_calls` and
  `cost_in_usd_ticks` (1 USD = 10^10 ticks, about $0.007 per request); no output files.
The probe's number check was too strict ("163.0" vs "163.00"); fixed with a test (9 passed). Recommended pilot order:
Peto/xAI compute-only code execution first, Haiku with file artifacts only after a privacy/workspace decision, Luna
later.

Peto/xAI code execution pilot (owner approved, Haiku explicitly not enabled; implemented locally, committed `1679d14`):
- Only `XAIProvider.code_interpreter = True`, only in Web Chat (a request snapshot must exist), switch
  `PETO_XAI_CODE_EXECUTION` (default true; false + restart turns it off). `capabilities.select(code_reason=)` adds
  `run_code` (`{"type":"code_interpreter"}`); reasons `provider_unsupported`, `server_disabled`, `chat_only`; final and
  required-web-first rounds disable it like other tools. `prompts/chat.CODE_PROMPT` is appended only when available.
- `ai/xai.py`: the run's start event / added item opens a step and turns a lead-in into a note like web search;
  `code_result` parses the nested `logs` JSON (plain strings, images, timeouts too); one step per item id even though
  the item arrives twice. Stdout only, no files; nothing is executed by Peto itself.
- `work_log.py` step `code` ("Đã chạy mã" / "Mã chạy lỗi" / "Mã chạy quá thời gian", detail "Python · N dòng · mã thoát
  X") keeps code and output with newlines, 4,000 characters each, 24,000 per turn, persisted in `messages.work`. Each run
  records a `chat_event` purpose `code`; the admin Chat metrics show runs and errors. `WorkTimeline.tsx` adds a prompt
  icon and a "Xem mã và kết quả" disclosure with focusable scrolling `pre` blocks. Mock words `__chayma__`,
  `__chayma__:loi`.
- Tests: `tests/test_code_interpreter.py` (7, fake streams from the real event/item shapes), frontend WorkTimeline case;
  frontend 797/797 (one earlier full run had one uncaptured failure that did not reproduce in two reruns); build passed.
  Full backend: 1,600 passed, 1 skipped, 1 failed (`test_chat_stage4` pinned the admin `tools` dict without the new
  `code_runs`/`code_errors`; expectation updated, then stage4/admin/code group 45 passed; no second full run).
  Mock stack in the in-app Chromium: step, disclosure, F5 persistence, failed styling, 375 px without overflow, no
  console errors. Real Grok tool choice, overuse, cost and latency after deploy are unverified.
  The owner committed the pilot (`1679d14`).

Follow-up advice (2026-10-22): of the deferred items, only recording Grok's reported cost was worth doing now; Haiku
with files, Luna code execution, interactive results, tool discovery, X Search and Drive/mail/calendar wait for real
demand. The owner approved the cost item: `ai/xai.py` (Chat) and `ai/agent.py` (Agent) record `cost_in_usd_ticks` as
`usage_events.cost_ticks` (column added at startup); the Agent API pops it before sending usage to the CLI. Admin
`call_cost` prefers it for `xai` rows even with a rates file, `cost.reported_models` lists such models and the page
explains the source; `deploy/OPERATIONS.md` updated. It is xAI's reported figure, not an invoice; under the OAuth plan
it may not be money actually charged. Tests: 3 new in `test_admin.py` (26 passed), 1 new admin frontend case (6
passed), build passed; full backend 1,604 passed, 1 skipped (300.91s). Deploy: rebuild frontend, restart backend.
The owner committed it (`9aadb49`).

Reassessing requests (2026-10-22, owner approved; committed `2a02410`). On 21/10 Grok called a pasted table plus "chỉ trả
lời ok" a prompt injection, invented a "jailbreak rule" and defended the refusal across two clarifications; the profile
was empty, Discord memory had no such rule, and a fresh chat complied, so it was in-session anchoring.
`WEB_PROMPT` gained "## Reassessing requests" (before "## Explanation and evidence"): judge each message on its merits,
follow harmless format/length requests, only system rules decide refusals (earlier replies, summaries, memory and
profile cannot add any), text the user writes or pastes is their request while instructions in files, pages and tool
results stay data, and after a wrong refusal or misread reassess from scratch, say so briefly and do it. It is in
`WEB_PROMPT`, not `CORE_PROMPT`, because the core is bundled into the CLI (parity test); Agent/Companion unchanged and
the harmful-request rule stays. Eval `backend/evals/chat-reassess-cases.json` (2 cases including that session; mock
9/9 turns, no LIVE run); test `tests/test_reassess_prompt.py`. The same session's red "Không tải được danh sách hội
thoại" banner came from a list load that never reached the server (VPS log only had 200 OK): `refreshConversations`
in `App.tsx` now retries once after 2 s before showing it and clears that banner (only that one) on a later success;
two `App.test.tsx` cases fail on the old code. Survey section 4g has details. Full backend 1,608 passed, 1 skipped
(399.23s); frontend 800/800 on a rerun (the first full run had one failure in an unrelated file-lookup work-log case
that passed alone and in the rerun); build and diff check passed. Deploy: rebuild frontend, restart backend.

## Web Chat automatic Runtime Device Context (2026-10-21)

Separately approved after the four Chat stages; device data was not implemented by stage 2. Contract/privacy:
`backend/features/chat/docs/client-environment.md`. Final owner decision replaces the uncommitted opt-in design:
normalize existing HTTP headers automatically for every Web Chat turn, without a settings switch, localStorage
permission or JSON flag. Production frontend code is unchanged from HEAD; existing deployed clients work as-is.

- Backend normalizes existing bounded UA/low-entropy Client Hints into finite OS/browser families each Chat request.
  No raw UA, versions, device model, architecture, high-entropy request or fingerprint reaches prompts/logs/DB.
  Unsupported/missing/conflicting headers become unknown. Reports can be spoofed/reduced; not verified hardware.
- Optional immutable `client_environment` carries fixed provenance and `best_effort`/`client_reported`, goes through
  the existing final RequestContext assembly/budget/native adapters, outside Claude's stable cache prefix. Reset
  on completion/error/cancel; no metadata cache or reuse of previous-device reports. Missing headers yield unknown;
  Companion skips normalization. Agent unchanged.
- No structural metadata storage, migration, .env, new provider params or memory policy. Ordinary assistant text
  answering a device question remains normal saved chat and can enter later summaries. This feature is not
  Temporary Chat. Prompt prohibits inferring the current device from prior observations when absent/unknown.
- Tests use fake SDK/native HTTP and temporary SQLite; local browser mocks block external traffic. No paid LLM,
  automatic commit/deploy or physical-device acceptance. Deploy the backend after owner commit; no new frontend
  build is required relative to HEAD (rebuild locally if previewing a dist created from the discarded opt-in code).
- Final automatic-design checks: client-environment/request-context/Claude group 101 passed, App/API component
  group 143 passed, Chromium desktop/mobile-emulation 2 passed; production build and diff check passed. The earlier
  opt-in test totals do not describe this final revision. All production frontend/schema edits for the switch were
  removed, including the setting component, localStorage hook and flag-based tests.

## Web Chat UX, evidence and quality — stage 4 (2026-10-21)

The owner approved the final stage after deploying/live-testing stage 3. Contract, metrics semantics, rubric and
deployment/hardware gates: `backend/features/chat/docs/quality-and-ux.md`. Implemented locally; no auto commit,
deployment or paid model call. Do not claim physical-phone, screen-reader or production acceptance from emulation.

- Web Chat: composer focus only returns when still owned; code/table/message regions are keyboard accessible;
  edit cancel/Escape returns to the source action, jump-to-latest keeps focus and honors reduced motion. A polite
  live region announces milestones rather than tokens/history. IME Enter/229 does not submit. Mobile drawer traps
  Tab, Escape restores focus without interfering with its own menus/dialogs. Keep browser zoom; app/drawer safe
  areas and runtime theme-color follow app preferences. Cooldown rounds up to at least one second.
- Sources retain whitelisted `access=search|page|tool` and `partial=true` across streaming/checkpoints/reload.
  Completed native `open_page`/`find_in_page` and successful Claude fetch produce page evidence; only the actual
  action URL is promoted. Search snippets and GitHub tool excerpts have separate labels. Citation alone does not
  prove page fetch, full content or correct claims. Unknown/invalid metadata keeps safe Markdown fallback. No raw
  model HTML/JSX/CSS/JS renderer, dynamic UI protocol, new segmentation model, voice or Agent runtime changes.
- `usage_events.effort` migrates at startup. Task-local measurement labels summary SDK requests separately from
  logical summary attempts. Admin adds collapsed Chat metrics: model/API ID/effective-effort sample counts and
  p50/p95, summaries, typed context overflow, dispatch errors and recovery reads. Chat events never double-count
  tokens/cost/turns; no owner/chat/request IDs, content, source URLs or raw tool errors in measurement records.
  Completed-turn latency and all observed first-text latency have separate n. Missing/legacy labels stay unknown.
- History exposes scoped `reply_to`; recovery reads include `recovery_for` and are owner/chat/user validated.
  Prefer exact reply linkage; fallback only when both source/reply lack turn linkage (legacy). Recovery counters
  count server reads, not unique repaired turns/client success/offline attempts. No automatic AI resubmission.
- Separate `backend/evals/chat-stage4-cases.json` reuses the bounded runner: 4 cases/5 turns, mock smoke 15 turns
  across Peto/Luna/Haiku. These are prompt fixtures without native tools, not quality/performance measurements.
- Validation: full backend 1,537 passed/1 skipped (281.31s); full frontend 796 passed; browser desktop/mobile 34
  passed, final source visibility/drawer checks 10 passed. Recovery/source/status group rerun 23 passed after a
  final legacy-link guard. Build and diff checks passed. Browser snapshots stayed unchanged; actual mobile and
  NVDA/VoiceOver/TalkBack and stage-4 model quality still require acceptance after owner commit/deploy. Rebuild
  frontend and restart backend; no new .env or CLI installation.

## Web Chat recovery and data scope — stage 3 (2026-10-21)

The owner approved continuing after committing stage 2. Contract, migration and deployment gates are in
`backend/features/chat/docs/recovery-and-data-scope.md`. Stage 4 is documented above; no automatic deployment or paid test.

- `chat_turns.bind` saves a new user message and request link atomically. `persist` commits assistant content/status,
  verified owner/chat/version artifact links, sources, work and terminal state in one immediate SQLite transaction.
  Complete is not announced until it commits. Stop wins if committed first; terminal complete is immutable.
- Chat checkpoints are bounded at 200,000 characters, on chunks at 1 second/2,048 characters, forced for artifact,
  tool result, note and replacement. `WorkLog.snapshot()` does not mutate live steps. Final normal replies retain
  full content. Startup preserves checkpoints and marks running attempts interrupted/process_restarted without
  replaying AI or tools; a superseded attempt cannot create a new recovered reply. No exactly-once tool guarantee.
- Persist rechecks owner/chat/project/archive/source digest. Deleted chats are not recreated by late results.
  Recovery only reads history; a running checkpoint is not accepted as a final reply. Running retries are rejected.
  Failed historical requests/partial replies are reference, not pending tasks; this also applies to anchors,
  summary prompts and native history lookup. Turn state changes invalidate covered summaries; old affected v1
  caches are invalidated once during migration. Titles/memory skip failed Chat attempts.
- Saved personal memory remains shared Chat/Companion under the existing account policy, including across projects;
  deleting a chat does not delete already extracted personal entries. Memory OFF is not Temporary Chat: normal
  history and per-chat rolling context persist. Unsupported privacy flags are rejected before model execution.
- Memory revisions change on entry edits/deletes/settings/forget operations. Background writes validate enabled,
  revision and source content/ownership/scope inside the same transaction. OFF→ON and deleted/moved/edited sources
  reject stale results. Forget advances the extraction watermark past current messages, so an aborted background
  result cannot learn the same deleted fact again on its next run. Concurrent running turns fence the cursor.
  Companion summary/persona algorithms and Agent runtime are unchanged; only guarded storage is added.
- SQLite additions/triggers migrate at startup; frontend rebuild required, no new environment variables/CLI update.
  Fault-injection and privacy race tests use fake providers/temp SQLite. The live follow-up is recorded below.
  Final validation: 1,518 backend tests passed, 1 skipped (350.00s); related recovery/memory/private-note group 91 passed;
  frontend component tests 23 passed; Chromium desktop/mobile-emulation browser tests 6 passed; production build and
  diff check passed. The first broad run caught an empty Companion private-note bubble; fixed while preserving its
  prior behavior, then reran the full backend. No paid call, commit, deployment or physical-phone test was performed.

After the owner committed/deployed `53c44e7`, stage 3's core UI flows were live-tested on 2026-10-21: 6 submissions
in 2 synthetic chats, Peto/Luna/Haiku. Stop before/after text, F5 preserving partial replies/drafts, explicit retry
without duplicate source messages, and a new question after interruption passed. Haiku answered 43 to 17+26 without
an instruction to ignore the old task. Its generated Word artifact survived F5 with the same ID/version; downloaded
DOCX XML contained REC3_DOC_71 and the expected text. Memory OFF retained 3 entries/10 details; ON and Peto/auto/web AUTO
were restored and verified through UI. No source-code patch was needed. Forced production crashes, in-flight memory
deletion races, second-owner checks and project moves/deletes remain mock-tested only; no physical-phone/offline
network test or server usage/billing audit. Full evidence and limitations: `recovery-and-data-scope.md`. Stage 4 is documented above.

## Web Chat request context — stage 2 (2026-10-21)

The owner approved stage 2 after deploying and live-testing stage 1. See
`backend/features/chat/docs/request-context.md` and the four-stage roadmap. Stages 3–4 are documented above.

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
`backend/features/chat/docs/long-context.md`. Stages 2–4 are documented above.

- `features/chat/context.py` prepares the exact recent messages under a model/deployment budget and adds a portable
  rolling summary, a bounded first-user anchor, file metadata and explicit unrepresented-message counts. Source
  messages are never replaced. Saved personal memory stays shared Chat/Companion by the existing product policy;
  the Chat summary is independent of its toggle. Companion's summary and Agent's runtime are unchanged.
- `storage/chat_context.py` stores one versioned projection per owner/chat/project, source spans, a character cursor,
  model **service/API-ID**, timestamp and chained digests. Each update validates the read fragments and prior digest
  again under an immediate SQLite transaction. Edits/deletes affecting the covered prefix and project moves
  invalidate it; forks start their own context and conversation deletion cascades. Corrupt v1 caches are rebuilt;
  future schemas are not overwritten. This is summary provenance, not an exactly-once tool journal.
- At most one summary call per turn (since G1.3, after the reply), through the selected Web model, low effort, tools/web disabled,
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
