# Companion notes

Scope: Companion tab: stage, characters and cards, voice relay and voice sources, hearing, emotions, private notes, web search, MAGIC motion, the Companion settings pages and own API keys. The YouTube Player is in `player.md`; shared memory in `accounts-memory.md`.

Moved out of `CLAUDE.md` on 2026-11-12 (G0.2). Write new notes for this area here, not in `CLAUDE.md`. Current behaviour comes first, then the dated log, newest first.

# Current behavior

### Minecraft and Companion plans (from "Language convention")

Minecraft planning context (Peto joining the owner's LAN world, from AIRI's Minecraft integration, 2026-09-28) is
recorded in [PETO_MINECRAFT_PLAN.md](PETO_MINECRAFT_PLAN.md) in the same way. Nothing of it is built yet; consult it
before any Minecraft work.

Companion direction is recorded in [PETO_COMPANION_PLAN.md](PETO_COMPANION_PLAN.md) (rewritten 2026-10-13): the AIRI drift
review, what AIRI is building now, the prioritised next steps and the "not doing" list; the original September plan is
kept at its end as history. The owner's calls of 2026-10-13: web first, and a Companion-only settings page at
`/companion/settings/` modelled on AIRI's web Settings, with the Companion group removed from the shared Settings dialog.
The page was built the same day (see "Companion settings page"). Consult the plan before any Companion work. Like the other plan files it is gitignored, so it
exists only on the owner's machine.

### Companion tab and voice relay

