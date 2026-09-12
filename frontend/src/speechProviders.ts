/**
 * Các dịch vụ đọc chữ thành tiếng, gọi thẳng từ trình duyệt.
 *
 * Khóa API là của chính người dùng, nằm trong trình duyệt của họ và không bao
 * giờ đi qua máy chủ Peto — ai muốn nghe thì tự trả tiền, và nguyên tắc "không
 * để khóa của máy chủ xuống trình duyệt" vẫn nguyên.
 *
 * Đã thử thật: cả ElevenLabs, OpenAI, Azure và Google đều cho gọi từ trình
 * duyệt (không bị CORS chặn), nên không cần backend chuyển tiếp.
 */

export interface CloudConfig {
  key: string;
  voice: string;
  model: string;
}

export interface CloudProvider {
  id: string;
  label: string;
  defaultVoice: string;
  defaultModel: string;
  /** Chỉ đường lấy khóa, hiện ngay dưới ô nhập. */
  keyHint: string;
  /** Danh sách giọng cố định, cho dịch vụ không có API liệt kê giọng. */
  voices?: { id: string; name: string }[];
  /** Lấy danh sách giọng của tài khoản; không hỗ trợ thì bỏ trống. */
  listVoices?: (key: string, signal: AbortSignal) => Promise<{ id: string; name: string }[]>;
  synthesize: (text: string, config: CloudConfig, signal: AbortSignal) => Promise<ArrayBuffer>;
}

function explain(status: number, label: string, detail: string): string {
  const why = detail ? ` Dịch vụ nói: ${detail}` : "";
  // Google trả 400 cho khóa sai chứ không phải 401, nên đừng chỉ nhìn mã số:
  // nội dung lỗi mới nói đúng chuyện gì đang xảy ra.
  const aboutKey = /api[ _-]?key|unauthorized|authentication|credential/i.test(detail);
  if (status === 401 || status === 403 || aboutKey) {
    return `${label} không nhận khóa API. Xem lại khóa trong Cài đặt nhé.${why}`;
  }
  // 429 của OpenAI phần lớn là hết hạn mức chứ không phải gọi nhanh, nên câu giải
  // thích của chính họ quan trọng hơn câu đoán của mình.
  if (status === 429) return `${label} từ chối: hết hạn mức hoặc gọi quá nhanh.${why}`;
  if (status === 400 || status === 404) return `${label} từ chối yêu cầu: xem lại mã giọng và model trong Cài đặt.${why}`;
  if (status >= 500) return `${label} đang trục trặc phía họ. Thử lại sau nhé.${why}`;
  return `${label} trả về lỗi ${status}.${why}`;
}

/** Lấy câu giải thích của chính dịch vụ, mỗi bên nhét vào một chỗ khác nhau. */
async function detailOf(response: Response): Promise<string> {
  try {
    const text = (await response.text()).trim();
    if (!text) return "";
    try {
      const body = JSON.parse(text) as {
        error?: { message?: string };
        detail?: { message?: string } | string;
        message?: string;
      };
      const detail = typeof body.detail === "string" ? body.detail : body.detail?.message;
      return (body.error?.message ?? detail ?? body.message ?? text).slice(0, 200);
    } catch {
      return text.slice(0, 200);
    }
  } catch {
    return "";
  }
}

async function audioFrom(response: Response, label: string): Promise<ArrayBuffer> {
  if (!response.ok) throw new Error(explain(response.status, label, await detailOf(response)));
  return response.arrayBuffer();
}

const elevenlabs: CloudProvider = {
  id: "elevenlabs",
  label: "ElevenLabs",
  // Rachel, giọng mẫu có sẵn trong mọi tài khoản; đổi được ở ô chọn giọng.
  defaultVoice: "21m00Tcm4TlvDq8ikWAM",
  // Flash v2.5 nhanh và rẻ nhất, đủ nhiều thứ tiếng.
  defaultModel: "eleven_flash_v2_5",
  keyHint: "Lấy ở elevenlabs.io, mục Profile → API Keys.",
  async listVoices(key, signal) {
    const response = await fetch("https://api.elevenlabs.io/v1/voices", {
      headers: { "xi-api-key": key },
      signal,
    });
    if (!response.ok) throw new Error(explain(response.status, "ElevenLabs", await detailOf(response)));
    const body = (await response.json()) as { voices?: { voice_id: string; name: string }[] };
    return (body.voices ?? []).map((item) => ({ id: item.voice_id, name: item.name }));
  },
  async synthesize(text, config, signal) {
    const url = `https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(config.voice)}?output_format=mp3_44100_128`;
    const response = await fetch(url, {
      method: "POST",
      signal,
      headers: { "xi-api-key": config.key, "Content-Type": "application/json" },
      body: JSON.stringify({ text, model_id: config.model }),
    });
    return audioFrom(response, "ElevenLabs");
  },
};

