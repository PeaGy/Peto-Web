# Agent gateway and Peto Harness notes

Scope: Peto Harness (ph, the desktop app forked from DeepSeek Harness), the `/api/agent/v1` gateway, the `/download/` page, desktop auto-update and Agent web search.

Moved out of `CLAUDE.md` on 2026-11-12 (G0.2). Write new notes for this area here, not in `CLAUDE.md`. Current behaviour comes first, then the dated log, newest first.

# Dated log (newest first)

## Grok goes silent while writing tool calls (2026-11-15, after deploying `dc25fa0`; not committed/deployed)

The owner's first try after deploying `dc25fa0` (same request, model `peto`) ended with `stalled`: the session log shows
reasoning until 64 s, the lead-in sentence, then no event at all for exactly 300 s. Pulses would have fired had xAI sent
anything, so xAI itself was silent. xAI's function-calling docs: "With streaming, the function call is returned in whole
in a single chunk, not streamed across chunks." So Grok writing a long tool call is minutes of total silence, and two
timers cut it at 300 s: the gateway's silence limit, and pi-ai's own idle watchdog in ph (`llm-pi-ai` adapter
`streamIdleTimeoutMs`, default 300,000 ms, reset only by content events, not `: ping`; a cut there is TIMEOUT and resent).
- `PETO_AGENT_XAI_SILENCE_SECONDS` (default 3,600 = the overall cap, 10–14,400): `StepLimits(service)` uses it for xAI;
  OpenAI and Claude stream arguments and keep `AGENT_STEP_TIMEOUT_SECONDS` (300). The xAI agent HTTP client's read
  timeout follows it (`_http_client(read_seconds)`), else httpx would end the read at 300 s of no bytes.
- Gateway keepalive: `_body` sends, after `KEEPALIVE_SECONDS` (60) without a content event, an empty
  `output_text.delta` into the open message slot (or an empty `reasoning_summary_text.delta` when only reasoning is
  open; else it opens a message slot). pi-ai pushes an event even for an empty delta, so ph's 300 s watchdog keeps
  waiting, invisible to the user; an unused message slot closes as an empty item that `_placeholder` drops on replay.
  Works for installed ph builds without a new release.
- `/api/agent/step`: `step_limits.ticking` wraps `agent_step` and yields `tick` every `STEP_PING_SECONDS` (15) of quiet;
  the CLI gets `: ping` (Cloudflare drops silent streams around 100 s) without the tick extending the silence limit.
- Mock `__viettepim__`: lead-in text, 20 s of silence, then the whole call at once (xAI style).
- Tests: `tests/test_agent_step_limits.py` 19 (Grok silence vs Luna `stalled`, keepalive into the open slot, keepalive
  before any output, CLI ticks not extending silence). pi-ai 1.3.0 against the mock backend (general silence 10 s,
  keepalive scaled to 2 s): `__viettepim__` not cut, pi-ai events at most 2.1 s apart during the 20 s silence, the call
  arrived whole at 20.1 s; `__viettep__` unchanged (60 deltas, max gap 0.3 s). Not checked with real Grok yet.
- Agent admission is one global semaphore (`PETO_AGENT_MAX_CONCURRENT`, queue `PETO_AGENT_MAX_QUEUE` 4); calls can now
  hold a slot for many minutes, so the owner raised the default from 2 to 6 ("Raise to 6"). A value set in the VPS
  `.env` still wins.

## Agent call time limits, live tool calls and big output caps (2026-11-15, owner committed `dc25fa0` and deployed it)

The owner's ph session "Tạo Word từ bài thuyết trình" (model `peto`, Medium) retried 9 times over 45 minutes. Session
log (`~/.peto-agent/sessions/…/session.v4.jsonl.zstd`, concatenated zstd frames): every attempt thought, wrote one
lead-in sentence, then streamed one tool call holding the whole 30-page report as a Python script; the gateway sent tool
calls only at the end, so the app saw ~4 minutes of pings, and `asyncio.timeout(AGENT_STEP_TIMEOUT_SECONDS)` cut the
whole call at 300 s. The failure `timeout: …` matched pi-ai's TIMEOUT class (llm-pi-ai `stream.ts`
`classifyPiAiError` reads the message text), so DSH resent the identical request up to 5 times; each attempt was charged
(output produced). Even uncut, Grok's agent output cap was 8,192 tokens (`XAI_MAX_OUTPUT_TOKENS`, shared with Chat). The
owner asked for the gateway fix and "output caps like the big providers; no interruptions to save money".
- **Output caps (Agent only; Chat keeps its own):** `PETO_XAI_AGENT_MAX_OUTPUT_TOKENS` 128,000 (1,024–500,000; xAI
  publishes no output limit for grok-4.7, only 500K context), `PETO_OPENAI_AGENT_MAX_OUTPUT_TOKENS` 128,000 (catalog
  max), Claude's existing 128,000. `budget.limits` and `_xai_step`/`_openai_step` use them, so `/models` and the CLI's
  context budget report 128,000; requests still clamp to the room left in the context window.
