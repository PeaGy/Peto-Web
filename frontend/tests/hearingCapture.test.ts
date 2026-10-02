import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { openMicrophone } from '../src/features/companion/speech/hearingCapture';

class Track extends EventTarget {
  readyState = 'live';
  stop = vi.fn(() => { this.readyState = 'ended'; });
}
class Node {
  port = { onmessage: null as ((event: unknown) => void) | null };
  gain = { value: 1 };
  connect = vi.fn(); disconnect = vi.fn();
}
class Context extends EventTarget {
  static all: Context[] = [];
  state = 'suspended'; sampleRate = 48000;
  audioWorklet = { addModule: vi.fn(async () => {}) };
  destination = new Node(); source = new Node(); silent = new Node();
  constructor() { super(); Context.all.push(this); }
  createMediaStreamSource() { return this.source; }
  createGain() { return this.silent; }
  async resume() { this.state = 'running'; }
  close = vi.fn(async () => { this.state = 'closed'; this.dispatchEvent(new Event('statechange')); });
}
let track: Track;
beforeEach(() => {
  track = new Track(); Context.all = [];
  vi.stubGlobal('AudioContext', Context); vi.stubGlobal('AudioWorkletNode', Node);
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn(async () => ({ getTracks: () => [track], getAudioTracks: () => [track] })) } });
});
afterEach(() => vi.unstubAllGlobals());

it.each(['ended', 'interrupted'])('nguồn micro %s giải phóng mọi tài nguyên đúng một lần', async reason => {
  const failed = vi.fn(), samples = vi.fn();
  const capture = await openMicrophone('', samples, failed);
  const context = Context.all[0];
  if (reason === 'ended') { track.readyState = 'ended'; track.dispatchEvent(new Event('ended')); }
  else { context.state = 'interrupted'; context.dispatchEvent(new Event('statechange')); }
  expect(failed).toHaveBeenCalledOnce(); expect(track.stop).toHaveBeenCalledOnce();
  expect(context.close).toHaveBeenCalledOnce(); expect(context.source.disconnect).toHaveBeenCalledOnce();
  capture.stop(); track.dispatchEvent(new Event('ended')); context.dispatchEvent(new Event('statechange'));
  expect(failed).toHaveBeenCalledOnce(); expect(track.stop).toHaveBeenCalledOnce();
});

it('bật/tắt 40 lần không để track, AudioContext hay sự kiện lỗi sống qua phiên', async () => {
  const failed = vi.fn();
  for (let i = 0; i < 40; i++) {
    track = new Track(); const current = track;
    const capture = await openMicrophone('', () => {}, failed); capture.stop(); capture.stop();
    current.dispatchEvent(new Event('ended'));
    expect(current.stop).toHaveBeenCalledOnce();
  }
  expect(Context.all).toHaveLength(40);
  for (const context of Context.all) { expect(context.close).toHaveBeenCalledOnce(); expect(context.state).toBe('closed'); }
  expect(failed).not.toHaveBeenCalled();
});

it('worklet khởi động lỗi vẫn đóng micro và context', async () => {
  vi.spyOn(Context.prototype, 'resume').mockRejectedValue(new Error('Không khởi động được'));
  await expect(openMicrophone('', () => {})).rejects.toThrow('Không khởi động được');
  expect(track.stop).toHaveBeenCalledOnce(); expect(Context.all[0].close).toHaveBeenCalledOnce();
});
