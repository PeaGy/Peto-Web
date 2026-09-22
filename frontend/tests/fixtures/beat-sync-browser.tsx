// Manual browser integration fixture. Synthetic capture only; never shipped by the production build.
import { createRoot } from 'react-dom/client';
import MusicVibePicker from '../../src/MusicVibePicker';
import { getMusicState, musicPose, startMusicVibe, stopMusicVibe } from '../../src/musicVibe';
import '../../src/styles.css';

async function run() {
  const status = document.getElementById('result')!;
  status.textContent = 'Running real AudioWorklet with stereo PCM (right channel only)…';
  const context = new AudioContext();
  const originalCapture = navigator.mediaDevices.getDisplayMedia;
  let timer: ReturnType<typeof setInterval> | undefined;
  let source: AudioBufferSourceNode | undefined;
  try {
    await context.resume();
    const buffer = context.createBuffer(2, context.sampleRate * 8, context.sampleRate);
    const right = buffer.getChannelData(1);
    for (let i = 0; i < right.length; i++) {
      const time = i / context.sampleRate, phase = time % 0.5;
      right[i] = phase < 0.15 ? Math.sin(2 * Math.PI * 80 * time) * Math.exp(-phase * 25) * 0.9 : 0;
    }
    const destination = context.createMediaStreamDestination();
    source = context.createBufferSource(); source.buffer = buffer; source.connect(destination);
    navigator.mediaDevices.getDisplayMedia = async () => destination.stream;
    await startMusicVibe();
    if (getMusicState().status !== 'active') throw Error(getMusicState().message);
    source.start();
    let peak = 0;
    timer = setInterval(() => {
      peak = Math.max(peak, Math.abs(musicPose(performance.now()).yaw));
      status.textContent = `AudioWorklet running: ${getMusicState().beats} beats; peak yaw ${peak.toFixed(2)}; level ${getMusicState().level.toFixed(2)}`;
    }, 100);
    await new Promise(resolve => { source!.onended = resolve; });
    clearInterval(timer);
    const beats = getMusicState().beats;
    stopMusicVibe();
    status.textContent = beats >= 8 && peak > 0 ? `PASS: ${beats} beats, peak yaw ${peak.toFixed(2)}; capture stopped.` : `FAIL: ${beats} beats, peak yaw ${peak.toFixed(2)}.`;
  } catch (error) { status.textContent = `FAIL: ${error}`; }
  finally { clearInterval(timer); stopMusicVibe(); source?.disconnect(); navigator.mediaDevices.getDisplayMedia = originalCapture; await context.close(); }
}
createRoot(document.getElementById('root')!).render(<main style={{ padding: 24, maxWidth: 960, margin: 'auto' }}>
  <h1>Beat Sync browser verification</h1><p>Synthetic right-channel PCM, real browser AudioWorklet and production service. No screen capture or audible output.</p>
  <button className="settings-button" onClick={event => { const button = event.currentTarget; button.disabled = true; void run().finally(() => { button.disabled = false; }); }}>Run PCM verification</button>
  <p id="result" role="status">Not run.</p><MusicVibePicker />
</main>);
