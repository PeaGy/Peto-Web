/**
 * Phát các mẩu âm thanh nối đuôi nhau, không hở tiếng.
 *
 * Giọng của trình duyệt đọc từng lượt rời nên nghe giật; còn ở đây mình có sẵn
 * âm thanh nên hẹn giờ phát mẩu sau đúng lúc mẩu trước dứt, sai số cỡ mẫu chứ
 * không phải cỡ trăm mili giây.
 *
 * `AnalyserNode` nối sẵn để bước 3 lấy biên độ mà nhép miệng nhân vật.
 */

/** Nhích một chút so với hiện tại, cho kịp giải mã và lên lịch. */
const LEAD_TIME = 0.02;

export class AudioQueue {
  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private levels: Uint8Array<ArrayBuffer> | null = null;
  private playing = new Set<AudioBufferSourceNode>();
  /** Mốc thời gian mẩu cuối cùng sẽ dứt, để hẹn mẩu kế tiếp vào đúng chỗ đó. */
  private endsAt = 0;

  /** Tạo muộn: AudioContext phải sinh ra từ một cú chạm của người dùng. */
  private context(): AudioContext {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 1024;
      this.levels = new Uint8Array(this.analyser.frequencyBinCount);
      this.analyser.connect(this.ctx.destination);
    }
    return this.ctx;
  }

  async play(bytes: ArrayBuffer): Promise<void> {
    const ctx = this.context();
    if (ctx.state === "suspended") await ctx.resume();
    const buffer = await ctx.decodeAudioData(bytes);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.analyser as AnalyserNode);

    const when = Math.max(ctx.currentTime + LEAD_TIME, this.endsAt);
    source.start(when);
    this.endsAt = when + buffer.duration;
    this.playing.add(source);
    source.onended = () => this.playing.delete(source);
  }

  stop(): void {
    for (const source of this.playing) {
      try {
        source.stop();
      } catch {
        // Mẩu chưa kịp phát thì stop ném lỗi; kệ nó.
      }
    }
    this.playing.clear();
    this.endsAt = 0;
  }

  get speaking(): boolean {
    return this.playing.size > 0;
  }

  /** Biên độ hiện tại, 0 tới 1. Bước 3 dùng để nhép miệng. */
  level(): number {
    if (!this.analyser || !this.levels || this.playing.size === 0) return 0;
    this.analyser.getByteTimeDomainData(this.levels);
    let sum = 0;
    for (const sample of this.levels) {
      const centered = (sample - 128) / 128;
      sum += centered * centered;
    }
    return Math.min(1, Math.sqrt(sum / this.levels.length) * 3);
  }
}

/**
 * Dùng chung một hàng đợi cho cả trang.
 *
 * Trình duyệt chỉ cho mở vài AudioContext mỗi trang, và nút "Nghe thử" với luồng
 * chat cũng nên cắt tiếng của nhau chứ không chồng lên nhau.
 */
export const sharedAudio = new AudioQueue();
