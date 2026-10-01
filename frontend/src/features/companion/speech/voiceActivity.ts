/** Đọc độ lớn WAV PCM16 từ bộ tạo giọng; không đổi đường phát âm thanh của trình duyệt. */
export function wavEnvelope(buffer: ArrayBuffer): { levels: Float32Array; step: number } | null {
  const view = new DataView(buffer);
  const tag = (at: number) => String.fromCharCode(...new Uint8Array(buffer, at, 4));
  if (buffer.byteLength < 44 || tag(0) !== "RIFF" || tag(8) !== "WAVE") return null;
  let rate = 0, channels = 0, stride = 0, data = 0, size = 0;
  for (let pos = 12; pos + 8 <= view.byteLength;) {
    const length = view.getUint32(pos + 4, true);
    if (pos + 8 + length > view.byteLength) return null;
    if (tag(pos) === "fmt " && length >= 16) {
      if (view.getUint16(pos + 8, true) !== 1 || view.getUint16(pos + 22, true) !== 16) return null;
      channels = view.getUint16(pos + 10, true);
      rate = view.getUint32(pos + 12, true);
      stride = view.getUint16(pos + 20, true);
    }
    if (tag(pos) === "data") { data = pos + 8; size = length; }
    pos += 8 + length + (length % 2);
  }
  if (!data || !rate || rate > 192000 || !channels || channels > 8 || stride !== channels * 2) return null;
  const frames = Math.floor(size / stride);
  const windowSize = Math.max(1, Math.floor(rate * 0.02));
  const levels = new Float32Array(Math.ceil(frames / windowSize));
  for (let i = 0; i < levels.length; i++) {
    let energy = 0, count = 0;
    for (let frame = i * windowSize; frame < Math.min(frames, (i + 1) * windowSize); frame++) {
      for (let ch = 0; ch < channels; ch++) {
        const sample = view.getInt16(data + frame * stride + ch * 2, true) / 32768;
        energy += sample * sample;
        count++;
      }
    }
    levels[i] = Math.min(1, Math.max(0, (Math.sqrt(energy / Math.max(1, count)) - 0.008) * 9));
  }
  return { levels, step: windowSize / rate };
}

let current: { audio: HTMLAudioElement; envelope: ReturnType<typeof wavEnvelope> } | null = null;

/** Gắn từng đoạn tiếng với thời gian phát thật; đoạn cũ không được xóa trạng thái đoạn mới. */
export function trackVoice(audio: HTMLAudioElement, blob: Blob): () => void {
  const track = { audio, envelope: null as ReturnType<typeof wavEnvelope> };
  current = track;
  if (typeof blob.arrayBuffer === "function") void blob.arrayBuffer().then((buffer) => {
    if (current === track) track.envelope = wavEnvelope(buffer);
  }).catch(() => {});
  return () => { if (current === track) current = null; };
}

export function voiceMouth(): number {
  if (!current || current.audio.paused || current.audio.ended || !current.envelope) return 0;
  const { levels, step } = current.envelope;
  return levels[Math.floor(current.audio.currentTime / step)] ?? 0;
}
