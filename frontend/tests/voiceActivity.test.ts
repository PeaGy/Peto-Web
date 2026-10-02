import { afterEach, describe, expect, it, vi } from 'vitest';
import { trackVoice, voiceMouth, voicePlaying, wavEnvelope } from '../src/features/companion/speech/voiceActivity';

afterEach(() => vi.unstubAllGlobals());
const decoded = () => ({
  sampleRate: 8000, numberOfChannels: 2, length: 320,
  getChannelData: (channel: number) => Float32Array.from({ length: 320 }, (_, i) => i < 160 ? 0 : channel ? -0.25 : 0.25),
}) as AudioBuffer;
const compressed = { arrayBuffer: async () => new ArrayBuffer(80) } as Blob;

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

  it('giải mã tiếng nén, stereo ngược pha vẫn mở miệng, chờ dữ liệu thì đóng', async () => {
    const decode = vi.fn(async () => decoded());
    vi.stubGlobal('OfflineAudioContext', class { decodeAudioData = decode; });
    const audio = Object.assign(new EventTarget(), { currentTime: 0.025, paused: false, ended: false }) as HTMLAudioElement;
    const stop = trackVoice(audio, compressed);
    await vi.waitFor(() => expect(voiceMouth()).toBe(1));
    expect(decode).toHaveBeenCalledOnce();
    audio.dispatchEvent(new Event('waiting'));
    expect(voicePlaying()).toBe(false);
    expect(voiceMouth()).toBe(0);
    audio.dispatchEvent(new Event('playing'));
    expect(voiceMouth()).toBe(1);
    audio.currentTime = 0;
    expect(voiceMouth()).toBe(0);
    audio.ended = true;
    expect(voicePlaying()).toBe(false);
    stop();
  });

  it('bỏ kết quả giải mã muộn khi đã dừng hoặc chuyển sang đoạn khác', async () => {
    let finish!: (value: AudioBuffer) => void;
    const decode = vi.fn(() => new Promise<AudioBuffer>(resolve => { finish = resolve; }));
    vi.stubGlobal('OfflineAudioContext', class { decodeAudioData = decode; });
    const audio = { currentTime: 0.025, paused: false, ended: false } as HTMLAudioElement;
    const old = trackVoice(audio, compressed);
    await vi.waitFor(() => expect(decode).toHaveBeenCalledOnce());
    const next = trackVoice(audio, { arrayBuffer: async () => wav() } as Blob);
    await Promise.resolve();
    old();
    finish(decoded());
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(voiceMouth()).toBe(1);
    next();
    expect(voiceMouth()).toBe(0);
  });

  it('bộ giải mã lỗi hoặc không có vẫn không ảnh hưởng tiếng đang phát', async () => {
    const decode = vi.fn(async () => { throw new Error('Định dạng không hỗ trợ'); });
    vi.stubGlobal('OfflineAudioContext', class { decodeAudioData = decode; });
    const audio = { currentTime: 0.025, paused: false, ended: false } as HTMLAudioElement;
    let stop = trackVoice(audio, compressed);
    await vi.waitFor(() => expect(decode).toHaveBeenCalledOnce());
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(voiceMouth()).toBe(0);
    expect(voicePlaying()).toBe(true);
    stop();
    vi.stubGlobal('OfflineAudioContext', undefined);
    stop = trackVoice(audio, compressed);
    await Promise.resolve();
    expect(voiceMouth()).toBe(0);
    expect(voicePlaying()).toBe(true);
    stop();
  });
});
