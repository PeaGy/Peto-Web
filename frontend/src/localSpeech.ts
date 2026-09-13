/**
 * Giọng nói chạy trên chính máy người dùng (local-tts/speak_server.py), không đi qua VPS.
 *
 * Trang chỉ gọi 127.0.0.1 khi người dùng tự bật trong Cài đặt: trang công khai gọi địa chỉ nội bộ
 * thì Chrome hỏi quyền truy cập mạng cục bộ, không nên bắt mọi người gặp hộp hỏi đó. Không có khóa;
 * máy chủ giọng nói tự kiểm tra yêu cầu có đến từ trang Peto không.
 */

export const LOCAL_VOICE_ORIGIN = "http://127.0.0.1:7862";
export const LOCAL_VOICE_ENABLED_KEY = "peto-local-voice";
export const LOCAL_VOICE_NAME_KEY = "peto-local-voice-name";

// Giọng đọc chỉ nhanh hơn thời gian thực một chút, nên các mẩu phải xấp xỉ bằng nhau: mẩu sau được
// xin ngay khi mẩu trước về, và chỉ kịp nếu nó không dài hơn mẩu đang phát là bao.
const CHUNK_TARGET = 150;
const CHUNK_MAX = 220;
const TAIL_MERGE = 40;

export type SpeakPhase = "loading" | "playing";

/** Hỏi máy chủ giọng nói trên máy này; trả danh sách giọng, hoặc null nếu nó chưa chạy. */
export async function probeLocalVoice(signal?: AbortSignal): Promise<string[] | null> {
  try {
    const response = await fetch(`${LOCAL_VOICE_ORIGIN}/health`, { signal });
    if (!response.ok) return null;
    const data = (await response.json()) as { voices?: unknown } | null;
    const voices = Array.isArray(data?.voices)
      ? data.voices.filter((item): item is string => typeof item === "string")
      : [];
    return voices.length ? voices : null;
  } catch {
    return null;
  }
}

/** Đổi markdown thành chữ để đọc: bỏ khối code, link và ký hiệu định dạng; mỗi dòng thành một câu. */
export function speakableText(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?(?:```|$)/g, "\n")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/https?:\/\/\S+/g, " ")
    .split("\n")
    .map((line) => line
      .replace(/^\s{0,3}#{1,6}\s+/, "")
      .replace(/^\s*>\s?/, "")
      .replace(/^\s*(?:[-+*]|\d+[.)])\s+/, "")
      .replace(/^[\s|:-]+$/, "")
      .replace(/[`*_~]/g, "")
      .replace(/\s*\|\s*/g, ", ")
      .replace(/\s+/g, " ")
      .replace(/^[,\s]+|[,\s]+$/g, ""))
    .filter(Boolean)
    .map((line) => (/[.!?…:;]$/.test(line) ? line : `${line}.`))
    .join(" ");
}

/** Cắt chữ thành các mẩu gần bằng nhau để xin tiếng lần lượt, không cắt giữa câu nếu tránh được. */
export function speechChunks(text: string): string[] {
  const sentences = text.split(/(?<=[.!?…]["'”’)\]]*)\s+/).flatMap(splitLong);
  const chunks: string[] = [];
  let current = "";
  for (const sentence of sentences) {
    if (!sentence) continue;
    const joined = current ? `${current} ${sentence}` : sentence;
    if (current && joined.length > CHUNK_TARGET) {
      chunks.push(current);
      current = sentence;
    } else {
      current = joined;
    }
  }
  if (current) {
    const last = chunks[chunks.length - 1];
    // Chỉ gộp phần đuôi thật ngắn, kẻo mẩu cuối dài gấp đôi mẩu trước và phải chờ.
    if (last !== undefined && current.length < TAIL_MERGE && last.length + 1 + current.length <= CHUNK_MAX) {
      chunks[chunks.length - 1] = `${last} ${current}`;
    } else {
      chunks.push(current);
    }
  }
  return chunks;
}

function splitLong(sentence: string): string[] {
  const trimmed = sentence.trim();
  if (trimmed.length <= CHUNK_MAX) return [trimmed];
  const pieces: string[] = [];
  let current = "";
  for (const word of trimmed.split(/\s+/)) {
    const joined = current ? `${current} ${word}` : word;
    if (joined.length <= CHUNK_MAX) {
      current = joined;
      continue;
    }
    if (current) pieces.push(current);
    current = word;
    while (current.length > CHUNK_MAX) {
      pieces.push(current.slice(0, CHUNK_MAX));
      current = current.slice(CHUNK_MAX);
    }
  }
  if (current) pieces.push(current);
  return pieces;
}

async function requestSpeech(text: string, voice: string, signal: AbortSignal): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(`${LOCAL_VOICE_ORIGIN}/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice }),
      signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new Error("Mất kết nối tới máy chủ giọng nói trên máy này.");
  }
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof data?.detail === "string" ? data.detail : "Máy chủ giọng nói chưa đọc được câu này.");
  }
  return response.blob();
}

/** Đọc một tin: xin tiếng từng mẩu, mẩu kế tiếp được xin ngay khi mẩu trước về để đỡ khoảng lặng. */
export class LocalVoicePlayer {
  private controller: AbortController | null = null;
  private audio: HTMLAudioElement | null = null;

  stop() {
    this.controller?.abort();
    this.controller = null;
    this.audio?.pause();
    this.audio = null;
  }

  async speak(text: string, voice: string, onPhase: (phase: SpeakPhase) => void): Promise<"done" | "stopped"> {
    this.stop();
    const chunks = speechChunks(speakableText(text));
    if (!chunks.length) throw new Error("Tin này không có chữ nào để đọc.");
    const controller = new AbortController();
    this.controller = controller;
    onPhase("loading");
    let pending = requestSpeech(chunks[0], voice, controller.signal);
    try {
      for (let index = 0; index < chunks.length; index += 1) {
        const blob = await pending;
        if (controller.signal.aborted) return "stopped";
        if (index + 1 < chunks.length) {
          pending = requestSpeech(chunks[index + 1], voice, controller.signal);
          // Lỗi của mẩu kế tiếp được ném ra khi tới lượt nó, không để trình duyệt báo lỗi chưa bắt.
          pending.catch(() => {});
        }
        onPhase("playing");
        await this.play(blob, controller.signal);
        if (controller.signal.aborted) return "stopped";
      }
      return "done";
    } catch (error) {
      if (controller.signal.aborted) return "stopped";
      throw error;
    } finally {
      if (this.controller === controller) {
        this.controller = null;
        this.audio = null;
      }
    }
  }

  private play(blob: Blob, signal: AbortSignal): Promise<void> {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      this.audio = audio;
      const finish = (error?: Error) => {
        signal.removeEventListener("abort", onAbort);
        audio.onended = null;
        audio.onerror = null;
        URL.revokeObjectURL(url);
        if (error) reject(error);
        else resolve();
      };
      const onAbort = () => {
        audio.pause();
        finish();
      };
      signal.addEventListener("abort", onAbort, { once: true });
      audio.onended = () => finish();
      audio.onerror = () => finish(new Error("Trình duyệt không phát được tiếng Peto."));
      audio.play().catch(() => finish(new Error("Trình duyệt chưa cho phát tiếng. Bấm Nghe lần nữa nhé.")));
    });
  }
}
