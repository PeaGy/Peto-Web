import { speakableText, speechChunks } from './localSpeech';
import { SpeechQueue } from './speechQueue';
import type { EmotionCue } from '../../../shared/api/api';

export interface SpeechExpressions {
  cues?: EmotionCue[];
  onEmotion: (emotion: string) => void;
}

const ABBREVIATIONS = /(?:\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|e\.g|i\.e)|\b[A-Z])\.$/i;

/** Chỉ đưa câu đã đủ dấu kết thúc và khoảng trắng vào giọng đọc; giữ phần chữ tới dở cho lần sau. */
export class StreamSpeechText {
  readonly queue = new SpeechQueue();
  private buffer = '';
  private closed = false;
  private offset = 0;
  private emotion: string | undefined;
  private cues: EmotionCue[] = [];
  constructor(private readonly onTextReady?: () => void, private readonly splitSentences = true) {}
  markEmotion(emotion: string, offset: number) {
    if (this.closed || !Number.isSafeInteger(offset) || offset < this.offset) return;
    this.cues.push({ emotion, offset });
    this.cues.sort((a, b) => a.offset - b.offset);
    this.drainCues();
  }
  private drainCues() {
    while (this.cues.length && this.cues[0].offset <= this.offset + this.buffer.length) {
      const cue = this.cues.shift()!;
      const length = cue.offset - this.offset;
      // Chốt đoạn trước bằng nét mặt cũ, kể cả khi dấu cách sau câu chưa tới.
      this.enqueue(this.buffer.slice(0, length));
      this.buffer = this.buffer.slice(length);
      this.offset = cue.offset;
      this.emotion = cue.emotion;
    }
  }
  push(delta: string) {
    if (this.closed) return;
    this.buffer += delta;
    this.drainCues();
    // Nghe lại đã có toàn bộ chữ: chỉ tách khi đổi mặt hoặc vượt giới hạn mẩu tiếng.
    if (!this.splitSentences) return;
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
    this.offset += consumed;
  }
  private enqueue(text: string) {
    for (const chunk of speechChunks(speakableText(text))) {
      this.onTextReady?.();
      this.queue.push(chunk, this.emotion);
    }
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
  markEmotion(emotion: string, offset: number): void;
  finish(): void;
  done: Promise<void>;
}
