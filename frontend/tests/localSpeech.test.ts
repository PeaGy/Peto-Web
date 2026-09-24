import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  fallbackOnly,
  serverSynth,
  speakableText,
  speechChunks,
  VOICE_FALLBACK_EVENT,
  withFallback,
  type VoiceFallbackDetail,
} from '../src/localSpeech';

afterEach(() => vi.unstubAllGlobals());

/** Giả máy chủ /api/voice/speak; trả lại danh sách thân yêu cầu và các lần báo chuyển giọng. */
function fakeServer(reply: (body: { voice: string; fallback?: string }) => Response) {
  const bodies: { text: string; voice: string; fallback?: string }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body));
    bodies.push(body);
    return reply(body);
  }));
  const announced: VoiceFallbackDetail[] = [];
  const listener = (event: Event) => announced.push((event as CustomEvent<VoiceFallbackDetail>).detail);
  window.addEventListener(VOICE_FALLBACK_EVENT, listener);
  return { bodies, announced, done: () => window.removeEventListener(VOICE_FALLBACK_EVENT, listener) };
}

const wav = (headers: Record<string, string> = {}) => new Response('RIFF', { headers: { 'Content-Type': 'audio/wav', ...headers } });

describe('giọng dự phòng', () => {
  it('máy chủ đổi sang giọng dự phòng thì báo một lần và các mẩu sau đi thẳng tới giọng đó', async () => {
    const server = fakeServer((body) => wav({ 'X-Peto-Voice': body.fallback ?? body.voice }));
    const used: number[] = [];
    const synth = serverSynth('stepfun:jilingshaonv', { fallback: 'playful-1', onUsed: (value) => used.push(value) });
    await synth('One.', new AbortController().signal);
    await synth('Two.', new AbortController().signal);
    server.done();
    expect(server.bodies).toEqual([
      { text: 'One.', voice: 'stepfun:jilingshaonv', fallback: 'playful-1' },
      { text: 'Two.', voice: 'playful-1' },
    ]);
    expect(server.announced).toEqual([{ voice: 'playful-1', reason: undefined }]);
    expect(used).toEqual([]);
  });

  it('Giọng Peto báo số ký tự đã dùng sau mỗi mẩu', async () => {
    const server = fakeServer(() => wav({ 'X-Peto-Voice': 'stepfun:jilingshaonv', 'X-Peto-Voice-Used': '120' }));
    const used: number[] = [];
    await serverSynth('stepfun:jilingshaonv', { onUsed: (value) => used.push(value) })('Hi.', new AbortController().signal);
    server.done();
    expect(used).toEqual([120]);
    expect(server.announced).toEqual([]);
  });

  it('khóa riêng lỗi thì đọc mẩu đó và các mẩu sau bằng giọng của máy chủ, kèm lý do', async () => {
    const server = fakeServer(() => wav({ 'X-Peto-Voice': 'playful-1' }));
    const primary = vi.fn(async () => { throw new Error('Khóa OpenAI không đúng hoặc chưa có quyền dùng giọng nói.'); });
    const synth = withFallback(primary, 'playful-1');
    await synth('One.', new AbortController().signal);
    await synth('Two.', new AbortController().signal);
    server.done();
    expect(primary).toHaveBeenCalledTimes(1);
    expect(server.bodies.map((body) => body.voice)).toEqual(['playful-1', 'playful-1']);
    expect(server.announced).toEqual([{ voice: 'playful-1', reason: 'Khóa OpenAI không đúng hoặc chưa có quyền dùng giọng nói.' }]);
  });

  it('người dùng dừng giữa chừng thì không chuyển giọng', async () => {
    const server = fakeServer(() => wav());
    const controller = new AbortController();
    const synth = withFallback(async () => {
      controller.abort();
      throw new DOMException('Aborted', 'AbortError');
    }, 'playful-1');
    await expect(synth('One.', controller.signal)).rejects.toThrow('Aborted');
    server.done();
    expect(server.bodies).toEqual([]);
    expect(server.announced).toEqual([]);
  });

  it('nguồn chính chưa dùng được thì đọc thẳng bằng giọng dự phòng, báo lý do một lần', async () => {
    const server = fakeServer(() => wav());
    const synth = fallbackOnly('playful-1', 'Đã hết lượt Giọng Peto tháng này.');
    await synth('One.', new AbortController().signal);
    await synth('Two.', new AbortController().signal);
    server.done();
    expect(server.bodies).toEqual([{ text: 'One.', voice: 'playful-1' }, { text: 'Two.', voice: 'playful-1' }]);
    expect(server.announced).toEqual([{ voice: 'playful-1', reason: 'Đã hết lượt Giọng Peto tháng này.' }]);
  });
});

describe('chữ để giọng nói đọc', () => {
  it('bỏ khối code, link và ký hiệu markdown, mỗi dòng thành một câu', () => {
    const text = speakableText([
      '## Quick plan',
      'Read **the docs** at [this page](https://example.com/docs) first',
      '```python',
      'print("không đọc")',
      '```',
      '- Use `git status`',
      '| Name | Age |',
      '|---|---|',
      '| Peto | 1 |',
    ].join('\n'));
    expect(text).toBe('Quick plan. Read the docs at this page first. Use git status. Name, Age. Peto, 1.');
  });

  it('gộp câu ngắn thành mẩu vừa, không cắt số thập phân và không làm mất chữ', () => {
    const input = ('Version 3.5 is out. ' + 'This sentence adds a little more length to the reply. '.repeat(12)).trim();
    const chunks = speechChunks(input);
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks[0].startsWith('Version 3.5 is out. This sentence')).toBe(true);
    expect(chunks.every((chunk) => chunk.length <= 220)).toBe(true);
    expect(chunks.join(' ')).toBe(input);
  });

  it('chia câu dài quá giới hạn ở khoảng trắng', () => {
    const long = Array.from({ length: 80 }, (_, index) => `word${index}`).join(' ');
    const chunks = speechChunks(long);
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.every((chunk) => chunk.length <= 220)).toBe(true);
    expect(chunks.join(' ')).toBe(long);
  });
});
