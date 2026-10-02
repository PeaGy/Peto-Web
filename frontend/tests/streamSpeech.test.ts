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
