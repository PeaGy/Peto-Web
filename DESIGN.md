# DESIGN.md — Peto Web frontend conventions

This file records **what the interface actually does**, taken from the existing CSS and components (2026-10-11, after
cleanup passes the same day), so new frontend work matches the small details: colours, type sizes, radii, control
heights, motion and Vietnamese UI copy. Every value below exists in the code; if you need a value that is not here,
copy it from the nearest existing component instead of inventing one.

Precedence when sources disagree:

1. The owner's screenshots and explicit requests.
2. Dated owner decisions in `CLAUDE.md` (Imagine, Companion, Settings, Docs sections).
3. This file.
4. General industry habits.

If new code deliberately departs from this file, update this file in the same commit.

The UI language is Vietnamese (see §9). This file is in English so agents parse it reliably; quoted UI strings stay in
Vietnamese.

## 1. Principles

- **Flat, neutral greys, one accent.** `--accent` is the text colour: white on the dark theme, black on the light
  theme. There is no brand colour for primary buttons and no decorative gradient in the app. References: Grok, Claude,
  ChatGPT.
- **Peto's answers have no bubble.** They run the full column width like a document; only user messages sit in a
  bubble.
- **Companion follows Project AIRI** (character stage, its own `--stage-*` palette). **Docs (`/docs/`) has its own
  design system** (`--docs-*`, `features/docs/docs.css`). Neither borrows decoration from Chat, and Chat does not
  borrow from them.
- **Do not add** new navigation rails, decorative motion, or buttons for features that do not exist. The app's real
  sidebar is always the only sidebar.
- **New UI starts as mockups** (the `prototype` skill in `.claude/skills`) for the owner to pick from; code comes after.
  For motion, follow the `emil-design-eng` skill.

## 2. Colour

### Core tokens (`shared/styles/base.css`)

Dark is the default on `:root`; light lives on `:root[data-theme="light"]`.

| Token | Dark | Light | Used for |
| --- | --- | --- | --- |
| `--bg` | `#141414` | `#ffffff` | Page background, input background inside the text-edit dialog |
| `--panel` | `#1a1a1a` | `#f9f9f9` | Sidebar, composer, cards, dialogs, composer option menus, Dropdown lists |
| `--panel-2` | `#262626` | `#efefef` | Hover/selected rows, chips, secondary buttons, Settings inputs |
| `--line` | `#2b2b2b` | `#e3e3e3` | 1px borders and dividers |
| `--text` | `#ececec` | `#0d0d0d` | Primary text |
| `--muted` | `#9b9b9b` | `#6b6b6b` | Secondary text, section labels, resting icons |
| `--accent` / `--on-accent` | `#ffffff` / `#141414` | `#0d0d0d` / `#ffffff` | Primary buttons, focus rings, hover borders |
| `--user` | `#262626` | `#f0f0f0` | User bubble |
| `--danger` | `#ff8a8a` | `#c22f45` | Errors and destructive actions |
| `--code-bg`, `--inline-code`, `--hl-*` | | | Code blocks, inline code, syntax colours |
| `--menu-bg`, `--menu-line`, `--menu-hover`, `--menu-shadow` | `#242424`, `#313131`, white 7% | `#ffffff`, `#e3e3e3`, black 5% | Action menus (§8), Settings navigation hover |
| `--seg-bg`, `--seg-on` | | | Segmented control |
| `--panel-3` | `#303030` | `#e4e4e4` | Hover background of buttons that already rest on `--panel-2` |
| `--tooltip-bg`, `--tooltip-fg`, `--tooltip-muted`, `--tooltip-shadow` | `#2f2f2f`, `#f5f5f5`, `#a3a3a3` | `#1f1f1f`, `#ffffff`, `#a8a8a8` | Button tooltips (§8); dark on both themes, like Grok |
| `--overlay-soft` | | | File-drop overlay |
| `--shadow` | | | Composer, composer option menus |
| `--dialog-shadow` | | | Dialogs, Dropdown lists, the history search dialog |
| `--shadow-strong` | | | Mobile sidebar drawer |

Rules:

- **Always use tokens.** A new token is declared in **both** theme blocks, next to its group, with a Vietnamese
  comment.
- **Theme follows the `data-theme` attribute, never a media query.** The inline script in `index.html` sets it before
  React runs (key `peto-theme`); the "Theo máy" choice is resolved to `light`/`dark` in JS
  (`usePreferencesPersistence.ts`). App CSS never uses `@media (prefers-color-scheme)`. JS that needs the theme reads
  `document.documentElement.dataset.theme`.
