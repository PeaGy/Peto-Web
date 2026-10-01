/**
 * Nguồn chép lời (phần Peto nghe) dùng khóa riêng của người dùng. Trình duyệt gọi thẳng cả bảy nhà cung cấp (kiểm
 * CORS ngày 2026-09-24), nên máy chủ Peto không nhận khóa hay âm thanh. Khóa nằm chung chỗ với phần Peto nói
 * (`peto-voice-keys`): nhập khóa Azure một lần là dùng được cho cả hai.
 *
 * Âm thanh gửi đi là một câu nói trọn vẹn, WAV PCM16 16 kHz một kênh (hearingAudio.wavFromSamples).
 */
import { azureRegion, baseUrl, toBase64, type KeyConfig } from "./voiceProviders";

export type HearingProviderId = "groq" | "azure" | "openai" | "deepgram" | "elevenlabs" | "gemini" | "compat";
export type HearingLanguage = "en" | "vi";

export interface HearingProvider {
  id: HearingProviderId;
  name: string;
  desc: string;
  keyHint: string;
  /** Nơi lấy khóa, hiện dạng chữ. */
  site: string;
  keyOptional?: boolean;
  needsBaseUrl?: boolean;
  /** Azure cần vùng của tài nguyên Speech. */
  needsRegion?: boolean;
  models?: string[];
  modelFree?: boolean;
  /** Có gói miễn phí không cần thẻ (Groq). */
  free?: boolean;
  /** Khóa này cũng dùng ở phần Peto nói. */
  sharedWithMouth?: boolean;
}

export const HEARING_PROVIDERS: HearingProvider[] = [
  {
    id: "groq", name: "Groq", desc: "Whisper large v3 turbo", keyHint: "gsk_…", site: "console.groq.com",
    models: ["whisper-large-v3-turbo", "whisper-large-v3"], free: true,
  },
  {
    id: "azure", name: "Azure Speech", desc: "Có tiếng Việt", keyHint: "Khóa Speech của Azure", site: "portal.azure.com",
    needsRegion: true, sharedWithMouth: true,
  },
  {
    id: "openai", name: "OpenAI", desc: "gpt-4o-mini-transcribe", keyHint: "sk-…", site: "platform.openai.com",
    models: ["gpt-4o-mini-transcribe", "gpt-transcribe", "gpt-4o-transcribe", "whisper-1"], sharedWithMouth: true,
  },
  {
    id: "deepgram", name: "Deepgram", desc: "Nova-3, chép rất nhanh", keyHint: "Khóa API Deepgram",
    site: "console.deepgram.com", models: ["nova-3", "nova-2"],
  },
  {
    id: "elevenlabs", name: "ElevenLabs", desc: "Scribe", keyHint: "Khóa API ElevenLabs", site: "elevenlabs.io",
    models: ["scribe_v2", "scribe_v1"], sharedWithMouth: true,
  },
  {
    id: "gemini", name: "Google Gemini", desc: "Gemini Flash nghe rồi chép", keyHint: "AIza…", site: "aistudio.google.com",
    modelFree: true, sharedWithMouth: true,
  },
  {
    id: "compat", name: "OpenAI", desc: "Máy chủ Whisper tự dựng", keyHint: "Nếu máy chủ cần",
    site: "máy chủ của bạn", keyOptional: true, needsBaseUrl: true, modelFree: true, sharedWithMouth: true,
  },
];

const DEFAULT_MODELS: Partial<Record<HearingProviderId, string>> = { gemini: "gemini-3.8-flash", compat: "whisper-1" };

export function hearingProvider(id: string): HearingProvider | undefined {
  return HEARING_PROVIDERS.find((provider) => provider.id === id);
}

/** Đủ thông tin để gọi chưa: có khóa (trừ máy chủ tự dựng), có địa chỉ, có vùng. */
export function hearingKeyReady(provider: HearingProvider, config: KeyConfig | undefined): boolean {
  if (!config) return false;
  if (!provider.keyOptional && !config.key?.trim()) return false;
  if (provider.needsBaseUrl && !baseUrl(config)) return false;
  if (provider.needsRegion && !azureRegion(config)) return false;
  return true;
}

export function sttModelOf(provider: HearingProvider, config: KeyConfig | undefined): string {
  return config?.sttModel?.trim() || provider.models?.[0] || DEFAULT_MODELS[provider.id] || "";
}

/** Lỗi khi chép lời. `fatal`: khóa, số dư hay cấu hình sai, nói tiếp cũng hỏng nên thôi nghe. */
export class HearingError extends Error {
  constructor(message: string, readonly fatal: boolean) {
    super(message);
  }
}

function providerError(status: number, name: string): HearingError {
  if (status === 401 || status === 403) return new HearingError(`Khóa ${name} không đúng hoặc chưa có quyền chép lời.`, true);
  if (status === 402) return new HearingError(`Tài khoản ${name} của bạn đã hết số dư.`, true);
  if (status === 429) return new HearingError(`${name} đang giới hạn lượt gọi của khóa này. Chờ một lát rồi nói tiếp.`, false);
  if (status === 400 || status === 404 || status === 413 || status === 422) {
    return new HearingError(`${name} không nhận model hay đoạn âm thanh này. Kiểm tra model trong Cài đặt → Giọng nói → Peto nghe.`, true);
  }
  return new HearingError(`${name} chưa chép được câu này (mã ${status}).`, false);
}

