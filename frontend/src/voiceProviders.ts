/**
 * Nguồn giọng dùng khóa riêng của người dùng (chủ web chọn ngày 2026-09-24, giống AIRI): khóa nằm trên trình duyệt
 * này và trình duyệt gọi thẳng nhà cung cấp, máy chủ Peto không nhận được khóa. Riêng StepFun (chặn trình duyệt gọi
 * thẳng) và Qwen (trả địa chỉ tệp âm thanh trình duyệt không tải được) đi qua /api/voice/relay: máy chủ chỉ chuyển
 * tiếp, không lưu, không ghi lại khóa.
 *
 * Âm thanh nào cũng được đổi về WAV PCM16 trước khi phát, để voiceActivity đọc được độ to cho nhân vật nhép miệng.
 */

export type KeyProviderId = "openai" | "elevenlabs" | "azure" | "gemini" | "minimax" | "qwen" | "stepfun" | "compat";

export interface KeyConfig {
  key?: string;
  voice?: string;
  model?: string;
  region?: string;
  baseUrl?: string;
}

export interface KeyProvider {
  id: KeyProviderId;
  name: string;
  desc: string;
  /** direct: trình duyệt gọi thẳng; relay: qua máy chủ Peto, không lưu. */
  route: "direct" | "relay";
  keyHint: string;
  /** Nơi lấy khóa, hiện dạng chữ. */
  site: string;
  keyOptional?: boolean;
  needsBaseUrl?: boolean;
  /** Azure cần vùng (chữ), Qwen chọn tài khoản quốc tế hay Trung Quốc. */
  region?: { label: string; placeholder?: string; options?: { value: string; label: string }[] };
  models?: string[];
  modelFree?: boolean;
  /** Danh sách giọng cố định, hay gợi ý khi voiceFree. */
  voices?: string[];
  voiceFree?: boolean;
  /** Danh sách giọng tải từ nhà cung cấp sau khi có khóa. */
  listsVoices?: boolean;
  defaultVoice: string;
}

export interface VoiceOption {
  id: string;
  label: string;
}

const GEMINI_VOICES = [
  "Kore", "Puck", "Zephyr", "Charon", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe", "Autonoe", "Enceladus",
  "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar", "Alnilam",
  "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
];

export const KEY_PROVIDERS: KeyProvider[] = [
  {
    id: "openai", name: "OpenAI", desc: "tts-1, tts-1-hd", route: "direct", keyHint: "sk-…", site: "platform.openai.com",
    models: ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"],
    voices: ["nova", "shimmer", "coral", "sage", "alloy", "ash", "echo", "fable", "onyx"], defaultVoice: "nova",
  },
  {
    id: "elevenlabs", name: "ElevenLabs", desc: "Kho giọng lớn, nhân bản giọng", route: "direct",
    keyHint: "Khóa API ElevenLabs", site: "elevenlabs.io",
    models: ["eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_turbo_v2_5"], listsVoices: true, defaultVoice: "",
  },
  {
    id: "azure", name: "Azure Speech", desc: "Có giọng tiếng Việt", route: "direct", keyHint: "Khóa Speech của Azure",
    site: "portal.azure.com", region: { label: "Vùng", placeholder: "southeastasia" }, listsVoices: true,
    defaultVoice: "en-US-AvaMultilingualNeural",
  },
  {
    id: "gemini", name: "Google Gemini", desc: "Gemini TTS", route: "direct", keyHint: "AIza…", site: "aistudio.google.com",
    models: ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"], voices: GEMINI_VOICES, defaultVoice: "Kore",
  },
  {
    id: "minimax", name: "MiniMax", desc: "MiniMax Speech", route: "direct", keyHint: "Khóa API MiniMax", site: "minimax.io",
    models: ["speech-2.8-turbo", "speech-2.8-hd"], voiceFree: true,
    voices: ["English_radiant_girl", "English_Graceful_Lady", "Japanese_Whisper_Belle"], defaultVoice: "English_radiant_girl",
  },
  {
    id: "qwen", name: "Qwen Cloud", desc: "Alibaba Cloud Model Studio", route: "relay", keyHint: "sk-…",
    site: "Alibaba Cloud Model Studio",
    region: { label: "Tài khoản", options: [{ value: "intl", label: "Quốc tế (Singapore)" }, { value: "cn", label: "Trung Quốc" }] },
    models: ["qwen3-tts-flash"], voiceFree: true, voices: ["Cherry", "Serena", "Ethan", "Chelsie"], defaultVoice: "Cherry",
  },
  {
    id: "stepfun", name: "StepFun", desc: "Cùng giọng với Giọng Peto", route: "relay", keyHint: "Khóa API StepFun",
    site: "platform.stepfun.ai", models: ["stepaudio-2.5-tts"], voiceFree: true, voices: ["jilingshaonv", "lively-girl"],
    defaultVoice: "jilingshaonv",
  },
  {
    id: "compat", name: "Tương thích OpenAI", desc: "Máy chủ tự dựng, địa chỉ riêng", route: "direct",
    keyHint: "Nếu máy chủ cần", site: "máy chủ của bạn", keyOptional: true, needsBaseUrl: true, modelFree: true,
    voiceFree: true, defaultVoice: "",
  },
];