- **Input focus borders** are mixed with `color-mix(in srgb, var(--text) N%, var(--line))`: 24% for the composer, 30%
  for Settings inputs, 45% for an open Dropdown. A new input picks the value of its closest relative.
- **Modal backdrops** are `rgba(0, 0, 0, 0.55)` (Settings) to `0.65` (confirm dialogs). The mobile sidebar backdrop
  is `0.45`.

### Scoped palettes

Declared on the area's root class, with their own light values. Never use these tokens outside their area.

| Class | Prefix | Notes |
| --- | --- | --- |
| `.companion` | `--stage-*` | Mobile stage after AIRI: patterned background, translucent teal bubbles |
| `.companion-settings` | `--cs-*` | Companion settings page after AIRI's Settings: cards on `--cs-card`, the allowed Companion teal for hover sweeps and on states |
| `.yt-player` | `--yt-*` | Owner-approved Peto Media Player: retro burgundy/cream desktop window; burgundy full-screen mobile view (2026-10-22) |
| `.adm` | `--adm-*` | Admin page; the three provider colours passed a colour-blindness check on both themes |
| `.docs` | `--docs-*` | Public guides |
| `.chat-image-viewer` | overrides `--text`, `--muted`, `--panel-2`, `--accent` | The image viewer is always dark, even on the light theme |
| Sheet views | `--sheet-*` | Excel-like grid in the document panel |

### Allowed hard-coded colours

Only these places may write hex directly. Any other new colour becomes a token.

- Discord button `#5865f2` (hover `#4752c4`). YouTube red and GitHub marks live in `shared/ui`.
- Companion teal for on/selected states: switch on-state `#219db5` and focus ring `#63bdd0`
  (`companion/characters/controls.css`), the selected expression card (`#219db5`) and character card (`#58bbd0`).
- File-type icons: Word `#3299ed`, PDF `#ec6767`, spreadsheet `#40ac7a`, slides `#df9950`, code `#a18ee8`.
- Loading logo: pink `#ee9dad`, rose `#d97591` (`shared/ui/loading.css`).
- The always-dark image viewer's own palette (`chatImageViewer.css`).
- Peto Media Player's own burgundy/cream palette (`companion/ytplayer/`), matching the owner's approved prototype.
- Charts: a palette checked for colour blindness, never colours picked by eye (see `.adm` in `features/admin/admin.css`).

### Shadows

- Floating surfaces use tokens: `--menu-shadow` (action menus), `--shadow` (composer and its option menus),
  `--dialog-shadow` (dialogs, Dropdown lists), `--tooltip-shadow` (tooltips), `--shadow-strong` (mobile drawer).
- Hard-coded shadows are allowed only for: small raised parts inside a control (switch knob, active segment, active
  connector tab), simulated paper and charts in document previews, the Imagine crop dimmer, Companion stage elements,
  the always-dark image viewer, and the sliding Settings page edge on mobile.

## 3. Type

- **UI font:** `15px/1.6 "Segoe UI", system-ui, -apple-system, sans-serif` on `body`. The app loads no web fonts (Docs
  and exported documents have their own).
- **Code font:** `Consolas, "Cascadia Code", monospace`.
- **Buttons and inputs do not inherit the font by themselves:** always write `font: inherit`, then set `font-size`.

### Size scale in use

| Size | Used for |
| --- | --- |
| 11px | Tiny secondary lines: descriptions in the "+" menu, file sizes |
| 12px | Secondary lines, the note under the composer, the "Đã dừng" tag, copy buttons |
| 12.5px | Settings hints, per-step times in the work log |
| 13px | Sidebar section labels ("Gần đây"), Settings row descriptions, empty hints |
| 13.5px | Chips (effort), the work log, account name, the Save button |
| 14px | Conversation rows, menu items, Dropdown fields, Settings inputs, tables inside answers |
| 14.5px | Sidebar navigation items, Settings row labels and group titles |
| 15px | Default UI text |
| 16px | Answer and message text (`.bubble`, line height 1.7); every input on touch screens |
| 19–20px | Settings page title (19), dialog titles (20) |
| 22px | Greeting, Admin page title |
| 26–30px | Login card (26), centred desktop greeting (30, weight 600, `letter-spacing: -0.01em`) |

Weights: 400 body, 500 labels and navigation, 600 titles and primary buttons, 650 headings and bold text **inside
answers**, 700 avatar initials and file-extension tags.

Rules:

