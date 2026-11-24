# Not yet tried for real

Gathered on 2026-11-12 from the notes moved out of `CLAUDE.md`: every place that said unverified, untested, not
checked, no live run, chưa thử, chưa kiểm… One line per thing still to try with real models, keys, apps or devices,
with the note file and section that hold the context. The original passages stay in those files. Tick or delete a
line once it has been tried, and record the result in the area's note file. Paid calls need the owner's go-ahead.

## Agent gateway and Peto Harness (`agent-gateway.md`)

- [x] G2.2 auto effort (checked 2026-11-18 on `7e14586`: low, low, medium, medium as expected, from `meta` and `chat_timing`): after deploying, send on Tự động a greeting, "thanh toán hóa đơn", "so sánh ưu nhược…" and a message with a file, then read `effort` of the newest `turn` rows in `usage_events` (expect low, low, medium, medium) — `chat.md`, "Auto effort by whole words…".
- [x] Install and relaunch through desktop auto-update in the installed ph app (2026-11-17, .20261107.1 → .20261117.1: works in ~42 s when left alone; the first try failed because the app was reopened mid-install; sign-in kept across the domain change) — `agent-gateway.md`, "First real auto-update".
- [ ] Real Grok output for Agent web search: does it list sources and keep to JSON — `agent-gateway.md`, "Peto Agent web search".
- [x] DSH's update status window and relaunch with the rc.3 installer, run as an update runs it over .20261117.2 (2026-11-17: window for the whole install, app reopened by itself, still signed in, steps card shown) — `agent-gateway.md`, "DSH 0.2.2-rc.3 merged into ph".
- [ ] The rc.3 update through the Update button once v0.2.2-rc.3.20261117.1 is published, and the status window title reading Peto Agent in that rebuilt installer — `agent-gateway.md`, "DSH 0.2.2-rc.3 merged into ph".
- [ ] Gzip request bodies through Cloudflare on the deployed gateway with a real ph build (tested only through httpx in-process and pi-ai against a local fake gateway), and whether long sessions stop failing with `Connection error` — `agent-gateway.md`, "Gzip request bodies on the agent endpoints".
- [ ] `/download/` against real GitHub Releases and a real installer build (only a mock GitHub was used) — `agent-gateway.md`, "Peto Agent download page".
- [ ] Whether Grok really refuses WebP/GIF images (the gateway converts them to PNG) — `agent-gateway.md`, "Agent gateway for Peto Harness".
- [ ] A long file write in the installed ph app with real Grok/GPT/Claude: no cut at 5 minutes (Grok is silent while writing; empty keepalive deltas every 60 s keep ph waiting), GPT/Claude show tool-call pieces while writing, and a long output really completes behind Cloudflare. First try on `dc25fa0` with Grok: `stalled` after 300 s of silence — `agent-gateway.md`, "Grok goes silent while writing tool calls".

## Admin and operations (`admin-ops.md`)

- [ ] The usage ledger on the VPS after deploy: rows appear for Chat, Agent, Companion (AIRI) and Imagine of the signed-in
  account, the 7-day window opens on first use, and Settings → Mức dùng matches the /admin cost for the same week —
  `admin-ops.md`, "Weekly usage pool, step 1".
- [x] G3.1: run `PRAGMA foreign_key_check` on a copy of the VPS database to list orphan rows left from when foreign keys were off, and decide whether to delete them (2026-11-13: the owner ran it on a backup copy; 0 orphan rows, nothing to delete) — `admin-ops.md`, "One SQLite connection helper (G3.1)".