export function keyProvider(id: string): KeyProvider | undefined {
  return KEY_PROVIDERS.find((provider) => provider.id === id);
}

// --- Khóa lưu trên trình duyệt này ------------------------------------------------------------------------------

export const VOICE_KEYS_KEY = "peto-voice-keys";

export function readKeyConfigs(): Partial<Record<KeyProviderId, KeyConfig>> {
  try {
    const data = JSON.parse(localStorage.getItem(VOICE_KEYS_KEY) ?? "{}") as unknown;
    return data && typeof data === "object" && !Array.isArray(data) ? data as Partial<Record<KeyProviderId, KeyConfig>> : {};
  } catch {
    return {};
  }
}

export function writeKeyConfigs(configs: Partial<Record<KeyProviderId, KeyConfig>>): void {
  try {
    localStorage.setItem(VOICE_KEYS_KEY, JSON.stringify(configs));
  } catch {}
}

/** Đủ thông tin để gọi chưa: có khóa (trừ máy chủ tự dựng), có địa chỉ, có vùng. */
export function keyReady(provider: KeyProvider, config: KeyConfig | undefined): boolean {
  if (!config) return false;
  if (!provider.keyOptional && !config.key?.trim()) return false;
  if (provider.needsBaseUrl && !baseUrl(config)) return false;
  if (provider.id === "azure" && !azureRegion(config)) return false;
  return true;
}

export function voiceOf(provider: KeyProvider, config: KeyConfig | undefined): string {
  return config?.voice?.trim() || provider.defaultVoice;
}

export function modelOf(provider: KeyProvider, config: KeyConfig | undefined): string {
  return config?.model?.trim() || provider.models?.[0] || (provider.id === "compat" ? "tts-1" : "");
}

function baseUrl(config: KeyConfig): string {
  const value = config.baseUrl?.trim().replace(/\/+$/, "") ?? "";
  return /^https?:\/\/[^\s]+$/i.test(value) ? value : "";
}

function azureRegion(config: KeyConfig): string {
  const value = config.region?.trim().toLowerCase() ?? "";
  return /^[a-z0-9-]{2,40}$/.test(value) ? value : "";
}

// --- WAV -----------------------------------------------------------------------------------------------------

/** Bọc PCM16 little-endian thành tệp WAV. */
export function pcmToWav(pcm: Uint8Array<ArrayBuffer>, sampleRate: number, channels = 1): Blob {
  const header = new ArrayBuffer(44);
  const view = new DataView(header);
  const text = (at: number, value: string) => [...value].forEach((char, index) => view.setUint8(at + index, char.charCodeAt(0)));
  text(0, "RIFF");
  view.setUint32(4, 36 + pcm.byteLength, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * channels * 2, true);
  view.setUint16(32, channels * 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, pcm.byteLength, true);
  return new Blob([header, pcm], { type: "audio/wav" });
}

/**
 * WAV phát trực tuyến (OpenAI, một số máy chủ tự dựng) ghi kích thước "không rõ" (0xFFFFFFFF) vào header; trình
 * duyệt vẫn phát được nhưng bộ đo độ to bỏ qua. Sửa kích thước theo độ dài thật; không phải WAV thì trả nguyên.
 */
export function normalizeWav(buffer: ArrayBuffer): ArrayBuffer {
  if (buffer.byteLength < 44) return buffer;
  const view = new DataView(buffer);
  const tag = (at: number) => String.fromCharCode(...new Uint8Array(buffer, at, 4));
  if (tag(0) !== "RIFF" || tag(8) !== "WAVE") return buffer;
  const copy = buffer.slice(0);
  const out = new DataView(copy);
  out.setUint32(4, buffer.byteLength - 8, true);
  for (let pos = 12; pos + 8 <= buffer.byteLength;) {
    const length = view.getUint32(pos + 4, true);
    if (tag(pos) === "data") {
      if (pos + 8 + length > buffer.byteLength) out.setUint32(pos + 4, buffer.byteLength - pos - 8, true);
      break;
    }
    if (pos + 8 + length > buffer.byteLength) break;
    pos += 8 + length + (length % 2);
  }
  return copy;
}

