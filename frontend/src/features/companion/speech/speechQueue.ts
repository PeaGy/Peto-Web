export interface SpeechChunk { text: string; emotion?: string }

/** Hàng chờ chữ của một lượt đọc; chỉ một người lấy, hủy thì bỏ toàn bộ phần chưa phát. */
export class SpeechQueue {
  private chunks: SpeechChunk[];
  private ended = false;
  private wake: (() => void) | null = null;
  constructor(chunks: string[] = []) { this.chunks = chunks.map(text => ({ text })); }
  push(text: string, emotion?: string) {
    if (this.ended || !text.trim()) return;
    this.chunks.push({ text, emotion });
    this.wake?.();
  }
  finish() { this.ended = true; this.wake?.(); }
  cancel() { this.chunks = []; this.finish(); }
  async next(signal: AbortSignal): Promise<string | null> {
    return (await this.nextChunk(signal))?.text ?? null;
  }
  async nextChunk(signal: AbortSignal): Promise<SpeechChunk | null> {
    while (!signal.aborted) {
      const text = this.chunks.shift();
      if (text !== undefined) return text;
      if (this.ended) return null;
      await new Promise<void>(resolve => {
        const wake = () => {
          signal.removeEventListener('abort', wake);
          if (this.wake === wake) this.wake = null;
          resolve();
        };
        this.wake = wake;
        signal.addEventListener('abort', wake, { once: true });
      });
    }
    return null;
  }
}
