import { trackVoice } from "./voiceActivity";
import { normalizeWav } from "./voiceProviders";
/** Đọc tin của Peto: tiếng từ máy chủ Peto (Giọng Peto, Máy nhà) hoặc từ khóa riêng của người dùng (voiceProviders). */

export const LOCAL_VOICE_ORIGIN = "/api/voice";
export const LOCAL_VOICE_ENABLED_KEY = "peto-local-voice";
export const LOCAL_VOICE_NAME_KEY = "peto-local-voice-name";
/** "home", "official" hay rỗng; máy đã lưu mã giọng theo kiểu cũ thì LocalVoice suy ra nguồn từ mã đó. */
export const VOICE_FALLBACK_KEY = 'peto-voice-fallback';
export const VOICE_SOURCE_KEY = "peto-voice-source";
export const OFFICIAL_VOICE_KEY = "peto-voice-official";

/** Tạo tiếng cho một mẩu chữ, trả WAV (hoặc âm thanh trình duyệt phát được). */
export type Synthesize = (text: string, signal: AbortSignal) => Promise<Blob>;

export interface VoiceHealth {
  voices: string[];
  home: { online: boolean; voices: string[] };
  official: { voices: string[]; allowed: boolean; used: number; limit: number; resets: string };
}

// Giọng đọc chỉ nhanh hơn thời gian thực một chút, nên các mẩu phải xấp xỉ bằng nhau: mẩu sau được
// xin ngay khi mẩu trước về, và chỉ kịp nếu nó không dài hơn mẩu đang phát là bao.
const CHUNK_TARGET = 150;
const CHUNK_MAX = 220;
const TAIL_MERGE = 40;

export type SpeakPhase = "loading" | "playing";

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

/** Hỏi máy chủ Peto: máy nhà có đang bật không, Giọng Peto có những giọng nào và tài khoản này còn bao nhiêu lượt. */
export async function probeVoiceHealth(signal?: AbortSignal): Promise<VoiceHealth | null> {
  try {
    const response = await fetch(`${LOCAL_VOICE_ORIGIN}/health`, { signal });
    if (!response.ok) return null;
    const data = (await response.json()) as Record<string, unknown> | null;
    const home = (data?.home ?? {}) as Record<string, unknown>;
    const official = (data?.official ?? {}) as Record<string, unknown>;
    const voices = strings(data?.voices);
    const homeVoices = strings(home.voices);
    return {
      voices,
      // Máy chủ cũ chưa có mục home: giọng máy nhà nằm trong danh sách chung khi máy đang bật.
      home: { online: typeof home.online === "boolean" ? home.online : voices.some((name) => !name.includes(":")),
              voices: homeVoices.length ? homeVoices : ["playful-1", "gentle-2"] },
      official: {
        voices: "voices" in official ? strings(official.voices) : voices.filter((name) => name.includes(":")),
        allowed: official.allowed !== false,
        used: typeof official.used === "number" ? official.used : 0,
        limit: typeof official.limit === "number" ? official.limit : 0,
        resets: typeof official.resets === "string" ? official.resets : "",
      },
    };
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

/** Sự kiện báo đã chuyển sang giọng dự phòng; ``reason`` là lỗi của nguồn chính khi biết. */
export const VOICE_FALLBACK_EVENT = "peto-voice-fallback";
export interface VoiceFallbackDetail {
  voice: string;
  reason?: string;
}

function announceFallback(voice: string, reason?: string) {
  window.dispatchEvent(new CustomEvent<VoiceFallbackDetail>(VOICE_FALLBACK_EVENT, { detail: { voice, reason } }));
}

/**
 * Tạo tiếng qua máy chủ Peto (Giọng Peto hay Máy nhà). Có ``fallback`` thì máy chủ tự đổi sang giọng đó khi giọng chính
 * lỗi hay hết lượt; ``onUsed`` nhận số ký tự Giọng Peto đã dùng tháng này sau mỗi mẩu.
 */
export function serverSynth(voice: string, options: { fallback?: string; onUsed?: (used: number) => void } = {}): Synthesize {
  let active = voice;
  return async (text, signal) => {
    const fallback = options.fallback && options.fallback !== active ? options.fallback : undefined;
    const response = await requestSpeech(text, active, fallback, signal);
    const selected = response.headers.get("X-Peto-Voice");
    if (!signal.aborted && selected && selected !== active) {
      // Các mẩu sau đi thẳng tới giọng dự phòng, khỏi lần nào cũng thử lại nguồn chính đã hỏng.
      active = selected;
      announceFallback(selected);
    }
    const used = Number(response.headers.get("X-Peto-Voice-Used"));
    if (!signal.aborted && Number.isFinite(used) && response.headers.has("X-Peto-Voice-Used")) options.onUsed?.(used);
    return response.blob();
  };
}

async function requestSpeech(text: string, voice: string, fallback: string | undefined, signal: AbortSignal): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${LOCAL_VOICE_ORIGIN}/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice, ...(fallback ? { fallback } : {}) }),
      signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new Error("Mất kết nối tới giọng nói Peto. Hãy thử lại.");
  }
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof data?.detail === "string" ? data.detail : "Máy chủ giọng nói chưa đọc được câu này.");
  }
  return response;
}

