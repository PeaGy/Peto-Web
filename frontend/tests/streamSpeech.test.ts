import { expect, it } from 'vitest';
import { StreamSpeechText } from '../src/features/companion/speech/streamSpeech';
import { SpeechQueue } from '../src/features/companion/speech/speechQueue';

const read = async (speech: StreamSpeechText) => {
  const result: string[] = [], signal = new AbortController().signal;
  for (let next = await speech.queue.next(signal); next !== null; next = await speech.queue.next(signal)) result.push(next);
  return result;
};

it('câu đầu về trước khi kết thúc lượt; câu sau giữ đúng thứ tự và không lặp', async () => {
  const speech = new StreamSpeechText(), signal = new AbortController().signal;
  speech.push('Good to see you');
  const first = speech.queue.next(signal);
  speech.push('. How was');
  expect(await first).toBe('Good to see you.');
  speech.push(' your day?');
  speech.finish();
  expect(await read(speech)).toEqual(['How was your day?']);
});

it('số thập phân, tên viết tắt và câu bị chia ở mọi vị trí đều giữ nguyên lời đọc', async () => {
  const text = 'Dr. Smith paid $0.40. It is nice to see you!';
  for (let split = 0; split <= text.length; split++) {
    const speech = new StreamSpeechText();
    speech.push(text.slice(0, split)); speech.push(text.slice(split)); speech.finish();
    expect((await read(speech)).join(' ')).toBe(text);
  }
});

it('không đọc code hay địa chỉ và giữ câu sau khối code', async () => {
  const speech = new StreamSpeechText();
  for (const text of ['Look here. ```js\nconsole.log("Hi! ', 'there.");\n```\nThat is all.']) speech.push(text);
  speech.finish();
  expect(await read(speech)).toEqual(['Look here.', 'That is all.']);
});

it('câu dài không có dấu được chia có giới hạn khi kết thúc; dừng bỏ phần chưa chốt', async () => {
  const speech = new StreamSpeechText();
  speech.push('Something to say '.repeat(40)); speech.finish();
  const chunks = await read(speech);
  expect(chunks.length).toBeGreaterThan(1);
  expect(chunks.every(chunk => chunk.length <= 220)).toBe(true);
  const cancelled = new StreamSpeechText();
  cancelled.push('Do not read this. '); cancelled.cancel(); cancelled.push('Or this. '); cancelled.finish();
  expect(await read(cancelled)).toEqual([]);
});

it('hủy lúc đợi chữ kết thúc ngay và không giữ tín hiệu hủy của phiên trước', async () => {
  const queue = new SpeechQueue(), controller = new AbortController();
  const waiting = queue.next(controller.signal);
  controller.abort();
  expect(await waiting).toBeNull();
  queue.cancel();
  expect(await queue.next(new AbortController().signal)).toBeNull();
});

it('mốc nét mặt giữ với đúng đoạn chữ, kể cả emoji và thẻ tới trước dấu cách', async () => {
  const speech = new StreamSpeechText(), signal = new AbortController().signal;
  speech.markEmotion('surprised', 0);
  speech.push('Oh 😮!');
  speech.markEmotion('happy', 6);
  speech.push(' That is great.'); speech.finish();
  expect(await speech.queue.nextChunk(signal)).toEqual({ text: 'Oh 😮!', emotion: 'surprised' });
  expect(await speech.queue.nextChunk(signal)).toEqual({ text: 'That is great.', emotion: 'happy' });
  expect(await speech.queue.nextChunk(signal)).toBeNull();
});

it('nghe lại dùng mốc trước khi đưa chữ vào, giữ biểu cảm qua đoạn dài và bỏ mốc cuối không có lời', async () => {
  const text = `Oh! ${'Good news '.repeat(35)}Done.`;
  const speech = new StreamSpeechText(), signal = new AbortController().signal;
  speech.markEmotion('surprised', 0); speech.markEmotion('happy', 3);
  speech.markEmotion('neutral', text.length);
  speech.push(text); speech.finish();
  const chunks = [];
  for (let chunk = await speech.queue.nextChunk(signal); chunk; chunk = await speech.queue.nextChunk(signal)) chunks.push(chunk);
  expect(chunks[0]).toEqual({ text: 'Oh!', emotion: 'surprised' });
  expect(chunks.slice(1).every(chunk => chunk.emotion === 'happy' && chunk.text.length <= 220)).toBe(true);
  expect(chunks.map(chunk => chunk.text).join(' ')).toBe(text);
});

it('bản đầy đủ không tách thêm yêu cầu tạo tiếng khi các câu giữ cùng biểu cảm', async () => {
  const speech = new StreamSpeechText(undefined, false), signal = new AbortController().signal;
  speech.markEmotion('happy', 0); speech.push('Good news! I passed.'); speech.finish();
  expect(await speech.queue.nextChunk(signal)).toEqual({ text: 'Good news! I passed.', emotion: 'happy' });
  expect(await speech.queue.nextChunk(signal)).toBeNull();
});