const openai: CloudProvider = {
  id: "openai",
  label: "OpenAI",
  defaultVoice: "alloy",
  defaultModel: "gpt-4o-mini-tts",
  keyHint: "Lấy ở platform.openai.com, mục API keys.",
  async synthesize(text, config, signal) {
    const response = await fetch("https://api.openai.com/v1/audio/speech", {
      method: "POST",
      signal,
      headers: { Authorization: `Bearer ${config.key}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: config.model,
        voice: config.voice,
        input: text,
        response_format: "mp3",
      }),
    });
    return audioFrom(response, "OpenAI");
  },
};

/** Base64 về mảng byte; Gemini trả âm thanh dạng này. */
function bytesFromBase64(value: string): Uint8Array {
  const binary = atob(value);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

/**
 * Bọc PCM thô thành WAV.
 *
 * Gemini trả PCM 16-bit mono chứ không phải mp3, mà decodeAudioData của trình
 * duyệt không nhận PCM trần — thiếu đúng 44 byte tiêu đề này là không phát được.
 */
function wavFromPcm(pcm: Uint8Array, rate: number): ArrayBuffer {
  const out = new Uint8Array(44 + pcm.length);
  const view = new DataView(out.buffer);
  const write = (at: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(at + i, text.charCodeAt(i));
  };
  write(0, "RIFF");
  view.setUint32(4, 36 + pcm.length, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, pcm.length, true);
  out.set(pcm, 44);
  return out.buffer;
}

const gemini: CloudProvider = {
  id: "gemini",
  label: "Gemini (Google AI Studio)",
  defaultVoice: "Kore",
  defaultModel: "gemini-2.5-flash-preview-tts",
  keyHint: "Lấy miễn phí ở aistudio.google.com, mục API keys — không cần thẻ.",
  voices: [
    { id: "Kore", name: "Kore — nữ, chắc giọng" },
    { id: "Aoede", name: "Aoede — nữ, nhẹ nhàng" },
    { id: "Leda", name: "Leda — nữ, trẻ" },
    { id: "Zephyr", name: "Zephyr — nữ, sáng" },
    { id: "Puck", name: "Puck — nam, tươi" },
    { id: "Charon", name: "Charon — nam, trầm" },
    { id: "Fenrir", name: "Fenrir — nam, mạnh" },
    { id: "Enceladus", name: "Enceladus — nam, thì thầm" },
  ],
  async synthesize(text, config, signal) {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(config.model)}:generateContent`;
    const response = await fetch(url, {
      method: "POST",
      signal,
      // Khóa đi bằng header chứ không nhét vào đường dẫn, cho khỏi lọt vào log.
      headers: { "x-goog-api-key": config.key, "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text }] }],
        generationConfig: {
          responseModalities: ["AUDIO"],
          speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: config.voice } } },
        },
      }),
    });
    if (!response.ok) throw new Error(explain(response.status, "Gemini", await detailOf(response)));

    const body = (await response.json()) as {
      candidates?: { content?: { parts?: { inlineData?: { data?: string; mimeType?: string } }[] } }[];
      output_audio?: { data?: string; mime_type?: string };
    };
    const part = body.candidates?.[0]?.content?.parts?.find((item) => item.inlineData?.data)?.inlineData;
    const data = part?.data ?? body.output_audio?.data;
    if (!data) throw new Error("Gemini không trả về âm thanh nào. Thử đổi model trong Cài đặt nhé.");
    const mime = part?.mimeType ?? body.output_audio?.mime_type ?? "";
    const rate = Number(/rate=(\d+)/.exec(mime)?.[1] ?? 24000);
    return wavFromPcm(bytesFromBase64(data), rate);
  },
};

export const CLOUD_PROVIDERS: Record<string, CloudProvider> = { gemini, elevenlabs, openai };

export function providerById(id: string): CloudProvider | undefined {
  return CLOUD_PROVIDERS[id];
}

export function defaultConfig(provider: CloudProvider): CloudConfig {
  return { key: "", voice: provider.defaultVoice, model: provider.defaultModel };
}