function audioBytesToWav(bytes: Uint8Array<ArrayBuffer>, rate = 24000): Blob {
  const riff = bytes.length >= 12 && String.fromCharCode(...bytes.subarray(0, 4)) === "RIFF";
  return riff ? new Blob([bytes], { type: "audio/wav" }) : pcmToWav(bytes, rate);
}

function fromBase64(value: string): Uint8Array<ArrayBuffer> {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

function fromHex(value: string): Uint8Array<ArrayBuffer> {
  const bytes = new Uint8Array(Math.floor(value.length / 2));
  for (let index = 0; index < bytes.length; index += 1) bytes[index] = parseInt(value.slice(index * 2, index * 2 + 2), 16);
  return bytes;
}

function escapeXml(text: string): string {
  return text.replace(/[<>&'"]/g, (char) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" })[char]!);
}

// --- Gọi nhà cung cấp ------------------------------------------------------------------------------------------

function providerError(status: number, name: string): Error {
  if (status === 401 || status === 403) return new Error(`Khóa ${name} không đúng hoặc chưa có quyền dùng giọng nói.`);
  if (status === 402) return new Error(`Tài khoản ${name} của bạn đã hết số dư.`);
  if (status === 429) return new Error(`${name} đang giới hạn lượt gọi của khóa này. Thử lại sau.`);
  if (status === 400 || status === 404 || status === 422) {
    return new Error(`${name} không nhận giọng hoặc model này. Kiểm tra lại trong Cài đặt → Giọng nói.`);
  }
  return new Error(`${name} chưa đọc được câu này (mã ${status}).`);
}

async function call(name: string, url: string, init: RequestInit, signal: AbortSignal): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, signal });
  } catch (error) {
    if (signal.aborted) throw error;
    // Lỗi CORS cũng rơi vào đây, kể cả khi khóa sai mà nhà cung cấp không gửi kèm header CORS (OpenAI).
    throw new Error(`Không gọi được ${name} từ trình duyệt. Kiểm tra mạng, khóa hoặc địa chỉ.`);
  }
  if (!response.ok) throw providerError(response.status, name);
  return response;
}

/** Đọc một mẩu bằng khóa của người dùng; trả WAV. */
export async function speakWithKey(provider: KeyProvider, config: KeyConfig, text: string, signal: AbortSignal): Promise<Blob> {
  const key = config.key?.trim() ?? "";
  const voice = voiceOf(provider, config);
  const model = modelOf(provider, config);
  const json = { "Content-Type": "application/json" };
  switch (provider.id) {
    case "openai":
    case "compat": {
      const base = provider.id === "openai" ? "https://api.openai.com/v1" : baseUrl(config);
      const response = await call(provider.name, `${base}/audio/speech`, {
        method: "POST",
        headers: { ...json, ...(key ? { Authorization: `Bearer ${key}` } : {}) },
        body: JSON.stringify({ model, input: text, voice, response_format: "wav" }),
      }, signal);
      return audioBytesToWav(new Uint8Array(await response.arrayBuffer()));
    }
    case "elevenlabs": {
      if (!voice) throw new Error("Chọn một giọng ElevenLabs trong Cài đặt → Giọng nói.");
      const response = await call(provider.name,
        `https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(voice)}?output_format=wav_24000`, {
          method: "POST",
          headers: { ...json, "xi-api-key": key, Accept: "audio/wav" },
          body: JSON.stringify({ text, model_id: model }),
        }, signal);
      return audioBytesToWav(new Uint8Array(await response.arrayBuffer()));
    }
    case "azure": {
      const ssml = `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">`
        + `<voice name="${escapeXml(voice)}">${escapeXml(text)}</voice></speak>`;
      const response = await call(provider.name, `https://${azureRegion(config)}.tts.speech.microsoft.com/cognitiveservices/v1`, {
        method: "POST",
        headers: {
          "Ocp-Apim-Subscription-Key": key,
          "Content-Type": "application/ssml+xml",
          "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
        },
        body: ssml,
      }, signal);
      return audioBytesToWav(new Uint8Array(await response.arrayBuffer()));
    }
    case "gemini": {
      const response = await call(provider.name, "https://generativelanguage.googleapis.com/v1beta/interactions", {
        method: "POST",
        headers: { ...json, "x-goog-api-key": key },
        body: JSON.stringify({
          model,
          input: [{ type: "user_input", content: [{ type: "text", text }] }],
          response_format: { type: "audio", mime_type: "audio/wav" },
          generation_config: { speech_config: [{ voice }] },
        }),
      }, signal);
      const data = findAudio(await response.json().catch(() => null));
      if (!data) throw new Error("Gemini không trả về âm thanh. Kiểm tra model trong Cài đặt → Giọng nói.");
      return audioBytesToWav(fromBase64(data));
    }
    case "minimax": {
      const response = await call(provider.name, "https://api.minimax.io/v1/t2a_v2", {
        method: "POST",
        headers: { ...json, Authorization: `Bearer ${key}` },
        body: JSON.stringify({
          model, text, stream: false, output_format: "hex",
          voice_setting: { voice_id: voice },
          audio_setting: { format: "wav", sample_rate: 24000, channel: 1 },
        }),
      }, signal);
      const data = await response.json().catch(() => null) as
        { data?: { audio?: unknown }; base_resp?: { status_code?: number } } | null;
      const status = data?.base_resp?.status_code;
      if (status && status !== 0) throw providerError(status === 1004 || status === 2049 ? 401 : 400, provider.name);
      if (typeof data?.data?.audio !== "string" || !data.data.audio) throw new Error("MiniMax không trả về âm thanh.");
      return audioBytesToWav(fromHex(data.data.audio));
    }
    case "qwen":
    case "stepfun": {
      let response: Response;
      try {
        response = await fetch("/api/voice/relay", {
          method: "POST",
          headers: { ...json, "X-Voice-Key": key },
          body: JSON.stringify({ provider: provider.id, text, voice, model, region: config.region || "intl" }),
          signal,
        });
      } catch (error) {
        if (signal.aborted) throw error;
        throw new Error("Mất kết nối tới máy chủ Peto. Hãy thử lại.");
      }
      if (!response.ok) {
        const detail = (await response.json().catch(() => null) as { detail?: unknown } | null)?.detail;
        throw new Error(typeof detail === "string" ? detail : `${provider.name} chưa đọc được câu này.`);
      }
      return audioBytesToWav(new Uint8Array(await response.arrayBuffer()));
    }
  }
}

