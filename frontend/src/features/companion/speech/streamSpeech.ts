import { speakableText, speechChunks } from './localSpeech';
import { SpeechQueue } from './speechQueue';

const ABBREVIATIONS = /(?:\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|e\.g|i\.e)|\b[A-Z])\.$/i;

/** Chỉ đưa câu đã đủ dấu kết thúc và khoảng trắng vào giọng đọc; giữ phần chữ tới dở cho lần sau. */
export class StreamSpeechText {
  readonly queue = new SpeechQueue();
  private buffer = '';
  private closed = false;
  push(delta: string) {
    if (this.closed) return;
    this.buffer += delta;
    let consumed = 0;
    for (const match of this.buffer.matchAll(/[.!?…]+["'”’)\]]*(?=\s)/g)) {
      const end = match.index + match[0].length;
      const sentence = this.buffer.slice(consumed, end);
      if ((this.buffer.slice(0, end).match(/```/g)?.length ?? 0) % 2) continue;
      if (match[0] === '.' && ABBREVIATIONS.test(sentence)) continue;
      this.enqueue(sentence);
      consumed = end;
    }
    this.buffer = this.buffer.slice(consumed);
  }
  private enqueue(text: string) {
    for (const chunk of speechChunks(speakableText(text))) this.queue.push(chunk);
  }
  finish() {
    if (this.closed) return;
    this.enqueue(this.buffer);
    this.buffer = '';
    this.closed = true;
    this.queue.finish();
  }
  cancel() { this.closed = true; this.buffer = ''; this.queue.cancel(); }
}

export interface VoiceStream {
  push(text: string): void;
  finish(): void;
  done: Promise<void>;
}
