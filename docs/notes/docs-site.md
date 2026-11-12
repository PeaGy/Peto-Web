# Peto Docs notes

Scope: The public guides at `/docs/` and how Peto answers from them.

Moved out of `CLAUDE.md` on 2026-11-12 (G0.2). Write new notes for this area here, not in `CLAUDE.md`. Current behaviour comes first, then the dated log, newest first.

# Current behavior

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
