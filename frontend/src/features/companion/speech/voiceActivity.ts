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
  if (!data || !rate || rate > 192000 || !channels || channels > 8 || stride !== channels * 2 || size / stride / rate > 120) return null;
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

let current: { audio: HTMLAudioElement; envelope: ReturnType<typeof wavEnvelope>; waiting: boolean } | null = null;
let decoding: Promise<void> = Promise.resolve();

/** Đo năng lượng từng kênh riêng để tiếng stereo ngược pha không bị tính thành im lặng. */
function decodedEnvelope(audio: AudioBuffer): ReturnType<typeof wavEnvelope> {
  const { sampleRate: rate, numberOfChannels: channels, length: frames } = audio;
  if (!rate || rate > 192000 || !channels || channels > 8 || frames / rate > 120) return null;
  const samples = Array.from({ length: channels }, (_, index) => audio.getChannelData(index));
  const windowSize = Math.max(1, Math.floor(rate * 0.02));
  const levels = new Float32Array(Math.ceil(frames / windowSize));
  for (let i = 0; i < levels.length; i++) {
    let energy = 0, count = 0;
    for (let frame = i * windowSize; frame < Math.min(frames, (i + 1) * windowSize); frame++) {
      for (const channel of samples) { energy += channel[frame] ** 2; count++; }
    }
    levels[i] = Math.min(1, Math.max(0, (Math.sqrt(energy / Math.max(1, count)) - 0.008) * 9));
  }
  return { levels, step: windowSize / rate };
}

/** Gắn từng đoạn tiếng với thời gian phát thật; đoạn cũ không được xóa trạng thái đoạn mới. */
export function trackVoice(audio: HTMLAudioElement, blob: Blob, bytes?: ArrayBuffer): () => void {
  const track = { audio, envelope: null as ReturnType<typeof wavEnvelope>, waiting: false };
  current = track;
  const wait = () => { track.waiting = true; };
  const play = () => { track.waiting = false; };
  audio.addEventListener?.('waiting', wait);
  audio.addEventListener?.('playing', play);
  const read = bytes ? Promise.resolve(bytes) : typeof blob.arrayBuffer === 'function' ? blob.arrayBuffer() : null;
  if (read) void read.then((buffer) => {
    if (current !== track || buffer.byteLength > 8 * 1024 * 1024) return;
    track.envelope = wavEnvelope(buffer);
    if (track.envelope || typeof OfflineAudioContext === 'undefined') return;
    // Giải mã ngoài đường phát tiếng, từng việc một để tránh tăng tải trên điện thoại.
    decoding = decoding.then(async () => {
      if (current !== track) return;
      const decoder = new OfflineAudioContext(1, 1, 48000);
      const decoded = await decoder.decodeAudioData(buffer.slice(0));
      if (current === track) track.envelope = decodedEnvelope(decoded);
    }).catch(() => {});
  }).catch(() => {});
  return () => {
    audio.removeEventListener?.('waiting', wait);
    audio.removeEventListener?.('playing', play);
    if (current === track) current = null;
  };
}

export function voicePlaying(): boolean {
  return Boolean(current && !current.waiting && !current.audio.paused && !current.audio.ended);
}

export function voiceMouth(): number {
  if (!voicePlaying() || !current?.envelope) return 0;
  const { levels, step } = current.envelope;
  return levels[Math.floor(current.audio.currentTime / step)] ?? 0;
}
