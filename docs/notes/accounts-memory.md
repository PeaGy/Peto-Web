# Accounts and memory notes

Scope: Identity and data isolation, user profile and avatar, the Discord memory gateway and Peto's own memory (shared by Chat and Companion).

Moved out of `CLAUDE.md` on 2026-11-12 (G0.2). Write new notes for this area here, not in `CLAUDE.md`. Current behaviour comes first, then the dated log, newest first.

# Current behavior

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
    is writing drops the result. `delete_conversation` removes the row, so deleting a thread deletes it too.
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
  - Deleting a Companion thread (conversation list, since 2026-10-25; "Bắt đầu lại" and its dialog saying memories
    are kept were removed) never deletes memories.
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

# Dated log (newest first)

## Conservative automatic memory attribution (2026-10-27, committed `ee8c6db`, not deployed)

Owner reported another person's cat Blue became their pet in Profile, and authorized implementing clearer attribution,
no uncertain guesses and durable-only automatic retention. No original chat/extractor trace was available; identified
code weaknesses, not a proven single incident cause: subjectless-writing instruction, no preceding referent context,
and free-form model changes without source evidence. Details: `backend/features/companion/memory-grounding.md`.
- Auxiliary memory prompt now preserves subjects/ownership and rejects third-party anecdotes, assistant claims,
  quotations/fiction/inferences and transient problems as personal facts. Summary/legacy/manual prompts also preserve
  attribution. Automatic extraction uses a separate typed contract; manual Memory-page APIs keep string details.
- `memory_grounding.py`: new facts require subject=user/certainty=explicit/retention=lasting, a new user message ID
  and its entire normalized nontruncated utterance. Existing strings are retained, not newly authorized. Vetoes for
  common VI/EN third-party/uncertain/temporary/negated-ownership signals are conservative, not semantic truth proofs.
- Extraction JSON has role/ID/conversation and context_only/new_messages. At most4 preceding rows/thread and12 total,
  plus existing12 new rows; text1500max. Prior context cannot authorize new facts; all source snapshots revalidated
  under write lock; no reads before off/forget boundary. New DB helper `memory_context_before` is owner/card/provider
  scoped. No extra LLM request; input/output tokens can increase due to evidence and context.
- Automatic changes retain omitted facts, reject unsupported title/summary rewrites; explicit grounded `forget` handles
  correction/removal. Real removals reset entry summary and invalidate Companion summaries atomically. Revision/
  updated_at guard covers whole-entry removal too; rejected proposals do not wipe summaries. Forget moves context
  boundary forward. MockProvider emits the real contract; no production test bypass or Blue-specific exception.
- No bulk repair of stored memories or live VPS data edits. User can correct Blue in chat after deployment or edit
  Settings; interpretation still depends on model labels, with conservative omissions possible. No frontend/env/
  dependency/SQLite schema changes; backend restart only. Tests use fake model/gateway; no paid API calls.
- Final verification:149 passed across `test_memory_grounding`, `test_companion_memory`, `test_memory_scope`,
  `test_discord_memory`, `test_discord_memory_settings`, `test_companion_cards`, `test_byok`; `git diff --check` clean.

## Discord bot memory import switch (2026-10-27, complete locally, committed `02af2a4`, not deployed)

Account settings now has one existing-style SettingsSwitch, "Trí nhớ từ bot Discord", visible only for Discord logins.
Defaults on to preserve current behavior. Choice is stored server-side in additive `users.discord_memory_enabled`
(default1), not reset by OAuth upsert. No bot writes, deletion, new env/dependency or changes to Peto's own memory toggle.
- GET/PUT `/api/account/discord-memory`: strict boolean only; identity from verified session, Discord numeric owner
  only (403 for other providers), no-store. Can save even if gateway unconfigured/offline. Settings never fetch memories.
- Shared `prompt_context._build_system_prompt` checks the stored flag before gateway fetch; applies to Web Chat and
  normal eligible Companion turns. Existing `memory=False` exclusion for BYOK/custom cards remains. Off stops new
  bot reads; it does not erase earlier answers, summaries or personal memories already saved from past interactions.
- UI loads on opening Account, re-reads when reopened, aborts stale reads, remounts per owner. Optimistic switch with
  save lock/rollback; reopening during a save waits before re-reading. Uses existing SettingsRow/Switch styling.
- Tests: backend `test_discord_memory_settings`, `test_discord_memory`, `test_auth`: 64 passed; frontend
  `DiscordMemorySettings.test.tsx` + `api.test.ts`:27 passed; browser `discord-memory.spec.ts`:4 passed on PC/mobile
  emulation (reload, second context/device, failed-save rollback, other providers hidden, dark/light, no overflow).
  Production build passed; docs tests47 passed. Fake gateway/model only, no paid calls. Article docs updated.
- Deploy: backend restart for additive migration + frontend build; no `.env` edits. Owner commits/deploys.

| Before | After | Why |
| --- | --- | --- |
| Discord bot memory is always imported for eligible Discord users | One compact account switch using the shared toggle | Clear per-account control, consistent with other settings |
| Choice has no saved account state | Server persistence and fresh read when Account reopens | Same preference across devices |
