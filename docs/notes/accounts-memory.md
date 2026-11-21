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

There are four ways in: Discord, Google and GitHub OAuth in `features/accounts/auth.py`, and a sign-in mail with a
button link in `features/accounts/email_login.py` (since 2026-11-19, see below). Google, GitHub and email logins with
the same verified address share one account; Discord never does. `owner_key(provider, external_id)` builds every
owner; `provider_from_owner` is what `session_owner` uses to reject a signed cookie carrying a malformed key.

### Email login (email and password, like AIRI)

On 2026-11-19 the owner went through three designs in one day: a 6-digit code, then AIRI's link-only flow, then (after
asking why signing in again needed a new mail) AIRI's full email-and-password flow, from screenshots of AIRI's pages.
Mail goes out through Resend, from `PETO_EMAIL_FROM` (default `Peto <no-reply@peagy.com>`), optional
`PETO_EMAIL_REPLY_TO` (`support@peagy.com` suggested). No `RESEND_API_KEY` means `providers.email` is false and the
login page hides the field. Steam login was built and dropped the same day (commit `e82a874`).
- **Pages** (`app/LoginScreen.tsx`, `app/ResetPasswordScreen.tsx`, `app/EmailLinkScreen.tsx`), each AIRI's page in
  Vietnamese: "Đăng nhập" (Email, "Tiếp tục", "hoặc", Discord/Google/GitHub, Terms line); "Tạo tài khoản" ("Peto sẽ tạo
  tài khoản mới cho …", Tên hiển thị optional, Tạo mật khẩu, Nhập lại mật khẩu, "Dùng email khác" on the right);
  "Kiểm tra hộp thư"; "Chào mừng trở lại" ("Tiếp tục với …", Mật khẩu, "Quên mật khẩu?" left, "Dùng email khác"
  right); "Đặt lại mật khẩu" and its "Nếu … khớp với một tài khoản" page; "Đặt mật khẩu mới" (`/#reset_token=`) and
  "Đã đổi mật khẩu" ("Đi tới đăng nhập"). Errors are one red centred line above the fields (`.login-error`), as AIRI.
  A password only needs 8 characters (owner: no letter/digit rules), at most 256.
- **`POST /check {email}`** answers `new`, `password` or `no_password` (an account without a password: a Google/GitHub
  account that merged the address, or an email account from the link-only days). Like AIRI this tells whether an
  address has an account; 60 checks an hour per IP slow down probing. `no_password` shows the red line "Email này đã
  có tài khoản nhưng chưa đặt mật khẩu…" and a "Đặt mật khẩu qua email" link to the reset page.
- **`POST /signup {email, password, display_name}`** hashes the password at once and sends "Xác nhận email cho Peto";
  409 if the address already has an account. No account exists until the mail's button is used (`POST /link`). The
  waiting page polls `/status`; the same-browser and other-device rules (request cookie, "Xác nhận đăng nhập" with the
  device label) are unchanged from the link flow, and on approval the row's password hash becomes the account's
  (`set_password(replace=False)`, never over an existing one) and the chosen name its display name.
- **`POST /password {email, password}`** signs in. Wrong or unknown both answer **400** "Email hoặc mật khẩu không
  đúng." (not 401: the frontend reads 401 as an expired session). 10 failures per address and 30 per IP in 15 minutes
  give 429 "Thử quá nhiều lần. Thử lại sau N phút." (AIRI shows "Too many requests" too); a success clears the
  address's count. Counters live in process memory.
- **`POST /reset {email}`** always answers `{ok: true}` and mails "Đặt lại mật khẩu Peto" only when an account exists.
  **`POST /reset/confirm {token, password}`** uses the row once and replaces the password; it does not sign in (AIRI
  sends you to sign in). Reset and signup tokens are not interchangeable (`kind`). Sessions are stateless signed
  cookies, so a reset does not sign out other devices.
- **Storage.** `account_passwords` (owner → `scrypt$n$r$p$salt$hash`, Python's own `hashlib.scrypt`, n=2^14, run in a
  thread). `email_login_links` gained `kind` (`signup` | `reset`; `signin` rows of the link-only deploy are dead) and
  `password_hash`, added by `ALTER TABLE` at startup. Only the newest unused mail of each kind works; rows go after a
  day. Tokens sit after `#` (never in server or Cloudflare logs) and are POSTed by the page; mail scanners only GET.
  The link origin comes only from operator config (`link_origin`).
- **No full address at rest**: `email_hash` (unkeyed SHA-256 of `peto-email-v1:<normalized>`) and the display name
  (the chosen name, else the part before @ without `+tag`). Gmail/Googlemail ignore dots and `+tag`, the listed
  providers ignore `+tag`. Tests scan every table for the address, the tokens, the User-Agent and the password.
- Email accounts have the same rights as Google and GitHub (owner's answer 2026-11-19) and never carry a Discord ID.

### Merging accounts by verified email

Asked by the owner on 2026-11-19 ("tránh mọi người tạo nhiều tài khoản"), after seeing that AIRI links a Google
account and an email account with the same address. `auth._linked_owner(identity, verified_email)`:
- Google now asks for `openid profile email` and uses `email` only when `email_verified` is true. GitHub asks for
  `user:email` and reads `/user/emails` for the primary, verified address (before the token is revoked). Only the hash
  is kept, in `email_accounts` (email → owner; several emails per owner).
- `account_identities` remembers which owner each Google/GitHub identity belongs to, so changing the address at Google
  later does not split the account.
- A brand-new identity whose verified address already belongs to an account (email, Google or GitHub) signs into that
  account. An address nobody has is attached to the identity's owner. An email login looks the address up the same
  way, so "Google first, email later" lands in the Google account (with its name and avatar).
- **Accounts that existed before merging keep their owner.** An identity that already has a `users` row keeps it.
  If its verified address belongs to an **email** account (the person signed in by email before this old Google or
  GitHub account logged in again with the email scope; the owner hit exactly this on 2026-11-19), that email account
  is folded in: `storage.email_login.move_email_account` moves every row with an `owner` column in one transaction,
  keeps the target's row where a unique constraint clashes (profile, avatar, fixed memory entries, settings), handles
  `users` last (avatars and player favourites cascade from it), and re-points the email hashes. The old email session
  then reads as signed out. Two old Google/GitHub accounts of one person are never merged automatically.
- **Discord never merges.** Discord asks for no email; `claim_email` refuses a `discord:` owner, so no email or Google
  login can ever resolve to a Discord ID and reach the bot's memory gateway.
- Existing Google and GitHub users see the provider's consent screen again once, for the new email permission.

**Guest login was removed on 2026-10-06** (the owner's call): anyone could mint unlimited guest accounts and spend the
web's AI quota, and a per-guest counter could be dodged by clearing cookies. GitHub login replaced the "Khách" button.
- `guest` left `config.PROVIDERS`, so an old `guest:` cookie fails `session_owner` and the visitor is signed out. Agent
  tokens of an owner that no longer parses are refused as expired (`device_auth`).
- GitHub uses its own OAuth App (`GITHUB_LOGIN_CLIENT_ID/SECRET/REDIRECT_URI`), separate from the Kết nối GitHub App
  (`PETO_GITHUB_*`). It asks only for `user:email` (since 2026-11-19, to merge accounts by verified email; see "Merging accounts by verified email"). The owner is `github:<numeric id>`; `login` can change,
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
Google, GitHub and email accounts and `features/chat/prompt_context.py` skips the memory gateway entirely for them. That
is what keeps open registration from exposing members' long-term memory.

### Deleting an account (Settings → Tài khoản → Xóa tài khoản)

Owner's decisions (2026-11-20): typed confirmation ("XÓA"), deletion is immediate (no grace period), admin accounts
(`PETO_OWNER_ACCOUNTS`) are blocked. The panel follows the owner's design: warning title, list of what goes, the Peto
art on the right (sad; head down once "XÓA" is typed; happy while the pointer or focus is on "Hủy"), from
`frontend/public/account-assets/peto-delete-*.webp`, cut from the owner's sheet.

- `POST /api/account/delete` (`features/accounts/deletion.py`) with `{"confirm": "XÓA"}` (case, spaces and combining
  accents ignored). 400 for anything else, 403 for an admin account, 409 while one of its chat turns is running (a
  `running` row updated in the last 10 minutes; older ones are orphans from a restart).
- It deletes every row whose table has an `owner` column, in one `BEGIN IMMEDIATE` transaction (children such as
  messages, document versions and exports follow by `ON DELETE CASCADE`), including `users`, `account_identities`,
  `email_accounts` and `account_passwords`, so signing in again with the same Google/GitHub/email starts an empty
  account. Then it removes the upload folders of its conversations and Imagine jobs and the listed attachment and image
  files, only inside `PETO_UPLOAD_DIR`. `usage_events` has no owner and stays. The Discord bot's memory is elsewhere
  and read-only, so it is untouched (the panel says so for Discord accounts). GitHub connector tokens are only deleted
  locally, as with "Ngắt kết nối" (not revoked at GitHub).
- Session revocation: cookies and Companion AIRI sync tokens are signed owner keys with a timestamp, with no session
  store. Deletion writes `deleted_accounts(owner_hash, deleted_at)` (SHA-256 of the owner, not the owner itself), and
  `auth.live_session_owner` / `airi_sync.live_token_owner` refuse anything signed before that moment. They back
  `current_owner`, `/api/auth/me`, the AIRI gateway and AIRI sync, so another browser still signed in gets 401 and
  cannot write into the deleted account. Marks older than the longest session or token lifetime are pruned on the next
  deletion. Agent devices are rows in `agent_devices`, so they stop working with the delete itself.
- The Privacy Policy and Terms (`/docs/quyen-rieng-tu/`, `/docs/dieu-khoan/`) now point to the button instead of
  "email the operator", dated 20/11/2026.

### User profile (Settings → Hồ sơ)

`features/accounts/profile.py` stores a self-written profile per owner in `user_profiles` — kept apart
from `users`, which is overwritten from Discord/Google/GitHub on every login: full name, what
Peto should call them, an occupation code from a fixed server-side list, and free-form
instructions (1500 chars). `features.chat.prompt_context._build_system_prompt` re-reads it on **every** turn and
appends `persona.build_profile_context` after the memory block, so an edit applies to the
very next message. Instructions are fenced with `USER_INSTRUCTIONS_START/END` and copies of
those markers are stripped from user text. Validation errors are Vietnamese 400s, not Pydantic's English 422s.

**How strongly instructions apply (since 2026-11-21, like ChatGPT and Claude custom instructions).** The owner's
kawaii instructions were ignored: Grok's own reasoning said "The system rules take precedence", because the old frame
said to follow them only "when compatible with system rules", "Context boundaries" called them preferences that
cannot override product policy, the default Personality and "without forcing slang or emojis" read as system rules,
and the memory block told it to follow saved notes on how to answer. Now `prompts.context.PREFERENCES_RULE` says the
instructions win over the default personality, casual-chat examples, style guidance and saved memory notes for tone,
persona, greetings and sign-offs, emojis and kaomoji, length, formatting, language and forms of address. Only safety,
honesty about being an AI, accuracy, privacy, not naming the model and tool capabilities still apply; a conflicting
part is dropped and the rest followed; a requested persona changes how Peto sounds, not who it is; instructions grant
no permissions and never justify refusing or weakening an answer. Matching edits: "## Personality" opens with "These
are defaults…", "Context boundaries" says preferences may restyle how Peto talks but never grant permissions, the core
emoji line says "…they have not asked for", and the memory block yields to profile preferences. Tests:
`tests/test_custom_instructions.py`.

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

## Custom instructions win over the default personality (2026-11-21, branch `custom-instructions-priority`, not merged)

See "How strongly instructions apply" under "User profile". Not yet tried with a real model: the live site runs the
old prompt until deployed; the plan is to set the owner's kawaii text on a test account and chat with Grok there.


## Delete account (G5) (2026-11-20, branch `g5-delete-account`, not merged)

Built from the owner's design (see "Deleting an account" above). A first try made `current_owner` require a `users`
row; 28 test call sites sign cookies for owners without one, and it would also have logged out any real session whose
row went missing, so revocation uses `deleted_accounts` timestamps instead and changes nothing for live accounts.
Checked on the mock stack: desktop dark and light, phone 375 px with no sideways scroll, the three moods, a real
deletion landing on the login page, and the old cookie then getting 401 on `/api/conversations` and `/api/chat`.


## Email and password like AIRI (2026-11-19, branch `email-login-fixes`)

After hearing why an email login needed a new mail each time, the owner sent AIRI's create-account, welcome-back,
forgot, reset and "too many requests" pages and asked for the same, with a password that only needs 8 characters. Built
as described in "Email login (email and password, like AIRI)"; the link-only sign-in for existing accounts is gone.
- Backend: `/check`, `/signup`, `/password`, `/reset`, `/reset/confirm` in `features/accounts/email_login.py`;
  `account_passwords` and the `kind`/`password_hash` columns in `storage/email_login.py`. `move_email_account` also
  carries the password of a folded-in email account.
- Frontend: `LoginScreen.tsx` (six steps), `ResetPasswordScreen.tsx`, `passwordRules.ts`, `emailLink.takeResetToken`;
  API helpers `checkEmail`, `signUpWithEmail`, `signInWithPassword`, `requestPasswordReset`, `confirmPasswordReset`.
- Tests: `test_email_login.py` (47), `App.test.tsx` login block, `login.spec.ts` (5 tests × PC/mobile, 12 screenshots
  each project).
- Not built: setting or changing a password from Settings while signed in (AIRI mentions it); Google/GitHub users set
  one through "Quên mật khẩu". Signing out other devices after a reset needs session versioning.

## Email login fixes after the owner's real test (2026-11-19, branch `email-login-fixes`)

The owner tried it on the live site: an email login and their older Google account with the same Gmail address stayed
two accounts, the name showed `tr•••@gmail.com`, and signing in by email after signing out asked for a new mail.
- Split accounts: the email login came first, so it created an email account; the "never move old accounts" rule then
  kept the Google one apart. Now the email account is folded into the Google/GitHub account on its next OAuth login
  (see "Merging accounts by verified email"). A user whose Google session is still open is merged at the next Google
  sign-in, not before.
- Name: the part before @.
- A new mail after signing out is how email-link sign-in works (Slack, Notion, AIRI); see the owner's decision on a
  remembered device, if any, below this entry once taken.
- Tests: `test_email_login.py` (fold-in with data, refusal for non-email sources, display name, old masked name).

## Email login, AIRI-style login page, account merging, Terms and Privacy (2026-11-19, branch `login-email-steam`, not merged)

The owner sent AIRI's sign-in page (email + Continue, "or", Google, GitHub, Steam, Terms line) and asked for it in
Peto, with email via Resend (sending) and Cloudflare Email Routing (receiving), Steam, and Terms/Privacy under `/docs/`
like AIRI. Three mockups (Như AIRI, Thẻ Peto, Tài khoản trước); the owner picked "Như AIRI" and said to drop Steam.
Discord stays: it is the only way to the bot's memory gateway. The same day, in three rounds:
1. A 6-digit code flow; Steam (OpenID 2.0 with `check_authentication`) built, then removed (`e82a874`, `62d28a3`).
2. After seeing it, the owner sent AIRI's link flow (inbox page, mail button, "Email verified" tab): link plus code
   (`b2dfdf7`).
3. The owner found the inbox page too wordy ("bám sát mẫu"), wanted a mail opened on the phone to sign the computer
   in, and asked for Google/email accounts with one address to be one account. Code removed, cross-device sign-in
   with a confirmation step, merging by verified email (see the two sections above).
- Backend: `features/accounts/email_login.py`, `storage/email_login.py` (`email_accounts`, `account_identities`,
  `email_login_links`; the code table of round 1 is dropped at startup), `auth._linked_owner`, config
  `RESEND_API_KEY`, `PETO_EMAIL_FROM`, `PETO_EMAIL_REPLY_TO` (`.env.example`). `conftest` sets a fake Resend key and an
  autouse `sent_emails` fixture that replaces `deliver`, so no test can send mail.
- Frontend: `LoginScreen.tsx`, `EmailLinkScreen.tsx`, `emailLink.ts`, `sendLoginEmail` / `openEmailLink` /
  `emailLoginStatus` in `api.ts`, `App.signedInByEmail`, account labels "Email" / "Đăng nhập bằng email".
  `browser-tests/login.spec.ts` with nine screenshots (sign-in dark and light, inbox, verified tab on PC and mobile;
  the phone's confirmation page).
- Docs: `dieu-khoan` and `quyen-rieng-tu` in `articles.json` (group Trợ giúp), drafted from the code and these notes;
  the owner still has to approve the wording (see `docs-site.md`).
- Tests: backend `test_email_login.py` (same browser, phone confirm, deny, a stranger polling, one use, newer mail,
  expiry, origin, limits, nothing stored, merging both orders, unverified email, old accounts kept, GitHub primary
  email, Discord refused), `test_auth.py` (new scopes); frontend `App.test.tsx` (7 login tests); Playwright
  `login.spec.ts` 6 passed (a second tab of the same context, and a separate "phone" context that confirms).
- Not tried for real: a Resend send from the VPS, delivery to Gmail/Outlook inboxes (spam placement), Google and
  GitHub returning the email with the new scopes, the `CF-Connecting-IP` limit behind the real tunnel (see
  `unverified.md`).

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
