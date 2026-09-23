# AIRI scene samples

Downloaded for local evaluation, not yet integrated into Peto Companion.

Source: https://github.com/moeru-ai/airi
Pinned revision: 595ea7260d95d25a654572cfdd52e96cb9441290

Files copied unchanged from `packages/stage-ui/src/assets/backgrounds/`:

- `cozy-tea-corner-in-pastel-hues.avif`
- `cute-streaming-room-with-pastel-decor.avif`

The upstream repository distributes these files under its root MIT license;
no separate license notice was found for these two assets in the inspected
directory tree or README. The root copyright and permission notice is retained
in `AIRI-LICENSE.txt`. This records the repository's licensing, not independent
verification of the artwork's original authorship.

The separate `fairy-forest.e17cbc2774.ko-fi.com.avif` asset was not copied because
its filename indicates an external source whose terms have not been checked.

## Implementation findings

- `packages/stage-pages/src/pages/settings/scene/index.vue`: scene gallery,
  image upload, select/clear, removal of user-added scenes.
- `packages/stage-ui/src/stores/background.ts`: seeds these two built-ins;
  persists image Blobs with localforage/IndexedDB; manages object URLs;
  stores active scene ID on the character card; synchronizes changes between windows.
- Scene images are shared locally; active scene selection belongs to each character.
- A separate layout background system provides wave/image/transparent modes,
  image cover rendering, blur, and a gradient overlay. These should not be
  confused with the character scene gallery.

Suggested Peto scope: a Companion background picker with the existing dark
background, these two samples, and local image import; per-character selection;
IndexedDB storage; fit-to-stage rendering for desktop and mobile. Blur and dim
controls can be added without changing the character's motion settings.
