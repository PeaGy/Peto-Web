import { useSyncExternalStore } from 'react';

type State = { status: 'off' | 'starting' | 'active'; message: string; strength: number };
let state: State = { status: 'off', message: '', strength: 0.5 };
const listeners = new Set<() => void>();
const publish = (patch: Partial<State>) => { state = { ...state, ...patch }; listeners.forEach(fn => fn()); };
export const useMusicVibe = () => useSyncExternalStore(fn => { listeners.add(fn); return () => { listeners.delete(fn); }; }, () => state);
export const musicSupported = () => !!navigator.mediaDevices?.getDisplayMedia && typeof AudioContext !== 'undefined';
export function setMusicStrength(value: number) { publish({ strength: Math.max(0, Math.min(1, value)) }); }

/** Adaptive bass-onset detector; steady tones and silence don't produce continuous beats. */
export class BeatPulse {
  private average = 0;
  private previous = 0;
  private last = -Infinity;
  private side = 1;
  private started = false;
  sample(energy: number, now: number) {
    const beat = this.started && energy > 0.025 && energy > this.average * 1.35
      && energy > this.previous * 1.12 && now - this.last > 260;
    this.average += (energy - this.average) * 0.08;
    this.previous = energy;
    this.started = true;
    if (beat) { this.last = now; this.side *= -1; }
    return beat;
  }
  pose(now: number, strength: number) {
    const elapsed = Math.max(0, now - this.last);
    const pulse = elapsed < 1400 ? Math.exp(-elapsed / 330) * Math.sin(Math.min(elapsed / 110, Math.PI / 2)) : 0;
    return { yaw: this.side * pulse * strength * 10, roll: this.side * pulse * strength * 7, pitch: -pulse * strength * 4 };
  }
}
let detector = new BeatPulse();
let generation = 0;
let release: (() => void) | undefined;
export function stopMusicVibe() {
  generation++;
  release?.(); release = undefined;
  detector = new BeatPulse();
  publish({ status: 'off', message: '' });
}
export const musicPose = (now: number) => detector.pose(now, state.status === 'active' ? state.strength : 0);

export async function startMusicVibe() {
  stopMusicVibe();
  if (!musicSupported()) { publish({ message: 'Trình duyệt này chưa hỗ trợ chia sẻ âm thanh. Hãy thử Chrome hoặc Edge trên máy tính.' }); return; }
  const token = generation;
  publish({ status: 'starting', message: 'Chọn tab đang phát nhạc và bật chia sẻ âm thanh.' });
  let stream: MediaStream | undefined;
  let context: AudioContext | undefined;
  let source: MediaStreamAudioSourceNode | undefined;
  let analyser: AnalyserNode | undefined;
  let mute: GainNode | undefined;
  let timer: ReturnType<typeof setInterval> | undefined;
  const cleanup = () => {
    clearInterval(timer);
    stream?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    source?.disconnect(); analyser?.disconnect(); mute?.disconnect();
    void context?.close().catch(() => {});
  };
  release = cleanup;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({ video: true,
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
    if (token !== generation) { cleanup(); return; }
    if (!stream.getAudioTracks().length) throw new Error('Nguồn vừa chọn không có âm thanh. Chọn tab nhạc và bật “Chia sẻ âm thanh”.');
    for (const track of stream.getTracks()) track.onended = () => { if (token === generation) stopMusicVibe(); };
    context = new AudioContext();
    await context.resume();
    if (token !== generation) { cleanup(); return; }
    source = context.createMediaStreamSource(stream);
    analyser = context.createAnalyser(); analyser.fftSize = 2048; analyser.smoothingTimeConstant = 0.2;
    mute = context.createGain(); mute.gain.value = 0;
    source.connect(analyser); analyser.connect(mute); mute.connect(context.destination);
    const bins = new Uint8Array(analyser.frequencyBinCount);
    const first = Math.max(1, Math.floor(40 * analyser.fftSize / context.sampleRate));
    const last = Math.min(bins.length - 1, Math.ceil(250 * analyser.fftSize / context.sampleRate));
    let lastSound = performance.now(), lastBeat = -Infinity;
    timer = setInterval(() => {
      analyser!.getByteFrequencyData(bins);
      let energy = 0;
      for (let i = first; i <= last; i++) energy += (bins[i] / 255) ** 2;
      energy /= last - first + 1;
      const now = performance.now();
      if (bins.some(value => value > 8)) lastSound = now;
      if (detector.sample(energy, now)) lastBeat = now;
      const message = now - lastSound > 4000 ? 'Chưa nghe thấy âm thanh. Kiểm tra tab nhạc và tùy chọn chia sẻ âm thanh.'
        : now - lastBeat < 2000 ? 'Đang nhún theo nhạc.' : 'Đang nghe, chờ nhịp nhạc…';
      if (message !== state.message) publish({ message });
    }, 33);
    publish({ status: 'active', message: 'Đang nghe, chờ nhịp nhạc…' });
  } catch (error) {
    cleanup();
    if (token !== generation) return;
    release = undefined;
    const message = error instanceof DOMException && error.name === 'NotAllowedError'
      ? 'Bạn đã hủy hoặc chưa cho phép chia sẻ âm thanh.'
      : error instanceof Error && !(error instanceof DOMException) ? error.message : 'Chưa mở được nguồn âm thanh. Hãy chọn lại nguồn.';
    publish({ status: 'off', message });
  }
}
