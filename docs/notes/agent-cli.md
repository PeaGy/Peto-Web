# Peto Agent CLI notes

Scope: The Peto Agent CLI (`agent-cli/`), its `/api/agent/step` backend, TUI, tools, browser, evals, durable runtime and multi-source models.

Moved out of `CLAUDE.md` on 2026-11-12 (G0.2). Write new notes for this area here, not in `CLAUDE.md`. Current behaviour comes first, then the dated log, newest first.

# Current behavior

### Agent/CLI planning context (from "Language convention")

Agent/CLI planning context is recorded in [PETO_AGENT_PLAN.md](PETO_AGENT_PLAN.md).
The clarified direction is a Windows CLI that runs the loop and executes local project tools, with VPS
authentication, step limits and model calls (first version: "Peto Agent (CLI)" below). Docker is optional; web
Work is later scope.
It distinguishes agreed direction from open implementation choices and does not
authorize deployment. Consult it when continuing Agent/CLI discussions or work.

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

# Dated log (newest first)

## Multi-source models: M6 release (2026-10-21; CLI 0.33.3 source)

The owner confirmed a real ChatGPT sign-in on 0.33.2 and asked for the next step. M6 per the roadmap; user/ops guide in
`agent-cli/docs/model-sources.md` (sources, quota, disconnect, disabling, backups/rollback, live-tested vs mock).
- `tests/test_acceptance_sources.py`: roadmap §7 as a deterministic test for both `openai-key` and `chatgpt-plan`
  (fake Peto and OpenAI on 127.0.0.1): Peto fixes `add`, the next `/step` is refused (out of steps), `/model gpt-6-luna`,
  the direct source fixes `mul` and runs an independent check, `/compact` on the new source, reopen and `/resume`, check
  again. Asserts no `/step` after the switch, the check ran exactly twice, saved source/connection, secret only in DPAPI.
- `migration.py`: on a CLI version change `main()` copies `config.json`, `connections.json`, `permissions.json` and the
  shared `AGENTS.md` to `<profile>/backups/<time>-<old>-to-<new>/` (keep 5; never credentials or sessions), then
  writes `cli_version`/`config_schema` (2). Prints nothing (keeps `peto models --json` clean).
- `connections._write` keeps rows it does not understand (newer providers) and refuses to overwrite a newer file
  version; 0.31 and older still drop ChatGPT rows when they rewrite the file, which the backups cover.
- Disable switch: backend `PETO_AGENT_DISABLED_SOURCES` (validated against `openai-key`, `chatgpt-plan`) → `/me`
  `disabled_sources`; local `disabled_sources` in `config.json`. Catalog hides those models, a default on a disabled
  source falls back to Peto with a notice, `/connect` and `peto connect` refuse with `OFF_MESSAGE`; connections, secrets
  and sessions stay, and re-enabling restores the old default.
- Web chat Agent guide mentions own sources (`peto connect openai|chatgpt`, `/connect`, `/models`) and never asks for
  keys; `/connect`/`/models` trigger it. Installer test: every `peto_agent/**/*.py` is in the wheel; the clean install
  imports every module and runs `peto models --json` without a traceback.
- Full CLI 755 passed in one run (after `leaked()` in `test_direct_source.py` skips SQLite `-shm` files, which a
  live journal locks; one earlier run failed there by timing); backend Agent/model/schema/prompt/installer 207 passed.
- Not done: a real ChatGPT-plan model call (tools, compact, resume, refresh, revoke) and the real-account run of §7.

## Multi-source models: M5 Continue with ChatGPT (2026-10-21; CLI 0.33.2 source)

The owner approved M5 from an OpenCode "Connect OpenAI" screenshot. Rereading OpenAI's docs corrected M0: the open-source
local path needs no requested client ID; each account registers dynamically (`client_id=dynamic_agent_client`, the
callback returns the issued ID; no client secret). "Request a client ID" is the commercial-partner waitlist. Owner's
picks: verify the RS256 ID token with the standard library instead of adding `cryptography`, and keep OpenAI's exact
English strings ("Continue with ChatGPT", "Use your ChatGPT plan", "Using ChatGPT plan", "Manage usage", "You're using
your ChatGPT plan"/"Got it") with Vietnamese around them.
- `jwt_rs256.py`: verify-only RSASSA-PKCS1-v1_5/SHA-256; recomputes the full EMSA encoding and compares bytes, rejects
  keys under 2048 bits, even exponents, `alg` other than RS256.
- `chatgpt_auth.py`: endpoints from `auth.openai.com/.well-known/openid-configuration`; persistent
  `ext_agent_host_id` as `urn:uuid:<UUIDv4>` in `config.json` (the first build sent "peto-…" and OpenAI answered
  `invalid_authorize_request` on that param; a malformed stored value is replaced once; the fix first shipped still
  numbered 0.33.0, so installed copies never updated: always bump the version with a CLI fix, now 0.33.1);
  the owner's first real sign-in then reached the browser callback but the code exchange failed with TLS "certificate
  has expired": their Windows intermediate (CA) store holds the old ISRG Root X2 cross-signed by X1 (expired
  2025-09-15), Python loads that store as trust anchors and OpenSSL prefers it over the valid X2 auth.openai.com sends
  (Let's Encrypt YE2 chain; api.openai.com uses Google Trust Services and was unaffected, Edge builds the chain itself).
  `transport.tls_context()` now loads the Windows CA+ROOT stores like Python (same server-auth filter, same verify
  flags) but skips expired certificates (`not_after` reads DER); an expired server certificate is still refused
  (checked against expired.badssl.com). OAuth TLS failures get their own message. CLI 0.33.2; fresh PKCE S256/state/nonce; `Callback` on `127.0.0.1` (port 1455 else any) opened
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
  browser tab on the fake loopback URL. Full CLI run (0.33.2) 748 passed in one run; backend installer/bundle 9 passed. Not yet
  accepted with a real ChatGPT account, which is M5's completion criterion.

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