/**
 * Nguồn chính lỗi thì chuyển sang giọng dự phòng của máy chủ cho mẩu này và các mẩu sau, như máy chủ vẫn làm với
 * nguồn của nó; dùng cho khóa riêng, vì máy chủ không thấy lỗi của lượt gọi thẳng từ trình duyệt.
 */
export function withFallback(primary: Synthesize, fallbackVoice: string): Synthesize {
  let current = primary;
  return async (text, signal) => {
    try {
      return await current(text, signal);
    } catch (error) {
      if (signal.aborted || current !== primary || !fallbackVoice) throw error;
      current = serverSynth(fallbackVoice);
      announceFallback(fallbackVoice, error instanceof Error ? error.message : undefined);
      return current(text, signal);
    }
  };
}

/** Nguồn chính chưa dùng được (hết lượt, máy nhà tắt, thiếu khóa): đọc thẳng bằng giọng dự phòng và báo một lần. */
export function fallbackOnly(fallbackVoice: string, reason: string): Synthesize {
  const synth = serverSynth(fallbackVoice);
  let announced = false;
  return async (text, signal) => {
    const blob = await synth(text, signal);
    if (!announced && !signal.aborted) {
      announced = true;
      announceFallback(fallbackVoice, reason);
    }
    return blob;
  };
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

  async speak(text: string, synth: Synthesize, onPhase: (phase: SpeakPhase) => void): Promise<"done" | "stopped"> {
    this.stop();
    const chunks = speechChunks(speakableText(text));
    if (!chunks.length) throw new Error("Tin này không có chữ nào để đọc.");
    const controller = new AbortController();
    this.controller = controller;
    onPhase("loading");
    let pending = synth(chunks[0], controller.signal);
    try {
      for (let index = 0; index < chunks.length; index += 1) {
        const blob = await pending;
        if (controller.signal.aborted) return "stopped";
        if (index + 1 < chunks.length) {
          pending = synth(chunks[index + 1], controller.signal);
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

  private async play(source: Blob, signal: AbortSignal): Promise<void> {
    // Sửa header WAV phát trực tuyến để bộ đo độ to (nhép miệng) đọc được; tệp khác giữ nguyên.
    const blob = typeof source.arrayBuffer === "function"
      ? new Blob([normalizeWav(await source.arrayBuffer())], { type: source.type || "audio/wav" })
      : source;
    if (signal.aborted) return;
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      const stopTracking = trackVoice(audio, blob);
      this.audio = audio;
      const finish = (error?: Error) => {
        stopTracking();
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