- **Silence, not total time** (`features/agent/step_limits.py`, used by the gateway `_pump` and `/api/agent/step`):
  `asyncio.timeout_at` rescheduled on every `agent_step` event; `AGENT_STEP_TIMEOUT_SECONDS` (300) now means silence,
  `PETO_AGENT_STEP_MAX_SECONDS` (3,600, 60–14,400) caps the whole call. `_responses_step` yields `pulse` every
  `PULSE_SECONDS` (10) while raw provider events flow with nothing to show; the Claude translator's `peto.pulse` counts.
  Failure codes: nothing produced → `timeout` (pi-ai retries, step refunded); output then silence → `stalled`;
  overall cap → `step_too_long` (asks to split the work). The last two messages avoid the word "timeout" so DSH does not
  resend a charged call. `/step` sends `: ping` comments for pulses (the CLI never had keepalives) and drops tool events.
- **Live tool calls:** `AgentEvent` gained `item`; kinds `tool_start` (call_id, name, id if any), `tool_delta`
  (argument JSON piece) and `pulse`. `_responses_step` maps `response.output_item.added` function_call and
  `response.function_call_arguments.delta`; the Claude translator now emits `call_id` on tool_use and
  `input_json_delta` as `response.function_call_arguments.delta` (Chat ignores both). `ResponseWriter` opens the
  function_call slot at `tool_start` with the final item's exact `call_id`/`id` (pi-ai fixes the tool-call id at
  `output_item.added`), streams deltas, and at `finish` reuses that slot and sends only `arguments.done` plus
  `output_item.done` (pi-ai takes the final item's arguments; Claude's streamed JSON differs in spacing from
  `json.dumps`). A live slot missing from the final output is left open on purpose: pi-ai then refuses the unfinished
  call instead of running a tool with `{}`.
- Mock `__viettep__` (agent mock): a `write` call streamed in 60 pieces over ~15 s.
- Tests: `tests/test_agent_step_limits.py` (14 then), `test_agent_budget.py` caps. Checked with pi-ai 1.3.0's own
  openai-responses client against a mock backend (silence limit 10 s): tool call started at 0.1 s with id
  `call_demo_9|fc_demo_9`, 60 deltas over 15.6 s (max gap 0.3 s), not cut at 15.7 s, full arguments at the end. Not
  checked: real Grok/GPT/Claude streams, the installed ph app, Cloudflare in front of a 20-minute call.
- Deploy: restart backend; no migration, frontend or ph change. Envs optional.

## Peto Agent auto-update (2026-11-07; owner committed `e7f43eb`, deployed it and published v0.2.2-rc.1.20261107.1)

Peto Agent (ph) builds are unsigned, which upstream DSH treats as local builds without an update feed, so installs never
updated. The owner picked "like DSH, unsigned": keep DSH's electron-updater flow (lower-left indicator, download, safe
restart) and serve the feed from Peto Web. ph's half is `PETO.md` "Auto-update" (`01a92ee30c`, `85383837c9`, pushed).
- ph: an unsigned Windows build gets the generic feed `<mandatory-policy origin>/api/agent/desktop/update/win-x64/`,
  channel `stable`; `app-update.yml` has no publisher, so only the installer's SHA-512 is checked.
  `apps/desktop/scripts/peto-release-assets.ts <version>` renames installer + blockmap to
  `Peto-Agent-Setup-<version>-x64.exe` and rewrites `stable.yml`; the owner uploads all three to the GitHub Release.
