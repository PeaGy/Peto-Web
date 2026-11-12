# Imagine notes

Scope: Imagine (image generation): jobs, library, viewer, edits, mobile workspace.

Moved out of `CLAUDE.md` on 2026-11-12 (G0.2). Write new notes for this area here, not in `CLAUDE.md`. Current behaviour comes first, then the dated log, newest first.

# Current behavior

### Imagine (image generation)

**Gallery generation UX (owner request, 2026-10-15):** `GenerationPreview` keeps the chosen ratio and tile positions
from pending to decoded final images. Auto uses a neutral square unless a pending reference's ratio is available;
read that ratio from the displayed source, never eagerly download reference images across historical jobs.
The provisional Auto frame does not claim an output size.
Subtle grain/dots indicate activity only: never show invented percent or fake intermediate AI images. Pause motion
for queued jobs, failed polling, inactive Imagine or a hidden document; honour `data-motion="reduced"`.
Image download/decode failures offer an image-only retry, never another generation POST.
“Tạo thêm” is an explicit new billed batch using the original prompt, count, quality, resolution, ratio and ordered
source snapshots, independent of the current composer draft. It reuses the existing in-flight lock, background job
and uncertain-receipt recovery, never retries an unknown job automatically, and does not create an edit-history child.
“Dùng lại mô tả” restores count too. Welcome templates only fill the draft; keep edit suggestions/reference guidance
removed as previously requested. No provider streaming-preview, video, removal or enhancement capability is implied.