async function call(name: string, url: string, init: RequestInit, signal: AbortSignal): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, signal });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new HearingError(`Không gọi được ${name} từ trình duyệt. Kiểm tra mạng, khóa hoặc địa chỉ.`, false);
  }
  if (!response.ok) throw providerError(response.status, name);
  return response;
}

const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");

async function blobBytes(blob: Blob): Promise<Uint8Array> {
  if (typeof blob.arrayBuffer === "function") return new Uint8Array(await blob.arrayBuffer());
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

/** Câu dặn Gemini; viết bằng tiếng Anh vì dặn bằng tiếng Việt thì Gemini hay dịch luôn câu tiếng Anh sang tiếng Việt. */
function geminiPrompt(language: HearingLanguage): string {
  const spoken = language === "vi" ? "Vietnamese" : "English";
  return `Transcribe this speech exactly as spoken. The speaker usually talks in ${spoken}; keep each word in the `
    + "language it was spoken in and do not translate. Reply with the transcript only. If there is no speech, reply "
    + "with nothing.";
}

/** Chữ Gemini trả trong Interactions API: bước `model_output`; chịu được cả dạng generateContent cũ. */
function geminiText(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const record = data as Record<string, unknown>;
  if (typeof record.output_text === "string") return record.output_text.trim();
  const parts: string[] = [];
  for (const step of Array.isArray(record.steps) ? record.steps : []) {
    const item = step as { type?: unknown; content?: unknown };
    if (item.type !== "model_output" || !Array.isArray(item.content)) continue;
    for (const part of item.content as { type?: unknown; text?: unknown }[]) {
      if (part.type === "text" && typeof part.text === "string") parts.push(part.text);
    }
  }
  if (!parts.length && Array.isArray(record.candidates)) {
    const content = (record.candidates[0] as { content?: { parts?: { text?: unknown }[] } })?.content;
    for (const part of content?.parts ?? []) if (typeof part.text === "string") parts.push(part.text);
  }
  return parts.join("").trim();
}

/** Chép một câu nói bằng khóa của người dùng; trả chữ, hoặc chuỗi rỗng khi không nghe ra chữ nào. */
export async function transcribeWithKey(
  provider: HearingProvider,
  config: KeyConfig,
  audio: Blob,
  language: HearingLanguage,
  signal: AbortSignal,
): Promise<string> {
  const key = config.key?.trim() ?? "";
  const model = sttModelOf(provider, config);
  const name = provider.name;
  switch (provider.id) {
    case "groq":
    case "openai":
    case "compat": {
      const base = provider.id === "groq" ? "https://api.groq.com/openai/v1"
        : provider.id === "openai" ? "https://api.openai.com/v1" : baseUrl(config);
      const form = new FormData();
      form.append("file", audio, "speech.wav");
      form.append("model", model);
      // Các model gpt-*-transcribe của OpenAI tự nhận ngôn ngữ; trường language chỉ dành cho whisper-1.
      if (provider.id !== "openai" || model === "whisper-1") form.append("language", language);
      form.append("response_format", "json");
      const response = await call(name, `${base}/audio/transcriptions`, {
        method: "POST",
        headers: key ? { Authorization: `Bearer ${key}` } : {},
        body: form,
      }, signal);
      const data = await response.json().catch(() => null) as { text?: unknown } | null;
      return text(data?.text);
    }
    case "azure": {
      const url = `https://${azureRegion(config)}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1`
        + `?language=${language === "vi" ? "vi-VN" : "en-US"}&format=simple`;
      const response = await call(name, url, {
        method: "POST",
        headers: {
          "Ocp-Apim-Subscription-Key": key,
          "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
          Accept: "application/json",
        },
        body: audio,
      }, signal);
      const data = await response.json().catch(() => null) as { RecognitionStatus?: unknown; DisplayText?: unknown } | null;
      if (data?.RecognitionStatus === "Success") return text(data.DisplayText);
      if (data?.RecognitionStatus === "Error") throw new HearingError("Azure Speech gặp lỗi khi chép câu này. Nói lại nhé.", false);
      // NoMatch, InitialSilenceTimeout, BabbleTimeout: có tiếng nhưng không ra chữ nào.
      return "";
    }
    case "deepgram": {
      const url = `https://api.deepgram.com/v1/listen?model=${encodeURIComponent(model)}&language=${language}&smart_format=true`;
      const response = await call(name, url, {
        method: "POST",
        headers: { Authorization: `Token ${key}`, "Content-Type": "audio/wav" },
        body: audio,
      }, signal);
      const data = await response.json().catch(() => null) as
        { results?: { channels?: { alternatives?: { transcript?: unknown }[] }[] } } | null;
      return text(data?.results?.channels?.[0]?.alternatives?.[0]?.transcript);
    }
    case "elevenlabs": {
      const form = new FormData();
      form.append("model_id", model);
      form.append("file", audio, "speech.wav");
      form.append("language_code", language);
      const response = await call(name, "https://api.elevenlabs.io/v1/speech-to-text", {
        method: "POST",
        headers: { "xi-api-key": key },
        body: form,
      }, signal);
      const data = await response.json().catch(() => null) as { text?: unknown } | null;
      return text(data?.text);
    }
    case "gemini": {
      const audioData = toBase64(await blobBytes(audio));
      const response = await call(name, "https://generativelanguage.googleapis.com/v1beta/interactions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-goog-api-key": key },
        body: JSON.stringify({
          model,
          input: [
            { type: "text", text: geminiPrompt(language) },
            { type: "audio", data: audioData, mime_type: "audio/wav" },
          ],
        }),
      }, signal);
      return geminiText(await response.json().catch(() => null));
    }
  }
}
