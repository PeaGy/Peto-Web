# Documents notes

Scope: Attachments and readers (PDF/OCR, Word, Excel, logs), generated Word/PDF, Mermaid diagrams, slides, spreadsheets, and editing uploaded Excel/Word files.

Moved out of `CLAUDE.md` on 2026-11-12 (G0.2). Write new notes for this area here, not in `CLAUDE.md`. Current behaviour comes first, then the dated log, newest first.

# Current behavior

### Attachments

`shared/attachments.py` validates by **magic bytes first**, then declared MIME / extension. A file
claiming to be an image but failing `sniff_image_mime` is rejected outright. Images become
data URLs for the model. `features/documents/reader.py` reads PDF text with page labels, DOCX body
paragraphs/tables, and UTF-8/UTF-16 text in a cancellable AnyIO worker process. `features/documents/ocr.py`
renders pages without native text with PDFium in cancellable workers (4 MP/4096 px output; checks source images
before rendering, 20 MP/image, 40 MP/page, 2000 objects and 8 form nesting levels) and feeds PNG through
stdin to local Tesseract (`vie+eng`, installed separately; see backend/README.md). Required languages are checked
before new OCR; do not silently accept Tesseract's fallback when only one language loads. OCR has a global two-page limiter,
one CPU thread per engine, 8 scanned pages/file, 30s total including queue/render time and 8s/page; subprocess
output is capped and cancellation closes/kills the engine. Native text survives OCR errors/timeouts. Labels keep
original page numbers and identify OCR; notices expose read/total counts and accuracy limitations.
Missing/disabled OCR and encrypted/broken/oversized documents retain honest reading status.
Do not promise PDF image/layout understanding, complete Word page layout, native Word charts or legacy .doc support.

**Word uploads** (`features/documents/word_reader.py`, 2026-10-06). The owner's Word uses are solving math exercises sent
as .docx and writing school reports. The old reader took only `w:t`, so every Word equation (Alt+=, OMML) vanished:
"Rút gọn A = (x+1)/(x²−1)" reached Peto as "Rút gọn biểu thức sau:". The owner's own exercise survived only because its
formulas were typed as Unicode math italics with combining overlines.
- **Equations** become LaTeX (`math/omml_in.py`): `$…$` inline, `$$…$$` for `m:oMathPara`. Fractions, roots, scripts,
  n-ary operators, functions and limits, accents, bars, delimiters (cases, matrices, binomials), equation arrays, group
  characters, boxes and phantoms are mapped; math alphanumerics such as 𝑥 go back to `x`, ℝ to `\mathbb{R}`.
- **Numbering labels.** Word's automatic labels (a), b), 1.1., •) are not text, so Peto never saw which sub-question was
  c). `Numbering` follows numbering.xml and paragraph styles like Word: counters per abstractNum, deeper levels restart,
  `startOverride` restarts a list on its first use, `numStyleLink` is followed once, bullets in Symbol/Wingdings read as •.
- **Symbol font.** Old worksheets typed Greek and operators in the Symbol font ("x Î A" for x ∈ A); runs in that font and
  `w:sym` are mapped through the Adobe Symbol table (`math/symbols.SYMBOL_FONT`).
- **Embedded pictures** (`word_images.py`, 2026-10-11) follow body relationships and retain `[Hình N trong tệp]`
  numbers. Raster pictures are normalized with Pillow in the reader process, respecting DrawingML crop/rotation;
  no external links or orphan media are loaded. At most the first 8 references are attempted, with 10 MiB/20 MP
  source limits, 2048 px maximum edge, 1 MiB/output and 4 MiB total. Unsupported/broken/omitted pictures remain
  explicitly unread; headers, footers, native charts and vector media are not rendered as Word pages.
  Chat history sends selected pictures through the existing shared Responses/Claude image pipeline, labelled with
  filename and figure number. The existing `MAX_HISTORY_IMAGES` budget (default 4) is shared with standalone images,
  preferring recent messages; omitted pictures are identified in model context. Word figures do not consume the
  standalone "Ảnh N" numbering used by generated documents. Selected project DOCX files use the same pipeline.
- **Marked, not read:** native charts (`[Biểu đồ N trong tệp]`) and MathType/Equation 3.0 OLE objects
  (`[Công thức MathType N: Peto không đọc được]`). These and unread pictures make status `partial`, with `truncated`
  false unless text was cut, so history does not suggest attachment text tools to recover images. The notice asks
  for a screenshot. Text boxes are read once (only the `mc:Choice` of an AlternateContent); tracked deletions are skipped.
- **Cache.** Word results carry `word_format` (`WORD_FORMAT` 3). Older Word reads are re-read lazily from the original
  file, including selected project files, without changing visible attachments. Normalized `embedded_images` stay
  in the internal document cache for follow-up turns; `public_document` exposes counts, never bitmap/data URLs.
  `formulas`, `formulas_unread`, `images`, `images_prepared` and `images_unread` are public.
- **Tests:** `tests/test_word_reader.py`, `tests/test_word_images.py`; provider tests use mocks, not paid API calls.