- **Numbers that change over time** (clocks, counters, numeric columns) use `font-variant-numeric: tabular-nums`.
- **Displayed numbers** use Vietnamese formatting via `toLocaleString('vi-VN')` (for example `1.201`).
- **Headings** may use `text-wrap: balance`. A long title in a row is cut with `text-overflow: ellipsis`, and a tag that
  must stay visible next to it (such as "· Nhập vai" on old roleplay chats) gets `flex-shrink: 0`.
- **Chat bubbles** use `overflow-wrap: anywhere`; table cells do **not** (`overflow-wrap: normal`, `min-width: 7.5em`),
  or phone layouts break words into single letters.
- **Answer rhythm** (`features/chat/chat.css`): paragraphs `0.8em` apart, `h1` `1.5em`, `h2` `1.32em`, `h3` `1.15em`,
  blockquotes with a 3px `--line` left border and `--muted` text. Changing it means rechecking formulas, tables and
  code blocks.

## 4. Size, spacing, radius

There is no spacing token. Common values: 2, 4, 6, 8, 10, 12, 14, 16, 20, 24px. Gaps inside a control are 6–12px;
padding inside cards and dialogs is 16–24px.

### Radius by element size

| Radius | Used for |
| --- | --- |
| 6px | Inline code, thumbnails inside chips |
| 7–8px | Small in-row buttons (copy, edit), action-menu items, Dropdown options, conversation rows |
| 9–10px | Settings navigation items (9); icon buttons, inputs, secondary buttons, error notices (10) |
| 11px | Segmented control frame |
| 12px | Code blocks, tables, web source cards, Dropdown lists, **all action menus**, sidebar navigation items |
| 14px | User bubble |
| 16px | Composer option menus, file cards in messages, Admin cards |
| 18px | Composer, Settings dialog, confirm dialogs, login card |
| 20px | Text-edit dialog, history search dialog |
| `999px` | Pills: Send button, effort chip, sources pill |
| `50%` | Avatars, the round "jump to latest" button |

### Control heights

| Element | Size |
| --- | --- |
| Icon button `.icon-btn`, `.menu-btn` | 36×36, radius 10, `--line` border, `--panel-2` background |
| Small in-row buttons (edit message, conversation actions) | 32×32 (36×36 on touch) |
| Close button `.dialog-close` / `.settings-close` | 32×32 / 34×34, radius 9 |
| Sidebar navigation item | 42 high, radius 12 |
| Effort chip | 34 high, radius `999px` |
| Action-menu item / option-menu item / Dropdown option | 36 / 40 / 38 (action and option items are 44 on touch) |
| Settings input, Save button | 36 |
| Dropdown field | 42 (36 inside Settings) |
| Switch | 48×28, knob 22 |
| Composer textarea | min 44, max 180 (`field-sizing: content`) |
| Imagine | 38px desktop controls; details in the Imagine section of `CLAUDE.md` |

**Touch screens: every target is at least 44×44.** Add new classes to `shared/styles/touchTargets.css` inside its
`@media (pointer: coarse)` block; do not enlarge them on desktop.

### Layout widths

| Area | Value |
| --- | --- |
| Sidebar | 260px default, draggable 220–420px, collapsed 64px; phones `min(280px, 86vw)` |
| Sidebar icon axis | 32px from the left edge (centre of the 64px rail); collapsing only narrows the width, icons stay put |
| Message column | max 900px: `padding: 24px max(20px, calc((100% - 900px) / 2))`, 22px between messages |
| Composer | `width: min(940px, 100%)` |
| User bubble | `min(680px, 82%)`, 92% on phones |
| Settings dialog | `min(920px, 100% - 48px)` × `min(700px, 100dvh - 48px)`, 216px section list |
| Confirm / text-edit / history search dialogs | 420 / 600 / 700px, always capped by the viewport (`min(…, 100% - 32px)` or similar) |
| Admin page | max 1180px |
| Main view | keeps at least 360px while the sidebar is dragged |

## 5. Breakpoints and input types

| Breakpoint | Meaning |
| --- | --- |
| `@media (max-width: 720px)` / `@media (min-width: 721px)` | **Main breakpoint.** Below 720px the sidebar becomes a drawer, large dialogs fill the screen, the composer docks at the bottom |
| `1100px` | Document and diagram panels switch from beside the chat to an overlay |
| `600px` | Document panel, sheets, chat tables and the error banner compact |
| `520px` | One-column cards (voice sources, connectors) |

