import { describe, expect, it } from 'vitest';
import { downsample, levelOf, Segmenter, thresholdFor, thresholdLevel, wavFromSamples } from '../src/hearingAudio';

const RATE = 16000;

/** Khúc 64 ms (1024 mẫu ở 16 kHz), to hay im. */
const chunk = (amplitude: number, length = 1024) => new Float32Array(length).fill(amplitude);

async function bytes(blob: Blob): Promise<Uint8Array> {
  if (typeof blob.arrayBuffer === 'function') return new Uint8Array(await blob.arrayBuffer());
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.readAsArrayBuffer(blob);
  });
}

describe('âm lượng và độ nhạy', () => {
  it('âm lượng đi từ 0 (lặng) tới 1 (nói to sát micro)', () => {
    expect(levelOf(0)).toBe(0);
    expect(levelOf(0.001)).toBe(0);
    expect(levelOf(0.01)).toBeCloseTo(0.4, 5);
    expect(levelOf(1)).toBe(1);
  });

  it('càng nhạy thì ngưỡng càng thấp, và vạch ngưỡng nằm đúng chỗ trên thanh đo', () => {
    expect(thresholdFor(100)).toBeLessThan(thresholdFor(50));
    expect(thresholdFor(50)).toBeLessThan(thresholdFor(0));
    expect(thresholdFor(50)).toBeCloseTo(0.01, 5);
    expect(levelOf(thresholdFor(30))).toBeCloseTo(thresholdLevel(30), 5);
    expect(thresholdFor(-20)).toBe(thresholdFor(0));
  });
});

describe('đóng gói WAV 16 kHz', () => {
  it('hạ mẫu 48 kHz về 16 kHz bằng trung bình từng đoạn', () => {
    const samples = new Float32Array(48).map((_, index) => (index % 3 === 0 ? 0.3 : 0));
    const pcm = downsample(samples, 48000);
    expect(pcm.length).toBe(16);
    expect(pcm[0]).toBe(Math.round(0.1 * 0x7fff));
  });

  it('kẹp mẫu vượt biên và giữ đúng dấu', () => {
    const pcm = downsample(new Float32Array([2, -2]), 16000);
    expect([...pcm]).toEqual([0x7fff, -0x8000]);
  });

  it('WAV ra đúng 16 kHz, PCM16, một kênh', async () => {
    const wav = await bytes(wavFromSamples(chunk(0.1, 4800), 48000));
    const view = new DataView(wav.buffer);
    expect(String.fromCharCode(...wav.subarray(0, 4))).toBe('RIFF');
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(1600 * 2);
  });
});

describe('cắt câu theo khoảng im lặng', () => {
  const make = () => new Segmenter(RATE, { threshold: thresholdFor(50), startMs: 100, silenceMs: 500, minSpeechMs: 200, preRollMs: 200 });

  it('im lặng thì không có gì; nói đủ lâu thì bắt đầu, im đủ lâu thì xong câu, kèm một chút âm trước lúc nói', () => {
    const segmenter = make();
    for (let index = 0; index < 5; index += 1) expect(segmenter.push(chunk(0))).toBeNull();
    expect(segmenter.push(chunk(0.2))).toBeNull();
    expect(segmenter.push(chunk(0.2))).toEqual({ type: 'start' });
    for (let index = 0; index < 6; index += 1) expect(segmenter.push(chunk(0.2))).toBeNull();
    const events = Array.from({ length: 8 }, () => segmenter.push(chunk(0))).filter(Boolean);
    expect(events).toHaveLength(1);
    const end = events[0]!;
    if (end.type !== 'end') throw new Error('phải xong câu');
    // Phần đệm giữ khoảng 200 ms tính tới lúc nhận ra đang nói: 2 khúc im + 2 khúc nói đầu. Rồi 6 khúc nói, 8 khúc im.
    expect(end.samples.length).toBe(1024 * (2 + 8 + 8));
    expect(end.samples[0]).toBe(0);
    expect(end.samples[1024 * 2]).toBeCloseTo(0.2, 5);
    expect(end.durationMs).toBeCloseTo((1024 * 18 / RATE) * 1000, 3);
    expect(segmenter.active).toBe(false);
  });

  it('tiếng cộp ngắn thì bỏ, không gửi đi chép', () => {
    const segmenter = make();
    segmenter.push(chunk(0.3));
    expect(segmenter.push(chunk(0.3))).toEqual({ type: 'start' });
    const events = Array.from({ length: 8 }, () => segmenter.push(chunk(0))).filter(Boolean);
    expect(events).toEqual([{ type: 'discard' }]);
  });

  it('câu quá dài thì cắt', () => {
    const segmenter = new Segmenter(RATE, { threshold: thresholdFor(50), startMs: 60, maxMs: 1000 });
    const events = Array.from({ length: 30 }, () => segmenter.push(chunk(0.3))).filter(Boolean);
    expect(events[0]).toEqual({ type: 'start' });
    expect(events[1]?.type).toBe('end');
    if (events[1]?.type === 'end') expect(events[1].durationMs).toBeGreaterThanOrEqual(1000);
  });

  it('đổi độ nhạy có hiệu lực ngay, và flush trả câu đang nói dở', () => {
    const segmenter = make();
    segmenter.setThreshold(0.5);
    segmenter.push(chunk(0.2));
    expect(segmenter.push(chunk(0.2))).toBeNull();
    segmenter.setThreshold(0.1);
    segmenter.push(chunk(0.2));
    expect(segmenter.push(chunk(0.2))).toEqual({ type: 'start' });
    segmenter.push(chunk(0.2));
    segmenter.push(chunk(0.2));
    expect(segmenter.flush()?.type).toBe('end');
    expect(segmenter.flush()).toBeNull();
  });
});
