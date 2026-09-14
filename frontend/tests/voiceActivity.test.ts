import { describe, expect, it } from 'vitest';
import { trackVoice, voiceMouth, wavEnvelope } from '../src/voiceActivity';

function wav() {
  const buffer = new ArrayBuffer(44 + 320 * 2);
  const view = new DataView(buffer);
  const tag = (at: number, text: string) => [...text].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  tag(0, 'RIFF'); tag(8, 'WAVE'); tag(12, 'fmt '); tag(36, 'data');
  view.setUint32(4, buffer.byteLength - 8, true); view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 8000, true); view.setUint32(28, 16000, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); view.setUint32(40, 640, true);
  // Nửa đầu im lặng, nửa sau có âm: mỗi nửa 20 ms.
  for (let i = 160; i < 320; i++) view.setInt16(44 + i * 2, i % 2 ? 8000 : -8000, true);
  return buffer;
}

describe('miệng theo tiếng đang phát', () => {
  it('im lặng đóng miệng, âm lớn mở miệng trong giới hạn', () => {
    const result = wavEnvelope(wav())!;
    expect(result.step).toBe(0.02);
    expect([...result.levels]).toEqual([0, 1]);
  });
  it('bỏ qua WAV hỏng hoặc định dạng chưa hỗ trợ', () => {
    expect(wavEnvelope(new ArrayBuffer(5))).toBeNull();
    const broken = wav();
    new DataView(broken).setUint32(40, 999999, true);
    expect(wavEnvelope(broken)).toBeNull();
    const float = wav();
    new DataView(float).setUint16(20, 3, true);
    expect(wavEnvelope(float)).toBeNull();
  });
  it('bám currentTime, đóng khi dừng và không cho đoạn cũ xóa đoạn mới', async () => {
    const audio = { currentTime: 0, paused: false, ended: false } as HTMLAudioElement;
    const blob = { arrayBuffer: async () => wav() } as Blob;
    const stopOld = trackVoice(audio, blob);
    const stopNew = trackVoice(audio, blob);
    await Promise.resolve();
    stopOld();
    expect(voiceMouth()).toBe(0);
    audio.currentTime = 0.025;
    expect(voiceMouth()).toBe(1);
    Object.assign(audio, { paused: true });
    expect(voiceMouth()).toBe(0);
    Object.assign(audio, { paused: false });
    stopNew();
    expect(voiceMouth()).toBe(0);
  });
});
