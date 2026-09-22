# Beat Sync browser verification

Start the frontend Vite development server and open `/tests/fixtures/beat-sync-browser.html`.
Click **Run PCM verification**. The fixture replaces capture only in this test page with an
8-second stereo stream containing 16 synthetic kick pulses on the right channel. It exercises
the production service, mono downmix, real browser AudioWorklet, beat events, movement output,
and resource cleanup without requesting screen permissions or playing audible sound.

Expected: `PASS`, around 16 beats, nonzero peak yaw, capture stopped. The Beat Sync button also
opens the production panel for desktop/mobile layout checks. These fixtures are not included
in the production Vite build.

This does not validate screen-sharing permissions or beat quality on actual music. For that,
open Companion, select a Live2D model, then **Nhân vật → Nhún theo nhạc → Mở Beat Sync**.
Select a music tab and explicitly include audio. Check the spectrum, input meter and beat count.
If the meter moves but the count does not increase, increase sensitivity or reset advanced
parameters. Check that browser stop-sharing, switching model and leaving Companion release
capture. No changes to idle/physics are needed to detect beats.
