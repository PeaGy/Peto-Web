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

// Giọng cài sẵn trong Windows đọc chậm hơn hẳn giọng của các dịch vụ trên mạng ở
// cùng mức 1.0, nên mặc định nhanh hơn một chút.
export const DEFAULT_VOICE: VoiceSettings = { on: false, voiceURI: "", rate: 1.2 };

// Bản 1 lưu rate 1.0 vì đó là mặc định cũ chứ không phải người dùng chọn.
const SETTINGS_VERSION = 2;

// Mỗi lượt đọc đều có quãng im ở đầu và cuối, nên càng ít lượt thì càng nghe liền
// mạch như người nói. Mẩu đầu đọc ngay cho kịp lúc chữ vừa hiện, rồi dồn dần: mẩu
// thứ hai dài hơn, từ mẩu thứ ba trở đi dài hẳn.
const CHUNK_STEPS = [0, 240, 480];
const MAX_CHUNK = 500;
// Chrome âm thầm tạm dừng lượt đọc dài quá ~15 giây; gọi resume đều đặn để nó đọc hết.
const KEEP_ALIVE_MS = 5000;

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
    const saved = JSON.parse(raw) as Partial<VoiceSettings> & { v?: number };
    const value = typeof saved.rate === "number" ? saved.rate : DEFAULT_VOICE.rate;
    const rate = value >= 0.5 && value <= 2 ? value : DEFAULT_VOICE.rate;
    return {
      on: saved.on === true,
      voiceURI: typeof saved.voiceURI === "string" ? saved.voiceURI : "",
      // Bản cũ chưa có số hiệu: nếu đang để đúng mặc định cũ thì nâng lên mặc định
      // mới một lần. Sau đó tôn trọng mọi giá trị người dùng đã tự chỉnh.
      rate: saved.v === SETTINGS_VERSION ? rate : rate === 1 ? DEFAULT_VOICE.rate : rate,
    };
  } catch {
    return DEFAULT_VOICE;
  }
}

export function saveVoiceSettings(value: VoiceSettings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...value, v: SETTINGS_VERSION }));
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

/** Cắt mẩu quá dài ở khoảng trắng gần nhất, để không lượt đọc nào quá dài. */
export function chunkLong(text: string, max = MAX_CHUNK): string[] {
  const pieces: string[] = [];
  let rest = text.trim();
  while (rest.length > max) {
    const space = rest.lastIndexOf(" ", max);
    const at = space > max / 2 ? space : max;
    pieces.push(rest.slice(0, at).trim());
    rest = rest.slice(at).trim();
  }
  if (rest) pieces.push(rest);
  return pieces;
}

/**
 * Gom chữ chảy về rồi đọc từng mẩu một.
 *
 * Giữ lại phần sau dấu mở khối mã cho tới khi khối đó đóng, để không đọc nửa
 * chừng đoạn mã rồi mới biết đó là mã.
 */
export class SpeechQueue {
  private buffer = "";
  /** Câu đã đủ nhưng còn chờ gom thêm cho đỡ ngắt quãng. */
  private pending = "";
  /** Đếm số lượt đã đọc trong câu trả lời này; mẩu đầu được ưu tiên đọc ngay. */
  private said = 0;
  private keepAlive: ReturnType<typeof setInterval> | undefined;

  constructor(private readonly settings: () => VoiceSettings) {}

  push(delta: string): void {
    this.buffer += delta;
    this.drain(false);
  }

  /** Hết lượt trả lời: đọc nốt phần lẻ còn lại. */
  flush(): void {
    this.drain(true);
    // Lượt trả lời sau lại được đọc ngay từ câu đầu.
    this.said = 0;
  }

  /** Im ngay và quên phần chưa đọc. */
  cancel(): void {
    this.buffer = "";
    this.pending = "";
    this.said = 0;
    this.stopKeepAlive();
    if (speechSupported()) window.speechSynthesis.cancel();
  }

  private drain(final: boolean): void {
    if (!this.settings().on || !speechSupported()) {
      // Đang tắt thì đừng giữ chữ lại, kẻo bật lên là đọc dồn cả bài cũ.
      this.buffer = "";
      this.pending = "";
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
    for (const piece of ready) this.enqueue(piece);
    this.buffer = rest + held;

    if (final) {
      const last = this.buffer;
      this.buffer = "";
      this.enqueue(last);
      this.sayPending();
    }
  }

  /** Mẩu đầu đọc ngay cho kịp lúc chữ vừa hiện; các câu sau gom lại cho liền mạch. */
  private enqueue(sentence: string): void {
    const piece = sentence.trim();
    if (!piece) return;
    this.pending = this.pending ? `${this.pending} ${piece}` : piece;
    const needed = CHUNK_STEPS[Math.min(this.said, CHUNK_STEPS.length - 1)];
    if (this.pending.length >= needed) this.sayPending();
  }

  private sayPending(): void {
    const text = this.pending;
    this.pending = "";
    for (const piece of chunkLong(text)) this.speak(piece);
  }

  private speak(text: string): void {
    const clean = speakableText(text);
    if (!clean) return;
    this.said += 1;
    const utterance = new SpeechSynthesisUtterance(clean);
    const { voiceURI, rate } = this.settings();
    const voice = listVoices().find((item) => item.voiceURI === voiceURI);
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang;
    }
    utterance.rate = rate;
    window.speechSynthesis.speak(utterance);
    this.startKeepAlive();
  }

  private startKeepAlive(): void {
    if (this.keepAlive !== undefined) return;
    this.keepAlive = setInterval(() => {
      const synth = window.speechSynthesis;
      if (!synth.speaking) {
        this.stopKeepAlive();
        return;
      }
      // Lúc đang đọc bình thường thì resume không ảnh hưởng gì; chỉ khi Chrome tự
      // tạm dừng giữa chừng nó mới có tác dụng.
      synth.resume();
    }, KEEP_ALIVE_MS);
  }

  private stopKeepAlive(): void {
    if (this.keepAlive === undefined) return;
    clearInterval(this.keepAlive);
    this.keepAlive = undefined;
  }
}
