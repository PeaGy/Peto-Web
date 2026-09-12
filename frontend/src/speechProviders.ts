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
  /** Lấy danh sách giọng của tài khoản; không hỗ trợ thì bỏ trống. */
  listVoices?: (key: string, signal: AbortSignal) => Promise<{ id: string; name: string }[]>;
  synthesize: (text: string, config: CloudConfig, signal: AbortSignal) => Promise<ArrayBuffer>;
}

function explain(status: number, label: string): string {
  if (status === 401 || status === 403) return `${label} không nhận khóa API. Xem lại khóa trong Cài đặt nhé.`;
  if (status === 429) return `${label} báo gọi quá nhanh hoặc hết lượt. Chờ chút rồi thử lại.`;
  if (status === 400 || status === 404) return `${label} không nhận mã giọng hoặc model đang chọn.`;
  if (status >= 500) return `${label} đang trục trặc phía họ. Thử lại sau nhé.`;
  return `${label} trả về lỗi ${status}.`;
}

async function audioFrom(response: Response, label: string): Promise<ArrayBuffer> {
  if (!response.ok) throw new Error(explain(response.status, label));
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
    if (!response.ok) throw new Error(explain(response.status, "ElevenLabs"));
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

export const CLOUD_PROVIDERS: Record<string, CloudProvider> = { elevenlabs, openai };

export function providerById(id: string): CloudProvider | undefined {
  return CLOUD_PROVIDERS[id];
}

export function defaultConfig(provider: CloudProvider): CloudConfig {
  return { key: "", voice: provider.defaultVoice, model: provider.defaultModel };
}