- JS uses the same value: `COMPACT_QUERY = "(max-width: 720px)"` (`characterView.ts`).
- **Do not add ad-hoc breakpoints.** A component that adapts to its own space uses `@container` (Admin tiles do).
- **Gate by input type, not width:**
  - `@media (pointer: coarse)`: 44px targets, 16px input text.
  - `@media (hover: hover) and (pointer: fine)`: every hover style (§6).
  - `@media (hover: none), (pointer: coarse)`: always show controls that otherwise appear on hover.
- Heights use `100dvh`, never `100vh`. Full-screen phone surfaces add `env(safe-area-inset-*, 0px)`.

## 6. Interaction

### Press

Every `button` shrinks to `scale(0.97)` over 160ms `var(--ease-out)` when pressed (`shared/styles/interactions.css`).
Full-width rows only change background instead: navigation items, conversation rows, the account row, menu items,
Settings navigation, the work-log header. **A new kind of full-width row must be added to the `:not(...)` list in that
file.**

### Hover

- **All hover styles sit inside `@media (hover: hover) and (pointer: fine)`.** On touch screens `:hover` sticks after a
  tap and leaves rows highlighted. Write the hover rule separately from `:focus-visible` (do not share one selector
  list), because the focus style must not be gated.
- **Like Grok (owner's screenshots, 2026-10-11): hover fills the background one step; it never flashes the border to
  `--accent`.**
  - Transparent buttons (icon or text): background `--panel-2`, text `--text`.
  - Buttons resting on `--panel-2` (`.icon-btn`, chips, secondary buttons): background `--panel-3`, border unchanged.
  - Primary buttons: `color-mix(in srgb, var(--accent) 86%, var(--bg))`.
  - Rows and menu items: background `--panel-2` (action menus and Settings navigation use `--menu-hover`).
  - Small remove buttons (×) and destructive text: text becomes `--danger`.
  - Common buttons without their own rule get these from the shared list in `shared/styles/interactions.css`; a new
    shared button class is added there, a feature-specific one writes its hover beside its base rule.
- Cards and fields may still change their border on hover (web source cards, Imagine tiles, Dropdown fields): they
  are not buttons.
- **Reveal-on-hover** (controls that appear when a row is hovered: `.conv-hover-actions`, `.user-message-actions`) is
  the one exception left ungated. It is allowed only together with `:focus-within` and a
  `@media (hover: none), (pointer: coarse)` rule that shows the controls permanently.
- Touch feedback for rows is the hover background on `:active`, as action menus do.

### Keyboard focus

- `:focus-visible` only. App-wide default: `outline: 2px solid var(--accent); outline-offset: 3px`
  (`shared/ui/dialog.css`).
- Rows inside lists: `outline-offset: -2px` plus the hover background.
- Action-menu items: the hover background alone, like native menus, because arrow keys move focus between them.
- Small chips: `outline-offset: 1px` to `2px`.
- Inputs have no outline; only the border darkens (§2). Never remove an outline without a replacement.

### Other

- Disabled buttons: `opacity: 0.5; cursor: not-allowed` (`button:disabled` in `base.css`, early in the cascade so a
  component can override it).
- The browser tap highlight is off (`-webkit-tap-highlight-color: transparent`). Buttons, `summary` and `label` cannot
  be text-selected; message text can.
- **Never wrap an input in a `<label>`**: link it with `htmlFor`. iOS Safari can refuse to edit an input inside a
  `user-select: none` element.
- No action may require hover on touch screens. Long press (500ms) selects images in Imagine; finger movement or a
  cancelled pointer cancels the timer so scrolling never selects.

## 7. Motion

### Curves (only these three; do not invent more)

| Token | Value | Used for |
| --- | --- | --- |
| `--ease-out` | `cubic-bezier(0.23, 1, 0.32, 1)` | Default for every interaction: press, menus, dialogs, chevrons |
| `--ease-drawer` | `cubic-bezier(0.32, 0.72, 0, 1)` | Drawers, sidebar resize, Settings pages sliding on phones |
| `--ease-in-out` | `cubic-bezier(0.77, 0, 0.175, 1)` | Objects moving across the screen |

Never `ease-in` for UI. Never `transition: all`: list the exact properties.

### Durations

| Action | Duration |
| --- | --- |
| Button press | 160ms |
| Hover colour/background | 120–150ms |
| Menus, Dropdown, rotating chevrons | 150–180ms (Dropdown 150, effort menu 180, account menu open 160 / close 110) |
| Dialogs | 200ms, backdrop 180ms |
| Sidebar resize | 240ms |
| Phones: Settings rises / page pushes in / page pops out | 260 / 300 / 240ms |

Stay under 300ms except page transitions on phones.

### Rules

- **Grow from the trigger:** set `transform-origin` at the corner nearest the trigger (composer menus open upward from
  their bottom corner). Start from `scale(0.95–0.98)` plus a 4px shift, never from `scale(0)`. Use `@starting-style`
  or a keyframe `from`.
- **Frequent actions do not animate:** opening a conversation, starting a new one, switching image versions, wheel
  zoom. Only the first send slides the composer down.
- **Animate only `transform` and `opacity`.** Never animate size, layout position or `filter`.
- **Exit animations need a timer fallback** before unmounting: jsdom and hidden windows fire no `animationend`.
- **Reduced motion is the app's own setting, not the OS media query.** The owner decided this on 2026-10-13, like
  Claude's Appearance → Motion.
  - **The setting:** Cài đặt → Giao diện → Chuyển động, stored as `peto-motion`:
    - "Mượt" (`full`, the default): animate even when the OS asks for reduced motion;
    - "Theo máy" (`system`): follow the OS;
    - "Giảm" (`reduced`).
  - **How it reaches the page:**
    - The inline script in `index.html` sets `<html data-motion="full|reduced">` before React runs, for /docs too.
    - `usePreferencesPersistence` keeps it current, including live OS changes under "Theo máy".
  - **CSS:** every animation ships a `:root[data-motion="reduced"]` rule that keeps fades and drops movement. Never write
    `@media (prefers-reduced-motion: …)` in app CSS.
  - **JS:** use `isReducedMotion()` or `useReducedMotion()` from `shared/motion.ts`, never `matchMedia` for motion.
  - **Owner-approved exceptions:**
    - The loading logo keeps animating.
    - Companion characters follow "Nhân vật cử động". Its "Theo cài đặt chung" option follows this setting;
      "Luôn cử động" ignores it.
    - Docs has its own switch. Until that switch is pressed, Docs follows the character choice.
  - **Playwright** emulates an OS that reduces motion and sets `peto-motion=system` in `mockPeto`, so screenshots stay
    still. `browser-tests/motion.spec.ts` checks the default.
- **The Companion settings page** (`features/companion/settings/companionSettings.css`) follows AIRI's Settings and departs
  from the timings above. The owner chose this look; do not copy these timings to other areas:
  - a 260ms rise per card, with a 70ms ripple step;
  - a 520ms rotation of the decorative icon when a page opens;
  - a 320ms teal sweep on hover, using transform and opacity only.

## 8. Reusable components

Before writing a new component, find the same kind below and copy its sizes.

### Buttons

| Kind | Style |
| --- | --- |
| Primary | `--accent` background, `--on-accent` text, weight 600. Pill in the composer (Send); radius 10 in dialogs and Settings |
| Secondary | `--panel-2` background, 1px `--line` border, radius 10, padding `9px 12px` (`.dialog-actions button`, `.load-more`) |
| Danger | `--danger` text and border (`.danger-button`) |
| Icon | `.icon-btn`, 36×36 |
| Transparent | No background, `--muted` text, `--panel-2` on hover (copy buttons, in-row buttons) |

Icon-only buttons need an `aria-label` and a tooltip (`data-tip`, below). Nearby buttons need distinct accessible
names ("Sao chép" vs "Sao chép câu trả lời"). The sidebar's search and collapse buttons are both 36×36, radius 10.

### Tooltips

Never use the native `title` attribute for a button hint: browsers draw it as a white system box after about a
second. Use the shared tooltip (`shared/ui/TooltipLayer.tsx`, mounted once in `App.tsx`), modelled on Grok:

| Attribute | Meaning |
| --- | --- |
| `data-tip` (no value) | Show the element's `aria-label` (React writes it as `"true"`, which the layer treats the same way) |
| `data-tip="Text"` | Show this text instead, when the hint differs from the accessible name |
| `data-tip-kbd="Ctrl+K"` | Shortcut shown in `--tooltip-muted` after the text; `Ctrl+` becomes `⌘` on Mac. Add `aria-keyshortcuts` too |
| `data-tip-side="right"` | Preferred side (`bottom` by default); flips when there is no room |

- Look: `--tooltip-bg` box, radius 8, padding `6px 10px`, 13px weight 500, 8px from the button. Sidebar buttons and
  the collapsed rail use `right`; most others keep `bottom`.
- Behaviour: appears after 450ms of mouse/pen hover, or on keyboard focus; moving to a neighbouring button within
  300ms switches instantly without animation. Hidden on touch, on press (until the pointer leaves), on scroll, Esc,
  blur, and while the button's own menu is open (`aria-haspopup` + `aria-expanded="true"`). Rendered as a
  `popover="manual"` so it sits above open modal dialogs.
- Native `title` stays only where it reveals the full text of a truncated name (conversation titles, file names,
  source URLs, prompts). Shortcuts in use: Ctrl+K opens history search; Ctrl+Alt+B toggles the document panel;
  Ctrl+` shows formulas in sheets.

### Menus

There are exactly two menu families. **A new menu joins one of them; do not create a third.**

| Family | Members | Style |
| --- | --- | --- |
| **Action menus** — class `popup-menu` (`shared/ui/menu.css`) | Account menu, conversation and project menus, avatar menu, diagram download menu | `--menu-bg`, 1px `--menu-line`, radius 12, padding 6, `--menu-shadow`. Direct `button`/`a` children are items: 36px (44 on touch), radius 8, 14px text, 18px `--muted` icon. Separator `.popup-menu-sep`; destructive item `.danger-button` (uses `--danger`, keeps an icon so labels align) |
| **Option menus** — class `effort-options` with `effort-option` items | Effort, model, image zoom, Imagine studio menus, Imagine library context menu, the composer "+" menu (`.composer-options`) | `--panel`, 1px `--line`, radius 16, padding 6, `--shadow`, opening from the trigger's corner. Items 40px (44 on touch), radius 10; heading 12px `--muted` |

- An action-menu component only sets its own position, width and open animation; surface and items come from
  `.popup-menu`. Never set `display` on `.popup-menu` itself: the conversation menu is a `<dialog>`.
- The character import menu in the character panel uses the action-menu tokens with its own two-line items.

Keyboard (see `EffortMenu.tsx`, `AccountMenu.tsx`):

- The trigger has `aria-haspopup`, `aria-expanded`, `aria-controls`. Arrow up/down on the trigger also opens the menu.
- Opening focuses the selected item, or the first item.
- ↑ ↓ move with wrap-around; Home and End jump to the ends.
- Esc closes and returns focus to the trigger. Inside a dialog, Esc calls `stopPropagation` so only the menu closes.
- Tab, a `pointerdown` outside, switching tabs or starting a stream closes the menu.
- Floating menus get a `dvh`-based `max-height`, `overflow-y: auto` and `overscroll-behavior: contain`.

### Select fields

- **Every select is `Dropdown`** (`shared/ui/Dropdown.tsx`); the app has no native `<select>` or `<datalist>` (owner's
  call, 2026-10-11). The native popup does not follow its field when a panel scrolls (reported 2026-09-25) and does
  not match the theme. `Dropdown` flips upward when space runs out and supports an editable variant (`editable`),
  groups and hint lines.
- Naming: pair it with ``<label htmlFor={id} id={`${id}-label`}>``, or pass `ariaLabel` when no label is visible
  (toolbars).
- Variants: the default field (42px, Settings forms); `className="compact"` for toolbars and panels (32px, 13px text,
  list aligned right and as wide as its text; add your own class for width); `.settings-choice` in Settings rows
  (transparent field, right-aligned value, action-menu surface).
- A container that clips overflow (`overflow: auto/hidden`) limits the list to the space inside it. A small popover or
  dialog holding a Dropdown sets `overflow: visible` (the Imagine library filter panel, the move-to-project dialog).

### Text fields

- Bordered text inputs use the shared class `text-field` (`base.css`): `--panel-2` background, 1px `--line` border,
  radius 10, padding `10px 12px`, 14px text (16px on touch). Focus has no outline; the border lightens to
  `color-mix(in srgb, var(--text) 30%, var(--line))`. Never leave the browser's default focus ring: on the dark theme it
  draws a thick black border (the owner's report on the archive search, 2026-10-11).
- Settings rows use `.settings-input`, the same look at 36px high. Inputs living inside a container that already has a
  border (composer, history search header, connector search) stay borderless and transparent.

### Dialogs

- Always a native `<dialog>` opened with `showModal()`, for the top layer, focus trapping and Esc without `z-index`.
- Owner-approved Peto Media Player reuses its custom window as a full-screen mobile dialog: stable body portal,
  `aria-modal`, keyboard focus loop and inert Companion content. Desktop remains a non-modal draggable window.
- **Set `display` only on `[open]`.** Setting `display` on a closed `<dialog>` overrides the browser's
  `display: none` and shows it.
- Close button: `.dialog-close`, top right. The Settings dialog has its own `.settings-close`. Do not delete
  `.dialog-close` while cleaning Settings CSS (it happened in commit 33d52a4).
- Confirm dialogs (`.confirm-dialog`): `h2` title at 20px, `--muted` description, `.dialog-actions` right-aligned with
  a 10px gap. Cancel (secondary) comes first; the confirming action (primary or danger) is last on the right.
- Closing returns focus to the trigger with `preventScroll`. If the trigger is gone (its menu closed), return focus to
  what contained it.
- Below 720px large dialogs fill the screen; confirm dialogs stay small and centred.

### Settings

Use the pieces in `features/settings/settingsUi.tsx`:

- `SettingsGroup` and `SettingsRow`: label and description on the left, control on the right, rows separated by 1px
  hairlines.
- `Segmented`: real radio inputs, so arrow keys and screen readers behave.
- `SettingsSwitch`: `input type="checkbox" role="switch"`.
- `SettingsIcon`: the icon set for the section list and action menus.

Sections never render their own heading; the dialog shows the section title. On phones, inputs and Dropdowns drop
below their label while switches stay on the right.

### Notices, errors, loading

- **Error** `.error`: `--danger` border and text, `--panel` background, radius 10. Dismiss button `.dismiss-error`
  36×36. Add `.chat-error-retry` when retrying is possible.
- **Plain notice** `.notice`: `--muted` text, `--line` border.
- **Form errors**: 12–13px `--danger`, right under the field.
- **Empty**: `.empty-hint`, 13px `--muted`.
- **Loading**: `LoadingIndicator` (`shared/ui/LoadingIndicator.tsx`) with `variant` `screen`, `panel` or `icon`. No
  other spinner styles, no invented percentages. The full-screen splash says "Loading" (the owner's choice); everything
  else is Vietnamese, for example "Đang tải…".
- A busy action changes its label to "Đang …" with `…` ("Đang xóa…", "Đang tạo…").

### Icons

- **Hand-written SVG**, no icon library:
  - `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`;
  - stroke width 1.7 (the sidebar and Settings set; older icons use 1.6–2);
  - round `strokeLinecap` and `strokeLinejoin`;
  - `aria-hidden="true"`.
- Sizes: 20 for sidebar navigation, 18 for menu items and Settings, 14–16 for checks, chevrons and chips, 14 in the
  work log.
- Add new icons beside their family: `ICONS` in `settingsUi.tsx`, or `app/navigationIcons.tsx` for anything the
  sidebar needs. The sidebar must not import icons from a lazily loaded module.
- Brand marks live in `shared/ui` with their licence notice (`GitHubIcon.NOTICE.txt`).

### Scroll areas and lists

- Sidebar lists fade over their last 20px:
  `mask-image: linear-gradient(to bottom, #000 calc(100% - 20px), transparent)` with `padding-bottom: 20px`, so a
  half-cut row never sits on the account row.
- Scrollbars have one global style in `base.css` (10px, rounded thumb). Peto Media Player is the owner-approved
  exception: scoped 8px rounded burgundy/cream scrollbars, including its floating menus (2026-10-22).

## 9. UI copy (Vietnamese)

- **Full Vietnamese diacritics** everywhere, including `aria-label`, `title`, placeholders and error messages.
- **Old-style tone mark placement, as the whole codebase uses:** hóa, khóa, xóa, hủy, hòa, thủy. Never hoá, khoá,
  xoá, huỷ.
- **Sentence case:** "Tải lại trang", never "Tải Lại Trang". Proper names keep their capitals: Peto, Companion, Peto
  Agent, Discord, Google, GitHub.
- **Buttons are short verbs:** Lưu, Hủy, Đóng, Xóa, Thử lại, Sao chép, Tải, Gửi, Dừng.
- **Punctuation:**
  - The ellipsis is the single character `…`, never `...`.
  - Curly quotes “…” when echoing the user's own text ("“Tên hội thoại” và các tệp đính kèm sẽ bị xóa.").
  - En dash `–` for ranges ("20–30 tuổi"); middle dot `·` between metadata items ("5 trang tính · 152 công thức").
- **Address:** the user is "bạn"; the assistant is "Peto" ("Peto sẽ tự ghi lại những điều đáng nhớ.").
- **Irreversible actions** state the consequence: "… sẽ bị xóa. Không thể hoàn tác."
- **Keep helper text short:** one sentence under a setting, no explanation of internals. The owner removed the Micro
  row's note ("… thanh âm lượng chỉ cho biết có âm thanh, chưa xác nhận đã nhận ra lời.") as too much text on
  2026-10-11. Put details in Docs instead.
- **Errors** say what happened and what to do next, with no jargon or English. Server errors (`ProviderError`) are
  already written for users and are shown verbatim.
- Model names and descriptions come from the server catalogue (`models` in `/api/auth/me`), never hard-coded in the
  frontend. The UI does not mention Grok or xAI; the owner-only Admin page is the exception.

## 10. Accessibility

- Correct ARIA roles: `menu` with `menuitem`/`menuitemradio`, `switch`, `status` for loading areas, `aria-current` for
  the open item in a navigation list.
- Everything clickable is keyboard-operable. When an overlay covers another area, the covered area is `inert`.
- Anything shown on hover is also shown on focus inside it (`:focus-within`).
- `--muted` is for secondary text only, never for information the user must read. Colour is never the only signal:
  errors have text, failed steps have an icon.

## 11. Phones

- Below 720px the sidebar is a drawer with a backdrop, the composer docks at the bottom (never centred), and the Send
  button shrinks to a 36×36 arrow.
- Inputs use 16px text on touch screens: below 16px iOS zooms the page and never zooms back. **Never** fix it with
  `maximum-scale=1`, which blocks people who need to zoom to read.
- `index.html` sets `interactive-widget=resizes-content`, so the Android keyboard shrinks the layout. Scroll areas whose
  newest content is at the bottom must keep their position when resized.
- `viewport-fit=cover` is enabled only by the screen that needs it (the mobile Imagine library) and restored after.
- Emulated phones do not replace real devices for keyboards, safe areas and touch feel. Say so when reporting results.

## 12. Files and CSS organisation

- CSS lives beside its feature's components. `shared/styles/styles.css` is an ordered import list; changing the order
  changes the cascade (see `frontend/README.md`). `shared/ui/menu.css` is imported right after `base.css`, so feature
  CSS can position its menus.
- CSS for lazily loaded parts (Admin, Imagine, document panels…) is imported from the component itself, keeping it out
  of the first load.
- Chat-only rules are scoped under `.chat …`; `.bubble` and the composer are reused by Companion.
- File names must not differ only by letter case (`localVoice.ts` vs `LocalVoice.tsx`): Windows resolves the wrong one.
- Write new CSS in the multi-line style of `base.css`. `conversationControls.css` is written as dense one-line rules;
  do not copy that style.

## 13. Known remaining exceptions

Left as they are on purpose; do not copy them into new code.

- Reveal-on-hover rules stay ungated (§6): `.conv-hover-actions`, `.user-message-actions` and the project section
  chevron (`.project-section-toggle:hover svg`). Each also shows on focus and has a touch fallback.
- Imagine's own send buttons (round accent and blue workspace send) keep their own colours and have no hover fill.
- Docs (`/docs/`) keeps its own design system and does not mount the tooltip layer.
- Switches, the selected expression card and the selected character card keep the Companion teal (§2), shared with the
  Companion hearing toggles, instead of `--accent`.
- The Companion Micro popover uses the stage palette with its own hard-coded shadow.
- Companion → Nhà cung cấp cards (2026-10-13) copy AIRI's provider cards: small uppercase outlined badges, a green "Gợi ý"
  badge and a tinted status foot with a dot. They live only on the Companion settings page, with its `--cs-*` palette.
- The Push to Talk strip and the phone "Giữ để nói" pad (2026-10-13) use the stage palette too; the pad is a 52px pill,
  and the strip shows the Space key as a small `kbd` keycap.

## 14. Before calling UI work done

- [ ] Both dark and light themes.
- [ ] Desktop and a 375px phone; no horizontal page scroll.
- [ ] Keyboard only: everything reachable by Tab, a visible focus ring, Esc closes exactly one layer.
- [ ] Reduced motion: no movement left, but presses still give feedback.
- [ ] Touch: 44px targets, 16px inputs, nothing that needs hover.
- [ ] Every icon-only button has `aria-label` + `data-tip`; no native `title` on buttons; no native `<select>`.
- [ ] Long Vietnamese strings (conversation titles, file names, error messages) neither overflow nor cover buttons.
- [ ] Every state: loading, empty, error, disabled, streaming.
- [ ] Checked in a real browser. jsdom applies no CSS, so vitest cannot see visual bugs, and a hidden browser pane
      paints no frames. Use Playwright (`npm run test:browser`, plus `--update-snapshots` only after looking at the
      new images) or headless Edge as described in `CLAUDE.md`, and keep a screenshot as evidence.