/** Tìm chuỗi base64 âm thanh trong phản hồi Gemini, chịu được cả dạng interactions lẫn generateContent cũ. */
function findAudio(value: unknown, depth = 0): string | null {
  if (!value || typeof value !== "object" || depth > 8) return null;
  const record = value as Record<string, unknown>;
  for (const key of ["output_audio", "outputAudio", "inlineData", "inline_data"]) {
    const part = record[key] as Record<string, unknown> | undefined;
    if (part && typeof part.data === "string" && part.data) return part.data;
  }
  for (const item of Array.isArray(value) ? value : Object.values(record)) {
    const found = findAudio(item, depth + 1);
    if (found) return found;
  }
  return null;
}

/** Giọng tải từ nhà cung cấp sau khi có khóa (ElevenLabs, Azure). null: nhà cung cấp này dùng danh sách cố định. */
export async function listKeyVoices(provider: KeyProvider, config: KeyConfig, signal: AbortSignal): Promise<VoiceOption[] | null> {
  const key = config.key?.trim() ?? "";
  if (provider.id === "elevenlabs") {
    const response = await call(provider.name, "https://api.elevenlabs.io/v2/voices?page_size=100", {
      headers: { "xi-api-key": key },
    }, signal);
    const data = await response.json().catch(() => null) as { voices?: { voice_id?: unknown; name?: unknown }[] } | null;
    return (data?.voices ?? [])
      .filter((item) => typeof item.voice_id === "string")
      .map((item) => ({ id: item.voice_id as string, label: typeof item.name === "string" ? item.name : item.voice_id as string }));
  }
  if (provider.id === "azure") {
    const response = await call(provider.name,
      `https://${azureRegion(config)}.tts.speech.microsoft.com/cognitiveservices/voices/list`, {
        headers: { "Ocp-Apim-Subscription-Key": key },
      }, signal);
    const data = await response.json().catch(() => null) as
      { ShortName?: unknown; DisplayName?: unknown; LocaleName?: unknown; Locale?: unknown }[] | null;
    // Companion nói tiếng Anh; giữ thêm tiếng Việt, Nhật cho ai muốn thử. Danh sách đầy đủ tới vài trăm giọng.
    return (Array.isArray(data) ? data : [])
      .filter((item) => typeof item.ShortName === "string" && /^(en|vi|ja)-/.test(String(item.Locale ?? "")))
      .map((item) => ({ id: item.ShortName as string, label: `${item.DisplayName ?? item.ShortName} · ${item.LocaleName ?? item.Locale}` }));
  }
  return null;
}
