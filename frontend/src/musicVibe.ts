import { useSyncExternalStore } from 'react';
import { startAnalyser, DEFAULT_ANALYSER_WORKLET_PARAMS, type Analyser, type AnalyserWorkletParameters } from '@nekopaw/tempora';
import workletUrl from '@nekopaw/tempora/worklet?url';
import { BeatPulse } from './beatMotion';
export { BeatPulse } from './beatMotion';

// Match AIRI's less restrictive initial settings; advanced modes remain optional.
export const DEFAULT_BEAT_PARAMETERS: AnalyserWorkletParameters = {
  ...DEFAULT_ANALYSER_WORKLET_PARAMS, warmup: false, adaptiveThreshold: false, spectralFlux: false,
};
type State = { status: 'off' | 'starting' | 'active'; message: string; strength: number;
  parameters: AnalyserWorkletParameters; spectrum: number[]; level: number; beats: number; lastBeat: number };
let state: State = { status: 'off', message: '', strength: 0.5, parameters: { ...DEFAULT_BEAT_PARAMETERS },
  spectrum: [], level: 0, beats: 0, lastBeat: -Infinity };
const listeners = new Set<() => void>();
const publish = (patch: Partial<State>) => { state = { ...state, ...patch }; listeners.forEach(fn => fn()); };
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn); }; };
export const getMusicState = () => state;
export const useMusicVibe = () => useSyncExternalStore(subscribe, getMusicState);
export const musicSupported = () => !!navigator.mediaDevices?.getDisplayMedia && typeof AudioContext !== 'undefined' && typeof AudioWorkletNode !== 'undefined';
export function setMusicStrength(value: number) { publish({ strength: Math.max(0, Math.min(1, value)) }); }
let activeAnalyser: Analyser | undefined;
export function setBeatParameters(patch: Partial<AnalyserWorkletParameters>) {
  const parameters = { ...state.parameters, ...patch };
  // Keep both frequency cutoffs ordered, including when restoring defaults.
  parameters.highpassFilterFrequency = Math.min(parameters.highpassFilterFrequency, parameters.lowpassFilterFrequency - 1);
  activeAnalyser?.updateParameters(parameters, true);
  publish({ parameters });
}
export function resetBeatParameters() { setBeatParameters({ ...DEFAULT_BEAT_PARAMETERS }); }

let detector = new BeatPulse();
let generation = 0;
let release: (() => void) | undefined;
export function stopMusicVibe() {
  generation++;
  release?.(); release = undefined;
  activeAnalyser = undefined;
  detector = new BeatPulse();
  publish({ status: 'off', message: '', spectrum: [], level: 0, beats: 0, lastBeat: -Infinity });
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
  let mono: GainNode | undefined;
  let beatAnalyser: Analyser | undefined;
  let timer: ReturnType<typeof setInterval> | undefined;
  const cleanup = () => {
    clearInterval(timer);
    stream?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    source?.disconnect(); mono?.disconnect(); analyser?.disconnect(); mute?.disconnect();
    beatAnalyser?.stop();
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
    beatAnalyser = await startAnalyser({ context, worklet: workletUrl, workletParams: state.parameters,
      listeners: { onBeat: () => {
        if (token !== generation || state.status !== 'active') return;
        const now = performance.now();
        detector.beat(now);
        publish({ beats: state.beats + 1, lastBeat: now });
      } },
    });
    if (token !== generation) { cleanup(); return; }
    activeAnalyser = beatAnalyser;
    // Parameters may have changed while the worklet was loading.
    beatAnalyser.updateParameters(state.parameters);
    source = context.createMediaStreamSource(stream);
    // Tempora processes its first input channel: mix stereo sources down before analysis.
    mono = context.createGain(); mono.channelCount = 1; mono.channelCountMode = 'explicit';
    analyser = context.createAnalyser(); analyser.fftSize = 2048; analyser.smoothingTimeConstant = 0.2;
    mute = context.createGain(); mute.gain.value = 0;
    source.connect(mono); mono.connect(analyser); analyser.connect(beatAnalyser.workletNode);
    beatAnalyser.workletNode.connect(mute); mute.connect(context.destination);
    beatAnalyser.workletNode.onprocessorerror = () => {
      if (token !== generation) return;
      stopMusicVibe(); publish({ message: 'Bộ phân tích nhịp đã dừng do lỗi. Hãy chọn lại nguồn âm thanh.' });
    };
    const bins = new Uint8Array(analyser.frequencyBinCount);
    const samples = new Float32Array(analyser.fftSize);
    let lastSound = performance.now();
    timer = setInterval(() => {
      analyser!.getByteFrequencyData(bins);
      analyser!.getFloatTimeDomainData(samples);
      const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
      const level = Math.max(0, Math.min(1, (20 * Math.log10(Math.max(rms, 1e-6)) + 60) / 60));
      const spectrum = Array.from({ length: 40 }, (_, i) => {
        const lo = Math.floor(Math.pow(bins.length, i / 40));
        const hi = Math.max(lo + 1, Math.floor(Math.pow(bins.length, (i + 1) / 40)));
        let peak = 0;
        for (let k = lo; k < Math.min(hi, bins.length); k++) peak = Math.max(peak, bins[k]);
        return peak / 255;
      });
      const now = performance.now();
      if (rms > 0.0001) lastSound = now;
      const message = context?.state !== 'running' ? 'Trình duyệt đã tạm dừng xử lý âm thanh. Hãy chọn lại nguồn.'
        : now - lastSound > 4000 ? 'Chưa nhận được tiếng nhạc. Kiểm tra tab nguồn và bật chia sẻ âm thanh.'
        : now - state.lastBeat < 2000 ? 'Đã bắt được nhịp — nhân vật đang nhận chuyển động.'
        : rms > 0.0001 ? 'Đang nhận âm thanh, chưa bắt được nhịp. Thử tăng độ nhạy.' : 'Đang chờ âm thanh từ nguồn chia sẻ…';
      publish({ message, spectrum, level });
    }, 80);
    publish({ status: 'active', message: 'Đang nghe, chờ nhịp nhạc…' });
  } catch (error) {
    cleanup();
    if (token !== generation) return;
    release = undefined;
    activeAnalyser = undefined;
    const message = error instanceof DOMException && error.name === 'NotAllowedError'
      ? 'Bạn đã hủy hoặc chưa cho phép chia sẻ âm thanh.'
      : error instanceof Error && !(error instanceof DOMException) ? error.message : 'Chưa mở được nguồn âm thanh. Hãy chọn lại nguồn.';
    publish({ status: 'off', message });
  }
}
