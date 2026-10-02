import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LocalVoicePlayer, type SpeakPhase } from '../src/features/companion/speech/localSpeech';
import { StreamSpeechText } from '../src/features/companion/speech/streamSpeech';

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

it('đổi nét mặt lúc đoạn tiếng bắt đầu, không đổi khi xin trước và không lặp lúc hết đệm', async () => {
  const player = new LocalVoicePlayer(), expressions: string[] = [];
  const speech = new StreamSpeechText();
  speech.markEmotion('surprised', 0); speech.push('Oh!');
  speech.markEmotion('happy', 3); speech.push(' Great news!'); speech.finish();
  const done = player.speakQueue(speech.queue, async () => blob, () => {}, chunk => expressions.push(chunk.emotion!));
  const first = await nextAudio(1);
  expect(expressions).toEqual([]);
  first.start(); await Promise.resolve();
  expect(expressions).toEqual(['surprised']);
  first.onwaiting?.(); first.onplaying?.();
  expect(expressions).toEqual(['surprised']);
  first.end();
  const second = await nextAudio(2);
  expect(expressions).toEqual(['surprised']);
  second.start(); await Promise.resolve();
  expect(expressions).toEqual(['surprised', 'happy']);
  second.end(); expect(await done).toBe('done');
});

it('dừng trước khi phát không cho callback biểu cảm tới muộn chạy', async () => {
  const player = new LocalVoicePlayer(), expression = vi.fn();
  const speech = new StreamSpeechText();
  speech.markEmotion('sad', 0); speech.push('Wait.'); speech.finish();
  const done = player.speakQueue(speech.queue, async () => blob, () => {}, expression);
  const audio = await nextAudio(1);
  player.stop(); audio.ready();
  expect(await done).toBe('stopped'); expect(expression).not.toHaveBeenCalled();
});

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

it('phát câu đầu khi luồng chữ vẫn mở và chỉ xin trước tối đa một đoạn', async () => {
  const player = new LocalVoicePlayer(), stream = new StreamSpeechText();
  const phases: SpeakPhase[] = [];
  const synth = vi.fn(async (_text: string, _signal: AbortSignal) => blob);
  const done = player.speakQueue(stream.queue, synth, phase => phases.push(phase));
  stream.push('Good to see you. ');
  const first = await nextAudio(1);
  first.start();
  stream.push('How was your day? I hope it was nice. ');
  await vi.waitFor(() => expect(synth).toHaveBeenCalledTimes(2));
  expect(FakeAudio.all).toHaveLength(1);
  first.end();
  const second = await nextAudio(2);
  second.start(); second.end();
  const third = await nextAudio(3);
  third.start(); third.end();
  await vi.waitFor(() => expect(phases.at(-1)).toBe('buffering'));
  stream.finish();
  expect(await done).toBe('done');
  expect(synth.mock.calls.map(call => call[0])).toEqual(['Good to see you.', 'How was your day?', 'I hope it was nice.']);
});

it('dừng khi đợi câu kế tiếp rồi phát lượt mới; chữ và tín hiệu cũ không chen vào', async () => {
  const player = new LocalVoicePlayer(), stream = new StreamSpeechText();
  const phases: SpeakPhase[] = [];
  const old = player.speakQueue(stream.queue, async () => blob, phase => phases.push(phase));
  stream.push('This is the first sentence. ');
  const first = await nextAudio(1);
  first.start(); first.end();
  await vi.waitFor(() => expect(phases.at(-1)).toBe('buffering'));
  player.stop();
  expect(await old).toBe('stopped');
  stream.push('A late sentence from the old reply. '); stream.finish();
  const newer = player.speak('New reply.', async () => blob, () => {});
  const second = await nextAudio(2);
  second.start(); second.end();
  expect(await newer).toBe('done');
  expect(FakeAudio.all).toHaveLength(2);
});