- Peto Web `features/agent/desktop_update.py`, `GET /api/agent/desktop/update/{target}/{channel}` (public, only
  `win-x64` and `stable.yml`/`nightly.yml`, else 404): reads `stable.yml` of the newest non-draft release that has one
  (download via github.com, redirects only to GitHub's asset hosts, 64 KB cap; up to 3 candidates), requires version ==
  tag, one `.exe` file present in the release with equal size, base64 SHA-512; returns a rebuilt YAML (version, files,
  path, sha512, releaseDate) with absolute GitHub URLs, `public, max-age=60`, cached 10 min (2 on none). PyYAML comes
  with `uvicorn[standard]`. `desktop_release.fetch_releases` is now shared. `PETO_DESKTOP_UPDATES=false` → 404.
  Drafting a bad release stops offering it within 10 minutes; installs never downgrade.
- `/download/` "Có bản mới thì sao?" now says Windows updates itself and builds before 7/11/2026 need one manual
  reinstall. `deploy/OPERATIONS.md` release steps and a "Cập nhật tự động" section updated.
- Tests: `tests/test_desktop_update.py` (12); related backend group 203 passed; `Download.test.tsx` 9 passed.
- Built 0.2.2-rc.1.20261107.1 (feed baked in); its real `stable.yml` passes `_feed`. A copy of the packaged app pointed
  at a loopback stand-in found a newer version, downloaded through GitHub-style redirects, passed SHA-512 and reached
  "ready to install"; install/relaunch not run (would overwrite the owner's install). Real check: after deploy and the
  .1 release, the next release should show Update in the installed app.
- Production checked after deploy: the feed returns that release with GitHub URLs (`nightly.yml` too, mac 404); the
  GitHub installer's sha256 equals the build; blockmap downloads, ranges answer 206. The owner installed .1 by hand
  (installed `app-update.yml` = the feed, updater cache holds the .1 installer). Install/relaunch still unverified.
  Deploy: restart backend + rebuild frontend; no migration.

## Peto Agent web search (2026-11-06; owner committed `9f7fd98` and deployed it; first ph build with it: 0.2.2-rc.1.20261106.5)

ph's `web_search` tool only had DeepSeek's providers (DeepSeek sign-in or key), so Peto accounts had no search. The
owner picked "Peto Web searches for it" and asked for it as close to DeepSeek as possible; ph's half is `PETO.md`
"Web search".
- `POST /api/agent/v1/search` (`gateway.search`): device token; body as the DeepSeek Search API (`query` ≤ 500,
  `count` 1–20 default 10, optional `ori_question` cut to 128, `need_content` ignored); reply `{"results": [{url,
  title, snippet, summary?, date}]}` in that API's shape, `no-store`. Costs `STEP_COST["low"] × peto.step_cost` (1)
  of the daily Agent steps, refunded on any failure; admission slot `agent:<owner>`, 60 s timeout; errors OpenAI-shaped
  like the rest of the gateway. Off with `PETO_AGENT_WEB_SEARCH` / `PETO_WEB_SEARCH_ENABLED` false (503
  `search_disabled`). Usage events: purpose `search`, `search_calls` 1, xAI's reported cost.
- `ai/web_lookup.py`: one xAI Responses call (`AGENT_MODEL`, reasoning low, `tools=[web_search]`,
  `tool_choice="required"`, `include=["web_search_call.action.sources"]`, `store=False`) with a JSON-only prompt.
  Results are only URLs the search returned (`action.sources` plus `url_citation`, normalized, matched ignoring `#…`
  and a trailing `/`); Grok's summary (600 chars) and date (40) are kept, snippet = summary cut to 200; pages the
  search returned but Grok did not list follow with title only. No search call at all is an error. `ai/agent.py`
  `xai_client()` is now shared with `_xai_step`. Mock: two sample results plus an invented URL that must be dropped;
  `__error__` fails.
- Tests: `tests/test_agent_search.py` (14). Real Grok output (whether it lists sources and keeps to JSON) is
  unverified until deploy. Deploy: restart backend; no migration, env or frontend change.

## Peto Agent account card support (2026-11-06; owner committed `8c5fb97` and deployed it)

The owner picked card "B · Thanh hạn mức" (https://claude.ai/artifact/4XMy3XBePSop8KJUthSj1g) for ph's Settings →
Account; the card itself lives in ph (`PETO.md` "Account card"). Peto Web side:
- `GET /api/agent/me` adds `steps_reset_at`: next midnight in `resolve_timezone()` as ISO 8601 with offset
  (`api._steps_reset_at`). The CLI ignores it; ph shows it in the viewer's zone. Test in `test_agent_api.py`.
- `/?settings=<section>` opens Settings at that section after sign-in (`features/settings/settingsLink.ts`, kept in
  sessionStorage across OAuth like `?agent_code=`; unknown sections are dropped). ph's "Manage on Peto Web" opens
  `?settings=agent`. Two `App.test.tsx` cases.
- ph builds before 0.2.2-rc.1.20261106.4 have no account card; ph against an older Peto Web shows no reset time and
  "Manage" lands on the home page.

## Peto Agent download page (2026-11-06, committed `105249d`, not deployed)

Owner picked the "Trưng bày" mockup (https://claude.ai/artifact/2mJz9cfrNXKv55LuQ6sYDQ) for a ph download page like
DeepSeek's /harness/, and GitHub Releases for the installers; on 2026-11-06 they made ph's own repo public to host them. Layout and
motion were measured on deepseek.com/en/harness with REA and live scroll readings; no DeepSeek assets or text copied.
- Public `/download/` (`main.tsx` mounts `features/download/Download.tsx`, its own chunk; `core/static_files.py` serves
  index with its own title/description, no `/api/auth/me` preload, a `<noscript>` text with cached release links only,
  so the HTML never waits for GitHub; `/download/x` stays 404). Uses Docs tokens, fonts, header and the shared theme and
  motion switches (moved from `Docs.tsx` into `docsShared.tsx`: `readLight`, `saveLight`, `useMotion`, `useScrolled`,
  `Switch`).
- Sections: hero with split download button + menu (every installer, macOS "Sắp có" when no .dmg, CLI), meta line
  (version, date, label, size, GitHub notes link), HTML replica of the app (`Showcase.tsx`, `--u` container units, dark
  in both themes), 4 cards with pausable looping demos (files, terminal, Peto account models, Read Only / Workspace
  Write / Full access), 3 install steps with a SmartScreen sketch ("More info" → "Run anyway"; unsigned), CLI card with
  the real `irm <origin>/install.ps1 | iex`, "Có bản mới thì sao?" (reinstall; the installer never touches the Harness
  home, per ph `installer/uninstall.nsh`), closing CTA, footer credit "Dựng trên DeepSeek Harness · MIT".
- Motion (`scrollMotion.ts`, only under `.docs-motion`): blocks with `data-reveal` fade/rise once in view (20/30/40 px,
  closing block blur 10 px, grid rows stagger 90 ms), app window tilts to 5°/0.985 over the first 900 px with a soft
  follow, closing glow grows from 0.85. Motion off shows everything static. No smooth-scroll library (DeepSeek has none).
- Backend `features/agent/desktop_release.py`, `GET /api/agent/desktop/release` (public, `max-age=60`): reads
  `api.github.com/repos/<PETO_DESKTOP_RELEASES_REPO>/releases?per_page=10` without a token, no redirects, 5 s, 2 MB cap,
  cache 10 min (2 min on failure, single-flight). Picks the newest non-draft release (pre-releases count) with an .exe/
  .msi/.dmg; download URLs must be under `https://github.com/<repo>/releases/download/`; sha256 from GitHub's `digest`.
  Any failure → `{"available": false}` and the page offers the CLI. Config default `PeaGy/peto-harness` (public since
  2026-11-06, no release yet); invalid names count as empty. Release steps: `deploy/OPERATIONS.md` "Phát hành bản Peto Agent".
- Copy claims checked against ph. Since 2026-11-07 Windows builds update from Peto Web ("Peto Agent auto-update").
- `GET /api/v0/check_client_update` (`desktop_release.policy_router`) answers ph's mandatory-update check with
  "no forced update" (`code 0`, `biz_code 0`, `biz_data null`); ph builds name Peto Web as that origin. Without it the
  app only records an error and retries with backoff. Code 40005 with `show_content` would force an update.
- Tests: backend `test_desktop_release.py` (10) and 4 new `test_static_files.py` cases; frontend `Download.test.tsx` (9).
  Checked on a mock stack (fake GitHub through `httpx.MockTransport`) in headless Chromium at 1440 and 390 px, dark and
  light, release present and absent: no console errors, every block revealed, no horizontal overflow. No real GitHub
  call, no real installer build. Deploy: rebuild frontend + restart backend; no migration.

## Agent gateway for Peto Harness (2026-11-05; owner committed `e29858f` and deployed it)

The owner forked DeepSeek Harness as the desktop app for Peto Agent ("ph", `~/Downloads/peto-harness`, private repo
PeaGy/peto-harness, branch `peto`; its `PETO.md` holds the fork's scope). ph writes its own system prompt and tools, so
`/api/agent/step` (server-owned prompt and schemas for the Python CLI) cannot serve it. Owner's decisions: OpenAI
Responses protocol, no Peto prompt injected, steps charged like the CLI, open to every account (no owner-only gate).
- `features/agent/gateway.py`, router `/api/agent/v1`: `GET /models` (account's Agent models, `id` = catalog key,
  `display_name`, `context_window`, `max_output_tokens`, plus Peto's own `reasoning_efforts`, the model's
  `supported_efforts`, added after `e29858f` so ph offers only real levels; not deployed yet) and `POST /responses`
  (stream only). Auth is the CLI's
  `device_auth` (Bearer `peto_…` from the device flow); quota is `STEP_COST[effort] × step_cost` on the same daily cap,
  refunded when nothing was produced. Calls `ai.agent.agent_step` with the app's instructions/tools, web search off.
  `agent_step` gained an optional `tool_choice` (auto/none/required; Claude only honours none).
- Input: leading `system`/`developer` messages (pi-ai's form) become `instructions`; later ones become a user message
  prefixed `System update:`. Item types message/function_call/function_call_output/reasoning only; function tools only;
  user images checked like `/step`. Efforts clamp to the nearest the model supports (pi-ai has `minimal`).
- Output: the gateway synthesizes standard Responses SSE (`response.created`, `output_item.added/done`,
  `output_text.delta`, `reasoning_summary_text.delta`, `function_call_arguments.*`, `response.completed` with usage)
  from `agent_step` events, identical for xAI, OpenAI and the Claude translator. Live slots open in arrival order, so a
  reasoning item only present in the final output can land after text in the app's history; `_reasoning_first` moves
  reasoning to the front of each model turn on input. Empty slots are closed with `rs_peto_…`/empty items, which the
  gateway drops when sent back.
- Errors are OpenAI-shaped `{"error": {...}}` with `x-should-retry`: quota 429 `insufficient_quota` (no retry),
  queue 429, retryable provider errors 503, context overflow 400 `context_length_exceeded` (DSH compacts on it). The
  handler waits up to 15 s for the first event so early failures get real HTTP statuses, then streams with `: ping`
  comments every 15 s (Cloudflare drops silent connections). Failures after output end in `response.failed`.
- Item cap (2026-11-06, owner committed `55a2d1e` and deployed it): the gateway has its own `MAX_ITEMS` of 10,000;
  `/step` keeps 300. The owner's long ph session failed on 300 items: each tool call adds about 3 items, DSH compacts
  only at 80% of the token window (400K for `peto`), and its overflow-recovery summary resends nearly the whole region,
  so it hit the same cap and the session stayed stuck. Anthropic documents 100,000 messages per request; OpenAI and xAI
  document no item cap, only tokens. Over the cap it is still `context_length_exceeded`, now saying to open a new
  session.
- Images (2026-11-06, owner committed `968f600` and deployed it; owner picked matching ph over lowering it): ph resends every past image
  and offloads the oldest only past its own defaults, 50 images or 20 MB of base64 per request (`llm-pi-ai`
  `DEFAULT_MAX_REQUEST_IMAGES`, `compaction-image-offload`), so the gateway's old 8 (shared with `/step`) stuck any
  session from the 9th pasted image on. The gateway now has `MAX_IMAGES` 50 and `MAX_REQUEST_BYTES` 32 MB
  (`_read_body` takes a limit; `/step` keeps 8 images and `PETO_AGENT_MAX_REQUEST_BYTES`). Providers allow more: xAI no
  image count limit, OpenAI 500, Claude 100 or 600. Images in tool results (pi-ai sends `function_call_output.output` as
  input_text/input_image parts) are now checked like pasted ones (data URL, magic bytes, 3 MB) and counted; before they
  were neither, and `ai/claude.py` passed the parts raw into `tool_result`, which Claude rejects.
  `features/agent/gateway_images.prepare` (run in a worker thread before the step is charged) turns such outputs into
  text and puts their images in one user message right after the run of outputs (the CLI's `tool_images` shape, which
  all three services take), then per service: xAI documents only JPG/PNG, so WebP/GIF become PNG; Claude limits each
  image to 2000×2000 px once a request has more than 20 images, so larger ones are shrunk then. Images Pillow cannot
  read pass unchanged; conversions are cached by hash (24 entries). Web Chat and the CLI still send WebP/GIF to Grok
  unchanged; whether Grok really refuses them is unverified (no live call). More image tokens per step: Luna and Haiku
  bill the owner's API accounts.
- Tests: `tests/test_agent_gateway.py` (26), `tests/test_gateway_images.py` (6); with agent_api, models, agent_tool_features, agent_bundle, claude and
  admin 194 passed. Checked end to end with pi-ai 1.3.0's own `openai-responses` client against a mock backend: text,
  thinking, a tool call and its result round-tripped, replay accepted. Deploy = restart backend; no migration, env or
  frontend change. After deploying, the owner signed in from ph's Welcome (dsh-peto-account) and chatted with `peto`
  through the gateway on 2026-11-05. Tool calls confirmed on 2026-11-06 with the installed app (0.2.2-rc.1.20261106.2):
  model `peto` read two files, edited one and ran a test command in one turn (4 steps, 47.2K tokens, 54% cache hit).