- [x] One main domain (checked 2026-11-17 on `b37be81`: old-domain pages 302 to peagy.com and stay signed in; `/api/health`, `/api/agent/v1/models` and `install.ps1` answer on the old domain): after setting `PETO_CANONICAL_ORIGIN=https://peto.peagy.com` on the VPS and deploying, open `https://peto.pearto.shop/chat/…` in a browser (lands on peagy.com) and check that Peto Agent/Harness and `irm https://peto.pearto.shop/install.ps1` still work — `admin-ops.md`, "One main domain".
- [x] G3.3 (CI #148 green on 2026-11-14: 325 browser tests passed, 0 flaky): the Playwright PC/mobile suite on CI (windows-latest) after the App.tsx split. It had been cancelled at 15 minutes since run #129; branch `ci-browser-tests` splits it into four jobs and fixes the stale specs and screenshots (local: 320 passed, 5 load-related failures that pass on rerun). Confirm the first CI run after merging — `frontend.md`, "Lint and App.tsx split (G3.3)".
- [x] G3.4 (checked 2026-11-13 on `144ee85`: signed in, Chat with web search and Stop, Companion with Live2D, a reply and the YouTube player, Imagine library; 0 `csp_violation`, 0 errors): after deploying, browse the real site (Chat, Companion with Live2D and the player, Imagine, Docs, phone too) and run `sudo journalctl -u peto-web --since today | grep csp_violation`; expect nothing before enforcing the CSP (signed-out pages checked 2026-11-13: only Cloudflare's injected beacon, now allowed; signed-in Chat, Companion and Imagine still to browse) — `admin-ops.md`, "Security headers, CSP report-only (G3.4)".

## Accounts and memory (`accounts-memory.md`)

- [ ] Email login with a real Resend key on the VPS: the mail arrives from `PETO_EMAIL_FROM` at Gmail and Outlook (inbox or spam?), its button opens `https://peto.peagy.com/#email_token=…` and signs in, the waiting tab continues by itself, a phone opening the mail gets "Xác nhận đăng nhập" and the computer then continues, a reply reaches `PETO_EMAIL_REPLY_TO` through Cloudflare Email Routing, and Outlook Safe Links does not spend the link (only a fake `deliver`, a mocked Resend API and mocked routes in Playwright have run) — `accounts-memory.md`, "Email login (email and password, like AIRI)".
- [ ] Email and password end to end on the live site: create an account ("Xác nhận email" mail arrives and signs in), sign out, sign in with the password, "Quên mật khẩu" mail and "Đặt mật khẩu mới", the 429 after 10 wrong passwords — `accounts-memory.md`, "Email login (email and password, like AIRI)".
- [ ] Account merging with real Google and GitHub: the new consent screens (email permission), `email_verified` from Google, `/user/emails` from GitHub, and an email login landing in the Google account of the same address (only mocked providers have run) — `accounts-memory.md`, "Merging accounts by verified email".
- [ ] The per-IP send limit behind the real Cloudflare Tunnel: two phones on different networks each get their own 10 sends an hour (tested only with a fake `CF-Connecting-IP`) — `accounts-memory.md`, "Email login (email and password, like AIRI)".
- [ ] The login page on a real phone: the mail app's in-app browser opening the button link (no request cookie there, so it shows the confirmation page even on the same phone) — `accounts-memory.md`, "Email login (email and password, like AIRI)".

- [ ] Deleting a real account on the live site: an email + Google merged account and a Discord account, the second
  browser being signed out, and the deleted account's upload folders gone on the VPS (mock stack only) —
  `accounts-memory.md`, "Deleting an account".
- [ ] How well a real model sorts and routes memory notes into entries (only the mock has run) — `accounts-memory.md`, "Memory (Brain)".
- [ ] Automatic memory extraction under the grounding contract with a real model (fake model/gateway only) — `accounts-memory.md`, "Conservative automatic memory attribution".

## Web Chat (`chat.md`)

- [ ] Past-chat search with real Luna and Haiku, and Grok not calling it when nobody refers to an earlier chat (Grok
  found and used the right chat on 2026-11-24) — `accounts-memory.md`, "Searching past chats".
- [ ] Asking real Grok "địa chỉ web là gì", "ai làm ra bạn" and a feature question after the About block: it gives
  peto.peagy.com, names PeaGy and the model's company, and opens /docs/ instead of searching — `chat.md`, "Peto knows
  Peto Web".
- [ ] A real disconnect on the live site (phone switching networks or airplane mode mid-answer): the turn finishes on
  the server, the tab shows "Peto vẫn đang trả lời", the text resumes through live sync after reconnecting, and the
  stored answer is complete — `chat.md`, "The turn outlives the HTTP request".
- [ ] Asking real Grok, Luna and Haiku "bạn chạy model gì?" after the 2026-11-23 change: each names its own provider
  and model from the runtime block, and the reasoning no longer argues about hiding it — `chat.md`, "Peto names its
  model when asked".
- [ ] The pinned question while streaming on a real phone (iOS Safari and Android Chrome, keyboard open and closing
  after send) and with real Grok streams, where work-log steps and sources appear above the text — `chat.md`,
  "Sending pins the question to the top".
- [ ] One sidebar row per version group on the live site: "Màu sắc Part 4 và Morioh" (three versions) shows once,
  stays highlighted while ‹ 1/2 › opens an older version, and rename, pin, archive, move and delete act on the whole
  group (tested with the mock provider and unit tests only) — `chat.md`, "One sidebar row per version group".
- [ ] The search-promise fix with real Grok in "auto": a price or comparison question either searches in the first
  round (the new prompt rule) or, after a bare "để mình lục xem…", gets one forced search whose answer replaces the
  promise; how often `announces_search` fires on ordinary replies in the VPS log — `chat.md`, "Promise to search,
  then stop".
- [ ] Custom instructions with real models after the 2026-11-21 frame change: the owner's kawaii text (greeting,
  kaomoji, sign-off) followed by Grok, Luna and Haiku on casual messages, while a technical question stays exact and
  identity rules hold (still Peto, an AI, no model name) — `accounts-memory.md`, "User profile".
- [ ] Live sync between two real devices on the live site, behind Cloudflare: the long `GET /api/chat/live` stream
  stays open past 100 s idle (pings), text arrives as it streams (not buffered), a phone that sleeps reconnects and
  catches up, and the 20-tab limit is never hit by normal use (mock stack in two tabs only) — `chat.md`, "Live sync
  of the Chat tab across tabs and devices".
- [ ] Voice input with real speech recognition: Vietnamese accuracy in Chrome and Edge on Windows, Safari on iPhone
  (permission prompt from the mic button, words while speaking) and Chrome on Android (only a fake recognition class
  has run) — `chat.md`, "Voice input in the composer (micro)".
- [ ] Choosing a microphone in real Chrome and Edge on Windows: the chosen headset is the one transcribed (the
  speech service, not just the meter), and Chrome below 133 or Safari keeps the default microphone (only Chromium's
  fake devices and a fake recognition class have run) — `chat.md`, "Micro and language menu".
- [ ] Real Claude prompt-cache hit rates on the admin page after deployment — `chat.md`, "Model choice (Peto and GPT-6)".
- [ ] Grok answer quality and real token counts under the English Chat prompt — `chat.md`, "English model instructions, provider overlays, no roleplay mode".
- [ ] G2.1: first LIVE run of `python -m evals run --suite chat-core --mode live --allow-paid` (covers the personality, log, reassess and stage-4 lines below); check the printed estimate against the real bill, and whether Haiku/Luna answers at the full Chat output cap fit in 300 s — `chat.md`, "LIVE eval suite `chat-core` (G2.1)".
- [ ] LIVE run of `evals/chat-personality-cases.json`; real tone from the owner's chats — `chat.md`, "Web Chat personality".
- [ ] LIVE run of `evals/chat-log-cases.json` (log workflow) — `chat.md`, "Tools survey and log workflow".
- [ ] Real-model use of the document readback `check` — `chat.md`, "Tools survey and log workflow".
- [ ] Grok code interpreter after deploy: tool choice, overuse, cost and latency — `chat.md`, "Tools survey and log workflow".
- [ ] LIVE run of `evals/chat-reassess-cases.json` — `chat.md`, "Tools survey and log workflow".
- [ ] Long-context summaries with a real model (semantic quality; only mocked providers) — `chat.md`, "Web Chat long context — stage 1".
- [ ] Request-context truthfulness of a deployed model (tests check structure only) — `chat.md`, "Web Chat request context — stage 2".
- [ ] Stage 3 recovery: forced production crashes, in-flight memory-deletion races, second owner, project moves/deletes, physical phone/offline network, usage/billing audit — `chat.md`, "Web Chat recovery and data scope — stage 3".
- [ ] Stage 4 UX on a physical phone and with NVDA/VoiceOver/TalkBack; stage-4 model quality — `chat.md`, "Web Chat UX, evidence and quality — stage 4".
- [ ] Runtime Device Context on physical devices — `chat.md`, "Web Chat automatic Runtime Device Context".
- [ ] Sources panel with a live provider, a physical phone and a screen reader — `chat.md`, "Web Chat sources panel from Grok".
- [ ] Seven Grok UX improvements on a physical phone, a screen reader, Safari and a live provider/VPS — `chat.md`, "Seven Grok-inspired Web Chat UX improvements".
- [ ] Citation rendering on a physical phone and with real model output — `chat.md`, "Web Chat citation rendering".
- [ ] User-message copy on a real phone and in production — `chat.md`, "User-message copy action".
- [ ] G1.1 real cache hit rates per provider (`cached_tokens` on the admin page: Grok with `prompt_cache_key`, Luna, Haiku) on a second turn and inside a tool loop — `chat.md`, "Web Chat stable prefix (G1.1)". 2026-11-13: Luna and Haiku confirmed on turns 2–3 (about 90% read); Grok and tool loops not checked.
- [x] G4.1 (2026-11-13: checked on the real app, desktop and a 375 px phone viewport): on the real app (desktop and phone), a sent message with `*`, `#`, a numbered list, a link and a fenced code block shows as typed, with a link chip and a code block — `chat.md`, "Plain-text user messages (G4.1)".
- [ ] Silent replies (2026-11-13: no error on the real app; the muted line needed a reload, fixed in `silent-reply-live`, not yet seen live): after deploying, "intelligent test: do not reply" sent a few times shows either a short reply or the muted "Peto không viết gì cho lượt này." line, never the error — `chat.md`, "Intentional empty replies are not errors".
- [x] G1.3 (2026-11-13: confirmed on the real app; the cut turn answered in 3.8 s and the summary ran after it; a follow-up lock wait was fixed in G1.3b): in a real conversation past the cut, the reply starts without the summary wait, and the next turn's envelope carries the new summary — `chat.md`, "Chat summary after the reply (G1.3)".
- [x] G1.2 (2026-11-13: Grok conversation cut once at turn 8 and kept the cut and fingerprint for three more turns at 81–86% cache reads): a real conversation past the budget or 200 messages cuts once and then keeps reading the cache on the following turns (`python -m ops.cache_check`), and answers still use the older messages that are now sent verbatim — `chat.md`, "Budget-based history window with a kept cut (G1.2)".
- [x] G1.1c (2026-11-13: Grok turns 2–4 read 92%, 90%, 90% on the real app, was 9%): after deploying, a new Grok conversation reads most of turns 2–4 from the cache (`python -m ops.cache_check --hours 1`, not 1,152 each turn) — `chat.md`, "Grok replays its runtime blocks (G1.1c)".
- [x] G1.1b (2026-11-13: Luna and Haiku confirmed at 87–93% with a stable fingerprint; the real Agent-guide answer was not tried): after deploying, a Luna and a Haiku conversation whose later messages say "peto" or ask for a diagram keep reading the cache (`python -m ops.cache_check --hours 1` shows no "phần đầu đổi" inside one conversation), and the Agent guide still reaches a real "Peto Agent" question — `chat.md`, "Keyword blocks out of the cached prefix (G1.1b)".
- [ ] G1.1: do Grok, Luna and Haiku still answer the time correctly and use the right tools when the runtime block sits after the user's message (developer item for Luna, mid-conversation system message for Haiku, fenced part of the user message for Grok) — `chat.md`, "Web Chat stable prefix (G1.1)".
- [ ] G1.1: real xAI and OpenAI acceptance of the trailing user/developer runtime items after `function_call_output`, and real Anthropic acceptance of system messages after `tool_result` and of replayed Haiku thinking across tool rounds (only fake services that apply the documented rules) — `chat.md`, "Web Chat stable prefix (G1.1)".
- [ ] G1.1: does a real model resist a user-typed `<peto_runtime>` lookalike and use the newest appended snapshot after a mid-turn manifest change — `chat.md`, "Web Chat stable prefix (G1.1)".

## Documents (`documents.md`)

- [x] Diagram titles with a colon (2026-11-13: owner confirmed the earlier Haiku diagram now renders): after deploying, the earlier Haiku diagram "Sơ đồ hoạt động: Quy trình đăng nhập" (and a new one) render in the chat card and the side panel, and PNG/PDF download still works — `documents.md`, "Diagram titles with a colon".
- [ ] Word cover pages in real Word: band rectangle, first-page border, cover heights, pre-filled contents — `documents.md`, "Documents in chat (`create_document`)".
- [ ] Alignment marks inside `m:eqArr` in real Word (currently avoided) — `documents.md`, "Documents in chat (`create_document`)".
- [ ] Generated decks in real PowerPoint — `documents.md`, "Presentations in chat (`create_presentation`)".
- [ ] Generated workbooks in real Excel or LibreOffice — `documents.md`, "Spreadsheets in chat (`create_spreadsheet`)".
- [ ] Edited uploaded workbooks in real Excel — `documents.md`, "Editing uploaded Excel files (`edit_spreadsheet`)".

## Companion (`companion.md`)

- [ ] The seven voice key providers other than Azure Speech with real keys — `companion.md`, "Companion tab and voice relay".
- [ ] CosyVoice through the relay with a real Alibaba key — `companion.md`, "Companion tab and voice relay".
- [ ] Hearing providers with real keys; a real browser recognition service and the owner's physical microphone — `companion.md`, "Companion tab and voice relay".
- [ ] Long-session recovery with a physical Android/iOS lock and live recognition/providers — `companion.md`, "Companion tab and voice relay".
- [ ] Spoken barge-in with physical microphones and real providers — `companion.md`, "Companion tab and voice relay".
- [ ] Push to Talk on a physical phone with a real recognition service (first-syllable loss) — `companion.md`, "Companion tab and voice relay".
- [ ] Companion web search with real Grok — `companion.md`, "Companion web search".
- [ ] MAGIC motion on a physical phone — `companion.md`, "Companion MAGIC motion (`characters/magic/`)".
- [ ] The eight brain providers and Tavily with real keys — `companion.md`, "Companion providers (own API keys, `/companion/settings/providers`)".
- [ ] Real model behaviour with user-written character cards, on physical phones and with real provider keys — `companion.md`, "Companion character cards, stage (a): server (2026-10-25)" and "stage (d)".
- [ ] Card packages against real AIRI, on physical phones — `companion.md`, "Companion character cards, stage (e): import/export (2026-10-26)".
- [ ] Full frontend/backend runs and the Playwright companion/layout specs for the AIRI chat UI (`companion.png` baseline) — `companion.md`, "Companion chat UI from AIRI".
- [ ] AIRI gateway with real Grok: a text turn, whether Grok accepts AIRI's 10 tool schemas and a forced `tool_choice` object, a real tool round trip, `cost_ticks` on `/admin` — `companion.md`, "AIRI Companion: `/companion/` serving and gateway".
- [ ] AIRI gateway with a real image from AIRI's chat (only a generated 8×8 PNG and the mock were used) — `companion.md`, "AIRI Companion: `/companion/` serving and gateway".
- [ ] AIRI's stop button during a real streamed reply behind Cloudflare: provider stream closed and slot freed (checked only with httpx closing the stream and raw ASGI disconnects in tests) — `companion.md`, "AIRI Companion: `/companion/` serving and gateway".
- [ ] The enforced main-site CSP on the deployed site: no `csp_violation … mode=enforce` in the journal in the first
  days, including the admin page, Word/PDF export and Docs on a phone (mock stack only) — `admin-ops.md`,
  "Security headers".
- [ ] `/companion/` (AIRI build) CSP reports on the deployed site after the fork's package 2 build (self-hosted fonts, no `localhost:6121`), phone included — `admin-ops.md`, "Security headers".
- [ ] The fork's "Peto build" workflow on GitHub (never run): corepack pnpm 11 on the runner, the filtered install, the package builds, the downloads of the Live2D SDK and sample models from a cold runner, the build within the runner's memory, the release with its asset and tag, the pruning of old releases; and that no upstream workflow runs in the private fork — `companion.md`, "Deploy", and the fork's `PETO.md`.
- [ ] `deploy/update-companion.sh` against GitHub and on the VPS (only `--from-file`, `--list`, `--rollback` and the refusals ran, in Git Bash on Windows against a temporary root): the release JSON through `python3`, the asset redirect, the size and digest checks, `flock`, a real fine-grained token, `/companion/` following the switched symlink behind Cloudflare without a restart — `companion.md`, "Deploy".
- [ ] The `/companion/` switch (package 5a) on the deployed site: `PETO_AIRI_DIR` on the VPS with a copied `dist`, sidebar and phone drawer into AIRI behind Cloudflare, a real phone, the rollback (unset and restart) — `companion.md`, "AIRI Companion: `/companion/` serving and gateway".
- [ ] The AIRI page's error message and no-retry rule with a real provider error (expired login, real 429/503) behind Cloudflare; checked only with the mock words on a local server — `companion.md`, "AIRI Companion: `/companion/` serving and gateway".
- [ ] AIRI gateway cache with real Grok after the append-only change (`[Context]` in instructions): cached share between user turns (expected close to the previous request's full length, with an occasional miss), a user image turn and a tool round from the real page — `companion.md`, "AIRI Companion: `/companion/` serving and gateway".
- [ ] AIRI page web search with the service "Peto" and real Grok: whether Grok searches when it should, the reply time with a search behind Cloudflare, `search_calls` and the search cost on `/admin` (only the mock `__search__` word ran) — `companion.md`, "AIRI Companion: `/companion/` serving and gateway".
- [ ] The AIRI page's new version notice after a real `deploy/update-companion.sh` on the VPS, behind Cloudflare and on a phone (checked only locally, with the served `index.html` pointed at a copy of the entry script under a new name) — the fork's `PETO.md`, "New version notice".
- [ ] AIRI chat sync on the deployed site: the WebSocket `/api/companion/airi-cloud/ws/v2/chat` through Cloudflare Tunnel (idle timeouts, reconnects), a real phone and a computer on one account, rename and delete from the page (checked only against the server), many chats from earlier builds moving on first load — `companion.md`, "AIRI Companion: chat sync between devices".
- [ ] A browser that already used the React Companion, after the switch: old bookmarks, its local Companion settings, and what visitors expect of their old server-side Companion threads, cards and memory (no migration was built) — `companion.md`, "AIRI Companion: `/companion/` serving and gateway".

## Player (`player.md`)

- [ ] Ducking on real speakers/microphone and on the owner's Xiaomi Android 13 Chrome — `player.md`, "Player — giảm nhạc khi trò chuyện, giai đoạn 4 (2026-10-24)".
- [ ] History and Previous on a real Android phone — `player.md`, "Player — lịch sử nghe và Previous, giai đoạn 3 (2026-10-24)".
- [ ] Resume after F5 on a real Android phone and with other videos — `player.md`, "Player — sửa phát tiếp sau F5 (2026-10-24)".
- [ ] Session save/restore on a real Android phone — `player.md`, "Player — lưu/khôi phục phiên nghe, giai đoạn 2 (2026-10-24)".
- [ ] Clear Queue/Clear All/Undo on a real Android phone — `player.md`, "Player — dọn phiên nghe và hoàn tác, giai đoạn 1 (2026-10-24)".
- [ ] Grade Peto's natural Player replies across many cases and models (no real AI eval yet) — `player.md`, "Companion điều khiển Player — nghiệm thu giai đoạn 4 (2026-10-23)" and "Player — lời đáp tự nhiên, đối chiếu biên nhận (2026-10-23)".
- [ ] Stage 2 Player control changes on a real Android phone — `player.md`, "Companion điều khiển Player — giai đoạn 2 (2026-10-23)".
- [ ] Long-run heat/battery and real speaker/microphone with the Player — `player.md`, "Player library — nghiệm thu giai đoạn 4 (2026-10-23)".
- [ ] Minimizing an Edge window by hand while the Player plays — `player.md`, "Player YouTube trong Companion (2026-10-22)".

## Peto Agent CLI (`agent-cli.md`)

- [ ] A real ChatGPT-plan model call (tools, compact, resume, refresh, revoke) and the real-account run of roadmap §7 — `agent-cli.md`, "Multi-source models: M6 release" and "M5 Continue with ChatGPT".
- [ ] A direct OpenAI-key session doing real work (the owner tested only `peto connect openai`) — `agent-cli.md`, "Multi-source models: M0–M3".
- [ ] `/models` and `/connect` dialogs in a real Windows Terminal and VS Code, with a real key — `agent-cli.md`, "Multi-source models: M4 `/models`, `/connect`, `/usage`".
- [ ] Real provider `context_length` overflow and compaction retry (tests mocked) — `agent-cli.md`, "Model-aware context and Sol 6.1".
- [ ] Token counts of the English tool descriptions — `agent-cli.md`, "English Agent tool descriptions".
- [ ] Durable runtime with a live provider and a physical power loss — `agent-cli.md`, "Durable Agent runtime, inbox and acceptance".
- [ ] Model selection of the `run_python` tool after the server offers `python_exec` — `agent-cli.md`, "Post-GTA continuity improvements".
- [ ] Grok's Agent reply voice under the English instructions, measured with evals — `agent-cli.md`, "Peto Agent (CLI)" (English Agent instructions bullet).
- [ ] Claude wrap-up turn (`tool_choice` none) with a real key — `agent-cli.md`, "Peto Agent (CLI)" (0.25.0 bullet).
- [ ] The OpenCode-style TUI in real Windows Terminal, conhost and VS Code, typing with Unikey/EVKey — `agent-cli.md`, "Peto Agent (CLI)" (0.16.0, 0.22.0 and input-line bullets).
- [ ] Whether real VS Code shows stale panel backgrounds after a resize and leaving the alternate screen — `agent-cli.md`, "Peto Agent (CLI)" (0.19.0 bullet).

## Imagine (`imagine.md`)

- [ ] Multi-image edits on the current xAI account (paid call) — `imagine.md`, "Imagine (image generation)".
- [ ] Phone keyboard, safe areas and touch feel on physical phones — `imagine.md`, "Imagine (image generation)".

## Frontend (`frontend.md`)

- [ ] G4.2: look at a real Chat answer with inline and display formulas (fractions, roots, sums) on desktop and phone after deploy; only a temporary Vite page was checked — `frontend.md`, "One KaTeX version (G4.2)".
- [ ] Chat image viewer touch feel on physical Android/iOS — `frontend.md`, "Frontend conventions".
- [ ] A live GitHub connection once the GitHub App and secrets are set up — `frontend.md`, "Frontend conventions".
