# Not yet tried for real

Gathered on 2026-11-12 from the notes moved out of `CLAUDE.md`: every place that said unverified, untested, not
checked, no live run, chưa thử, chưa kiểm… One line per thing still to try with real models, keys, apps or devices,
with the note file and section that hold the context. The original passages stay in those files. Tick or delete a
line once it has been tried, and record the result in the area's note file. Paid calls need the owner's go-ahead.

## Agent gateway and Peto Harness (`agent-gateway.md`)

- [ ] Install and relaunch through desktop auto-update in the installed ph app (the next release should show Update) — `agent-gateway.md`, "Peto Agent auto-update".
- [ ] Real Grok output for Agent web search: does it list sources and keep to JSON — `agent-gateway.md`, "Peto Agent web search".
- [ ] `/download/` against real GitHub Releases and a real installer build (only a mock GitHub was used) — `agent-gateway.md`, "Peto Agent download page".
- [ ] Whether Grok really refuses WebP/GIF images (the gateway converts them to PNG) — `agent-gateway.md`, "Agent gateway for Peto Harness".

## Admin and operations (`admin-ops.md`)

- [ ] G3.1: run `PRAGMA foreign_key_check` on a copy of the VPS database to list orphan rows left from when foreign keys were off, and decide whether to delete them — `admin-ops.md`, "One SQLite connection helper (G3.1)".

## Accounts and memory (`accounts-memory.md`)

- [ ] How well a real model sorts and routes memory notes into entries (only the mock has run) — `accounts-memory.md`, "Memory (Brain)".
- [ ] Automatic memory extraction under the grounding contract with a real model (fake model/gateway only) — `accounts-memory.md`, "Conservative automatic memory attribution".

## Web Chat (`chat.md`)

- [ ] Real Claude prompt-cache hit rates on the admin page after deployment — `chat.md`, "Model choice (Peto and GPT-6)".
- [ ] Grok answer quality and real token counts under the English Chat prompt — `chat.md`, "English model instructions, provider overlays, no roleplay mode".
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
- [ ] G1.1 real cache hit rates per provider (`cached_tokens` on the admin page: Grok with `prompt_cache_key`, Luna, Haiku) on a second turn and inside a tool loop — `chat.md`, "Web Chat stable prefix (G1.1)".
- [ ] G1.1: do Grok, Luna and Haiku still answer the time correctly and use the right tools when the runtime block sits after the user's message (developer item for Luna, mid-conversation system message for Haiku, fenced part of the user message for Grok) — `chat.md`, "Web Chat stable prefix (G1.1)".
- [ ] G1.1: real xAI and OpenAI acceptance of the trailing user/developer runtime items after `function_call_output`, and real Anthropic acceptance of system messages after `tool_result` and of replayed Haiku thinking across tool rounds (only fake services that apply the documented rules) — `chat.md`, "Web Chat stable prefix (G1.1)".
- [ ] G1.1: does a real model resist a user-typed `<peto_runtime>` lookalike and use the newest appended snapshot after a mid-turn manifest change — `chat.md`, "Web Chat stable prefix (G1.1)".

## Documents (`documents.md`)

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

- [ ] Chat image viewer touch feel on physical Android/iOS — `frontend.md`, "Frontend conventions".
- [ ] A live GitHub connection once the GitHub App and secrets are set up — `frontend.md`, "Frontend conventions".
