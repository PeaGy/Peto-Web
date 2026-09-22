import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { BeatPulse, musicPose, startMusicVibe, stopMusicVibe } from '../src/musicVibe';

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
  vi.stubGlobal('navigator', { mediaDevices: { getDisplayMedia: capture } });
  vi.stubGlobal('AudioContext', class {
    sampleRate = 48000; destination = {}; close = close;
    resume = vi.fn().mockResolvedValue(undefined);
    createMediaStreamSource = () => ({ connect() {}, disconnect() {} });
    createGain = () => ({ gain: { value: 1 }, connect() {}, disconnect() {} });
    createAnalyser = () => ({ fftSize: 2048, frequencyBinCount: 1024, smoothingTimeConstant: 0,
      connect() {}, disconnect() {}, getByteFrequencyData(data: Uint8Array) { data.fill(0); } });
  });
});
afterEach(() => { stopMusicVibe(); vi.useRealTimers(); vi.unstubAllGlobals(); });
it('detects repeated onsets but not a steady tone, and returns to rest after silence', () => {
  const pulse = new BeatPulse();
  for (let t = 0; t < 1000; t += 33) expect(pulse.sample(0.1, t)).toBe(false);
  expect(pulse.sample(0.8, 1100)).toBe(true);
  const first = pulse.pose(1200, 1);
  expect(Math.abs(first.yaw)).toBeGreaterThan(1);
  expect(pulse.sample(0.9, 1133)).toBe(false);
  for (let t = 1200; t < 1600; t += 33) pulse.sample(0.01, t);
  expect(pulse.sample(0.8, 1700)).toBe(true);
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
  expect(musicPose(10000).yaw).toBe(0);
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