**Excel uploads** (`features/documents/workbook_reader.py`, 2026-10-04, the owner's next step after `create_spreadsheet`).
`.xlsx` and `.xlsm` are accepted as attachments (magic bytes `PK`, counted as media like PDF/Word). An OLE container
(`CFB_MAGIC`: legacy `.xls` or a password-protected workbook) and `.xls` are refused at upload with a Vietnamese hint
to save as `.xlsx`.
- **No new dependency.** Parsing uses `zipfile` and defusedxml `iterparse` (DTD forbidden), streaming each part through
  `_Limited` (48 MB per part, 8 MB for workbook/styles/rels; declared total 192 MB, 5000 entries). Reading stops at
  50,000 rows per sheet, 256 columns, 400,000 cells, 30 sheets and 200,000 shared strings, and the notice says what was
  skipped. It runs in the document reader's worker process under the same timeout. Macros never run, formulas are
  never recalculated: values are the results Excel stored.
- **Text for the model**, one row per line so the attachment tools work: a workbook line (sheet list, chart sheets,
  visible defined names), then per sheet a header (area, row count, hidden), merged ranges, formulas grouped into
  copied-down/copied-right runs by relative pattern (`relative_pattern`), then `Hàng N | A: … | B: …`.
  - Values use the `create_spreadsheet` cell syntax: machine numbers, percents rounded to the format's decimals, ISO
    dates (1900 and 1904 systems), `TRUE`/`FALSE`, error codes. So Peto can rebuild an uploaded workbook with the tool;
    the prompt says colours, custom formats and charts of the original are lost.
  - Shared formulas are expanded by shifting relative references (`shift_formula`); formulas without a stored result
    show `(chưa có kết quả)` and are counted in the notice.
  - **What the owner's planted-error test exposed** (2026-10-05, `bang_test_loi_luong_diem.xlsx` against Claude.ai's
    answer key). Peto missed three planted errors only because the text hid them; all three were fixed that day:
    - Only 10 merges were listed, and the bad `E10:F10` was the 11th. `MAX_MERGES_SHOWN` is now 100.
    - `_cell_text` stripped spaces, so "Võ Thị Em " and " Bùi Lan" looked clean. Now an empty text, text with spaces
      at either end, and text starting with `"` are written in double quotes (inner quotes doubled, as in formula
      strings). One workbook line explains the quotes, and each sheet head lists the padded cells (up to 30).
    - Excel stores a formula returning "" as `t="str"` with an empty `<v>`, which ElementTree reads as no value. Every
      `IF(…,"",…)` therefore showed `(chưa có kết quả)` and counted as "made by other software". It now shows `""`.
      An empty `<v>` on a number cell (XlsxWriter's way to force a recalc) still counts as uncached, and
      `workbook_grid` marks pending cells by the same rule (`Cell.has_value`).
- **Long workbooks** use `workbook_reader.condense`, not the log condenser: shape-collapsing would erase data rows,
  which all look alike. It keeps every header and formula line and, per sheet, head and tail rows (totals live at the
  end), with `[… bỏ qua dòng a–b của tệp (hàng Excel x–y) …]` markers that cite the full text's line numbers for
  `read_attachment_lines`.
- **Charts, tables, pivot tables and cell notes** (2026-10-05) are read by `workbook_parts.py`: classic and `chartEx`
  charts with their series ranges and cached values, drawings' text boxes, Excel Tables, pivot table layouts, legacy
  notes and threaded comments with their authors (at most 30 charts, 40 text boxes and 200 notes). Chart sheets get a
  `[Trang biểu đồ "X"]` block. `SHEET_FORMAT` (3 since the fixes above) is stored in the cache, so older cached
  workbooks are re-read lazily.
- `public_document` exposes `sheets`, `sheets_read` and `rows`; the chat shows "· N trang tính" (or `k/N`). The composer
  shows a note about what Excel reading covers. Excel error codes count as signal lines for the log condenser too.
- **Tests:** `tests/test_workbook_reader.py` (XlsxWriter-built workbooks plus hand-built packages for shared formulas,
  missing addresses, DTDs and oversized parts), frontend `DocumentReading.test.tsx` and an Excel case in `App.test.tsx`.

The `attachments.document` JSON cache stores text plus version/status/notice and counts.
Version 3 caches OCR text per page privately; tools reuse it when the engine signature matches. Old cache versions
are lazily reread; a changed engine path/mtime, enabled flag, languages or page limit triggers rereading scanned
files on follow-up. Disabling/uninstalling OCR preserves already cached OCR text; fully cached scans require no engine
process even for tools. Adding language data or retrying transient failures without a settings change requires reupload.
`_public_attachment` exposes only the status metadata, never native/OCR text, engine settings or disk paths. Read new
documents inside admission, before shielded writes; emit `reading` SSE without treating it
as acceptance. `meta` acknowledges persistence. Legacy files are lazily cached with an
owner-filtered UPDATE, at most MAX_ATTACHMENTS total reads per turn including new files.
`_to_chat_messages` applies MAX_DOCUMENT_CONTEXT_CHARS, newest message first and shared
between files in that message. Always tell the model when text is missing/truncated.
PDF parsing has page/decompression/time limits; DOCX ZIP/XML has size limits and rejects
DTD/external entities. Dependencies: pinned pypdf and defusedxml in requirements.txt.

**Long files** (2026-09-29, both levels picked by the owner after "a long log, and Peto read only a little of it").
Before this, a text file kept only its first 80,000 characters, so the errors at the end of a log never reached Peto.
- **Condensed excerpt.** `document_reader.condense_text` keeps a text file over `MAX_TEXT_EXCERPT_CHARS` in three
  parts: the start (15%), error/warning blocks from the middle (`SIGNAL`, 2 lines of context each, one block per line
  shape, up to 35%), and the end (the rest). It cuts only at line boundaries.
  - Runs of 5+ lines of the same shape (digits and hex ignored) collapse into first, "[… N dòng cùng dạng …]", last.
  - Each block opens with "[Dòng a–b]" in real line numbers. Files of 20 lines or fewer keep a head and tail by
    characters instead.
  - `VERSION` went to 2, so old cached excerpts are re-read lazily.
  - The notice is shown to users under "Đọc được một phần", so it names no tools.
- **Tools** (`shared/attachment_tools.py`): `search_attachment` (plain case- and diacritic-insensitive text, alternatives
  split by " | ", never regex) and `read_attachment_lines` (at most 400 lines).
  - They work on the whole file, re-read from disk. Text is decoded as is; PDF and Word go through
    `read_full_document`, still bounded by the page cap and the timeout.
  - Only files in the owner-filtered rows of this turn (`AttachmentFiles(rows)`, chat mode) can be opened, by the stored
    path. Results are capped (40 matches, 16,000 characters) and carry `DATA_NOTE`.
  - `ai/xai.py` offers them only when the conversation has files, and emits `file_lookup` / `file_lookup_done` chunks.
    Each lookup becomes a `lookup` step of the work log (see "Work log").
  - `_to_chat_messages` tells the model the tool names and the file name whenever an excerpt is partial.
  - The mock answers `__timtep__:<query>` by searching the newest file.
- **anyio re-runs the parent's `__main__` file** in the reader's worker process. A dev launcher script without an
  `if __name__ == "__main__":` guard around `uvicorn.run` starts a second server there, and every read then fails as
  "Bộ đọc tài liệu đang gặp lỗi" (hit on 2026-09-29 with a scratch launcher; `uvicorn main:app` is safe).
- **Tests:** `tests/test_attachment_tools.py` (excerpt, tools, provider loop with a fake client, chat API);
  `frontend/tests/api.test.ts` and `App.test.tsx` for the event and the work log.

Only the `MAX_HISTORY_IMAGES` (default 4) most recent images are re-sent to the model;
older ones degrade to a text placeholder. This is computed twice — in
`features.chat.history._to_chat_messages` (which decides what to read off disk) and in
`ai/xai._recent_image_keys` (which decides what to send). Keep them consistent.

### Documents in chat (`create_document`)

`features/documents/tools.py` gives the Chat tab (not Companion or the agent) a `create_document` tool. The model sends a title and
Markdown; `document_jobs.build_files` renders a PDF (ReportLab, `pdf_out.py` behind `document_export.render_pdf`) and a DOCX
(python-docx, `docx_out.py` behind `render_docx`), `storage/documents.py` keeps them per owner, and the card shows page 1
of the PDF (pypdfium2). The DOCX preview is that PDF, so a feature must exist in both renderers or the preview misleads.
`export.py` keeps what both share: Markdown → blocks, the math glue, column widths and font registration. The four styles
and the cover page are under "Styles and cover" below.

On 2026-09-30 the owner picked a Word/PDF upgrade as the first step of the document roadmap. Mermaid diagrams in chat
came second, PowerPoint third and Excel fourth (sections below).
- **Real lists.** Every Markdown list gets its own Word numbering definition (`_numbering_level`), so numbers restart per
  list, honour `start`, and Word renumbers when the user edits. Nested ordered lists go 1. → a. → i., bullets • → –.
  The PDF draws the same labels (`list_label`) at the same hanging indents (`list_indent`). Later paragraphs of an item
  carry no number.
- **Images.** A line `![caption](anh-N)` inserts the Nth image the user sent in this conversation (`features/documents/images.py`),
  with the caption below it.
  - Only that owner's images of that conversation, filtered in SQL and read from the stored path. Any other image URL
    stays text (`[Ảnh: …]`) and is never fetched.
  - Images are shrunk to 1600 px: PNG for transparency, screenshots and GIFs, JPEG for photos. At most 12 per document;
    images over 40 megapixels are refused before decoding.
  - "Ảnh N" counts the conversation's images by `created_at, rowid`. `db._attach_files` puts the same `number` on each
    image, `ai/xai.build_input_payload` labels it `[Ảnh N: name]` for the model, and `conversation_actions.fork` copies
    images in that order, so a new version keeps the numbers.
  - The tool refuses a number that does not exist, so the model can fix it. A hand-edited draft shows text instead.
- **Contents.** A line `[TOC]` (or `[Mục lục]`) outside lists and quotes becomes "Mục lục" with headings of levels 1–3,
  followed by a page break.
  - PDF: ReportLab's `TableOfContents` with real page numbers (`multiBuild`). Every heading also becomes a PDF bookmark.
  - DOCX: a TOC field marked dirty. Word asks to update fields on open, then fills in page numbers; other viewers show
    the heading list written into the field. The tool result tells Peto to mention that prompt.
- **Word styles.** python-docx's template gives Title and Heading styles theme fonts (`asciiTheme`), which beat the font
  name set on them: Word showed Calibri instead of Times New Roman or Arial, and a blue rule under the title. `render_docx`
  strips the theme attributes and the rule, and matches heading sizes and spacing to the PDF.
- **Render queue.** `document_jobs.RenderQueue` still renders one document at a time per process (small VPS). Later
  requests wait in a short line instead of failing at once as the old lock did: 4 waiting at most, 30 s for the tool,
  15 s for exports, 10 s for preview pages.
- **Formulas** (2026-10-06, step 2 of the owner's Word plan). Before, the tool said "Chưa hỗ trợ LaTeX" and a math
  solution printed `$\bar{x}$` raw, so the owner copied answers from the chat, which turned overlines into "xˉ".
  - **Extraction first.** `math/markdown.extract` swaps `$…$`, `$$…$$`, `\(…\)` and `\[…\]` for private-use placeholders
    before markdown-it runs: a display formula continued on a line starting with "+ " would otherwise become a bullet,
    and Markdown eats the backslash of `\(`. Code spans and fences are skipped. Dollar rules follow Pandoc ("giá $5 và $10"
    is not math); `~p` in operand position is negation, as in the chat's `tildeNegation`.
  - **One tree, two renderers.** `math/latex.py` parses a fixed command set (tables in `math/symbols.py`) into nodes and
    refuses anything else with a Vietnamese message naming the formula, so Peto rewrites it and calls again.
    `math/omml_out.py` writes native Word equations: Cambria Math runs, `\text` in the document font, child order per the
    OMML schema. `aligned` and `cases` are `m:m` matrices with justified columns, since alignment marks inside `m:eqArr`
    are unverified; primes stay plain characters as in Word.
  - **PDF** (`math/layout.py`): a TeX-style layout with the bundled STIX Two Math (OFL; the MATH table constants are
    copied into `C`). Italic letters use the Unicode math alphanumerics; tall delimiters, radicals, braces and wide
    accents are vector paths, because ReportLab cannot reach the font's size variants.
    - Inline formulas sit in an `<img>` slot of the formula's size (`assets/math-slot.png`, `valign` = −depth).
      `attach_math` tags each slot's ImageReader with its box, and `MathCanvas.drawImage` (`math_canvas`) draws vector
      math there.
    - Body styles use `autoLeading="max"`, so tall inline fractions push lines apart. Display formulas are a flowable,
      shrunk to fit, with `\tag` at the right.
    - Plain-text symbols Tinos lacks (≤, ∈, →) are drawn in STIX via `<font>` instead of failing the PDF.
  - Limits: 600 formulas, 4,000 characters and 3,000 nodes per formula. Tables now allow 12 columns (a 4-variable
    truth table has 9).
  - Neither Word nor LibreOffice is installed here, so the OMML was checked by round trips (`omml_out` → `omml_in`) and
    schema order. The owner then opened a sample DOCX in Word: the equations display and can be edited.
- **Styles and cover** (step 3 of the owner's Word plan). The owner found Peto's reports "non, chưa chỉnh chu": US Letter,
  Arial, no cover page, a title printed twice. They have no school-specific rules. On 2026-10-06 they saw three live
  mockups (https://claude.ai/artifact/R79UV3ASRLWUd49j79ZvzR) and kept all three:
  - **Khung đôi** (`classic`, the default) for đồ án tốt nghiệp and khóa luận.
  - **Dải màu** (`band`) for báo cáo môn học and đồ án nhóm.
  - **Tối giản** (`minimal`) for tiểu luận, lời giải and simple documents.

  `essay` stays for nghị luận. The prompt picks a style by document type and follows the user when they name one.
  - **Shared standard** (`themes.py`). Every style uses the usual Vietnamese school layout: A4, Times New Roman 13, 1.5
    line spacing, justified, 1 cm first-line indent, margins top 2, bottom 2, left 3, right 2 cm. A frozen `Theme` holds
    only what differs:
    - heading sizes, caps, italics and colour;
    - the title block when there is no cover;
    - tables (`grid`, `band`, `booktabs`) and code boxes (`box`, `bar`, `rules`);
    - captions, header (none, `split`, `title`), footer and cover.
  - **Old `report` documents** keep their stored files; anything rendered now (a revision, or exporting a hand-edited
    version) uses `classic` (`ALIASES`). The API still accepts `report`; the tool offers only the four, and new manual
    drafts send `classic`.
  - **PDF fonts.** Tinos and Cousine are bundled (OFL, metric-compatible with Times New Roman and Courier New), so line
    breaks and page numbers almost match Word. Documents no longer use Noto; the files stay in `assets/fonts`.
  - **Cover data** (`cover.py`). It is a `--- … ---` block of `khóa: giá trị` lines at the very start of the Markdown, so
    the user can fix a school name or MSSV in "Sửa nội dung" without asking Peto.
    - Keys are matched unaccented, with English aliases. The cover keys are: `trường`, `khoa`, `cơ quan`, `loại`, `môn`,
      `đề tài`, `phụ đề`, `giảng viên` (or `GVHD`), `nhóm`, `lớp`, `nơi`, `ngày` and `logo: anh-N`.
    - `thành viên` is a list of `- Tên | MSSV | ghi chú` lines, 15 at most.
    - An unknown key is refused with the allowed list, so the model fixes the call. A block that is not at the start, or
      never closes, is ordinary content.
    - Missing fields print dotted blanks (`DOTS`) for the user to fill. A missing date is the current month in
      `DEFAULT_TIMEZONE`. The prompt forbids inventing a school, instructor, members or MSSV.
  - **Word cover** (`docx_out.py`).
    - Word cannot push text to the page foot, so the cover is a borderless three-row layout table with exact row heights:
      the school block at the top, the title mid-page, the people at the bottom.
    - Each style draws its own frame:
      - `classic`: a double frame as a page border on the first page only (`w:pgBorders display="firstPage"`);
      - `band`: a navy rectangle anchored to the page (`wps` inside `mc:AlternateContent` with a VML fallback, behind the
        text);
      - `minimal`: rules made of paragraph borders.
    - The cover page has no header or footer. Elements python-docx lacks are inserted in schema order (`_insert`),
      because Word calls a file damaged when children are out of order.
  - **PDF cover** (`pdf_out.py`). It is painted straight onto page 1 (`onFirstPage`), and the text flow starts on page 2.
  - **Title.** An opening heading equal to the title, or the only heading at its level (`# Lời giải bài tập 5` followed
    by `## Bài 1`), becomes the title block instead of printing twice (`body_blocks`). The remaining headings are
    renumbered from level 1. Without a cover, page 1 has no running header.
  - **Captions and slots.**
    - A paragraph "Bảng: tên" right above a table becomes "Bảng N. tên" ("Bảng N: tên" in `band`), kept with the table.
    - Captioned images become "Hình N. …".
    - `![chú thích](khung-anh)` leaves a dashed 5.4 cm frame reading "Chỗ dán ảnh chụp màn hình", with its Hình number,
      where the user pastes a screenshot in Word (30 per document).
  - **Tables.** Column widths come from the visible text (`column_widths`): never narrower than the longest word, and
    math counted by the symbols it shows. Header rows repeat on every page.
  - **Page breaks.** Both renderers now break pages the same way.
    - Tables of up to `SHORT_TABLE_ROWS` (12) rows never split. Word gets this from rows that keep with the next one and
      `cantSplit`; the PDF from a KeepTogether. Longer tables split between rows.
    - In the PDF, headings and long-table captions stay with the start of the next block, as Word's "keep with next"
      does. This is `_KeepStart`, plugged in through the template's `handle_keepWithNext`.
    - ReportLab's own grouping caused two problems. It moved a heading together with a whole long paragraph or table to
      the next page, which left up to half a page blank. It also never grouped a heading with a following KeepTogether,
      so a heading before a short table or an image could end up alone at the bottom of a page.
    - The group now moves only when the space left cannot hold the heading plus the next block's own first split: two
      lines of a paragraph, or the header and first row of a table.
  - **Word contents.** The TOC field is still marked dirty, so Word offers to update it. `build_files` (and `export_file`
    for hand-edited versions that have a `[TOC]` line) now renders the PDF first and passes its heading pages
    (`toc_pages`) to the DOCX. Viewers that never update fields (phones, Google Docs) therefore show real page numbers
    with dot leaders.
  - **Mock.** `__baocao__` (or `__baocao__:band`, `:minimal`) creates a sample report with placeholder names.
  - **Not yet checked in real Word:** the band rectangle, the first-page border, the cover heights and the pre-filled
    contents.
  - **Tests:** `tests/test_document_themes.py`.
- **Small fixes that day.** The essay header said "Nghị luận xã hội" on every essay (now the title). Table cells and
  code lines took the essay's first-line indent and justification.
- **Not done:** charts and images from Imagine (the user attaches them). Editing an uploaded Word file in place is
  "Editing uploaded Word files" below.
- **Tests:** `tests/test_document_features.py`, `test_document_export.py`, `test_document_artifacts.py`,
  `test_document_math.py`.

### Diagrams in chat (Mermaid)

The second step of the document roadmap. On 2026-09-30 the owner picked "Thẻ bên phải" from mockups: a ```mermaid block
in a Chat reply becomes a card in the bubble (`DiagramCard.tsx`: thumbnail, title, kind), and clicking it opens the
diagram large in a panel on the right (`DiagramPanel.tsx`), where the document panel sits.
- **Mermaid 11, not 12.** 12 (released 2026-09-10) needs Safari 17.4+ and bundles the heavier ELK layout by default.
  `diagrams.renderDiagram` imports it dynamically, so it loads only once a reply has a diagram. The panel is its own
  `preloadable` chunk (`diagramPanelLazy.ts`), warmed when the pointer enters a card.
- **Rendering.** `mermaid.initialize` is global, so renders queue one at a time: a light-theme export must not leak into
  a dark card.
  - `securityLevel: "strict"`: the code is written by the model, which a web page can steer, so no HTML, links or click
    handlers.
  - `htmlLabels: false`: labels are SVG text, not `foreignObject` HTML, which taints the canvas and breaks PNG and PDF.
  - Colours come from the app's tokens (`PALETTE`), including `rowOdd`/`rowEven`. Left unset, Mermaid 11 derives ERD rows
    from the primary colour, which gave pale rows with unreadable text on the dark theme.
  - `useDiagramTheme` follows `data-theme`. A theme change re-renders and keeps the old picture until the new one is
    ready.
- **While a reply streams** the card only says "Đang vẽ sơ đồ…" (`pending`), because half-written code would flash
  syntax errors. Code Mermaid rejects shows a Vietnamese note and the code.
- **`components` in `ChatMessage` must stay memoized** (`useMemo` on `writing`). An inline object gave react-markdown new
  component types on every render, which remounted every card (re-running Mermaid) and reset code-block copy buttons.
- **Title and kind.** The title is `title:` in the block's `---` front matter; the kind comes from the first keyword.
  Mermaid has no activity or use case diagram, so Peto draws them with `stateDiagram-v2`, `swimlane-beta` and
  `flowchart` and starts the title with "Sơ đồ hoạt động: " or "Sơ đồ use case: ". `NAMED_KINDS` reads the kind from that
  prefix, and `kindNote` avoids "Sơ đồ tuần tự · Sơ đồ tuần tự".
- **Swimlanes.** Mermaid 11.17 ships `swimlane-beta`: flowchart syntax, each `subgraph` a lane, laid out as real lanes.
  draw.io's import turns it into its own lane shapes (both checked on 2026-09-30).
  - Vertical lanes only: `LR` routed arrows in long loops around the whole diagram.
  - A node declared outside every lane gets an extra lane with no name, so the prompt puts every node, start and end
    included, inside its lane. Cross-lane arrows go after the last `end`: a node lands in the first lane that mentions
    it, so an arrow written inside one lane pulls the node it points to into that lane.
  - The lane header row sits where Mermaid puts the title, so `renderDiagram` raises `flowchart.titleTopMargin` to
    `LANE_TITLE_MARGIN` for these diagrams.
  - UML symbols come from Mermaid 11's shapes: `sm-circ` start, `fr-circ` end, `fork` bars, `{}` decisions. `themeCSS`
    fills the start dot and the end's inner dot with the line colour; by default they took the node fill and the pale
    border colour. The second rule skips nodes with text, so a labelled double circle `((( )))` keeps its fill.
  - It is a beta: recheck it (and the prompt) after any Mermaid update. The lock file pins 11.17.2.
- **Panel.**
  - Drag to pan; zoom with the wheel (a non-passive listener, since React's is passive), a pinch, or + − 0 and arrows.
    "Vừa khung" fits the diagram above the zoom controls. A "Mã" tab shows the code with a copy button.
  - ‹ › and "N / M" walk the conversation's diagrams. `diagramCodes` in `App.tsx` collects them with `diagramBlocks`,
    which reads fences as Markdown does (`~~~`, longer fences, blocks in lists, an unclosed last block) and skips the
    reply still streaming. `normalizeDiagram` makes a card's code (from the hast tree) equal the list's (from raw text).
  - It reuses the document panel's `<dialog>` and classes: `show()` beside the chat, `showModal()` over the screen at
    1100px and below. Opening a diagram closes the document panel. Switching conversations, Ctrl+Alt+B and the document
    panel's button close the diagram.
- **Downloads** ("Tải", `diagramExport.ts`) always render the light theme, so a PNG pasted into Word is not a black
  block. PNG at 2×, SVG as rendered, and PDF: a 3× JPEG on one A4 page (portrait or landscape by shape, 36 pt margin),
  written by `pdfFromJpeg` without a library. Canvases stay under 16 M pixels, since iPhone Safari draws a blank image
  above about 16.7 M.
- **draw.io.** The "draw.io" link is `https://app.diagrams.net/#create=` plus the JSON that draw.io's own tool
  (@drawio/mcp) builds: `{type: "mermaid", compressed, data}`, with `data` the base64 of deflate-raw of
  `encodeURIComponent(code)`, or the raw code when `CompressionStream` is missing. draw.io turns it into editable shapes,
  which is the way to manual layout and a vector PDF.
  - **Keep the URL free of query parameters.** With any of them (that tool adds `grid`, `pv`, `border`, `edit`), draw.io
    asked "Tất cả mọi thay đổi sẽ mất!" right after opening, and "Loại bỏ" threw the diagram away. Checked in headless
    Edge on 2026-09-30.
- **Prompt.** A `WEB_PLATFORM_PROMPT` line tells Peto that diagrams, unlike pictures, are drawn right in the reply, never
  in Tạo ảnh. The detailed `persona.DIAGRAM_PROMPT` (front-matter titles, IDs and quoting, class, sequence, activity, use
  case, ERD) is appended only on Chat turns whose recent user messages mention diagrams
  (`build_diagram_guide`, unaccented keywords), so other turns pay nothing for it. Its rules come from real Mermaid 11
  errors: `<<choice>>`, `<<fork>>` and `<<join>>` states declared after their first use render as plain boxes, and
  parentheses in an unquoted `[ ]` label are a syntax error.
- **Not done:** use case diagrams (Mermaid has none; Peto approximates them with a flowchart), and diagrams inside
  `create_document` files (the user can download the PNG and attach it).
- **Tests.**
  - `frontend/tests/diagrams.test.ts`: kinds and titles, fences, the PDF's structure and xref offsets, the draw.io
    payload round trip.
  - `DiagramPanel.test.tsx` mocks `mermaid`: cards, the panel, the download menu, the draw.io link, sharing the space
    with the document panel, pending and error cards, re-rendering on a theme change.
  - `backend/tests/test_diagrams.py`: the guide's keywords and where it is appended. The mock answers `__sodo__` with a
    class, a sequence, an activity and a swimlane diagram (`DIAGRAM_SAMPLE`). Its chunker now streams whitespace
    exactly; it used to drop the spaces after each chunk, which broke code indentation.

### Presentations in chat (`create_presentation`)

The third step of the document roadmap, built on 2026-10-04. The owner liked all three styles from live mockups
(`frontend/prototypes/slides`, deleted after the pick) and chose to keep them all: Gọn sáng (`clean`, default), Học thuật
(`academic`) and Đậm nét (`bold`). Peto picks one by context and follows the user when they name one. There is no manual
slide editor in v1, also the owner's call: changes go through chat and create a new version.
- **Tool.** `features/documents/slides/spec.py` holds the strict schema. A deck has a title, a theme and up to 25
  slides in seven layouts: cover, agenda, bullets, two_columns, image_text, table, chart.
  - Every field of every layout is present and null when unused.
  - Tables and charts are flat `table_*` / `chart_*` fields, not nullable nested objects, because not every provider
    accepts `anyOf` in strict mode.
  - `normalize` cleans the text and checks limits per layout. Its errors name the slide ("Slide 3 (bullets): …"), so
    the model can fix the call and try again.
  - `DocumentSession.present` mirrors `create`: at most two artifacts per turn, idempotent, rejects unaccented
    Vietnamese, and takes images only from this conversation's `[Ảnh N]`.
- **One layout, two renderers.** `layout.py` turns each slide into positioned shapes (`scene.py`, points on a 960×540
  slide). `pptx_out.py` (python-pptx) and `pdf_out.py` (ReportLab) only draw those shapes, so the preview matches the
  download.
  - **Metrics.** Text is wrapped with real font metrics. The PPTX names Arial and Times New Roman; measuring and the
    PDF use the bundled Liberation Sans and Serif. Their widths match exactly (checked 2026-10-04), so line breaks
    match PowerPoint.
  - **No Georgia.** It lacks precomposed glyphs such as "ố" and broke Vietnamese accents in the first mockup.
  - **Shrink, then refuse.** Text shrinks within a size range. If it still doesn't fit, `SlideOverflow` asks the
    model to shorten the slide or split it.
- **PPTX details.**
  - Titles sit in the slide's real title placeholder (outline view, screen readers), raised above shapes drawn
    before it.
  - Bullets are real PowerPoint bullets (`a:buChar`). Text boxes have zero insets and exact line spacing, slide
    numbers are `slidenum` fields, and runs carry `lang="vi-VN"`.
  - Tables use the "No Style, No Grid" table style with explicit borders.
  - Charts are native (column, bar, line, pie). Their value axis is fixed by `nice_axis` and shared with the preview.
    Bar charts reverse their data so the first category is on top.
  - The file's theme gets the style's fonts and accent colours, and the layouts of python-pptx's 4:3 template are
    widened, so slides the user adds still fit.
  - Speaker notes go to each slide's notes page.
- **Storage and API.**
  - The content is the normalized deck as compact JSON. History hands it back to the model, which is how "sửa slide
    3" works.
  - Decks store their file in `document_assets.pptx`, a new nullable column added by manual migration; `docx` is
    empty for decks.
  - Export serves `pptx` and `pdf`. A `docx` export of a deck returns 400, and so does a manual `versions` edit.
  - The conversation fork copies assets with an explicit column list. Its old positional insert would have broken
    with the new column.
- **UI.**
  - The card shows the whole first slide with a "Xem slide · N slide" chip, and "Tải PDF" replaces "Sửa nội dung".
  - The panel pages by "Slide N / M" and shows that slide's notes below it (`slideNotes`).
- **Mock.** `__slide__` or `__slide__:academic` creates a six-slide sample (`slide_sample`).
- **Not done:**
  - manual slide editing;
  - notes pages in the PDF;
  - transitions;
  - images from Imagine or the web;
  - a check in real PowerPoint: none is installed on this PC, so the custom XML was only checked against the
    schema's element order.
- **Tests:** `backend/tests/test_presentations.py`, frontend `DocumentArtifactCard.test.tsx` and `DocumentPanel.test.tsx`.

### Spreadsheets in chat (`create_spreadsheet`)

The fourth step of the document roadmap, built on 2026-10-04. The owner picked "Lưới Excel" from three live variants
(`frontend/prototypes/sheets`, deleted after the pick; the others were print pages like Word/PDF and a reading table
with formulas per column). The card shows a light mini grid of the first sheet; the panel shows an Excel-like grid.
- **Tool.** `features/documents/sheets/spec.py` holds the strict schema. A workbook has a title and 1–5 sheets, and each
  sheet is one table at A1: row 1 holds the headers, `rows[0]` is row 2, and the optional total row follows the last
  data row. This fixed addressing is what lets the model write correct formulas.
  - Columns have a format (text, number, percent, vnd, usd, date) and optional decimals. Cells are strings: text,
    machine numbers, `8%`, ISO dates or formulas.
  - `parse_cell` refuses malformed numbers (`1.500.000`, `7,5`), percents without `%` and non-ISO dates, naming the
    cell. Words in number columns (`Vắng`) stay text.
  - Limits: 20 columns, 300 data rows, 4000 cells, 4 charts per sheet and 8 per workbook; pies at most 10 rows.
  - `DocumentSession.tabulate` mirrors `present`: two artifacts per turn, idempotent, rejects unaccented Vietnamese.
    Its result carries `results` (total-row values, `view.summary`), so Peto quotes computed numbers instead of
    redoing the arithmetic.
- **Formulas** (`formula.py`, `engine.py`). Formulas are tokenized and parsed into a tree, never evaluated as code.
  - Only the functions in `FUNCTIONS` are accepted: Excel 2007-era names, so no `_xlfn.` prefix is needed. `;`
    separators become `,` when no `,` is present, smart quotes are normalized, and the canonical text (uppercase names
    and references, quoted sheet names) is what the file and the stored JSON hold.
  - XlsxWriter stores 0 as each formula's cached result, so phone previewers and LibreOffice (which by default does
    not recalculate Excel files) would show 0. `engine.compute` evaluates every formula by Excel's rules (coercion,
    15-significant-digit rounding and comparison, COUNTIF criteria with wildcards, 1900 date serials from 01/03/1900)
    in topological order, so long chains never recurse. The writer stores the results, and XlsxWriter's
    `fullCalcOnLoad` makes Excel recalculate on open.
  - Any error result, a cycle, a reference outside the table or to an unknown sheet is refused with the cell, the
    formula and a hint, so the model fixes it (IFERROR when an error is intended).
  - Approximate VLOOKUP/HLOOKUP/MATCH on unsorted or mixed data is refused (`#UNSORTED`, never written to a file):
    Excel's binary search gives unpredictable results there. Range arithmetic (`A2:A9*B2:B9`) is refused too;
    SUMPRODUCT and SUMIFS cover it.
  - Whole-column references are lazy: functions walk only the used area and count blank cells arithmetically, so
    COUNTBLANK(A:A) matches Excel.
- **File** (`xlsx_out.py`, `view.py`).
  - The header row is tinted with a teal rule, frozen, with autofilter. Data rows are banded by conditional formatting,
    which survives sorting. The total row is bold.
  - Number formats such as `#,##0 "₫"` follow the user's locale in Excel; the grid always shows Vietnamese style
    (`view.display`). Column widths come from display lengths, with room for the filter button, capped at 50 with wrap.
  - Print setup: A4, fit to width, repeated header row, the sheet title in the page header, page numbers in the footer.
  - Charts are native (column, bar, line, pie), anchored right of the table (8 columns or fewer) or below it. Their
    value axes are fixed by `view.nice_axis`, shared with the grid's SVG charts.
- **Storage and API.**
  - The content is the normalized workbook as compact JSON with canonical formulas. History hands it back to the
    model for revisions.
  - Files live in `document_assets.xlsx`, a new nullable column added by manual migration. `docx`, `pdf` and `preview`
    are empty, and `pages` is the sheet count.
  - `GET /api/documents/{id}/sheet?version=` recomputes the grid from the stored content (display strings, formulas,
    widths, charts). Export serves only `xlsx`, preview returns 404, a manual `versions` edit returns 400, and the
    conversation fork copies `xlsx`.
- **UI.**
  - `SheetPreview.tsx` (main chunk): `useSheet` fetches `/sheet` per card, with no cache shared across accounts. The
    card shows the first rows as a light mini grid and counts formulas and charts.
  - `SheetView.tsx` (lazy, `sheetViewLazy.ts`): formula bar (name box, formula, value chip, "Công thức" toggle or
    Ctrl+`), sticky letters, row numbers and header row, arrow keys and Enter to move, sheet tabs. It opens on the first
    formula cell; only keyboard moves scroll, so opening never hides column A. `SheetChart.tsx` draws the charts as SVG
    at their anchor cells, measured after layout.
  - Opening a workbook from its card collapses the panel's file list once, to give the grid room.
- **Mock.** `__excel__` (grade book with statistics and two charts) and `__excel__:chitieu` (dates, VND, SUMIF,
  percent, pie).
- **Not done:**
  - conditional formatting rules, merged title rows, PDF export, manual cell editing;
  - array formulas and newer functions (XLOOKUP, IFS, TEXT…);
  - a check in real Excel or LibreOffice: neither is installed on this PC, so the XML was inspected instead.
- **Tests:** `backend/tests/test_spreadsheets.py`, frontend `DocumentArtifactCard.test.tsx` and `DocumentPanel.test.tsx`
  (`tests/sheetFixture.ts`).

### Editing uploaded Excel files (`edit_spreadsheet`)

Built on 2026-10-05, after Excel uploads could only be read. Peto edits the user's own file and keeps everything it
does not touch. The upload never changes; each edit is a new version.
- **No openpyxl.** It drops cached formula results, sparklines and other `x14` extensions, and drawings it does not
  understand. `features/documents/workbook_edit/` patches the package surgically instead.
  - lxml for small parts, so namespace declarations such as `mc:Ignorable` survive.
  - A regex row/cell parser for `sheetData` keeps untouched rows byte-identical.
  - The rest of a sheet is a skeleton (`before` + `<sheetData peto-sheet-data="1"/>` + `after`), parsed only when
    something outside the cells changes.
- **Operations** (`ops.py`, strict `SCHEMA`): set, fill (formulas copied like drag-fill), clear, format, insert/delete
  rows and columns, merge/unmerge, add/rename sheet. At most 40 changes per call; each uses the coordinates the previous
  one left. New formulas may only use `sheets.formula.FUNCTIONS`.
  - Guards refuse what Excel refuses: writing inside a merged range, a pivot table, part of an array formula, a Table's
    totals row, a protected sheet. `merge` refuses to discard data (Excel keeps only the top-left value) and partial
    overlaps; `unmerge` drops every merge touching the range.
  - Inserting or deleting rewrites references with Excel's rules (`refs.py`: quoted and Unicode sheet names, 3D,
    external and structured references, defined names). Merges, CF/DV ranges, charts, drawing anchors, notes, Tables,
    pivot caches and print areas move too. Inserting right above a total row also widens its SUMs, and charts over the
    same block, which Excel itself does not.
  - Writing next to a Table grows it; calculated columns fill; renaming a header updates the Table and structured
    references.
- **A batch is atomic, but every refusal comes back at once** (up to `MAX_PROBLEMS`, 8). Until 2026-10-05 only the
  first error was reported, so a workbook with several errors cost one 1–2 minute round per error. The tool result
  says nothing was written and asks for the whole list again.
- **Recalculation** (`recalc.py`): changes propagate through dependents (whole columns, other sheets, defined names)
  and are evaluated with `sheets/engine`. New formulas that evaluate to an error or form a cycle are refused, as in
  `create_spreadsheet`. Existing formulas Peto cannot compute lose their cached value rather than keep a stale one.
  `fullCalcOnLoad` is set and `calcChain.xml` dropped, so Excel recalculates on open.
- **Chart caches** (`chart_cache.py`, 2026-10-05). Excel redraws charts from cells on open, but phone viewers and the
  reader use the numbers cached in the chart. The owner's edited grade book still read "Giỏi 1, Khá 0" from its chart
  after the count cells became 2 and 2. Series (`numRef`/`strRef`, single-level chartEx `lvl`) whose range touches a
  cell written or recalculated in this edit (`Report.cells`), or a sheet that had rows or columns inserted or deleted,
  are re-read from the cells. Other charts stay byte-identical. Defined names, multi-area and whole-column ranges keep
  their old cache.
- **Storage and API.**
  - Edits run in a worker process (`to_process`, 45 s, behind the render queue).
  - Each success is a `style='workbook'` document version holding the xlsx; an upload becomes a new document. At most
    `MAX_EDITS_PER_TURN` (4) saved edits per turn.
  - **One card per file per turn** (the owner's first real run on 2026-10-05 left three cards for one file). Editing
    the same file again in a turn passes the earlier edit's lines and changed cells to the worker (`carried`).
    - `Session.carry` keeps them, and later inserts, deletes and renames in the new edit move them. A line whose area
      was deleted says so.
    - The new version's change list and tinted cells therefore cover the whole turn.
    - `DocumentSession._turn_edits` puts the new card in place of the earlier one, and the page replaces a card with
      the same id.
    - The model still gets only that call's lines (`new_lines`), and `change_count` gives the card its full total.
  - The content holds the change lines ("Thay đổi:"), "Ô đã sửa: …" and a 40,000-character readout, so follow-ups and
    the attachment tools see the new file.
  - `/sheet` returns `workbook_grid.grid`: 500 rows × 60 columns per sheet, Vietnamese number formats, theme colours,
    charts drawn from the live ranges. `.xlsm` downloads keep the macro MIME type and `vbaProject.bin` byte for byte.
- **UI** ("Nhật ký thay đổi", picked by the owner from live variants on 2026-10-05).
  - The card lists the first changes.
  - The panel puts the change list on top; clicking one selects its area. Below are a formula bar ("Peto vừa sửa",
    "Excel tính khi mở tệp") and a grid in the app's theme with changed cells tinted.
- **Mock:** `__suaexcel__` edits the newest workbook of the conversation.
- **Not done:**
  - new charts, conditional formatting, sorting and filters, images;
  - a check in real Excel (none on this PC).
- **Tests:** `backend/tests/test_workbook_edit.py` and `test_turn_limits.py`, frontend `DocumentArtifactCard.test.tsx`
  (`tests/workbookFixture.ts`).

### Editing uploaded Word files (`edit_document`)

Step 4 of the owner's Word plan, built 2026-10-12. Their use: a teacher's exercise file (Đại số Bool, hồi quy…) where
answers go right under each question, with real equations, truth tables and Karnaugh maps. Before this they pasted Peto's
chat answer into Word, which broke overlines into "xˉ".
- **Tracked changes, author "Peto"** (the owner's pick over plain text or bold answers). Every insertion is `w:ins`, every
  removal `w:del` with `w:delText`, so the user reviews in Word and uses Accept All or Reject. Revision ids continue
  after the largest `w:id` in the file. Replacing or deleting Peto's own earlier insertion removes it outright, as Word
  does for your own tracked text, so revising an answer never stacks two layers of marks.
- **Package** (`features/documents/word_edit/package.py`): only `word/document.xml` is rewritten (lxml, keeps namespace
  declarations for `mc:Ignorable`); every other part is copied byte for byte with its name, order, date and compression.
  Same size limits as the reader; DTDs, encrypted/OLE (.doc) and Strict Open XML files are refused with a hint.
- **Operations** (`ops.py`, strict schema, at most 30 per call, atomic, up to 8 refusals reported at once):
  `insert_after` (Markdown content, parsed by `export.parse_blocks`: paragraphs, lists written as text labels, Markdown
  tables, `$…$`/`$$…$$` as native OMML through `math/omml_out`), `replace` (one paragraph), `delete` (paragraph or table)
  and `fill_cell` (row/column by grid position, honouring `gridSpan`, refusing `vMerge` continuations).
  - Targets are the reader's own numbers: `word_reader.numbered_blocks` is shared by `read_body` and the editor, and every
    target in one call refers to the file before that call. Repeated inserts after one target keep their order;
    deletions run last.
  - Paragraphs or cells holding equations, pictures, fields, footnotes, text boxes or section breaks cannot be replaced
    or deleted (Peto inserts a new paragraph instead); Peto's own insertions inside them do not count.
  - Inserted text takes font, size and language from the target paragraph, or the nearest paragraphs that set them,
    never bold/italic/colour. Tables get single borders, a header row (`tblHeader`), widths from `export.column_widths`
    and the page's text width. An empty Peto paragraph separates two adjacent tables (Word would merge them) and follows
    a table that would otherwise end the body.
  - The reader now numbers empty tables too (`[Bảng N]` / `(bảng trống: R hàng × C cột)`) so Peto can fill a blank
    answer grid; a file with nothing but empty tables still reads as no text. `WORD_FORMAT` is 4.
- **Storage.** Each success is a `style='wordedit'` version (`docx` asset, `pages` 0, no PDF/preview: no Word on the
  server to lay pages out). Content holds the change lines, a "Mã dấu sửa của từng thay đổi" line (each change's first
  and last revision id) and a 40,000-character reread with the new numbers, which Peto reads next turn. The same
  card-per-file-per-turn merging as Excel applies; `MAX_EDITS_PER_TURN` is shared.
- **API.** Export serves only `docx` (pdf 400); manual `versions` edits 400; `/preview` 404.
  `GET /api/documents/{id}/word?version=` (`preview.py`) rebuilds blocks from the stored file: parts marked ins/del,
  equations as LaTeX, Word numbering labels, per-block revision ids, and the change list with its id ranges.
- **UI** ("Nhật ký", picked by the owner 2026-10-12 from three live variants; the others were a white Word-like page with
  a markup/final toggle, and a diff of only the changed spots). The card (`WordEditArtifactCard`) lists the first changes
  ("Đoạn 5 · Chèn 1 bảng"). The panel (`WordView.tsx`, lazy, KaTeX) puts the clickable change list above the content in
  the app theme: inserted blocks tinted with `--sheet-accent`, deletions struck in `--danger`. A change jumps to the
  blocks whose revision ids fall in its range, so it stays right on later versions that still carry earlier marks.
- **Prompt.** Both cores tell Peto to use `edit_document` only when asked to write into the file, to put a whole
  exercise in one call, and to say it cannot draw circuits or figures into the file. `asks_edit` also matches "chèn",
  "làm bài", "giải bài"… for the Grok follow-up nudge.
- **Mock:** `__suaword__` inserts a sample answer (paragraph with an equation, and a table) after Đoạn 1 of the newest
  Word file.
- **Checked in real Word by the owner (2026-10-12):** insertions, including equations (`w:ins` wrapping `m:oMath`), show
  as tracked insertions, the deletion is struck, and Accept All leaves a clean file. That check also found "F_{\min}"
  drawn as "Fmin□": `omml_out` wrote a function name with no argument as `m:func` with an empty `m:e`, which Word shows
  as an empty slot. A bare function name is now a plain upright run (this also fixes `create_document`).
- **Tests:** `backend/tests/test_word_edit.py`, frontend `DocumentArtifactCard.test.tsx` and `DocumentPanel.test.tsx`.

# Dated log (newest first)

## Diagram titles with a colon (2026-11-13, committed on branch `diagram-title-quotes`, not deployed)

Found during the G1.1b real-app check: Haiku wrote `title: Sơ đồ hoạt động: Quy trình đăng nhập` and the chat card said
"Mã sơ đồ không hợp lệ". The second ": " makes the YAML frontmatter invalid (Mermaid's parser: "bad indentation of a
mapping entry", reproduced with the deployed Mermaid build), and `persona.DIAGRAM_PROMPT` itself asked for titles that
start with "Sơ đồ hoạt động: " without asking for quotes, so any model could hit it.
- `diagrams.quoteTitle` puts double quotes (escaping `\` and `"`) around an unquoted `title:` value inside the leading
  `---` block; quoted values, block scalars (`|`, `>`) and code without frontmatter are left alone. `renderDiagram` applies
  it to the copy handed to Mermaid only, so the source shown, copied or downloaded and the diagram identity
  (`normalizeDiagram`) are unchanged, and old messages render again.
- `DIAGRAM_PROMPT` now says `title: "..."` with the title in double quotes.
- Tests: `frontend/tests/diagramTitle.test.ts` (4, including the real Mermaid parser rejecting the original and accepting
  the quoted copy). The quoted copy of the real failing diagram also rendered to SVG (title and 10 nodes) in the in-app
  browser.

## Tolerant text/log reader (2026-10-19)

The owner's Minecraft report was valid UTF-8 (75,168 bytes) but rejected before any model call because it contained
seven NULs in nvspcap64.dll version metadata. `features/documents/text_reader.py` now supplies the shared decoder
used by upload validation, excerpts and full attachment search/line reads. Strict UTF-8/BOM UTF-16/UTF-32 decoding;
no Latin-1 fallback or lossy replacement. Sparse C0/C1 controls other than TAB/CR/LF become visible `[U+XXXX]`
markers, with a notice/count. More than 1% controls or 4096 total is rejected. Preserve original uploaded bytes and
line breaks; even short excerpts retain leading/trailing blank lines so line tools and context agree.
`reader.py` keeps `decode_text` as a compatibility import. New text results carry text_format=1, encoding and
normalized_controls. Global reader VERSION stays 3 to avoid invalidating PDF/Word/Excel/OCR caches. Old long-text
excerpts (recognized by their existing "Tệp dài " notice) expire through Chat's bounded legacy re-read path.

Long-log selection prioritizes Caused by/Suppressed/Description/fatal/critical/panic/Traceback, then errors, then
warnings, retaining source order and true line numbers. Oversized candidates are skipped rather than stopping the
search. This is deterministic excerpt selection, not semantic diagnosis; full search/read tools remain available.
No model/provider prompt change, frontend change, new dependency or CLI update. User's actual file passed validation,
process extraction (~366 ms locally, not AI latency), search and read at line 114; 608 lines and original SHA-256
unchanged, all 12 unusual controls made visible. Synthetic fixtures avoid committing the private crash report.
Validation: focused reader/document/attachment tests 67 pass; full backend 1408 pass, 1 skip. Changed Python modules
compile and `git diff --check` passes. Provider tests are mocked; no paid calls, commit, deployment or original-file
changes. Deploy/restart backend for the fix; the local parsing time does not measure model response latency.
