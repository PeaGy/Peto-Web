/**
 * Đọc câu trả lời của Peto bằng giọng có sẵn trong máy (Web Speech API).
 *
 * Không tốn tiền và không cần khóa của ai, đổi lại chất lượng tùy máy: Windows
 * và Android có giọng tiếng Việt, máy khác thì có thể không. Đây là bước đệm để
 * dựng xong đường đi của tiếng nói trước khi cắm dịch vụ giọng thật.
 *
 * Đọc dần theo từng câu ngay trong lúc chữ còn đang chảy về, nên Peto bắt đầu
 * nói gần như cùng lúc với lúc mình đọc được chữ đầu tiên.
 */

const FENCE = "```";
const KEY = "peto-voice";
const ENDERS = ".!?…;:";

export interface VoiceSettings {
  on: boolean;
  /** Rỗng nghĩa là để máy tự chọn giọng. */
  voiceURI: string;
  rate: number;
}

export const DEFAULT_VOICE: VoiceSettings = { on: false, voiceURI: "", rate: 1 };

export function speechSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function listVoices(): SpeechSynthesisVoice[] {
  return speechSupported() ? window.speechSynthesis.getVoices() : [];
}

export function loadVoiceSettings(): VoiceSettings {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT_VOICE;
    const saved = JSON.parse(raw) as Partial<VoiceSettings>;
    const rate = typeof saved.rate === "number" ? saved.rate : 1;
    return {
      on: saved.on === true,
      voiceURI: typeof saved.voiceURI === "string" ? saved.voiceURI : "",
      rate: rate >= 0.5 && rate <= 2 ? rate : 1,
    };
  } catch {
    return DEFAULT_VOICE;
  }
}

export function saveVoiceSettings(value: VoiceSettings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(value));
  } catch {
    // Trình duyệt chặn localStorage thì thôi, không đáng làm hỏng lượt chat.
  }
}

/**
 * Bỏ những thứ đọc lên chỉ thành tiếng ồn: khối mã, bảng, dấu markdown.
 *
 * Khối mã chưa đóng (đang gõ dở) cũng phải bỏ, không thì Peto đọc từng dấu ngoặc.
 */
export function speakableText(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, " (khối mã) ")
    .replace(/```[\s\S]*$/, " (khối mã) ")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^[ \t]*\|.*$/gm, " ")
    .replace(/^[ \t]{0,3}#{1,6}[ \t]+/gm, "")
    .replace(/^[ \t]{0,3}>[ \t]?/gm, "")
    .replace(/^[ \t]*[-*+][ \t]+/gm, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Thay khối mã đã đóng bằng một câu ngắn.
 *
 * Phải làm trước khi cắt câu: xuống dòng bên trong khối mã cũng là dấu ngắt, để
 * nguyên thì một đoạn mã bị xé thành nhiều mẩu và Peto đọc "khối mã" mấy lần.
 */
function stripCode(text: string): string {
  return text.replace(/```[\s\S]*?```/g, " (khối mã). ");
}

/**
 * Tách phần đã đủ câu ra khỏi bộ đệm.
 *
 * Chỉ cắt khi sau dấu câu là khoảng trắng, nên "3.14" hay "v.d" không bị xé đôi.
 * Dấu câu ở ngay cuối bộ đệm thì để lại: biết đâu chữ tiếp theo còn đang về.
 */
export function splitSentences(buffer: string): { ready: string[]; rest: string } {
  const ready: string[] = [];
  let start = 0;
  for (let i = 0; i < buffer.length; i += 1) {
    const char = buffer[i];
    const next = buffer[i + 1];
    const isBreak = char === "\n" || (ENDERS.includes(char) && next !== undefined && /\s/.test(next));
    if (!isBreak) continue;
    const piece = buffer.slice(start, i + 1).trim();
    if (piece) ready.push(piece);
    start = i + 1;
  }
  return { ready, rest: buffer.slice(start) };
}

/**
 * Gom chữ chảy về rồi đọc từng câu một.
 *
 * Giữ lại phần sau dấu mở khối mã cho tới khi khối đó đóng, để không đọc nửa
 * chừng đoạn mã rồi mới biết đó là mã.
 */
export class SpeechQueue {
  private buffer = "";

  constructor(private readonly settings: () => VoiceSettings) {}

  push(delta: string): void {
    this.buffer += delta;
    this.drain(false);
  }

  /** Hết lượt trả lời: đọc nốt phần lẻ còn lại. */
  flush(): void {
    this.drain(true);
  }

  /** Im ngay và quên phần chưa đọc. */
  cancel(): void {
    this.buffer = "";
    if (speechSupported()) window.speechSynthesis.cancel();
  }

  private drain(final: boolean): void {
    if (!this.settings().on || !speechSupported()) {
      // Đang tắt thì đừng giữ chữ lại, kẻo bật lên là đọc dồn cả bài cũ.
      this.buffer = "";
      return;
    }

    let safe = this.buffer;
    let held = "";
    const fences = this.buffer.split(FENCE).length - 1;
    if (fences % 2 === 1 && !final) {
      const open = this.buffer.lastIndexOf(FENCE);
      safe = this.buffer.slice(0, open);
      held = this.buffer.slice(open);
    }

    const { ready, rest } = splitSentences(stripCode(safe));
    for (const piece of ready) this.speak(piece);
    this.buffer = rest + held;

    if (final) {
      const last = this.buffer;
      this.buffer = "";
      this.speak(last);
    }
  }

  private speak(text: string): void {
    const clean = speakableText(text);
    if (!clean) return;
    const utterance = new SpeechSynthesisUtterance(clean);
    const { voiceURI, rate } = this.settings();
    const voice = listVoices().find((item) => item.voiceURI === voiceURI);
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang;
    }
    utterance.rate = rate;
    window.speechSynthesis.speak(utterance);
  }
}
