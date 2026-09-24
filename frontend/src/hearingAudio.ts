/**
 * Phần tính toán của phần Peto nghe, không đụng tới trình duyệt nên test được: đo âm lượng, cắt câu theo khoảng
 * im lặng và đóng gói WAV 16 kHz để gửi đi chép lời.
 */
import { pcmToWav } from "./voiceProviders";

export const TARGET_RATE = 16000;

// Âm lượng hiển thị đi từ -60 dB (lặng) tới -10 dB (nói to sát micro).
const FLOOR_DB = -60;
const RANGE_DB = 50;

export function rmsOf(samples: Float32Array): number {
  let sum = 0;
  for (let index = 0; index < samples.length; index += 1) sum += samples[index] * samples[index];
  return samples.length ? Math.sqrt(sum / samples.length) : 0;
}

function dbOf(rms: number): number {
  return 20 * Math.log10(Math.max(rms, 1e-6));
}

/** Âm lượng 0..1 cho thanh đo. */
export function levelOf(rms: number): number {
  return Math.max(0, Math.min(1, (dbOf(rms) - FLOOR_DB) / RANGE_DB));
}

/** Độ nhạy 0..100 thành ngưỡng dB: càng nhạy thì ngưỡng càng thấp (-20 dB ít nhạy nhất, -60 dB nhạy nhất). */
function thresholdDb(sensitivity: number): number {
  const value = Math.max(0, Math.min(100, sensitivity));
  return -20 - value * 0.4;
}

/** Ngưỡng coi là có tiếng nói, theo RMS. */
export function thresholdFor(sensitivity: number): number {
  return 10 ** (thresholdDb(sensitivity) / 20);
}

/** Vị trí ngưỡng trên thanh đo (0..1), để vẽ vạch ngưỡng đúng chỗ. */
export function thresholdLevel(sensitivity: number): number {
  return Math.max(0, Math.min(1, (thresholdDb(sensitivity) - FLOOR_DB) / RANGE_DB));
}

/** Hạ mẫu về 16 kHz (lấy trung bình từng đoạn, đủ cho giọng nói) và đổi sang PCM16. */
export function downsample(samples: Float32Array, fromRate: number, toRate = TARGET_RATE): Int16Array<ArrayBuffer> {
  const ratio = fromRate / toRate;
  const length = Math.max(0, Math.floor(samples.length / ratio));
  const output = new Int16Array(length);
  for (let index = 0; index < length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.max(start + 1, Math.min(samples.length, Math.floor((index + 1) * ratio)));
    let sum = 0;
    for (let cursor = start; cursor < end; cursor += 1) sum += samples[cursor];
    const value = Math.max(-1, Math.min(1, sum / (end - start)));
    output[index] = value < 0 ? Math.round(value * 0x8000) : Math.round(value * 0x7fff);
  }
  return output;
}

/** Một câu nói thành tệp WAV PCM16 16 kHz một kênh, định dạng mọi nhà cung cấp đều nhận. */
export function wavFromSamples(samples: Float32Array, fromRate: number): Blob {
  const pcm = downsample(samples, fromRate);
  return pcmToWav(new Uint8Array(pcm.buffer), TARGET_RATE);
}

export interface SegmenterOptions {
  /** RMS từ mức này trở lên là có tiếng nói. */
  threshold: number;
  /** Phải to liên tục chừng này mới tính là bắt đầu nói (bỏ qua tiếng cộp, tiếng gõ phím). */
  startMs?: number;
  /** Im chừng này thì xong câu. */
  silenceMs?: number;
  /** Câu có ít tiếng nói hơn thế thì bỏ, khỏi gửi đi chép lời. */
  minSpeechMs?: number;
  /** Câu dài quá thì cắt, để yêu cầu chép lời không quá lớn. */
  maxMs?: number;
  /** Giữ lại chừng này âm thanh trước lúc bắt đầu nói, để không mất âm đầu. */
  preRollMs?: number;
}

export type SegmentEvent =
  | { type: "start" }
  | { type: "end"; samples: Float32Array; durationMs: number }
  | { type: "discard" };

/**
 * Cắt luồng âm thanh từ micro thành từng câu dựa vào âm lượng: đủ to trong `startMs` thì bắt đầu, im `silenceMs`
 * thì xong. Không dùng model nhận biết giọng nói, nên phòng ồn thì người dùng giảm độ nhạy.
 */
export class Segmenter {
  private readonly options: Required<SegmenterOptions>;
  private speaking = false;
  private loudMs = 0;
  private silentMs = 0;
  private speechMs = 0;
  private totalMs = 0;
  private chunks: Float32Array[] = [];
  private preRoll: Float32Array[] = [];
  private preRollTotal = 0;

  constructor(private readonly sampleRate: number, options: SegmenterOptions) {
    this.options = {
      startMs: 90, silenceMs: 800, minSpeechMs: 250, maxMs: 30000, preRollMs: 300, ...options,
    };
  }

  get active(): boolean {
    return this.speaking;
  }

  setThreshold(threshold: number) {
    this.options.threshold = threshold;
  }

  push(samples: Float32Array): SegmentEvent | null {
    const ms = (samples.length / this.sampleRate) * 1000;
    const loud = rmsOf(samples) >= this.options.threshold;
    if (!this.speaking) {
      this.preRoll.push(samples);
      this.preRollTotal += ms;
      while (this.preRoll.length > 1 && this.preRollTotal - this.durationOf(this.preRoll[0]) >= this.options.preRollMs) {
        this.preRollTotal -= this.durationOf(this.preRoll.shift()!);
      }
      this.loudMs = loud ? this.loudMs + ms : 0;
      if (this.loudMs < this.options.startMs) return null;
      this.speaking = true;
      this.chunks = this.preRoll;
      this.totalMs = this.preRollTotal;
      this.speechMs = this.loudMs;
      this.silentMs = 0;
      this.preRoll = [];
      this.preRollTotal = 0;
      return { type: "start" };
    }
    this.chunks.push(samples);
    this.totalMs += ms;
    if (loud) {
      this.silentMs = 0;
      this.speechMs += ms;
    } else {
      this.silentMs += ms;
    }
    if (this.silentMs >= this.options.silenceMs || this.totalMs >= this.options.maxMs) return this.finish();
    return null;
  }

  /** Kết thúc câu đang nói dở (khi tắt nghe); không có câu nào thì trả null. */
  flush(): SegmentEvent | null {
    return this.speaking ? this.finish() : null;
  }

  reset() {
    this.speaking = false;
    this.loudMs = 0;
    this.silentMs = 0;
    this.speechMs = 0;
    this.totalMs = 0;
    this.chunks = [];
    this.preRoll = [];
    this.preRollTotal = 0;
  }

  private durationOf(samples: Float32Array): number {
    return (samples.length / this.sampleRate) * 1000;
  }

  private finish(): SegmentEvent {
    const length = this.chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const samples = new Float32Array(length);
    let offset = 0;
    for (const chunk of this.chunks) {
      samples.set(chunk, offset);
      offset += chunk.length;
    }
    const speechMs = this.speechMs;
    const durationMs = this.totalMs;
    this.reset();
    return speechMs >= this.options.minSpeechMs ? { type: "end", samples, durationMs } : { type: "discard" };
  }
}
