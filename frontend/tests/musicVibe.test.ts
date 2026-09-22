import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { BeatPulse, DEFAULT_BEAT_PARAMETERS, getMusicState, musicPose, resetBeatParameters, setBeatParameters, startMusicVibe, stopMusicVibe } from '../src/musicVibe';
const tempora = vi.hoisted(() => ({ start: vi.fn(), stop: vi.fn(), update: vi.fn(), onBeat: null as null | (() => void) }));
vi.mock('@nekopaw/tempora', async importOriginal => ({ ...await importOriginal<typeof import('@nekopaw/tempora')>(),
  startAnalyser: tempora.start,
}));

const capture = vi.fn();
const close = vi.fn().mockResolvedValue(undefined);
function media(audio = true) {
  const videoTrack = { stop: vi.fn(), onended: null as null | (() => void) };
  const audioTrack = { stop: vi.fn(), onended: null as null | (() => void) };
  const tracks = audio ? [videoTrack, audioTrack] : [videoTrack];
  return { getAudioTracks: () => audio ? [audioTrack] : [], getTracks: () => tracks, tracks };
}
beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks();
  resetBeatParameters();
  vi.stubGlobal('AudioWorkletNode', class {});
  tempora.start.mockImplementation(async (options) => {
    tempora.onBeat = options.listeners.onBeat;
    return { workletNode: { connect() {}, disconnect() {} }, stop: tempora.stop, updateParameters: tempora.update };
  });
  vi.stubGlobal('navigator', { mediaDevices: { getDisplayMedia: capture } });
  vi.stubGlobal('AudioContext', class {
    state = 'running';
    sampleRate = 48000; destination = {}; close = close;
    resume = vi.fn().mockResolvedValue(undefined);
    createMediaStreamSource = () => ({ connect() {}, disconnect() {} });
    createGain = () => ({ gain: { value: 1 }, connect() {}, disconnect() {} });
    createAnalyser = () => ({ fftSize: 2048, frequencyBinCount: 1024, smoothingTimeConstant: 0,
      connect() {}, disconnect() {}, getByteFrequencyData(data: Uint8Array) { data.fill(0); },
      getFloatTimeDomainData(data: Float32Array) { data.fill(0); } });
  });
});
afterEach(() => { stopMusicVibe(); vi.useRealTimers(); vi.unstubAllGlobals(); });
it('moves on worklet beats and returns to rest after silence', () => {
  const pulse = new BeatPulse();
  pulse.beat(1100);
  const first = pulse.pose(1200, 1);
  expect(Math.abs(first.yaw)).toBeGreaterThan(1);
  pulse.beat(1700);
  expect(Math.sign(pulse.pose(1800, 1).yaw)).toBe(-Math.sign(first.yaw));
  expect(pulse.pose(4000, 1).yaw).toBe(0);
  expect(pulse.pose(1800, 0).pitch).toBe(-0);
});
it('stops every track and the audio context when disabled', async () => {
  const stream = media(); capture.mockResolvedValue(stream);
  await startMusicVibe();
  expect(vi.getTimerCount()).toBe(1);
  stopMusicVibe();
  stream.tracks.forEach(track => expect(track.stop).toHaveBeenCalled());
  expect(close).toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
  expect(tempora.stop).toHaveBeenCalled();
  expect(musicPose(10000).yaw).toBe(0);
});
it('connects Tempora, publishes beats, and forwards live parameter changes', async () => {
  capture.mockResolvedValue(media()); await startMusicVibe();
  expect(tempora.start.mock.calls[0][0].workletParams).toEqual(DEFAULT_BEAT_PARAMETERS);
  tempora.onBeat!();
  expect(getMusicState().beats).toBe(1);
  setBeatParameters({ sensitivity: 0.9 });
  expect(tempora.update).toHaveBeenLastCalledWith(expect.objectContaining({ sensitivity: 0.9 }), true);
  stopMusicVibe(); tempora.onBeat!();
  expect(getMusicState().beats).toBe(0);
});
it('silence is visible instead of claiming audio is received', async () => {
  capture.mockResolvedValue(media()); await startMusicVibe();
  vi.advanceTimersByTime(5000);
  expect(getMusicState().level).toBe(0);
  expect(getMusicState().message).toContain('Chưa nhận được');
});
it('stops a worklet whose load finishes after cancellation', async () => {
  let finish!: (value: unknown) => void;
  tempora.start.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  capture.mockResolvedValue(media()); const pending = startMusicVibe();
  await vi.waitFor(() => expect(finish).toBeDefined());
  stopMusicVibe();
  finish({ workletNode: { connect() {}, disconnect() {} }, stop: tempora.stop, updateParameters: tempora.update });
  await pending; expect(tempora.stop).toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
});
it('releases a selected source with no audio', async () => {
  const stream = media(false); capture.mockResolvedValue(stream);
  await startMusicVibe();
  expect(stream.tracks[0].stop).toHaveBeenCalled();
  expect(vi.getTimerCount()).toBe(0);
});
it('releases late permission results after leaving Companion', async () => {
  let resolve!: (value: unknown) => void;
  capture.mockImplementation(() => new Promise(done => { resolve = done; }));
  const pending = startMusicVibe(); stopMusicVibe();
  const stream = media(); resolve(stream); await pending;
  stream.tracks.forEach(track => expect(track.stop).toHaveBeenCalled());
  expect(vi.getTimerCount()).toBe(0);
});
it('browser stop-sharing also releases the entire session', async () => {
  const stream = media(); capture.mockResolvedValue(stream);
  await startMusicVibe(); stream.tracks[0].onended!();
  expect(close).toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
});
