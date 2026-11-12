# Frontend notes

Scope: Static serving and routing, Settings and the account menu, the Motion setting and frontend conventions. Visual rules are in `DESIGN.md`.

Moved out of `CLAUDE.md` on 2026-11-12 (G0.2). Write new notes for this area here, not in `CLAUDE.md`. Current behaviour comes first, then the dated log, newest first.

# Current behavior

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

The index page is not served verbatim: the handler inserts `og:image` (plus alt text)
from `app_identity.get_app_identity()` — the bot's Discord CDN icon, already the absolute
URL Open Graph requires. That keeps the domain out of the build and makes link previews
follow the bot icon. The other preview tags are static in `frontend/index.html`; crawlers
such as Discordbot never run JS, so they must stay in the HTML. Because the home page now
awaits `get_app_identity`, that function must never raise.

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
