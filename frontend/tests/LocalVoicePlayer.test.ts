import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LocalVoicePlayer, type SpeakPhase } from '../src/features/companion/speech/localSpeech';

class FakeAudio {
  static all: FakeAudio[] = [];
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onplaying: (() => void) | null = null;
  onwaiting: (() => void) | null = null;
  onstalled: (() => void) | null = null;
  onpause: (() => void) | null = null;
  paused = true;
  ended = false;
  currentTime = 0;
  ready!: () => void;
  reject!: (error: Error) => void;
  constructor() { FakeAudio.all.push(this); }
  play() { return new Promise<void>((resolve, reject) => { this.ready = resolve; this.reject = reject; }); }
  start() { this.paused = false; this.onplaying?.(); this.ready(); }
  pause() { this.paused = true; this.onpause?.(); }
  end() { this.ended = true; this.onended?.(); }
}

beforeEach(() => {
  FakeAudio.all = [];
  vi.stubGlobal('Audio', FakeAudio);
  URL.createObjectURL = vi.fn(() => 'blob:test');
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => vi.unstubAllGlobals());
const blob = {} as Blob;
const nextAudio = async (count: number) => {
  await vi.waitFor(() => expect(FakeAudio.all).toHaveLength(count));
  return FakeAudio.all[count - 1];
};

it('chỉ báo đang nói khi tiếng phát thật và giữ chờ qua khoảng đệm', async () => {
  const player = new LocalVoicePlayer();
  const phases: SpeakPhase[] = [];
  const done = player.speak('Hello Peto.', async () => blob, phase => phases.push(phase));
  const audio = await nextAudio(1);
  expect(phases).toEqual(['loading']);
  audio.start();
  await Promise.resolve();
  expect(phases).toEqual(['loading', 'playing']);
  audio.onwaiting?.();
  expect(phases.at(-1)).toBe('buffering');
  audio.onplaying?.();
  expect(phases.at(-1)).toBe('playing');
  audio.end();
  expect(await done).toBe('done');
  expect(audio.onplaying).toBeNull();
  expect(URL.revokeObjectURL).toHaveBeenCalledOnce();
});

it('xin trước một đoạn, chờ đoạn kế tiếp rồi phát tiếp; dừng hủy cả đoạn đang xin', async () => {
  const player = new LocalVoicePlayer();
  const phases: SpeakPhase[] = [];
  let signal!: AbortSignal;
  let finish!: (blob: Blob) => void;
  const synth = vi.fn((_text: string, abort: AbortSignal) => {
    signal = abort;
    return synth.mock.calls.length === 1 ? Promise.resolve(blob) : new Promise<Blob>(resolve => { finish = resolve; });
  });
  const done = player.speak('This is a sentence. '.repeat(30), synth, phase => phases.push(phase));
  const first = await nextAudio(1);
  expect(synth).toHaveBeenCalledTimes(2);
  first.start(); first.end();
  await vi.waitFor(() => expect(phases.at(-1)).toBe('buffering'));
  player.stop();
  expect(signal.aborted).toBe(true);
  finish(blob);
  expect(await done).toBe('stopped');
  expect(FakeAudio.all).toHaveLength(1);
});

it('nối nhiều đoạn và giải phóng mọi đoạn sau khi đọc hết', async () => {
  const player = new LocalVoicePlayer();
  const phases: SpeakPhase[] = [];
  const done = player.speak('This sentence is long enough to make two separate audio chunks. '.repeat(4), async () => blob, phase => phases.push(phase));
  const first = await nextAudio(1);
  first.start(); first.end();
  const second = await nextAudio(2);
  expect(phases.at(-1)).toBe('buffering');
  second.start(); second.end();
  expect(await done).toBe('done');
  expect(phases).toEqual(['loading', 'playing', 'buffering', 'playing']);
  expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2);
});

it('lỗi phát hủy đoạn xin trước, dọn sự kiện và không báo đang nói', async () => {
  const player = new LocalVoicePlayer();
  let signal!: AbortSignal;
  const phases: SpeakPhase[] = [];
  const done = player.speak('This sentence will have multiple chunks. '.repeat(12), async (_text, abort) => { signal = abort; return blob; }, phase => phases.push(phase));
  const failure = expect(done).rejects.toThrow('Trình duyệt chưa cho phát tiếng');
  const audio = await nextAudio(1);
  audio.reject(new Error('Blocked'));
  await failure;
  expect(signal.aborted).toBe(true);
  expect(audio.paused).toBe(true);
  expect(phases).toEqual(['loading']);
  expect(audio.onwaiting).toBeNull();
  expect(URL.revokeObjectURL).toHaveBeenCalledOnce();
});

it('dừng trước khi play hoàn tất không để tín hiệu phát muộn đổi trạng thái', async () => {
  const player = new LocalVoicePlayer();
  const phases: SpeakPhase[] = [];
  const done = player.speak('Hello.', async () => blob, phase => phases.push(phase));
  const audio = await nextAudio(1);
  player.stop();
  audio.ready();
  expect(await done).toBe('stopped');
  expect(phases).toEqual(['loading']);
  expect(URL.revokeObjectURL).toHaveBeenCalledOnce();
});
