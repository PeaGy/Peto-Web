import { useEffect, useState } from "react";
import { SpeechQueue, listVoices, speechSupported, type VoiceSettings as VoicePrefs } from "./speech";
import { CLOUD_PROVIDERS, defaultConfig, providerById, type CloudConfig } from "./speechProviders";

const SAMPLE = "Chào cậu, Peto đây. Nghe rõ không?";

/**
 * Mục Giọng nói trong Cài đặt.
 *
 * Hai nguồn giọng: giọng có sẵn trong máy (miễn phí) hoặc một dịch vụ trả tiền
 * do chính người dùng cắm khóa. Khóa nằm trong trình duyệt của họ và không gửi
 * lên máy chủ Peto, nên phải nói rõ điều đó ngay cạnh ô nhập.
 *
 * Nhãn gắn bằng htmlFor chứ không bọc ô nhập, cùng lý do đã ghi ở ProfileSettings.
 */
export default function VoiceSettings({ value, onChange, chars, onChars }: {
  value: VoicePrefs;
  onChange: (next: VoicePrefs) => void;
  /** Số ký tự đã gửi cho dịch vụ trả tiền trong phiên này. */
  chars: number;
  /** Nghe thử cũng tốn tiền, nên cũng phải cộng vào bộ đếm. */
  onChars: (added: number) => void;
}) {
  const supported = speechSupported();
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>(listVoices);
  const [cloudVoices, setCloudVoices] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const provider = providerById(value.provider);
  const config: CloudConfig | null = provider
    ? value.cloud[provider.id] ?? defaultConfig(provider)
    : null;

  useEffect(() => {
    if (!supported) return;
    // Giữ tham chiếu ngay tại đây: lúc dọn dẹp mà đọc lại biến toàn cục thì gặp
    // đúng cảnh nó không còn nữa (jsdom trong test là một ví dụ).
    const synth = window.speechSynthesis;
    const refresh = () => setVoices(listVoices());
    refresh();
    synth.addEventListener("voiceschanged", refresh);
    return () => synth.removeEventListener("voiceschanged", refresh);
  }, [supported]);

  const providerId = provider?.id;
  const key = config?.key ?? "";
  const region = config?.region ?? "";
  useEffect(() => {
    const fetchVoices = providerId ? CLOUD_PROVIDERS[providerId]?.listVoices : undefined;
    if (!fetchVoices || !key) {
      setCloudVoices([]);
      return;
    }
    const controller = new AbortController();
    fetchVoices({ key, voice: "", model: "", region }, controller.signal)
      .then(setCloudVoices)
      // Khóa sai hay mạng hỏng thì thôi, để người dùng tự gõ mã giọng.
      .catch(() => setCloudVoices([]));
    return () => controller.abort();
  }, [providerId, key, region]);

  // Giọng lấy được từ tài khoản thì ưu tiên; không có thì dùng danh sách cố định
  // của dịch vụ; không có nữa thì để người dùng tự gõ mã giọng.
  const voiceOptions = cloudVoices.length > 0 ? cloudVoices : provider?.voices ?? [];

  function setCloud(patch: Partial<CloudConfig>) {
    if (!provider || !config) return;
    onChange({ ...value, cloud: { ...value.cloud, [provider.id]: { ...config, ...patch } } });
  }

  function playSample() {
    setError(null);
    const queue = new SpeechQueue(() => ({ ...value, on: true }), { onError: setError, onChars });
    queue.cancel();
    queue.push(SAMPLE);
    queue.flush();
  }

  return (
    <section className="settings-section" aria-labelledby="voice-title">
      <h3 id="voice-title">Giọng nói</h3>
      <p className="settings-hint">
        Peto đọc câu trả lời thành tiếng. Giọng trong máy thì miễn phí; dịch vụ trả tiền
        nghe tự nhiên và liền mạch hơn, nhưng bạn tự cắm khóa và tự trả tiền.
      </p>

      <div className="voice-form">
        <div className="voice-row voice-check">
          <input
            id="voice-on"
            type="checkbox"
            checked={value.on}
            onChange={(event) => onChange({ ...value, on: event.target.checked })}
          />
          <label htmlFor="voice-on">Đọc câu trả lời của Peto</label>
        </div>

        <div className="voice-row">
          <label htmlFor="voice-provider">Nguồn giọng</label>
          <select
            id="voice-provider"
            value={value.provider}
            onChange={(event) => onChange({ ...value, provider: event.target.value })}
          >
            <option value="browser">Giọng trong máy (miễn phí)</option>
            {Object.values(CLOUD_PROVIDERS).map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
        </div>

        {!provider ? (
          !supported ? (
            <p className="settings-hint" role="status">Trình duyệt này chưa đọc thành tiếng được.</p>
          ) : (
            <>
              <div className="voice-row">
                <label htmlFor="voice-pick">Giọng</label>
                <select
                  id="voice-pick"
                  value={value.voiceURI}
                  onChange={(event) => onChange({ ...value, voiceURI: event.target.value })}
                >
                  <option value="">Giọng mặc định của máy</option>
                  {voices.map((item) => (
                    <option key={item.voiceURI} value={item.voiceURI}>{item.name} — {item.lang}</option>
                  ))}
                </select>
              </div>

              <div className="voice-row">
                <label htmlFor="voice-rate">Tốc độ</label>
                <input
                  id="voice-rate"
                  type="range"
                  min={0.5}
                  max={2}
                  step={0.1}
                  value={value.rate}
                  onChange={(event) => onChange({ ...value, rate: Number(event.target.value) })}
                />
                <span className="voice-rate">{value.rate.toFixed(1)}×</span>
              </div>
            </>
          )
        ) : (
          <>
            <div className="voice-row">
              <label htmlFor="voice-key">Khóa API</label>
              <input
                id="voice-key"
                type="password"
                autoComplete="off"
                value={config?.key ?? ""}
                onChange={(event) => setCloud({ key: event.target.value })}
              />
            </div>
            <p className="settings-hint">
              {provider.keyHint} Khóa chỉ nằm trong trình duyệt này, không gửi lên máy chủ Peto.
            </p>

            {provider.needsRegion && (
              <div className="voice-row">
                <label htmlFor="voice-region">Vùng</label>
                <input
                  id="voice-region"
                  value={config?.region ?? ""}
                  onChange={(event) => setCloud({ region: event.target.value })}
                />
              </div>
            )}

            <div className="voice-row">
              <label htmlFor="voice-cloud-voice">Giọng</label>
              {voiceOptions.length > 0 ? (
                <select
                  id="voice-cloud-voice"
                  value={config?.voice ?? ""}
                  onChange={(event) => setCloud({ voice: event.target.value })}
                >
                  {voiceOptions.map((item) => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              ) : (
                <input
                  id="voice-cloud-voice"
                  value={config?.voice ?? ""}
                  onChange={(event) => setCloud({ voice: event.target.value })}
                />
              )}
            </div>

            {provider.defaultModel !== "" && (
              <div className="voice-row">
                <label htmlFor="voice-model">Model</label>
                <input
                  id="voice-model"
                  value={config?.model ?? ""}
                  onChange={(event) => setCloud({ model: event.target.value })}
                />
              </div>
            )}

            {provider.oneShot && (
              <p className="settings-hint">
                Gói miễn phí của {provider.label} siết số lượt gọi mỗi phút, nên Peto đọc sau
                khi trả lời xong thay vì đọc dần từng câu.
              </p>
            )}

            {chars > 0 && (
              <p className="settings-hint">
                Phiên này đã gửi {chars.toLocaleString("vi-VN")} ký tự cho {provider.label}.
              </p>
            )}
          </>
        )}

        <button type="button" className="voice-test" onClick={playSample}>Nghe thử</button>
        {error && <p className="settings-hint voice-error" role="alert">{error}</p>}
      </div>
    </section>
  );
}