For UI polish, apply the owner's selected `emil-design-eng` and `mobile-native` skills when available
(source: https://github.com/emilkowalski/skills). Keep the owner's Grok screenshots and interaction requests
authoritative. Use the existing motion tokens/press feedback; gate hover by pointer capability, retain
keyboard focus, keep touch inputs at least 16px, and preserve pinch zoom and canvas gestures. Do not add
navigation rails or decorative motion by default. `break-ui` is installed for explicit UI stress reviews.
Emulated mobile tests do not certify Safari keyboard, safe areas, or physical touch feel.

Fully separated from chat: its own router (`features/imagine/api.py`), its own REST call to
`/v1/images/generations` (`ai/imagine.py`), its own `imagine_jobs` / `imagine_images`
tables. Chat **intentionally has no image-generation tool**, so Peto never draws when the
user was just talking.

The current frontend submits `background: true` with a unique `request_id`. The API persists a queued job and
its sources before returning 202, then generates and saves the result independently of the HTTP connection.
`GET /api/imagine/{id}` tracks queued/running/complete/failed/unknown; the frontend resumes polling after reload.
Status reads, workspace history and library reads bypass cache and have a 10-second abortable deadline,
including reading the JSON body. This only cancels the read, never the background AI job. Polling accepts each
job as soon as its response arrives, independently of other stalled/failed reads, then retries transient read
failures without another POST. A completed edit updates history and selects its image only if that root is still
open; closing the viewer must not reopen it on a late result. Sort pending IDs so reordering history does not
restart polling. The library, workspace, status and receipt GET APIs send `Cache-Control: private, no-store`;
image files retain their existing cache policy. Clear the connection notice when no jobs are pending.
`GET /api/imagine/requests/{request_id}` recovers a lost POST response without submitting again. The owner-scoped
`imagine_requests` ledger keeps a fingerprint and job ID even after deletion, so duplicate requests cannot generate
a second billed batch. Conflicting reuse is 409; a deleted original request is 410. An uncertain POST receipt lives
in sessionStorage until checked. No automatic paid retry happens on timeout, restart or lost provider response.

The runner uses the existing `admission` limiter under `imagine:<owner>` and the batch timeout. SQLite serializes
acceptance, allowing one active image job per owner and at most `MAX_CONCURRENT + MAX_QUEUE` accepted image jobs.
Run the backend as a **single process**, as already required by voice: its background tasks are process-local.
Startup marks orphan queued/running rows unknown, and graceful shutdown cancels tracked tasks without replay.
Outputs are only exposed when complete; partial save failure removes them while retaining source snapshots and
an error state. Old clients may still omit `background` and use the original synchronous response/rollback behavior.

Edits accept up to five ordered `source_images: [{data: base64} | {image_id: owned_id}]`; the old mutually exclusive
`source_image` / `source_image_id` fields remain accepted, but cannot be mixed with the new list. PNG/JPEG/WebP
sources are decoded with Pillow and bounded at 8 MiB each (configurable), 16 MiB combined, and 40 MP each.
The Imagine POST route caps the raw JSON body at 24 MiB before parsing, including chunked requests. Sources are
copied per job with explicit `position`, `parent_image_id` and `parent_job_id`, so deleting a prior output never
breaks later edits. Provider JSON uses `image` for one source and `images` for multiple; no multipart API is used.
The API returns both ordered `source_images` and legacy `source_image` (first source). All 15 fixed xAI ratios plus
auto are accepted. Paid provider calls have not been used to verify the current account's multi-image support.

The composer copies Grok's Imagine at the owner's request. Chips above the box pick Nhanh/Chi tiết, the
count and the ratio (`StudioMenu.tsx`, a popover reusing the `.effort-options` classes). The box holds the
source-image button, 1K/2K where Grok has Image/Video, and a round send button whose accessible name stays
"Tạo ảnh"/"Sửa ảnh". Desktop always shows all of it. Below the 720px breakpoint `.studio-dock` floats over
the gallery and collapses to a bar (a library button showing the newest image, a one-line prompt, an options
button) until the prompt is focused or the options button is pressed. A tap outside or a submit collapses it
and blurs the prompt so the phone keyboard hides.

Reference edits use a compact strip of thumbnail attachments. Do not restore the reference-count guidance,
"Gợi ý chỉnh sửa" section, suggestion buttons or their explanatory text: the owner explicitly removed them.
Desktop thumbnails are 56px with a remove button; numbered badges and an accessible first-source action
appear only for multiple sources. File names stay in tooltips instead of large text cards. Reordering
or removing a reference that renumbers others shows a dismissible reminder to check numbered references in
the prompt. Ratio options include purpose hints. The preview's "Thêm làm tham chiếu" appends the viewed
image to the current draft; "Dùng ảnh này" replaces the draft's sources with the viewed image and fills its
prompt from the saved job. It keeps the viewer and large canvas open, replaces the chip/single edit field
with the shared studio composer, and focuses the prompt. Attachments appear above the text; existing
quality/count/ratio controls sit in its footer, and no request is made until Send. The right panel's ratio
and palette prompt actions operate on this same draft. The suspended library must not render another
composer at the same time, to avoid duplicate input IDs and competing refs. `MeasuredImage.tsx` reads actual
natural dimensions after loading for library tiles, previews and comparison panes; it hides previous-image
metadata when the URL changes, rather than guessing dimensions from requested resolution or aspect ratio.

`ImagineLibrary.tsx` opens as a non-modal `<dialog>` within Imagine on desktop, beside the existing app
sidebar; on mobile it remains a full-screen modal. The real sidebar stays usable and can collapse/expand
in both the desktop library and viewer. The gallery behind either view is hidden from keyboard navigation.
It shows output tiles, searches
loaded prompts ignoring Vietnamese diacritics via a top search toggle, and offers medium/small square tiles
(localStorage), All/Liked tabs and created/edited filters. Desktop tiles stay bounded to 240–360px (medium) or
180–240px (small), even with only one image; mobile retains 2/3 columns. Selection/download/delete actions
live in the top bar. Neither library nor viewer adds its own left sidebar/rail. The extra reference-slot guidance row is removed; limits remain enforced by the reference action. The same composer moves into the library, then hides during selection; a ResizeObserver
keeps the last grid row clear of its floating dock. The API returns 40 jobs per page; `before=<last-job-id>` loads earlier jobs with a stable created_at/id order.
The composer appends uploads/paste/drop sources and selected library images (in selection order), with remove and
"Đặt làm ảnh đầu" controls. "Dùng lại mô tả" restores every source. `ImageComparison.tsx` compares a selectable
source and output side by side without stretching. `EditHistory.tsx` follows saved parent links lazily when opened,
including parents outside the current page, and keeps snapshot fallbacks if an ancestor was deleted. A normal click opens the viewer; "Chọn" or a 500 ms long press enters multi-selection. The click generated by releasing a long press is suppressed only for that tile, with an expiry; moving to scroll or cancelling the pointer cancels the timer. Right click opens a per-image menu without entering selection. Selection can share (Web Share with files, hidden when
unsupported), download or delete. Deletion is per image: `DELETE /api/imagine/images/{id}` removes one output
and deletes the job, source image included, once no output is left. `PUT /api/imagine/images/{id}/like` stores
`imagine_images.liked`. Source images of edits cannot be deleted or liked on their own. The heart button lives
in `ImageWorkspace.tsx`, a desktop viewer inside Imagine beside the real app sidebar (modal on mobile):
a fitted image and wide edit prompt in the central area, existing tools across the top of the right
details/action panel (above the image on mobile), zoom/panel toggles, navigation, and side-by-side
comparison in the central stage. `imageTools.ts` implements local normalized crop and vector brush/eraser
strokes with Canvas, extracts a four-color palette, and encodes a new PNG source without overwriting the
stored original. Undo keeps the original plus at most five recent PNG versions in memory; closing/reloading
loses these local drafts, which are labelled as unsaved. Download/reference/edit uses the working PNG;
unchanged images keep their saved ID. A modified reference obeys the existing 5-source, 8 MiB each/16 MiB
aggregate limits. Palette presets only append an editable prompt; no provider request occurs before Send.

The owner's latest desktop screenshots supersede the earlier interpretation of the left tool strip:
info/palette/crop/brush belong in a horizontal row at the top of the right panel. Keep the actual Peto
sidebar visible and usable; never create another navigation sidebar or hide it with a desktop modal.
Back sits at the top-left of the main area, zoom at the top-right. The composer is centered below the
canvas, up to 760px of usable width in an 800px dock regardless of portrait width. Photos retain their aspect ratio and
fit the available height, with extra top clearance when the central area is narrow. Collapsing the right
panel leaves a 60px rail (72px with a coarse pointer) with the existing aspect/reference/share/like/download actions, and an expand
button; it does not add unavailable Grok actions. The full panel groups actions at its bottom. The reaction
row has like/download only: no X social action or duplicate close button. Back closes the viewer. Mobile gives the
image more height and scrolls the detail panel below; the body grid must use `minmax(0,1fr)` to prevent
its controls expanding beyond narrow screens. Opening the viewer suspends the library dialog without
resetting its search/filter state; Back/Escape restores it. Saved versions now appear in an 80px
rail beside the real sidebar, with 64px thumbnails, independent scrolling and overflow arrows.
The rail contains the selected root image and its persisted edits, never sibling outputs from `job.images`.
On mobile it becomes a horizontal strip. Do not animate version selection or wheel zoom.
`imagine_jobs.root_image_id` groups edit jobs under one original output; `edit_parent_image_id` retains
branch ancestry and `edit_kind` distinguishes AI/crop/brush. Existing rows keep NULL roots and their previous
independent library behavior. `/api/imagine` lists roots plus a separate `active_edits` recovery field; children
stay out of the library/gallery/sidebar. Workspace GET resolves an owner-scoped root and its child jobs.
Confirming a crop persists a new file/job with an idempotency receipt, without an AI call. Brush Apply now
requests an AI edit on both desktop and mobile; legacy brush PNG revisions remain readable. Reference uploads
viewed as sources keep temporary crop drafts; applying their brush sketch requests an AI result. Unapplied strokes/prompts remain drafts.
Deleting a root deletes its child jobs/files and preserves request tombstones; active AI/local saves block root
deletion. Source copies used by independent jobs remain independent. Every lookup/mutation filters by owner.
Viewer URLs use `/imagine/<root-image-id>/<version-image-id>` with browser Back/Forward and reload recovery;
the previous `/#imagine/<root-image-id>/<version-image-id>` links remain supported.
These are authenticated workspace links, not public sharing links. Keep dialog opening dependent on initial
library loading as well as the selected image; deep links can resolve before the dialog exists in the DOM.
Mouse-wheel input within the single-image canvas changes its fitted zoom from 50% to 800%, using a
non-passive native listener. Normalize pixel/line/page wheel deltas and keep the image point under the
pointer in place along scrollable axes. Ignore browser zoom modifiers, horizontal scrolling, active brush
strokes and the comparison view. Clicking the percentage restores 100% (the existing fitted scale) and
clears the canvas scroll offsets; plus/minus retain their 25-point steps. Do not animate wheel zoom.
Library and viewer inherit the project's body font, including native buttons, inputs and selects.
Desktop controls are 38px high; viewer panel text is 14px, metadata 12px, and edit text 16px in a
60px-high composer. The panel is bounded to 280–360px. Keep touch targets at least 44px and touch
input text at least 16px. Escape dismisses one library layer at a time; cancellation of the nested delete
confirmation must not also cancel the selection. Resizing across the desktop/mobile boundary switches
dialog modes without clearing the open library's filters.
The mobile library uses a dedicated fullscreen layout: close/select at the top, edge-to-edge tiles,
and a bottom search/filter dock. Compact defaults to three square columns; Wide uses two columns and
the loaded image's natural aspect ratio. Persist mobile density separately from desktop density.
Use explicit max-content grid rows so opening the selection dock never compresses the thumbnails.
Tap views an image; a 500ms hold enters selection and selects it. Suppress the release click and native
touch context menu. Pointer movement/cancel and a second touch anywhere cancel the pending hold; keep
native vertical scrolling and pinch available. Selection shows a top-right check only on picked images,
with the existing share/download/reference/delete actions at the bottom. Hide the dock with zero picks.
Do not mount the generation composer in the mobile library or add an unavailable Tag action.
Mobile controls have 44px targets, search text is 16px, and the header/footer honor all safe-area insets.
Enable viewport-fit=cover only while this mobile library is visible, restoring the previous viewport meta
when it closes or yields to the viewer, so other screens keep their existing viewport behavior.
The mobile image workspace follows the owner's Grok recording (2026-10-08): the image is centered,
small version thumbnails scroll horizontally above the bottom actions, and the direct edit input stays
compact. Render the original thumbnail even before it has edits. Entering tools replaces that dock with
a tool row, horizontal palette presets, or a floating vertical brush-size slider. Collapse the size/color
controls when a stroke starts; keep undo, redo and eraser available. Mobile send always requests one
AI edit, including stroke-only submissions: send the annotated PNG with the selected parent image ID.
Without typed text, use a Vietnamese instruction to turn the sketch into matching image details and
preserve the subject/composition. Crop confirmation still saves PNG versions locally on the server;
do not route brush Apply or mobile send to that endpoint.
Use a separate bottom sheet for metadata, fitted zoom, aspect ratio, comparison and reference actions;
it supports backdrop/Escape dismissal, focus trapping/restoration, and dragging its handle down to close.
Use a non-passive touchstart listener only on custom drag surfaces (drawing canvas, crop box, sheet
handle) to suppress compatibility taps. Do not cancel native scrolling on the version/palette tracks.
The crop overlay takes focus and makes the underlying mobile workspace inert until it closes.
Keep the mobile viewer layout intact. Pending edits cover PNG preparation, the in-flight HTTP request and
the actual pending job for the blurred image, dotted overlay, pending thumbnail and "Đang tạo…" label;
do not wait for the POST receipt to show progress or use timers that fake success. A rejected submission
restores the editable sketch; uncertain requests still require receipt checking before another send.
New results still belong to their root only.
Desktop brush follows the owner's latest Grok references (2026-10-08). Brush size, eraser/color and Style
live in the right panel; sketch undo/redo/delete sit over the canvas next to the existing zoom controls.
Entering brush hides the central composer before drawing. Once there are strokes, redo history, typed text,
or an explicit style, the right panel replaces its usual bottom actions with a prompt, Apply and Reset.
Typing, the first stroke, and pending updates must not resize/reposition the fitted image; reserve a fixed
40px dock for status below it. Reset clears sketch/redo/prompt/style without a request or saved version.
Style defaults to preserving the original. Manga, Illustration, Painting and Realistic (Vietnamese UI labels)
append an aesthetic instruction to the existing edit prompt only on Apply; never send on selection or add
an unsupported provider `style` field. Official xAI image editing docs describe prompt-based style transfer:
https://docs.x.ai/developers/model-capabilities/images/editing . The four consumer dropdown choices come
from the owner's screenshots; the docs do not specify the consumer drawing tool's internal implementation.
Desktop pending blur applies to both the source image and annotation canvas. Clip the white moving dot
overlay to the picture bounds; only animate transform/opacity, never image layout/filter. The dots continue
from PNG preparation through HTTP acknowledgement and job polling, with disabled editing controls and a
pending version thumbnail. Reduced motion keeps static dots/status instead. Always include the root thumbnail
on desktop too, so the first edit doesn't insert a new rail and shrink the image. Failed sends preserve the
sketch, prompt and style. Keep the uncertain-request receipt checks and parent/root grouping unchanged.
Desktop-specific styles live in `features/imagine/imageWorkspaceDesktop.css`; use project fonts and existing
38px controls. The style menu reuses StudioMenu, with focus restoration without scrolling and Escape closing
just the menu. Do not describe annotated reference uploads as a dedicated mask/inpaint implementation.
Mobile styles live in `features/imagine/imageWorkspaceMobile.css`. Sheet transitions use transform/opacity
(260ms entrance, 160ms exit), tool entrance is 180–220ms, and explicit tool layout changes use a 220ms FLIP
transform captured before the action and measured at the final fitted size before paint. Never restart
picture animations for polling, metadata sheets, color popovers, keystrokes or viewport measurements.
The brush color popover overlays the dock; closing it during a stroke must not resize/move the image.
Measure only nonzero stage dimensions and skip identical measurements; keep an unloaded image hidden
until its real fit is known. Move viewport-fit setup to the viewer lifecycle so selecting a version does
not restore/reapply the viewport meta. Focus restoration uses preventScroll, and thumbnail auto-scroll
only scrolls its own track, never dialog/canvas ancestors. Version navigation and wheel zoom remain instant.
Keyboard actions and reduced motion skip
these transitions. Honor viewport-fit/safe areas, 44px touch targets and 16px inputs; use visualViewport
height/offset for keyboards that shrink only the visible viewport, without resizing during browser pinch.
Chromium emulation covers gestures/layout/animation, but physical-phone keyboard, safe-area and touch
feel still need hardware verification.
The viewer's direct edit field sends one edit result; its "Dùng ảnh này" composer uses the existing studio
controls and request path. Both use
the existing background/idempotency/uncertain-request path, without issuing a request just to attach an image.
Edits submitted from the viewer remain there while pending and select the saved result on completion.
No segmentation, AI mask/inpainting guarantee, transparent-background removal, video or tag manager is
implemented here; do not add placeholder buttons that pretend those features are available.