**Product direction (owner reaffirmed 2026-10-01):** Companion strongly follows Project AIRI. Use
[AIRI overview](https://airi.moeru.ai/docs/en/docs/overview/) and [upstream repository](https://github.com/moeru-ai/airi)
as the primary references when proposing or implementing Companion work. Ground feature comparisons in the relevant
upstream documentation/code and distinguish implemented features from roadmap/WIP items. Prioritize AIRI-style
Ears/Mouth/Body/Brain interaction and the web/mobile stage experience. History navigation is a supporting improvement;
voice interaction and character presence should drive the Companion roadmap. Adapt to Peto's current stack and retain
the owner's existing choices for the stage, short English replies, microphone defaults and optional web search.
Since 2026-10-13 the web comes first (AIRI's `apps/stage-web` and the shared `packages/stage-pages`/`stage-ui` code, not its
desktop-only features). The next steps and the AIRI comparison live in `PETO_COMPANION_PLAN.md`.

`Companion.tsx` is mounted alongside Chat like `Imagine.tsx` (an `active` prop, kept alive once
visited) and shows one thread at a time from `GET /api/companion` (since 2026-10-25 several threads, one per character
card each; see the section at the top). It
sends `mode: "companion"`, speaks stable sentences as they arrive unless muted, and stops speaking when the
tab is left.

**Companion persona** (`prompts/companion.py`). Since 2026-09-27 (commit 64097d5) Companion has its own base prompt,
`COMPANION_SYSTEM_PROMPT`, instead of a short addition to the assistant core; `COMPANION_PROMPT` is only an alias kept for
imports. On 2026-09-29 (commit 40203b7) the owner rewrote it: Peto is an adult virtual girl and AI companion, warm and a
little mischievous. Light affection (virtual hugs, kisses, flirting) is allowed without AI disclaimers; pressure,
exclusivity, jealousy, guilt and fostering dependency are forbidden. Real help comes first for serious questions. Replies
are always in English and written for the ear: no Markdown, lists, emoji or `*action*` stage directions. It never names
the model behind it, and never claims capabilities Peto Web does not give it. The prompt also defines the EMOTION and
PRIVATE NOTES markers (sections below). This persona is the owner's own Companion character, separate from the Discord
bot's roleplay character (whose web roleplay mode was removed on 2026-10-18). `tests/test_persona.py` checks only that this
prompt does not name Grok/xAI.

On desktop the layout is a stage on the left and a ~380px chat column on the right (since 2026-10-25 AIRI's size: up
to 500px, below a top row holding the Profile button). The stage holds
the character and the model's credit line. The owner added an animated three-dot thinking bubble on
2026-10-02; other text and controls remain in the chat column. The chat column carries the speaking status, the mute toggle, the conversation list (it replaced "Bắt đầu lại" on
2026-10-25), a notice when
voice is on but the chosen source cannot speak (`voice.problem`), the mic button and its panel (see "Hearing" below), and
the Chat tab's composer styles. Enabling
voice, choosing a source and a voice, and "Nghe thử" live on the Giọng nói page of the Companion settings page, in
`VoiceSettings.tsx` (see "Voice sources"
below).

The default character is the Live2D sample Hiyori; users can import their own Live2D or VRM models (see "Companion
characters, scenes and Beat Sync"). `Live2DStage.tsx` is lazy-loaded and mounted only while Companion is active,
and renders Hiyori from `public/characters`, or an imported model from IndexedDB, with PixiJS 6 and
`pixi-live2d-display/cubism4`. The model path, mouth parameter and head height live in
`characterConfig.ts`; licensing notes are in `frontend/CHARACTER.md`. Because the stage has no
controls, the view changes by gesture: wheel or pinch zooms around the pointer, dragging pans (with the
middle mouse button at the owner's request, or one finger on a touchscreen), double-click resets, and the view is
saved in `localStorage`. The pure math (zoom, pan limits, look
direction, wheel steps) lives in `characterView.ts` with its own tests.

When motion is allowed the model plays its `Idle` motions, breathes, blinks and turns toward the
pointer anywhere on the page; otherwise it holds its pose. "Nhân vật cử động" (since 2026-10-14 the first row of the
Chuyển động block on Cài đặt Companion → Nhân vật) picks `system` ("Theo cài đặt chung", the default) or `always`. Since 2026-10-13 `system` follows the web's
Cài đặt → Giao diện → Chuyển động (default "Mượt", so characters move) instead of the OS. Before that it followed
`prefers-reduced-motion`, and Windows with Animation effects off reports reduced motion, which is why the owner asked
for the "Luôn cử động" override. The
mouth follows the audio that is actually playing (`voiceActivity.ts` reads a 20 ms loudness
envelope against `currentTime`). PCM16 WAV takes the direct path; other browser-supported formats
use `OfflineAudioContext.decodeAudioData` without rerouting or delaying playback. Decoding is serialized,
bounded to 8 MB encoded / 120 s decoded / 8 channels, and stale results are ignored. An unavailable decoder
or unsupported codec leaves speech playback intact and lip sync at zero. `VoiceMouthBlend` gives Live2D
and VRM the same time-based attack/release at 24/30/60 FPS; pause, waiting and stop immediately close the
speech-driven mouth. Authored emotion mouth baselines remain independent.

Companion presence (2026-10-02) adapts AIRI's `packages/stage-ui-live2d/src/components/scenes/live2d/presence-bubble.vue`
and `packages/stage-shared/src/presence-bubble/{placement,follow}.ts`: the renderer updates a shared DOM bubble each frame,
anchored to the head, preferring above and switching sides with hysteresis when space runs out. Live2D uses a
Head/Face hit areas where available, otherwise adapts AIRI's `head-anchor.ts` to identify drawables moved by head
angles once before showing the model. Probing restores parameters; subsequent frames read only selected bounds.
Models without a head rig retain a face-height fallback; VRM projects its head bone. A damped spring follows
the animated head with slight lag/overshoot, substepped at 120 Hz, with stabilized placement decisions.
It follows pan/zoom, never receives input, hides with unavailable/offscreen characters and on stop/end/tab exit,
and uses static dots when the web reduces motion unless the owner selects "Luôn cử động". Generation controls it independently of speech playback.
Character settings include per-model `composerGaze` (default true, including old saved preferences). Only actual
typing in a focused desktop composer attracts eyes/head for 3 s after the latest keystroke; blur, send and inactivity release attention.
Both renderers restore the previous pointer/idle behavior with a 0.45 s release time constant, retaining gaze
ownership until settled so idle/pointer cannot snap the head back. The switch is independent of cursor tracking
and respects the existing system/always motion preference. Recognized speech and old drafts never trigger it.
Typing the next draft during generation/playback still attracts gaze without changing the body phase or lip sync.

Companion phase 2 (2026-10-02) coordinates Body with Ears and Mouth:
- `useCompanionActivity` prioritizes actual playback, generation/waiting, then hearing/typing attention.
  A manual keystroke holds listening attention for 3 s; an unsent or recognized draft alone never holds it.
  Hearing `speaking` and `transcribing` both hold attention, but opening a silent microphone does not.
- `LocalVoicePlayer` publishes `playing` only after media `playing` or a fulfilled `play()` promise.
  `buffering` covers gaps between chunks and media waiting. The body holds its speaking pose for 350 ms,
  then thinks until playback resumes; the mouth follows media independently and stays closed during gaps.
- Completion, failures and stop dispose media callbacks, envelope tracking and object URLs, and abort any
  prefetched synthesis request. Late play/decode callbacks cannot change a newer speech session.
- Switching character stops the old speech and clears its expression. Leaving the tab keeps the existing
  reply request behavior but stops playback and unmounts the renderer. Mobile stage layout, opt-in microphone,
  auto-send, motion preferences and frame-rate limits are preserved.
- Regression coverage: activity, audio envelopes, speech lifecycle, both renderers and Companion unit tests;
  browser tests record/decode a local Opus sample with real media playback and exercise UI lifecycle at
  desktop/mobile sizes. External providers and speech recognition are mocked, with no paid calls.
  The hearing browser test uses a synthetic looping PCM16 fixture instead of Chromium's intermittent
  fake microphone beep, so its AudioWorklet meter check is deterministic on Windows.

VRM characters (`VRMStage.tsx`) got the missing items of AIRI's Body list on 2026-09-28, at the owner's pick:
- **Idle eyes.** After 3 s without pointer movement the eyes glance around (`IdleEyes`, as in Live2D).
  - The glance is an angle around the head (`IDLE_YAW`, `IDLE_PITCH`). VRM bone look-at turns the eyes only about 10°
    for a 90° gaze, so small offsets would not show.
  - The head follows a little only when motion is allowed. The eyes still glance under reduced motion, as the Live2D
    test (`idle eyes override motion eye values even with … reduced motion on`) has pinned since 2026-09-23.
- **Blinks.** `Blinker` blinks at random gaps of 1.5–6 s, sometimes twice in a row, and only when motion is allowed.
  Before, VRM blinked every 4.3 s exactly.
- **Checking it.** On 2026-09-28 the owner's VRoid model was checked in headless Edge. This machine's Windows has
  animation effects off, so headless Edge reports reduced motion too. Emulate `prefers-reduced-motion: no-preference`
  (`Emulation.setEmulatedMedia`) to see blinks. Since 2026-10-13 this only matters when Chuyển động is "Theo máy": by
  default the web ignores the OS setting.

Phones get AIRI's mobile look instead, at the owner's request. Below `COMPACT_QUERY` (the same 720px
breakpoint as the CSS) the character fills the screen in a fixed frame (`compactHeight` and
`compactTop` in `characterConfig.ts`). The header, messages and a pill composer float over it in
translucent `--stage-*` colours defined on `.companion`. Zoom, drag and double-click are ignored
there; since 2026-10-15 the size and position are set on Cài đặt Companion → Nhân vật instead (see "Companion character
page"). A finger held on the screen acts as the pointer, and the character looks at it until
the finger lifts. `index.html` sets `interactive-widget=resizes-content`, so on Chrome for Android the
keyboard shrinks the layout instead of panning the page away. That shrink keeps the message list's scroll position,
which used to hide the newest reply behind the keyboard (the owner saw the middle of the thread on 2026-09-27). A
ResizeObserver in `Companion.tsx` now pins the list to its bottom on every resize, unless the user has scrolled up.
Check it in a pane that is really drawing: a hidden browser skips ResizeObserver callbacks and scroll events. The compact frame keeps the tallest stage
height seen at the current width, so the shorter stage leaves the character's size and position alone.
Safari on iOS ignores that viewport setting.

The home source ("Máy nhà của Peto") is generated on the owner's Windows PC, never on the VPS, and reaches
listeners through the VPS in three hops:

1. `local-tts/speak_server.py` lives in a gitignored experiment folder with its own venvs. It loads
   Qwen3-TTS 0.6B through faster-qwen3-tts and serves `GET /health` and `POST /speak` (up to 300
   characters in, WAV out) on `127.0.0.1:7862` only. It still rejects foreign Origins and any Host
   other than 127.0.0.1/localhost, but browsers no longer call it.
2. `voice-worker/relay.py` (run by `voice-worker/start-relay.ps1` in the same venv) connects **out**
   to the site over HTTPS, so the PC opens no port. Every 5 s it checks the local server and, if both
   voices are loaded, posts a heartbeat. It polls `GET /api/voice/worker/next`, has the local server
   speak the job, and posts the WAV to `/api/voice/worker/result/{id}`, or an empty body with
   `X-Voice-Error: 1` if speaking failed. It sends `PETO_VOICE_WORKER_TOKEN` (32+ characters, the
   same value as on the VPS) only to the site, requires an HTTPS `PETO_VOICE_SERVER_URL`, and never
   follows redirects. `tests/test_voice_worker.py` checks the token never reaches the local server.
3. `backend/features/voice/api.py` serves signed-in users. `GET /api/voice/health` reports `home.online` (a
   heartbeat in the last 15 s) and lists the home voices in `voices` only then. `POST /api/voice/speak`
   with `playful-1` or `gentle-2` and up to 300 characters queues a job and waits up to 120 s for the audio: 429 when four jobs are
   already queued or this owner has one, 503 when the worker is offline or reports a failure, 504 on
   timeout. Results must be a RIFF/WAVE body under 8 MB. A listener disconnect removes the job, late
   audio is rejected instead of reaching another listener, and nothing is written to disk.
   `tests/test_voice.py` covers this with fake WAVs.

The queue and heartbeat live in process memory, so the backend must run as a **single** uvicorn
process with a single relay. A restart drops waiting jobs, and a job claimed by a relay that dies
waits out the 120 s timeout. Registration is open, so any signed-in account can
use the owner's GPU while the relay runs; stopping the relay stops sharing. Setup and operating
limits are in `voice-worker/README.md`.

**Voice sources** (option A, picked by the owner from mockups on 2026-09-24, modelled on AIRI's "official provider plus
your own key"). The Giọng nói page of the Companion settings page shows the sources as cards in two groups, and the card picked is the source
Companion speaks with:

- **Giọng Peto** (`official`): the voices in `speech_cloud.catalog()` (StepFun, plus OpenAI or Qwen Cloud when
  enabled), called with the owner's keys. Each Discord, Google or GitHub account gets `PETO_TTS_FREE_CHARS_MONTHLY`
  characters (5000) a month, counted in `voice_usage` by `PETO_DEFAULT_TIMEZONE` month (`voice.MEMBERS`; guests got 403
  until guest login was removed). `db.take_voice_chars` checks and adds in one statement before
  the call, a failed line gives its characters back, and `X-Peto-Voice-Used` returns the new total. A used-up
  allowance is a 429 with `X-Peto-Quota: exhausted`, which, like 502/503/504, lets `/speak` switch to the request's
  `fallback` voice. The shared USD ceiling (`PETO_TTS_MONTHLY_USD`, `speech_budget`) still applies on top.
- **Máy nhà của Peto** (`home`): the relay above.
- **Khóa của bạn**: since 2026-10-13 the keys are entered on Cài đặt Companion → Nhà cung cấp (see "Companion
  providers"); the Giọng nói page only picks the source, model and voice. Eight providers in `voiceProviders.ts` (OpenAI,
  ElevenLabs, Azure Speech, Google Gemini, MiniMax,
  Alibaba Cloud, StepFun, any OpenAI-compatible server). Keys stay in that browser's `localStorage` (`peto-voice-keys`)
  and bill the user's own account. The browser calls the provider directly, except StepFun (it blocks browser calls,
  checked 2026-09-24) and Alibaba Cloud (Qwen answers with an audio URL the browser cannot fetch, and CosyVoice is a
  WebSocket that needs the key in a header). Those two go through `POST /api/voice/relay` with the key in
  `X-Voice-Key`: used for that one call, never stored, logged or charged to the owner. Voice and
  model ids must match `[\w.\- ]{1,64}`, and the region must be a key of `QWEN_ENDPOINTS`. All audio becomes WAV PCM16
  (`audioBytesToWav`, `normalizeWav`) along the existing provider paths; lip sync also accepts other
  browser-decodable audio now, without changing those provider request formats.
  On 2026-09-24 the owner tried Azure Speech with a real key: "Nghe thử" and Companion both spoke. The other seven
  are still untested with real keys; their request shapes follow each provider's docs from that day.

The fallback (`peto-voice-fallback`) is `home`, `official`, or empty for text only. Unset means `home`, and older values
(a voice id) map to their source. Server sources send it to `/speak` as `fallback`. Key sources fall back in the
browser (`withFallback`) on any error, and the notice carries the provider's error, so a wrong key is not hidden. A
source that cannot speak at all (allowance used up, home machine off, key missing) speaks through the fallback directly
(`fallbackOnly`), and `status` counts a usable fallback as ready. "Nghe thử" never falls back (`speak(…, { fallback:
false })`): hearing the fallback would hide the very problem being tested.

The detail panel follows the selected card in the DOM with `grid-column: 1 / -1` in a `grid-auto-flow: dense` grid. On
desktop it opens below the card's row, on phones (one column below 520px) right below the card, and screen readers
reach it in order. Fields use `htmlFor` labels (the iOS rule under "User profile"), and the on/off switch reuses the
character settings switch. `backend/tests/test_voice_sources.py`, `frontend/tests/voiceProviders.test.ts`,
`localSpeech.test.ts` and `Companion.test.tsx` cover the allowance, the relay, each provider's request and the fallback
rules.

Every picker on the Giọng nói and Nghe pages of the Companion settings page and in the Micro panel is `Dropdown` from `voiceUi.tsx`, never a native
`<select>` or `<datalist>`. The owner reported on 2026-09-25 that the datalist popup stayed where it was while
Settings scrolled, since the browser draws it as a separate window, and asked for AIRI's behaviour.
- **Placement.** The list sits in the page right under the field (`position: absolute`), so it moves with the field. It
  flips above when there is not enough room below the nearest clipping ancestor, and it re-checks on every scroll
  (a capture listener on `window`) and on resize.
- **Variants.** There are two: select-only (a `role="combobox"` button) and `editable` (an input that filters
  suggestions as you type and still accepts any id).
- **Keyboard.** Arrow keys, Home and End, Enter, type-ahead, and Esc. Esc stops propagation, so it closes only the list
  and not the Settings dialog or the Micro panel.
- **Labels.** `Field` gives its label the id `${id}-label`, which names the listbox.
- **Tests.** `tests/voiceUi.test.tsx` covers the flip and scroll behaviour with mocked rects.

**Alibaba Cloud card: Qwen-TTS and CosyVoice.** The owner liked AIRI's Alibaba voices (龙婉, 龙硕, Stella…) and on
2026-09-25 picked option A from mockups: one card, one Alibaba key, a Model dropdown, like AIRI. The provider id stays
`qwen`, so saved keys survive the rename.
- **Models.** Each model has its own voice set in `KeyProvider.modelInfo`: `qwen3-tts-flash` (48 voices, Vietnamese notes
  translated from the Qwen Cloud voice list), `cosyvoice-v2` (default) and `cosyvoice-v3-flash`.
  - `suggestedVoices`, `defaultVoiceOf` and `voiceNoteOf` pick the set for the current model.
  - Switching models keeps the voice only if the new model has it. Otherwise it falls back to that model's default.
- **Why not v1.** AIRI reaches CosyVoice v1 through its own unspeech proxy. Alibaba shuts v1 down on 2026-10-10.
  - v2 keeps 18 of AIRI's 20 voices as `<id>_v2` (龙彤 and 龙祥 are v1-only) at ¥2 per 10,000 characters.
  - v3 Flash keeps 14 of them as `<id>_v3` at ¥1.
  - Prices are from the China account's model pages, checked 2026-09-25.
- **Voice lists.** `cosyVoices.ts` holds the official China-account voice tables from that day: 100 v2 and 80 v3 Flash
  voices.
  - Only voices that speak English are kept, since Companion replies in English.
  - Voices are grouped by Alibaba's scenes, with Vietnamese notes. Labels are the Chinese name plus a romanisation of
    the id ("龙婉 · Long Wan").
  - The editable voice field shows that label while not being edited, and the raw id while being edited.
- **Relay.** `speech_cloud._cosyvoice` speaks Alibaba's WebSocket protocol:
  - `run-task` with `format: pcm`, 24 kHz and `language_hints: ["en"]`; then `continue-task` and `finish-task` once
    `task-started` arrives. Binary frames are collected until `task-finished`, and the PCM is wrapped as WAV.
  - `task-failed` codes and handshake statuses map to the same Vietnamese messages as the HTTP relays (`relay_error`).
    Alibaba's error text never reaches the user.
  - `websockets` is imported lazily and pinned `>=14` in `requirements.txt`, so an old install breaks only CosyVoice.
    A dedicated logger at WARNING keeps websockets from logging the handshake headers, which include the key.
  - `tests/test_voice_sources.py` runs it against a fake WebSocket server on 127.0.0.1.
  - Nothing has been tried with a real key yet.

**Hearing (Peto nghe, "Ears")**. This is option A, picked by the owner from mockups on 2026-09-24 (AIRI's mic button).
- **UI.** A mic button sits at the left of the Companion composer. Clicking it starts listening and opens the "Micro"
  panel above the composer: a big toggle, a level meter, "Tự gửi", the microphone select and a link to the Nghe page
  of the Companion settings page (`/companion/settings/modules/hearing`). The panel sits inside the chat column, never on the stage, and closes when listening stops. On phones
  (below 720px) a compact status bar above the pill composer replaces it. It all runs in the browser; the backend has no
  part in it.
- **Store.** `hearingEngine.ts` is a module store, like `musicVibe.ts`, shared by Companion and Settings. It holds:
  - the settings, under the `peto-hearing-*` keys;
  - the phase: `off` / `starting` / `waiting` / `speaking` / `transcribing` / `paused`;
  - interim text;
  - a separate level store, so the meter's ~20 updates a second re-render only the meter.
- **Where text goes.** Companion registers a sink (`setHearingSink`) that appends each final sentence to its draft
  (`joinSpeech`). "Nghe thử" in Settings uses a test sink and never touches the draft. The mic opens only on a click, and
  leaving the Companion tab stops listening.
- **Sources.** The first is "Có sẵn trong trình duyệt": the Web Speech API in `browserSpeech.ts`.
  - Interim results show live in the composer, which is read-only while they stream.
  - Browser hearing starts synchronously on the mic click, before opening the optional volume meter, preserving user
    activation. The phase stays `starting` until recognition `onstart`; an unacknowledged start fails after 10 seconds.
    Meter capture failures leave recognition running. Both use the default microphone; the mic selector is disabled
    for this source without erasing the selected device saved for key sources. Two separate captures still exist:
    volume alone is not proof of successful recognition.
  - Speech events or at least 300 ms of audio above 0.01 RMS arm an 8-second no-text notice. This is a diagnostic
    heuristic, not model VAD. Silence alone does not arm it; new words clear it. No-speech notices remain visible in
    Settings while listening. Source availability only claims API support, not a proven working service.
  - All callbacks reject stopped/replaced recognition instances. Intentional mic toggles retain interim words as
    editable draft text; automatic tab cleanup and reply pauses discard them. Unexpected session end/network errors
    retain partial text without auto-send; later finalized speech cannot auto-send that draft until it is manually
    edited or sent. While interim text is displayed, Enter/send cannot drop it by sending only
    the previous draft. Default auto-send and pause choices are unchanged.
  - Chrome ends continuous sessions after silence, so sessions restart. Five sessions in a row that end within a
    second of starting stop with an error; restarts wait 300 ms and stop clears every pending timer.

  The others are the seven key providers in `hearingProviders.ts`: Groq, Azure, OpenAI, Deepgram, ElevenLabs, Gemini and
  OpenAI-compatible servers.
  - The browser calls them directly (CORS checked 2026-09-24).
  - Keys share the Mouth's `peto-voice-keys` store through `voiceProviders.getKeyConfigs` / `updateKeyConfig` /
    `useKeyConfigs`. That store is one snapshot keyed by the raw localStorage string, so saving a key in one tab never
    drops a key entered in the other.
  - `sttModel` is kept apart from the TTS `model`.
- **Recording for key sources.** `hearingCapture.ts` calls getUserMedia with echo cancellation and runs the AudioWorklet
  `hearingWorklet.js`, which batches 2048 frames. The worklet is imported with `?url&no-inline`: Vite otherwise inlines
  files under 4 KB as `data:` URLs, which not every browser loads as a worklet.
- **Cutting sentences.** `hearingAudio.Segmenter` works on volume, with no VAD model:
  - 90 ms of loud audio starts a sentence and 800 ms of quiet ends it;
  - it keeps 300 ms of audio from before the start, caps a sentence at 30 s, and drops blips under 250 ms of speech;
  - sensitivity 0..100 maps to a threshold of -20..-60 dBFS.

  Each sentence becomes WAV PCM16, 16 kHz mono, and sentences are transcribed in order.
- **Errors.** Auth, billing and bad-model errors (`HearingError.fatal`) stop listening. Rate limits and network errors
  show a notice and listening continues.
- **Cách nghe.** "Luôn nghe" (default) or "Giữ để nói"; see "Push to Talk" below.
- **Switches.** "Tạm không nghe khi Peto đang nói" is on by default. It pauses listening while a reply streams or Peto
  speaks, so Peto does not transcribe itself through the speakers, and resumes afterwards. "Tự gửi" is off by default,
  the owner's call, as in AIRI. It sends 700 ms after a heard sentence, and only text that came from hearing: typing
  cancels the pending send.
- **Not done:**
  - official hearing on the owner's key with an allowance;
  - Whisper on the home machine;
  - a model-based VAD;
  - Discord voice. That would live in the bot repo, and since March 2026 Discord requires DAVE end-to-end encryption for
    voice.
- **Tests:** `hearingAudio.test.ts`, `hearingProviders.test.ts`, `browserSpeech.test.ts` and `Hearing.test.tsx` (a fake
  SpeechRecognition and a mocked `hearingCapture`). `browser-tests/hearing.spec.ts` exercises real Chromium microphone
  capture/AudioWorklet with a fake audio device, mocked recognition and blocked external requests on PC/mobile.
  This validates text delivery/lifecycle, not a real browser recognition service or the owner's physical microphone.
  On 2026-09-24 real Edge with Chromium's fake microphone showed the worklet delivering levels.
  No provider has been tried with a real key yet.
- **File names.** `hearingEngine.ts` and `HearingControls.tsx` are deliberately not `hearing.ts` / `Hearing.tsx`: those
  differ only by case, which is the `LocalVoice` problem below.

`localSpeech.ts` holds markdown → speakable text, chunking, the player and the `/api/voice` calls;
`voiceProviders.ts` holds the key providers; `LocalVoice.tsx` holds `useLocalVoice`, `SpeakButton` and the speaker
icons. The "local" names date from the first design, where the browser called 127.0.0.1 directly. Keep the
`peto-local-voice*` storage keys so saved choices survive (a saved name containing `:` is read as a Giọng Peto voice),
and keep those file names distinct beyond letter case: on Windows `./LocalVoice` resolves to a `localVoice.ts` before
the `.tsx`.

`useLocalVoice` is called once in `App.tsx` and passed to both Companion and `VoiceSettings`, so they
share one enabled flag, probe result and player. `speak()` returns a promise that rejects with a
Vietnamese message, and each caller shows its own error. Companion's speech keys start with
`companion-` so the Settings sample does not change Companion's status line.

Companion phase 3 (2026-10-02) reduces the wait before speech and coordinates turn cancellation:
- Chat `meta.voice_stream` explicitly allows early speech only for Companion with web search off. Missing/false
  capability uses completed-reply playback, so older servers and search drafts remain safe.
- `StreamSpeechText` buffers incomplete sentences, decimal numbers, common abbreviations and open fenced code;
  `SpeechQueue` feeds the same player used for replay. Final completion flushes the tail without replaying the whole
  response. Speech still needs a ready, enabled voice and an unmuted, active Companion.
- One audio segment plays at a time, with only one synthesis request prefetched. Stop aborts generation, playback,
  pending synthesis and queue waits. Version/controller guards discard late callbacks. Leaving the tab, muting or
  changing character suppresses automatic speech for the rest of that turn.
- The composer accepts drafts during generation. Delayed server acceptance clears only the draft that was sent;
  newer edits survive. During generation, use Dừng before sending the next turn. While only speech remains,
  Gửi can start the next turn and cancels the previous speech.
- Hearing resumes only if it was enabled and still wanted. Auto-send requires a finalized draft, the waiting hearing
  phase and no reply/speech; speaking again or editing postpones/cancels it. Pausing key-based hearing aborts queued
  and in-flight transcriptions and discards their late results after resume.
- Regression tests cover sentence boundaries, player cancellation, Companion draft/turn isolation, hearing
  resume/auto-send and PC/mobile streaming browser flows using fake services.

Companion long-session recovery (2026-10-02):
- Hidden pages, `pagehide` and offline events stop hearing, including Settings tests. Interim text is retained as
  an editable, non-final draft in its original sink; returning/going online never reopens the microphone or auto-sends it.
  Late permission/capture/transcription callbacks are rejected by the session generation. Starts require a visible,
  online page. Leaving the in-app Companion tab retains its existing cleanup behavior.
- Track end or suspended/interrupted AudioContext disposes key-source capture and reports a restart notice; a failed
  optional browser meter does not stop native recognition. Capture shutdown is idempotent and removes event listeners.
- Key transcription retains at most three segments, including the active request, and each request times out at 30 s.
  Overflow is reported without allocating another WAV; timeout is recoverable. Synthesis times out at 45 s, and media
  playback aborts after 20 s without progress. Cancellation resolves waits even when a provider ignores its signal.
- Background/offline speech stops immediately, discards prefetched audio and suppresses automatic speech for that turn.
  Background text generation is retained; reconnect uses the existing history recovery and never resends a chat.
- Coverage: lifecycle/capture/player/Companion unit regressions, 40 mocked capture cycles and 30 actual Chromium
  capture cycles per PC/mobile project. Hidden-page/lock behavior is simulated; physical Android/iOS lock and live
  browser recognition/provider services still require device trials.

Optional spoken barge-in (2026-10-02) is "Cho phép nói chen" on the Nghe page of the Companion settings page:
- Off by default. Enabling it neither starts the microphone nor enables auto-send. While enabled, the existing
  pause-while-speaking preference is preserved but temporarily overridden; its switch is disabled with an explanation.
  Turning barge-in off restores that choice. No extra controls or panels are added to the stage.
- Browser hearing uses native speech-start events, with non-empty recognition text as a fallback. The volume meter
  never triggers browser barge-in. Key-based hearing uses the existing RMS segmenter with a 250 ms onset instead of
  90 ms to reject short clicks; it retains pre-roll and the current recording/transcription rather than restarting it.
  This is an amplitude detector, not a model-based VAD or speaker classifier.
- Only active Companion hearing can interrupt. Settings' Nghe thử and stale microphone sessions cannot interrupt
  chat, and voice samples from Settings are excluded. New speech cancels Companion generation, current audio and
  queued synthesis and clears the spoken expression, while preserving typed/interim words and the same listener.
  Already received reply text remains; late SSE/audio callbacks cannot overwrite the new turn. Speech remaining after
  generation completes is interruptible too. Final words enter the draft and auto-send follows its existing setting.
- Recommend headphones: capture requests browser echo cancellation, but speaker playback may still be detected as
  new speech and cause false interruption. Do not claim reliable full duplex or verified automatic barge-in in AIRI.
  Unit tests and `browser-tests/companion-barge-in.spec.ts` cover cancellation, draft retention, noise guards,
  default settings and PC/mobile flows with simulated speech/services; physical microphones/providers need real trials.

Push to Talk ("Giữ để nói", 2026-10-13, after AIRI PR #2729) is the "Cách nghe" choice on the Nghe page:
- **Pick.** The owner chose "Bật rồi giữ" from three live mockups (the others: the mic button as the hold control with no
  arming step, and a messaging-app recorder where an empty composer's Send becomes a mic with slide-to-cancel). Testing the
  mockup, they found that clicking the mic then pressing Space only toggled it, because the button kept focus; so Space on
  the armed mic button and pressing and holding it with the mouse or a finger also talk, and a quick click still disarms.
- **Setting.** `HearingSettings.mode` is `always` (default, as in AIRI) or `hold`, in `peto-hearing-mode`. With `hold`, the
  pause-while-speaking and barge-in rows are hidden: the microphone only opens during a hold.
- **Engine** (`hearingEngine.ts`). In hold mode `startListening()` only arms (`phase: "ready"`, no capture). `beginHold()`
  must run inside the key or pointer event, because browser recognition needs the user activation; `endHold()` returns
  `short` under `MIN_HOLD_MS` (300, a cancel) and otherwise finishes; `cancelHold()` drops it (Esc), and blur, hidden page,
  pagehide and offline cancel it keeping interim words as an unfinalized draft. `MAX_HOLD_MS` (60 s) ends a stuck hold.
  - Browser source: one recognition per hold; release calls the new `BrowserSpeechSession.finish(done)`, which uses
    `stop()` (not `abort()`), treats leftover interim text as final because the user said they were done, and never
    restarts. A 3 s safety timer takes the interim text if the browser never ends the session. The level meter opens after
    recognition starts.
  - Key sources: the whole hold is one recording (no silence segmenter), sent once on release; a hold with under 150 ms
    above the sensitivity threshold sends nothing and shows a hint.
  - `onHoldStart` on the sink: starting a hold always stops Peto's speech and reply, like barge-in without its switch.
  - `hint` in the state is a short message that clears itself (`flashHearingHint`).
- **UI** (`HearingControls.tsx`). Arming does not open the Micro popover. Desktop shows `HoldControls`' strip above the
  composer ("Giữ Space hay micro để nói", then "Đang nghe" with levels and a timer, Tự gửi switch); phones (720px) show a
  large "Giữ để nói" button and a Tự gửi pill instead, and `HearingBar` is hidden. `MicButton` focuses itself after arming
  (except on coarse pointers, where the tooltip would cover the pill) so the next Space is a hold. Companion's window
  listener follows AIRI's `KEY_OWNER_SELECTOR` (`SPACE_OWNERS`) and also ignores Space while a `dialog` is open.
- **Auto-send** in hold mode fires as soon as the phase is back to `ready` after a release, with no 700 ms wait.
- **Tests:** `Hearing.test.tsx` (Space, Esc, blur, the armed mic button, Groq one-file recording, the settings row),
  `browserSpeech.test.ts` (`finish`), `browser-tests/hearing.spec.ts` (real capture only during a hold, PC Space and phone
  pad). Not checked on a physical phone or with a real recognition service; the first syllable can be lost while the
  microphone opens, which neither Peto nor AIRI has measured.

Companion images (2026-10-02), following the owner's AIRI desktop/mobile references:
- The image button sits immediately left of the mic on desktop, and as a small separate round button left of the pill
  composer on mobile. Thumbnail previews with remove buttons stay inside the composer; no stage panels or camera/screen
  capture are added. The file picker, clipboard paste and drop accept JPEG/PNG/WebP/GIF, up to 4 images. Following
  AIRI's `packages/stage-ui/src/components/scenarios/chat/composables/use-chat-images.ts`, source files may be up to
  20 MB; `prepareCompanionImage.ts` reduces non-GIF images to at most 1920 px on the longest edge, preserving aspect
  ratio and PNG/WebP transparency. JPEG uses quality 0.85; if the encoded file still exceeds 3 MB the edge decreases
  by 20% per attempt. Small images and GIF animation are retained. Prepared images total at most 3 MB per turn.
  Local originals are never modified; previews and provider uploads use the prepared file. Unreadable images fail
  locally. `useCompanionImages.ts` reserves pending slots, prevents sending before preparation completes, discards
  late batches after reset/unmount, and owns/revokes the draft object URLs on remove/accept/reset/unmount.
- Sending accepts images with or without text. A finalized microphone question sends the selected images with it;
  selecting/removing an image cancels any pending auto-send, and interim speech cannot be sent prematurely.
- The server keeps the existing magic-byte validation, account ownership, attachment persistence and recent-image
  context limits. Non-image files remain rejected in Companion. Image input reaches the existing provider vision
  payload, not OCR or a new image service. Reopening Companion shows the saved images; clicking opens the image.
- Encoding and delayed acknowledgments preserve newer draft text/images. Only image IDs included in the acknowledged
  turn are cleared. Failed/unaccepted sends retain their draft, and cancellation before encoding completes cannot
  dispatch a late request. Optimistic message images use separate data URLs before draft URLs are revoked.
- `Companion.test.tsx`, `Hearing.test.tsx`, chat API tests and `browser-tests/companion-images.spec.ts` cover lifecycle,
  microphone questions, provider payload/history, ownership/deletion and desktop/mobile layout with fake services.

Companion timing diagnostics (2026-10-02) live on the Chẩn đoán page of the Companion settings page ("Kiểm tra tốc độ
Companion", shown open since 2026-10-13; before that it was a collapsed section under Settings → Giọng nói). `companionTiming.ts` keeps at most five in-memory records containing source IDs,
input kind, search flag and monotonic `performance.now()` milestones only; it stores no message, audio or key and
does not add requests. Reload/unmount or Xóa kết quả đo clears them and invalidates pending updates.
- Hearing supplies provider-confirmed end/finalization timestamps. Browser end can arrive after final text, or never
  arrive; key-based hearing marks end when the existing silence segmenter closes a segment. These are detector events,
  not a precise physical end-of-speech measurement. The last finalized sentence supplies the voice draft timestamps;
  manual edits discard them. Missing/reversed intervals are unavailable rather than guessed.
- Turns mark send, first visible text, first speakable sentence, synthesis request, actual playback and reply completion.
  Search replacement discards draft milestones. Stop/error freezes a record; late callbacks cannot alter it or a new
  turn. Player cancellation from settings also marks stopped. A completed text-only turn never claims audio playback.
- UI separates recognition, user/auto-send wait, first text, sentence/search wait, synthesis-to-playback and total wait.
  It shows the voice source selected at send, not a claim about the fallback voice ultimately used. No model/network
  latency claim is made from these client-observed combined intervals. AIRI-style stage layout and microphone defaults
  remain unchanged. Coverage includes store guards, real hooks with fake services and PC/mobile Settings/browser flows.

- Voice stays off until the user turns on the "Bật giọng nói" switch on the Giọng nói page, and nothing calls
  `/api/voice` before that. Even once enabled, the hook only probes after Companion (or its settings page, which is
  part of the Companion tab) has been opened, so the Chat tab never calls it. `tests/Companion.test.tsx` asserts both.
- Chunks stay roughly equal (target 150 characters). Generation is only slightly faster than real
  time; the next chunk is requested when the previous one arrives, so it is ready in time only if
  it is not much longer than the one playing. One request at a time also fits the backend's
  one-job-per-owner limit. An aborted request frees that slot only once the backend notices the
  disconnect (it checks every 0.25 s), so a request sent right after an abort can get 429.
- The backend only relays text and audio, or calls TTS APIs over HTTP. Never add TTS models or their packages to the
  backend or the frontend: `pip install` and `npm ci` on the VPS would ship them to every deployment.

### Companion private notes

On 2026-09-27 the owner tried "pick a number from 1-9 and remember it". Peto said it had picked one and judged
guesses ("No, that wasn't it"), then admitted it never had a number. The model keeps nothing between turns except the
conversation text. The owner picked option A from two: a hidden note (`features/companion/private_notes.py`), rather than only telling
Peto to be honest and swap roles.

- **Prompt.** The PRIVATE NOTES section of `COMPANION_SYSTEM_PROMPT` tells Peto to write a game secret once in
  `<private>...</private>`. That is the one exception to "plain spoken text". Peto must never claim a secret choice
  that is not in an earlier note, and answers guesses only from the note.
- **Storage.** The reply is stored raw, note included, and `_to_chat_messages` sends it back to the model as it is.
- **Stream.** `NoteFilter` removes notes from Companion `delta` events and keeps back a tail that may be the start of a
  tag cut between chunks. `flush` releases that tail at the end of the reply. An unclosed note hides the rest of the
  reply.
- **History.** `_public_message(row, companion=True)` strips notes for `GET /api/companion`. `GET
  /api/conversations/{id}/messages` does the same for Companion threads. The browser, the voice and the copy of the
  reply therefore never see a note.
- **Edge cases.** A reply that is only a note counts as no answer and is not saved (`_visible`), so no empty bubble
  appears. Memory extraction strips notes. The summary keeps them, so a game that outlives the history window keeps
  its secret.
- **Scope.** Only Companion threads are filtered. A Chat reply can contain a literal `<private>` in XML code, and
  must not lose it.
- **Tests.** `tests/test_private_notes.py` feeds the filter at every chunk size and every split point. The mock answers
  `__bimat__:x`, a reply hiding x, and `__doan__`, which reads back the latest note from the history it was sent.

### Companion emotions (Brain)

The second Brain feature. The owner picked from mockups on 2026-09-27: the card layout (B), AIRI's nine emotions, and
initially one emotion per reply, expanded to spoken-segment expressions on 2026-10-02, then restored to one per reply
on 2026-10-05 because rapid face changes looked unnatural in short replies. Before this, Hiyori never changed expression: the sample model ships no expression files, and the
keyword guess (`replyEmotion`) almost never matched once the Companion prompt banned emoji.

- **The model picks.**
  - The EMOTION section of `COMPANION_SYSTEM_PROMPT` asks for exactly one AIRI-style marker at the start of every reply,
    choosing the emotion for the whole reply and keeping it throughout:
    `<|EMOTE_HAPPY|>`, `SAD`, `ANGRY`, `THINK`, `SURPRISED`, `AWKWARD`, `QUESTION`, `CURIOUS` or `NEUTRAL`.
  - ANGRY is meant as mild sulking, never hostility.
  - Private notes and the marker are the two exceptions to "plain spoken text".
- **Stream.** `emotion_tags.MarkerFilter` runs after `NoteFilter` on Companion replies:
  - It removes every `<|...|>` marker from `delta` events, and holds back a marker cut between chunks (up to
    `MAX_MARKER_CHARS`).
  - Only the first recognized marker emits an SSE `emotion` with its UTF-16 offset in public text, interleaved with
    `delta` in source order. Extra and unknown markers are stripped without changing expression. Split markers and
    emoji preserve positions. Replacement filters inherit the turn's first emotion, preventing a second event.
  - Both filters share `reply_spacing.Spacing`. A reply never starts or ends with whitespace, and the whitespace on
    both sides of a removed note or marker merges into one gap: the side with more line breaks, otherwise one space.
    Whitespace away from a removed part stays as the model wrote it. The bubble is `pre-wrap`, and before 2026-09-28
    only spaces merged, so a reply opening with a note and a blank line streamed as a bubble with two empty lines at the
    top (history trimmed them, so a reload hid it).
  - Each module's `strip` runs its filter over the whole text, so history equals the stream character for character.
    The tests compare them exactly at every cut point, never after collapsing whitespace, which is how the blank lines
    slipped through before.
  - The reply is stored raw, marker included, so the model keeps seeing its own habit.
- **History and helpers.**
  - `_public_message(companion=True)` strips markers and returns first `emotion` plus a single `emotion_cues` entry at
    offset zero for the whole reply, including old stored replies with multiple markers, without a schema migration.
    After replacement the saved reply is prefixed with the turn's first marker if needed to keep replay consistent.
  - `_visible` strips notes and markers.
  - Memory and summary input (`companion_memory._talk`) never contain markers.
  - Chat replies are left untouched.
- **Timing (`Companion.tsx`).**
  - `cue()` sets `stageEmotion` (`{emotion, key}`; the key makes two equal emotions in a row count as new).
  - With a ready, unmuted voice, the first offset-based cue waits for actual playback. Prefetch, final text completion
    and buffering cannot change the face. Companion ignores additional emotion events, including those from older
    servers. `StreamSpeechText` carries the same emotion through all queued chunks without restarting the face.
    Completed-reply/replay playback keeps normal chunk limits; replay normalizes old multiple cues to one at zero.
    Muted/unavailable voice uses the first text-time cue; old servers without offsets retain immediate cues.
    Replace clears draft offsets and retains the original first emotion for the whole turn, matching persistence.
    Stopped/replaced speech cannot update the next turn's expression or finalize its timing diagnostic.
  - The face holds while Peto speaks. It is released 1.5 s after speech ends, or 6 s after the reply when nothing is
    read aloud.
  - Tracking begins during voice loading, so a failure before playback still releases the face. Buffering
    keeps the same reply's expression. An ending old speech session cannot schedule a release over a new
    streamed reply's cue; a new cue always cancels the previous release timer.
  - A reply without a marker falls back to `replyEmotion`.
- **Faces.** `characterExpressions.faceSource` decides per emotion:
  - **Auto** (no mapping): an expression file whose name matches, otherwise the built-in face.
  - **Mapping values:** a file id, `@builtin` (`BUILTIN_FACE`), or `''` for none. A mapped file the model no longer
    has falls back to the built-in face.
- **Built-in faces** (`builtinFaces.ts`) are Cubism standard parameters in three kinds:
  - `set` blends toward a value, `scale` multiplies eye openness so blinking survives, and `add` adds head angles so
    pointer tracking survives.
  - `mouthOpen` holds the mouth slightly open when silent; lip sync takes the larger value.
  - `FaceBlend` cross-fades (in ~0.15 s, out ~0.5 s). `Live2DStage` applies the face in `beforeModelUpdate`, after the
    idle-eye blend and before the additive head sway.
  - The values were tuned on real renders of Hiyori. Her ranges: mouth form -2..1 with a default of 1 (she already
    smiles), eye open 0..1.2, cheek -1..1.
  - Her brows sit under the bangs, so the faces differ through eyes, mouth, cheeks and head angle. Angles under ~15°
    barely show on her.
  - Happy closes the eyes fully (eye open 0 plus eye smile gives "^ ^"). At 30% open the owner read it as squinting
    (2026-09-28).
- **VRM.** `VRM_EMOTIONS` maps onto the VRM presets (happy, sad, angry, surprised, relaxed) plus a head roll, and uses a
  model's own expression when it defines one with the emotion's name. `vrmFace` returns the weights, the roll and the
  mouth baseline.
  On 2026-10-11 the owner requested gentler VRM faces: happy/sad use 0.7 and surprised 0.8, matching AIRI's
  `packages/stage-ui-three/src/composables/vrm/expression.ts`; angry was already 0.7. FaceBlend timing, mouth baselines,
  other emotions and Live2D presets stay unchanged. The model's native overrideBlink/overrideMouth rules still apply;
  lower weights may leave more room for blink/lip sync but do not guarantee that for every imported model.
  `browser-tests/companion-vrm.spec.ts` is an opt-in real-render check using `PETO_VRM_SAMPLE_PATH`, with API mocks
  and a local silent WAV. It compares old/new weights on the same real VRM, reads applied mesh morphs and captures
  face previews; the inspection hook and old-weight substitution exist only in test network responses.
- **Picker** (`ExpressionPicker.tsx`, layout B).
  - Nine cards in a 3×3 grid, the on/off switch, and the selected card's source: the shared `Dropdown` for Live2D,
    plain text for VRM.
  - A card sends `previewExpression(id, emotion)`. The stage holds the face for 6 s even when the switch is off.
  - It is the Biểu cảm block of Cài đặt Companion → Nhân vật, beside the page's own stage, so the face shows live.
    Until 2026-10-14 it sat in a dialog covering the stage, and the stage photographed the head for the picker
    (`publishSnapshot`, `faceThumbnail`); that pipeline was removed with the dialog.
- **Checking faces.** A hidden browser pane draws no frames, so the face never moves there. Real renders were captured
  with headless Edge over the DevTools protocol, with a temporary profile and a debug build that exposes `show` on
  `window`. That hook must never reach the source.
- **Tests.**
  - `backend/tests/test_emotion_tags.py`: the filter at every cut point, event order, notes plus a marker, the Chat
    tab. The mock prefixes `<|EMOTE_X|>` for `__camxuc__:x`.
  - Frontend: `builtinFaces.test.ts`, `characterExpressions.test.ts`, `ExpressionPicker.test.tsx`,
    `Live2DStage.test.tsx` (built-in face), `VRMStage.test.tsx`, `api.test.ts`, and `Companion.test.tsx`
    (stubbed stage reading the `emotion` prop).

### Companion web search

On 2026-09-28 the owner decided Companion should only gain features AIRI has, and picked AIRI's web-search module from
the list, with option C from mockups: the page shows no sources.

- **Switch, off by default.** Later on 2026-09-28 a Companion reply on the owner's phone was slow. The owner then picked
  a switch in Settings → "Tra web" (option A, like AIRI's Modules → Web Search; since 2026-10-13 it is the Tra web page
  under Mô-đun of the Companion settings page),
  off by default as in AIRI.
  - `companionSearch.ts` keeps it per browser (`peto-companion-web-search`); `SearchSettings.tsx` renders it.
  - Companion sends `off` unless the switch is on.
- **Server.** With the switch on, a Companion turn uses `web_search="auto"`, so Peto decides when to search.
  - A page sending `on` gets `auto`; there is no forced search in Companion. `off` keeps search off.
  - `PETO_WEB_SEARCH_ENABLED=false` still turns search off for everyone.
- **Telling a search from a slow model.** `journalctl -u peto-web` has one `chat_timing` line per turn (`first_text_ms`,
  `total_ms`, `search`). Each model call also logs a `model_usage` line (`elapsed_ms`, `reasoning_tokens`,
  `search_calls_seen`). `search_calls_seen` counts the search calls in xAI's own output, so it catches a search even if
  the page never showed "Đang tra web…".
- **Spoken instructions.**
  - `_stream_reply(spoken=True)` sets `web_search.spoken_reply`, a ContextVar like `document_tools.current_session`,
    and `search_context` then returns `SPOKEN_SEARCH_CONTEXT`. No provider signature changed.
  - The chat text asks for Vietnamese answers with source links. The spoken one keeps English speech with no links or
    citation marks, asks for one quick query, and says where facts came from in plain words.
- **Replace.** When Peto writes before deciding to search, the provider drops that draft (`replace`), and Companion
  clears the bubble in `onReplace`.
  - That draft often held only the emotion marker. `event_stream` therefore remembers the turn's first emotion.
  - If the text after the search has no marker or starts with a different emotion, the stored reply gets the first
    marker back, so a replayed message keeps the same face for the whole reply.
- **Page.** While searching, the header status and the pending bubble say "Đang tra web…" (`searching`, from
  `onSearch`). Sources still stream and are stored with the message, but Companion never renders them.
- **Tests.**
  - `test_web_search.py` checks the instructions through the real provider with a fake client, and the replace path.
  - `Companion.test.tsx` checks the status and bubble, the cleared draft, that no source is shown, and the switch (off
    by default, `auto` once on).
  - The mock provider never fakes a search (`test_mock_does_not_fabricate_search_results`). The real-render check on
    2026-09-28 therefore used a scratch server that patched the mock.
  - Not yet tried with real Grok.

### Companion characters, scenes and Beat Sync

All three run in the browser only. Nothing goes through the backend, and nothing syncs across devices. Clearing site
data deletes them.

- **Character library** (`characters/characterLibrary.ts`, `useCharacters.ts`, `CharacterPicker.tsx`).
  - **Where it opens.** Since 2026-10-14 the library is the "Chọn nhân vật" dialog (AIRI's ModelSelectorDialog) of the
    Cài đặt Companion → Nhân vật page (see "Companion character page"). It only selects, imports, renames and deletes;
    picking a card or finishing an import closes it so the new character shows on the page's stage. The character name
    in the Companion header ("Đổi nhân vật"), the person button beside the stage, "Nhân vật" in the phone sidebar and
    the settings home card all open that page.
  - **Storage.** Hiyori is built in. Users can add up to 20 of their own models, saved in IndexedDB `peto-characters`
    (stores `models` and `assets`). The selected id lives in `peto-selected-character`; a missing id falls back to
    Hiyori, and a `storage` event keeps tabs in sync. Card thumbnails are captured from the rendered canvas
    (`characterThumbnail`).
  - **Actions.** Users can rename or delete their own models. Deleting removes only the library copy, never the
    user's original files.
- **Import** (`characterImport.ts`, loaded on demand).
  - **Live2D** comes as a ZIP (unpacked with fflate) or a folder (`webkitdirectory`).
    - It needs exactly one `.model3.json` (Cubism 3+) and a `MOC3` magic header.
    - Limits: 1–16 textures, at most 100 expressions and 200 motions.
    - Only files referenced from `.model3.json` are imported. Paths that are absolute, contain control characters or
      `: ? # %`, climb out of the package with `..`, or repeat another path (ignoring case) are refused. Inside a ZIP,
      `__MACOSX/` entries and hidden dot-files are skipped.
    - `CharacterImportReview.tsx` lists motions, expressions, textures, physics and any warnings first; any error
      blocks the import.
  - **VRM** is a single `.vrm` file. The GLB header and the VRM extension are checked, external `uri` references are
    refused, and the name and author are read from the model's metadata. It is rendered with `@pixiv/three-vrm`.
  - **Limits** (`characterLimits.ts`, raised by the owner on 2026-10-11): 200 MB per import, 400 MB unpacked, 128 MB
    per file, 4 MB per JSON file, 512 files.
- **Per-character settings**, the blocks of the Nhân vật page (`CharacterSections.tsx`).
  - **Live2D:**
    - "Cách chuyển động": Hiện tại or MAGIC (`MotionDriverPicker.tsx`, see "Companion MAGIC motion");
    - the idle motion: "auto" (random `Idle` group), off, or one looped motion file, in `peto-idle-motion:<id>`;
    - switches for cursor tracking, idle eyes, breathing, physics and composer gaze, all on by default, in
      `peto-character-effects:<id>`. Physics is disabled when the model declares none. `withCharacterEffects` skips
      only those additive effects for a frame and leaves motions, blinks, pose and lip sync alone;
    - size and position, the expression picker and Beat Sync.
  - **VRM:** composer gaze and the expression picker only (no size, position or Beat Sync).
- **Render quality** (`renderQuality.ts`, `stageQuality` in `companionMotion.ts`). On desktop it is fixed at 30 FPS and
  up to 1.5× resolution. Below the 720px breakpoint it defaults to 24 FPS at 1×; the "Hiển thị trên điện thoại" block
  of the Nhân vật page (shown on phones only) can raise it to 60 FPS and up to 2× (`peto-mobile-render-quality`), for both Live2D and VRM.
- **Scenes** (`CompanionScenes.tsx`, `sceneLibrary.ts`; built 2026-09-23). A background picture behind the stage and chat
  column (`.companion-with-scene`).
  - **Where it opens.** The "Bối cảnh" dialog opens from the image button beside the stage, or "Bối cảnh" in the phone
    sidebar (App's `sceneRequest` counter; on the settings page that sidebar item opens the Bối cảnh page instead). The
    Bối cảnh page of the Companion settings page shows the same `SceneEditor`. A `peto-scene-change` event keeps every
    `useCompanionScene` instance in step, since Companion stays mounted while its settings page is open; it reloads the
    stored images only when images were added or removed.
  - **Backgrounds.** Three are built in: `dark` (the default, no picture) and two of Project AIRI's backgrounds in
    `public/scenes/airi/` (MIT, `AIRI-LICENSE.txt`). Users can upload PNG/JPEG/WebP/AVIF files up to 12 MB and 32
    megapixels. Uploads are stored unchanged as Blobs in IndexedDB `peto-scenes` and shared by every character.
  - **Per character.** Each character remembers its background, darkening (0–80%, default 20) and blur (0–20 px) in
    `peto-scene:<character id>`. Deleting the selected upload falls back to `dark`.
- **Beat Sync** (`musicVibe.ts`, `beatMotion.ts`, `MusicVibePicker.tsx`; built 2026-09-22). The character bobs its
  head to music. This is Live2D only; `VRMStage` does not use it.
  - **Audio source.** `getDisplayMedia` asks the user to share a tab with its audio. The video track is ignored, and
    the source must have audio. It works only where display capture and AudioWorklet exist, in practice desktop
    Chrome/Edge.
  - **Analysis.** Beats come from the `@nekopaw/tempora` analyser worklet, with AIRI's looser defaults (warmup,
    adaptive threshold and spectral flux off). `BeatPulse` adapts AIRI's sway trajectory and beat spring (MIT,
    `public/vendor/beat-sync/`).
  - **Motion.** It adds yaw, pitch and roll to the head angles, scaled by `CompanionMotion`'s `musicWeight` so
    conversation poses take precedence. It moves only when character motion is allowed.
  - **Saved settings.** Strength (default 50%) and analyser parameters are kept per character in
    `peto-beat-sync:<id>`.
  - **Lifecycle.** Capture always needs a fresh click and is never restarted automatically. It stops when the shared
    track ends, the model changes, or the user leaves the Companion tab or signs out (`leaveMusicVibe`, run when the
    Live2D stage or the settings page unmounts). Opening the Companion settings page unmounts the stage but keeps
    sharing, so the Nhún theo nhạc page works. Closing the panel keeps it running. Audio is analysed on the device and never uploaded.
- **Tests:** frontend `characterLibrary`, `characterImport`, `CharacterImportReview`, `CharacterPickerImport`,
  `characterEffects`, `sceneLibrary`, `musicVibe`, `beatMotion` and `MusicVibePicker`.

### Companion MAGIC motion (`characters/magic/`)

AIRI PR #2376 (v0.12.0-beta.5): "Markovian Animation Generator with Illusory Conditioning", procedural Live2D motion AIRI
calls "Neuro-sama like (aka Neuro bump)". Surveyed 2026-10-13 (notes in `PETO_COMPANION_PLAN.md` §4); the owner tried a
live mockup with four variants and on 2026-10-14 chose: add it, default stays "Hiện tại" (AIRI's default is Universal),
keep the mouth-form switch.
- **Setting.** Per Live2D character in Cài đặt Companion → Nhân vật → Chuyển động → "Cách chuyển động: Hiện tại / MAGIC"
  (AIRI: Settings → Models →
  Animation → Motion driver). `magicSettings.ts` stores `{driver, profile, viewTarget, mouthForm}` in
  `peto-character-magic:<id>` with a change event, like `characterEffects.ts`. Profiles: Hào hứng (`excited`, AIRI's
  "Speaking / excited", the default profile), Bình thản (`calm`, "Idle / calm") and Theo lúc nói (`speech`, Peto's own:
  calm while waiting, blending to excited while `voicePlaying()` or activity `speaking`; AIRI makes the user pick one).
  "Mắt nhìn thẳng" is AIRI's force-view-target (eyes counter the head); "MAGIC điều khiển dáng miệng" off keeps the model's
  default `ParamMouthForm` (AIRI always drives it). With MAGIC the idle motion select, cursor tracking and idle eyes are
  disabled, as in AIRI; composer gaze, breathing, physics, blink, emotions, lip sync and Beat Sync stay.
- **Model** (`magicModel.ts`): AIRI's VAR only (production AIRI never uses AR-HMM): ridge regression on the last 20 frames
  at 30 Hz, duplicate channels folded, generation = prediction + a residual drawn from the recording × 1.15, clamped to the
  recording's range, seeded random (mulberry32). Algorithms unchanged, comments translated; MIT notice in
  `AIRI-LICENSE.txt` beside it.
- **Data.** `idle-calm.json` and `speaking-excited.json` are AIRI's two recordings already resampled to 30 Hz (what AIRI fits
  on) and rounded to 4 decimals: 137 + 132 KB, 17 + 21 KB gzipped, versus AIRI's 49 + 65 KB. `magicProfiles.ts` imports them
  and fits both; `loadMagic()` reaches it through a dynamic import (a 42 KB gzipped chunk) only when a character uses MAGIC,
  caching the fit for the page. Fitting both takes about 60–190 ms in the browser on the owner's PC.
- **Runtime** (`magicMotion.ts`): `MagicSource` generates 30 Hz frames on the stage's own clock (AIRI uses a separate
  requestAnimationFrame loop) through AIRI's output filter (cutoff 0.0575, smoothing 0.8) and drops generated mouth opening;
  `MagicRuntime` runs both profiles, blends them (0.35 s in, 0.9 s out), applies the view target and AIRI's spring
  (follow 1, inertia 0.6, 1/120 s substeps), and takes or releases control over ~0.3 s (`owned`).
- **Live2DStage.** `start()` awaits `prepareMagic()` before the first frame, so the Companion loading screen covers the fit;
  a later switch loads it on the fly. `magicWriter` writes in `afterMotionUpdate` (before physics, like AIRI's "final" motion
  plugin, so hair follows the head): head ×30°, body ×10°, eye balls, mouth form, honouring an imported model's
  `live2dControls` mappings for head and eyes. Squint multiplies eye openness in `beforeModelUpdate` after blinking, then the
  emotion face is applied on top (so Vui still smiles and closes the eyes). Values written before `saveParameters` persist
  into the next frame, so on release a parameter no motion rewrote eases back to the model default instead of freezing
  (the prototype had left Hiyori's mouth stuck). `magicOffset` shifts the whole model (AIRI: ±20 px across, ±40 px down).
  Reduced motion (unless "Luôn cử động") keeps MAGIC off. A failed chunk shows "Chưa tải được MAGIC…" and keeps the old
  motion.
- **Not done:** VRM (AIRI has none either); AIRI's motion workbench (recording, keyframe editor, gamepad) and custom
  datasets; checks on a physical phone. Lip sync with MAGIC was checked in headless Edge with a muted fake voice.
- **Tests:** `tests/magic.test.ts` (fit, determinism, ranges, real datasets, filter, runtime, writer release and mappings,
  settings), `CharacterSections.test.tsx` and `Live2DStage.test.tsx` MAGIC cases.

### Companion settings page (`/companion/settings/`)

Built 2026-10-13. The owner picked the "Thẻ AIRI" variant from three live mockups (the others were a settings column
beside the stage, and a two-column page with an overview). Plan and AIRI reading notes: `PETO_COMPANION_PLAN.md`.
- **Routes.**
  - `app/routes.ts` (`CompanionSettingsPage`, `companionSettingsRoute`, `companionSettingsPage`) defines:
    - `/companion/settings/`;
    - `character` (see "Companion character page");
    - `modules`, `modules/brain`, `modules/voice`, `modules/hearing`, `modules/web-search` and `modules/beat-sync`;
    - `providers` and `providers/<id>` (see "Companion providers");
    - `scene`, `memory` and `diagnostics`.
  - Each works with or without a trailing slash. `appView` maps them to `companion`, so the sidebar keeps Companion
    selected.
  - The backend fallback accepts exactly these paths.
  - `tests/routes.test.ts`, `backend/tests/test_static_files.py` and `browser-tests/routing.spec.ts` cover deep links,
    F5, Back/Forward and 404s.
- **App wiring.**
  - On these paths App renders the lazy `features/companion/settings/CompanionSettings.tsx`, and Companion stays mounted
    with `active=false`. As when leaving the tab, speech stops, the stage unmounts and the microphone closes; a reply
    that is streaming keeps going.
  - Entry points:
    - the gear "Cài đặt Companion" in the Companion chat column header (`onOpenSettings`);
    - the Micro panel link, which opens the Nghe page.
  - Navigation:
    - Sidebar "Companion" returns to `/companion`.
    - Each page's back button goes to its parent; the home page's back button returns to `/companion`.
- **Layout** (after AIRI's `stage-layouts/settings.vue`, `page-header.vue`, `icon-item.vue` and `ripple-grid`).
  - One centred column, at most 1040px wide, with a sticky header: back button, the parent page's name small above, and
    the page title at 30px.
  - The home page is a list of large cards: Nhân vật, Nhà cung cấp, Mô-đun, Bối cảnh, Trí nhớ, Chẩn đoán. Each card has
    a title, one description line and a large faded icon.
  - Mô-đun is a two-column grid: Bộ não, Giọng nói, Nghe, Tra web, Nhún theo nhạc.
    - A green dot means "on now": voice enabled, microphone listening, web search on, Beat Sync sharing.
    - Each card also has a one-line status.
  - Leaf pages reuse the existing components: `VoiceSettings` (now without tabs), `HearingSettings`, `SearchSettings`,
    `BeatSyncBody`, `SceneEditor`, `MemorySettings` and `CompanionTimingPanel`. Each `SettingsGroup` is styled as a card
    with a large grey title.
  - Palette: scoped `--cs-*` tokens, using the Companion teal already allowed for on/selected states.
  - Icons are drawn locally (`settingsIcons.tsx`). AIRI's Solar icon set was not copied; its licence has not been
    checked.
- **Motion** (owner, 2026-10-13: smooth by default even when the OS asks for reduced motion).
  - The header title slides in over 250ms.
  - Cards rise with a ripple delay from the card clicked last: 70ms per grid step, 260ms each.
  - On hover (fine pointers only): a teal sweep (transform/opacity), the dotted pattern grows stronger, and the icon
    scales and tilts.
  - A giant faded icon rotates in at the bottom right.
  - `:root[data-motion="reduced"]` keeps only the fades: users choose "Giảm" in Cài đặt → Giao diện → Chuyển động.
  - Focus moves to the page title on every page change.
- **Tests:**
  - `Companion.test.tsx`: the gear, levels, Back, the back buttons, focus, the Nhân vật page from the header and the
    card, and a deep link to Trí nhớ.
  - `App.test.tsx`: the shared dialog has no Companion group.
  - `Hearing.test.tsx`: the Micro panel link and leaving the page stopping a test listen.
  - Playwright: `companion-barge-in`, `companion-stream` and `routing`.

### Companion character page (`/companion/settings/character`)

Built 2026-10-14. The owner asked for AIRI's Settings → Models layout "vì có nhân vật nằm ở giữa để dễ xem những gì đã
thay đổi", picked "Như AIRI" from three live variants (the others: editing in place where the chat column swaps for the
settings, and a three-column page with the library always visible), and had AIRI's "We support both 2D and 3D models"
callout dropped as cramped and unneeded.
- **Layout** (`settings/CharacterPage.tsx`, after AIRI's `pages/settings/models/index.vue` and `model-settings/`). The
  settings page header, then a panel on the left (`clamp(340px, 31%, 440px)`): "Chọn nhân vật" with the current name and
  format, the blocks, a footnote. The page's own `Live2DStage`/`VRMStage` fills the rest and centres the character there
  (Companion's stage is unmounted on settings pages). No scene background, as on AIRI's page. Phones: header, a sticky
  44dvh stage, then the blocks scroll under it, so the character stays in view.
- **Blocks** (`characters/CharacterSections.tsx`, AIRI's collapsible `Section`s; Kích thước và vị trí open first):
  - Kích thước và vị trí (AIRI: Scale And Position): Thu phóng, Ngang, Dọc sliders with reset buttons and "Về vừa khung".
    They write the same per-model view as wheel/drag on the stage; `writeCharacterView(view, id, source)` now dispatches
    `peto-character-view-change` and `watchCharacterView` listens, so the stage moves at once and the sliders follow
    wheel and drag. When only the zoom changes, `Live2DStage` zooms around the head (`zoomAt` at the head point) and
    writes the new pan back. VRM: a note.
  - **Phones** (owner's correction, 2026-10-15): size and position are adjustable on phones too, only here, since the
    phone stage still takes no pinch or drag. The phone view is stored apart from the desktop one
    (`peto-character-view-compact:<id>`; `readCharacterView`/`writeCharacterView` take a `compact` flag and events carry
    it), because the phone frame is an upper-body close-up and the desktop a full body. On phones `Live2DStage`
    measures pan in units of the frame height (horizontal: `PHONE_ASPECT`, 9 : 19.5, of it), so the 44dvh preview
    places the character exactly as the full-screen Companion stage does, only smaller, and the keyboard never moves
    it. Crossing 720px saves any pending view and switches to the other frame's view.
  - Chuyển động (AIRI: Animation): "Nhân vật cử động", MAGIC (`MotionDriverPicker`), idle motion, the effect switches.
  - Biểu cảm (`ExpressionPicker`), Nhún theo nhạc (`BeatSyncBody`, Live2D only) and, on phones only, Hiển thị trên điện
    thoại (render quality).
  - Collapsing animates `grid-template-rows` 0fr → 1fr (240 ms); content is `inert` while closed and may overflow only
    once open, so dropdowns are not clipped.
  - Not ported: AIRI's "Extract colors from model" (Peto has no model-derived theme colour) and the manual parameter
    sliders of "Model Parameters".
- **Removed with the old dialog:** `IdleMotionPicker.tsx`, the Beat Sync dialog (`MusicVibePicker`'s default export)
  and the face snapshot pipeline (`publishSnapshot`, `watchSnapshots`, `faceThumbnail`). App no longer holds
  `characterPickerOpen`; `openCharacters` navigates to the page.
- **Tests:** `CharacterSections.test.tsx`, `CharacterPickerImport.test.tsx`, `Live2DStage.test.tsx` (view sync and
  head-anchored zoom), `Companion.test.tsx` (header and card entry, stage beside the blocks), route tests, Playwright
  `routing`, `companion-presence`, and the opt-in `companion-vrm` / `companion-live2d-controls`.

### Companion providers (own API keys, `/companion/settings/providers`)

Built 2026-10-13. The owner asked for AIRI's Settings → Providers so users can bring their own API keys, and picked the
"Như AIRI" variant from three live mockups (the others: keys inside each module page like Giọng nói, and one "Khóa API"
page per company). Their calls the same day:
- Own keys change only Companion's brain; the Chat tab stays Peto, Luna, Haiku.
- Own-key turns neither read nor write memory, because AIRI's memory is still work in progress. Chat history is still
  stored.
- Web search uses the provider's own search where it has one (xAI, OpenAI, Anthropic, Gemini). Otherwise the user enters
  a Tavily key on the Tra web page, as in AIRI's Web Search module.
- The first batch is xAI, Anthropic, OpenAI, DeepSeek, Ollama (the ollama.com cloud, the owner's pick; the server cannot
  reach Ollama on the user's machine), Google Gemini, Azure OpenAI and Mistral.

**Backend** (`ai/byok.py`, `features/companion/providers_api.py`).
- `ChatRequest.provider` (`{id, model, endpoint?}`) is accepted only in Companion (400 elsewhere). The key comes in
  `X-Peto-Provider-Key`, the Tavily key in `X-Peto-Search-Key`; both live only for that turn and are never stored or
  logged, like the voice relay's `X-Voice-Key`. `byok.choose` validates the id, model and key (printable ASCII, 8–512
  characters) before anything is stored.
- The server only calls a fixed list of hosts. Azure OpenAI accepts only `https://<name>.openai.azure.com` (or
  `cognitiveservices.azure.com`, `services.ai.azure.com`) and calls `<endpoint>/openai/v1`. This keeps users from using the
  server to reach arbitrary addresses.
- Provider kinds:
  - xAI and OpenAI: a keyed `ResponsesProvider` subclass. `send_reasoning` drops `reasoning` and the encrypted reasoning
    include for models that reject them: OpenAI outside `o*`/`gpt-5`/`gpt-6`, and xAI outside `XAI_MODEL` and
    `grok-3-mini`.
  - Anthropic: `ClaudeProvider` with the user's SDK client. `ClaudeClient(adaptive=False)` skips adaptive thinking for
    models older than generation 5.
  - Gemini: the native `streamGenerateContent` API (SSE), with `google_search` grounding when search is on. The key is
    sent in `x-goog-api-key`, never in the URL. The OpenAI-compatible layer has no search.
  - DeepSeek, Mistral and Azure OpenAI: `ChatCompletionsProvider`.
  - Ollama cloud: `OllamaProvider` on `/api/chat` with NDJSON.
  - Both share `_ToolLoopProvider`: up to 3 tool rounds with the time tool and, with a Tavily key, a `web_search`
    function backed by `api.tavily.com`. Text written before a tool call becomes a `replace` draft, like Grok's.
  - DeepSeek and Ollama get image labels instead of images.
  - No SDK retries. HTTP failures map to Vietnamese messages (key refused, quota, rate limit, unknown model, provider
    down); provider text is only logged, clipped.
- A Tavily provider without a Tavily key forces `web_search="off"`, so early speech still works.
- `remembers` is false for own-key turns, and `_build_system_prompt(memory=False)` drops the Discord memory, the memory
  list and the thread summary. `messages.provider` (new column, `''` for Peto) marks both messages of the turn.
  `memory_messages_after` and `messages_before_window` skip marked rows, so a later Peto turn never mines them.
- Usage events use service `byok`, model `byok:<id>` and slug `byok/<id>/<model>` (`usage_service` and `usage_slug` on the
  provider). The admin page therefore never prices them as owner cost, even when the model name matches a priced slug.
- `POST /api/companion/providers/check` (authenticated, `no-store`) lists models with the user's key to verify it.
  Results are filtered to chat models. Azure returns an empty list; the user types the deployment name. Ollama's tag list
  may not prove the key; a bad key then fails on the first turn.
- Mock mode (`PETO_AI_PROVIDER=mock`): own-key turns use `MockProvider("byok:<id>:<model>")`, and the check returns sample
  models (a key containing `__sai__` is refused).

**Frontend.**
- Catalogue: `features/companion/providers/catalog.ts` mirrors `PROVIDERS`.
- Keys share the `peto-voice-keys` store by provider id, so one OpenAI or Gemini key serves the brain, voice and hearing.
  `KeyConfig` gained `endpoint` and `deployment`.
- Brain store: `providers/brain.ts`.
  - `peto-companion-brain` holds `{provider, model}`; Peto when absent.
  - `peto-provider-models` holds the model list from the last successful check.
  - A provider is "connected" only after a check with the current key. Editing or forgetting the key clears that list and
    resets the brain to Peto.
  - `brainRequest(search)` builds the turn's `provider`, key and, only for Tavily providers with search on, the Tavily
    key. `sendMessage` sends the keys as headers.
- Pages (`settings/ProvidersPages.tsx`):
  - `/companion/settings/providers`: intro box, tabs Bộ não / Giọng nói / Nghe, a price filter (not on Giọng nói, whose
    catalogue has no free-tier data), and AIRI-style cards with a status foot (Đã kết nối, Chưa kiểm tra, Chưa có khóa,
    Không cần khóa).
  - `/companion/settings/providers/<id>`: key fields, Kiểm tra kết nối for brain providers, and where the key is used.
  - `/companion/settings/modules/brain`: provider and model dropdowns plus the own-key notice.
  - Tra web: `TavilySection`.
  - Giọng nói and Nghe no longer show key inputs. `KeyLink` reads "Đã có khóa X · Sửa ở Nhà cung cấp" and opens the
    provider page. Model and voice choices stay there.
- Routes: `COMPANION_PROVIDER_IDS` in `app/routes.ts` (`companionProviderRoute`, `companionProviderId`) matches the
  catalogue (a test compares them) and `_COMPANION_PROVIDERS` in `core/static_files.py`.
- Companion's status line under the character's name adds the provider ("Trả lời ngắn bằng tiếng Anh · DeepSeek").
- **Tests:**
  - `backend/tests/test_byok.py`: turns, validation, memory exclusion, the check endpoint, request shapes over
    `httpx.MockTransport`, Tavily, Gemini, Ollama, error messages and usage labels.
  - `frontend/tests/Providers.test.tsx`.
  - Updated key tests in `Companion.test.tsx` and `Hearing.test.tsx`.
  - Browser: `browser-tests/companion-providers.spec.ts` and `routing.spec.ts`.
- **Not checked:** none of the eight providers or Tavily has been called with a real key; request shapes follow each
  provider's docs as of 2026-10-13.

# Dated log (newest first)

## Companion chat UI from AIRI (2026-10-26, in progress, committed `e96fd91`)

The owner asked to port AIRI's chat UI/UX "nguyên bản" (commit `74ddd90`: history.vue, user/assistant-item, action-menu,
reply-*, send-button, ChatArea, chat-panel-header, MobileInteractiveArea). Owner's picks: no reasoning line (it could leak
`<private>` game secrets); self-hosted Nunito for the Companion chat. Code: `features/companion/chat/` (CompanionHistory,
ChatActionMenu, Reply, SendButton, sendMode, chatTime, useSwipeReply, CompanionMarkdown, companionChat.css, fonts/).
- Time separators (5 min gap), "…" menu (Nghe lại, Trả lời, Sao chép, Xóa; right-click; 250 ms long-press on phones,
  no "…" there), swipe left to reply, reply strip + quote, Markdown in bubbles, follow-tail scroll rules, phone top fade,
  AIRI composer (desktop block; phone: paperclip, soundwave → Nghe sheet, pill, Dừng/Gửi/mic), send-key menu
  (Enter / Ctrl+Enter / double Enter, `peto-companion-send-mode`), typing during a reply turns Dừng into Gửi which stops
  then sends. Header is one line (title + mute); status only for screen readers; gear moved beside the Profile pill.
  `SpeakButton` removed (replay is "Nghe lại" in the menu).
- Backend: `messages.quote_id` (startup migration), `ChatRequest.quote_id` (Companion only), model input gets
  `[Replying to: …]` (480 chars, `features/companion/quotes.py`); `DELETE /api/companion/messages/{id}` (409 while a turn
  runs, deletes images, resets a summary that covered it); `done` carries `message_id`.
- Verified: backend `tests/test_companion_messages.py` 10 passed; frontend Companion/Hearing/Providers 99 passed plus
  `tests/companionChat.test.ts` 6; build type-check passed; real-app Edge flows desktop/phone, dark/light, 20/20 checks.
  Not yet done: full frontend/backend runs, Playwright companion/layout specs (were running; `companion.png` baseline will
  need an update after review), docs article, plan and memory notes.

## Companion character cards, stage (e): import/export (2026-10-26)

Last of the five card stages. The layout the owner picked for (d) already placed Upload on the list and Export on the
detail page. Built from AIRI `stage-ui/src/services/airi-card-import-export.ts` and ccc `exportToJSON` (commit `74ddd90`).
Frontend only, committed `308e4bb`.
- Format (`cards/cardPackage.ts`, its own lazy chunk): a ZIP with `manifest.json` (`format: 'airi-character-card'`,
  `version: 1`, `card: {path: 'card.json', spec: 'chara_card_v3'}`, optional `resources.displayModel {path, format, name}`),
  `card.json` in CCv3 (`spec_version` '3.0') and `models/body-model.zip` (`live2d-zip`: the library's normalized files
  re-zipped) or `models/body-model.vrm`. Written with fflate `zipSync` (model stored, JSON deflated): the streaming `Zip`
  writes data descriptors, which Peto's own streaming reader cannot read for stored entries.
- Export ("Xuất thẻ", detail page): fields mapped as AIRI does (first greeting → `first_mes`, others
  `alternate_greetings`), `extensions.airi.modules` empty (provider ids differ), Peto's modules in `extensions.peto`
  (`version`, `display_model`, `modules`). Built-in Hiyori is not packaged (AIRI skips presets too), only
  `display_model: 'hiyori'`. A model this browser lacks exports the card alone, and the toast says so. File name = card
  name minus Windows-forbidden characters. No keys or conversations are ever included.
- Import ("Nhập thẻ" on the list, or a `.zip` dropped on the grid; Files drags only): `readCardPackage` checks manifest
  format/version, card spec and name. It reads through `characterImport.readZip`, now taking `ZipLimits` (packages: 64
  files, model up to `MAX_IMPORT_BYTES`, total +16 MB, JSON 4 MB), and resolves paths with `modelPath` (no traversal).
  The model goes through `importCharacter` and `library.addPrepared(prepared, false)` (new `choose` flag), so neither
  the stage character nor the active card changes. A model failure imports the card alone with a warning; a card
  failure shows the error and removes the model just added. Taken names get " (2)", " (3)" (the server 409s duplicates).
- Warnings (dismissible `card-notice`): greetings past 10 dropped, a non-empty `mes_example` dropped (Peto has no such
  field), names cut to 60, unsupported model formats (Spine, PMX, tachie…) skipped. `extensions.peto.modules` is restored
  when present; an AIRI package keeps only `consciousness`/`speech` providers Peto also has (`BRAIN_IDS`/`VOICE_IDS`,
  tested against the catalogs), never Peto's own sources. Longer fields hit the server's `cards.LIMITS` and fail the
  import with its message.
- Docs: Companion article bullets and keywords `goi the nhan vat`, `the nhan vat airi` (two `test_docs_api.py` pins).
- Tests: `tests/cardPackage.test.ts` (9: AIRI structure, VRM and Live2D round trips, built-in, AIRI-made package,
  unknown providers, errors, names) and two `Companion.test.tsx` cases (import with rename/warnings and a broken zip;
  export download). Real app on the mock stack in Edge: export, re-import as "Mika (2)", an AIRI package with a Live2D
  model (stage unchanged, re-export carries the model), drag-drop, broken zip, 390 px layout, no console errors. Full
  frontend 1,025 passed, build passed, docs tests 47 passed.
- Not done: SillyTavern PNG/JSON cards, Live2D control mappings (`live2dControls`) and AIRI `controls`, a check against
  real AIRI, physical phones. `zipSync` holds the model in memory a few times over, so near-limit models are heavy on
  phones. Deploy: rebuild frontend; restart the backend for the docs article.

## Companion character cards, stage (d): card pages (2026-10-25)

The owner picked prototype variant 1 "Như AIRI" (over a stage-beside editor and a prompt-first master/detail). Built from
AIRI source (commit `74ddd90`): `settings/airi-card/index.vue`, `components/card-list-item.vue`, `card-model-preview.vue`,
`card-detail.vue`, `CardEditor.vue`. The owner committed it (`43baada`). Prototype deleted.
- Routes (`app/routes.ts`, `core/static_files.py` `_COMPANION_CARDS`): `/companion/settings/cards`, `/cards/new`,
  `/cards/<id>`, `/cards/<id>/edit` (`?section=behavior|modules|prompt`); ids are `peto` or 32 hex (`CARD_PATH`, same as
  `cards.CARD_ID`). New `CompanionSettingsPage` values `cards`, `card-new`, `card`, `card-edit`; `onNavigate(page, id)`
  takes a provider or card id. Home page gets a "Thẻ nhân vật" card first; Profile menu "Quản lý Profile" opens the list.
- `cards/CardPages.tsx` + `cardPages.css`: list (search ignoring accents, sort Mới thêm/A–Z/Z–A, 3:4 grid with "Đang dùng"
  outline), detail (hero, Dùng thẻ này, Sửa thẻ, Prompt đầy đủ from `GET /cards/{id}/prompt`, Xóa with the card's
  conversation count / Khôi phục bản gốc for a modified `peto`), editor (hero Tên/Biệt danh/Model hiển thị/Phiên bản +
  side nav Danh tính, Hành vi, Mô-đun, Prompt; AIRI's new-card defaults; Lưu / Lưu và dùng in the settings header through
  a portal slot; PATCH sends only changed fields so `peto` keeps following the built-in; unsaved changes ask on the header
  back button and `beforeunload`, not on browser Back/sidebar). Toasts live in a module store so they survive navigation.
- Card modules now apply (server only stores them): `brainRequest(search, card.modules.brain)` (`peto` forces Peto; a
  provider not connected in this browser falls back to the global brain) and `useLocalVoice(active, cardVoice)` from App
  (`speakSource`, `cardVoice`, `globalProblem`; a key source without a key here falls back to the global voice; Nghe thử
  on the Giọng nói page uses `global: true`). Brain and Giọng nói pages note when the active card overrides them.
- Companion follows card changes made on these pages (`threadCard` vs `cards.active` effect: activate or delete the
  active card, then return). Activating/saving the active card selects its display model if this browser has it.
- `GET /api/companion` for a card with no conversation now returns the card's first greeting as an unsaved preview
  message; the first turn persists the same greeting (`open_conversation`).
- `public/characters/hiyori-preview.webp` (Peto's own 256×320 render of Hiyori) is the card image until this browser has
  drawn Hiyori once (`CHARACTER.md`). Docs: Companion article "## Thẻ nhân vật" (keywords need "companion").
- Tests: `Companion.test.tsx` (3 card cases), `routes.test.ts`, `test_static_files.py`, `test_companion_cards.py` (greeting
  preview), `test_docs_api.py`, Playwright `routing.spec.ts` (deep link to the editor, F5, back, 404s). Real model output
  with user cards, physical phones and real provider keys are untested.

## Companion character cards, stage (a): server (2026-10-25)

The owner chose AIRI-style character cards (AIRI commit `74ddd90`: `stores/modules/airi-card.ts`, `stores/chat.ts`,
`stores/chat/session-store.ts`). Users write the persona; NSFW is not banned and there is no 18+ gate (owner accepts the
xAI-account and cost risk, billing like AIRI's Flux later). One server rule is always appended and not editable:
`prompts/companion_runtime.COMPANION_CARD_RULE` (no sexual content involving anyone under 18). Plan and the remaining
stages (b) conversation list, (c) Profile switcher, (d) card pages, (e) import/export: `PETO_COMPANION_PLAN.md` §3.
The owner committed it with stages (b) and (c) (`6733e1a`).
- `storage/cards.py`: `companion_cards` (PK owner+id; CCv3-like fields, `greetings`/`modules` JSON,
  `active_conversation`), `companion_card_state` (active card), `conversations.card_id` (startup migration sets old
  Companion threads to `peto`). The default card `peto` is created lazily; its NULL columns mean the server's built-in
  values (`features/companion/cards.BUILTIN`: name Peto, `system_prompt` = `COMPANION_SYSTEM_PROMPT`, model hiyori), so
  later edits of the built-in prompt reach users who never edited it; sending a value equal to the built-in stores NULL.
- Prompt (`cards.prompt_parts`, used by `_build_system_prompt(card=)`): system prompt, description, personality,
  scenario (AIRI order), `{{char}}`/`{{user}}` replaced, then the usual server blocks, then post-history instructions and
  the fixed rule; the time block still comes last. Emotion/`<private>` filters run on every card.
- Each Companion conversation keeps the card it was created with; a new one uses `ChatRequest.card_id` or the active
  card and starts with the card's first greeting (`open_conversation`). Opening a conversation of another card makes that
  card active (AIRI keeps the active card; Peto switches so stage and persona match).
- Shared memory (Chat + Companion) and the thread summary apply only to the `peto` card: `storage/memory.MEMORY_SOURCE`
  excludes other cards, `remembers` and `memory=` are false for them. Per-card memory (AIRI `memory.indexFor(persona)`)
  is not built.
- API: `GET/POST /api/companion/cards`, `PUT /cards/active`, `GET/PATCH/DELETE /cards/{id}`, `POST /cards/peto/reset`,
  `GET /cards/{id}/prompt` (the whole assembled prompt, owner's choice to make it public; per-turn Player/search parts
  not included); `GET /api/companion?conversation_id=`, `GET/POST /api/companion/conversations`,
  `PUT /api/companion/active`. Limits: 50 own cards, field caps in `cards.LIMITS`, 40,000 prompt characters, 10
  greetings, unique names (409). Deleting a card deletes its conversations; `peto` can only be reset.
- Tests: `tests/test_companion_cards.py` (13). Real model behaviour with user cards is untested.

## Companion character cards, stages (b) conversation list and (c) Profile (2026-10-25)

The owner picked prototype variant "Như AIRI" and asked for AIRI's chat-panel size so the Profile button sits above it.
Built from AIRI source (commit `74ddd90`): `apps/stage-web/src/pages/index.vue` (`InteractiveArea` absolute right-4,
max 500px, min 30%, 85dvh, Header row above), `chat-panel-header.vue`, `sessions-dialog.vue`/`sessions-list.vue`,
`profile-switcher-popover.vue`. Committed with (a) (`6733e1a`).
- Desktop (`cards/companionCards.css`): `.companion` second column `clamp(360px, 42%, 500px)`, panel margin
  `72px 16px 76px 0`; `.companion-profile-slot` (Profile pill) at top 16px / right 16px. Phones: the Profile button is a
  round avatar in the header tools; menus become bottom sheets (`CompanionPopover`, portal to body).
- Header title = current thread title (`GET /api/companion` now returns `title`), line below = card name · state
  (`.companion-state`). It opens `ConversationList`: "Hội thoại mới" (POST, card greeting), every thread of every card
  with relative time and card name, delete needs two clicks. "Bắt đầu lại" and its dialog were removed.
- `cards/companionCards.ts` is a module store of the account's cards (loaded once per owner by Companion; a bad or
  failed response leaves Companion working without the Profile button). Profile lists cards, "Lưu thành Profile mới"
  duplicates the active card under a new unique name and switches to it. "Quản lý Profile" comes with stage (d).
- Model link: switching card or opening a thread of another card selects the card's `display_model` when this browser
  has it; App writes a user's character choice into the active card (skipping the first value, so one device does not
  overwrite another's); an unmodified default card adopts the model chosen before cards existed.
- Switching threads/cards loads quietly (`load(id, true)`, no full-screen loading), stops speech, and is blocked while
  a reply streams; menu actions are disabled meanwhile.
- Tests: `Companion.test.tsx` (thread list, Profile, cards unavailable), Hearing/Providers mock `listCompanionCards`,
  Playwright fixtures serve cards/conversations; companion specs updated for the new header.
