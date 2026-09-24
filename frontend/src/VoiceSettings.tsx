import { VOICE_FALLBACK_KEY } from "./localSpeech";
import { useEffect, useState } from "react";
import { VOICE_LABELS, type LocalVoice, type LocalVoiceStatus } from "./LocalVoice";

/** Giọng mẫu chỉ nói tiếng Anh, nên câu nghe thử cũng bằng tiếng Anh. */
const SAMPLE_TEXT = "Hi, it's Peto! This is how I sound when we talk in Companion.";
const SAMPLE_KEY = "voice-sample";

const STATUS_TEXT: Record<Exclude<LocalVoiceStatus, "off">, string> = {
  checking: "Đang kiểm tra giọng nói Peto…",
  ready: "Giọng nói đã sẵn sàng: Peto sẽ nói khi trả lời xong trong Companion.",
  missing: "Giọng nói Peto đang ngoại tuyến. Bạn vẫn có thể chat chữ và thử lại sau.",
};

/**
 * Mục Giọng nói trong Cài đặt: bật hay tắt giọng nói trên máy này, xem máy chủ đã chạy chưa, chọn và
 * nghe thử giọng. Nút tắt tiếng không nằm ở đây mà ở cột chat của Companion, vì đó là thao tác lúc
 * đang trò chuyện.
 */
export default function VoiceSettings({ voice, open }: { voice: LocalVoice; open: boolean }) {
  const [error, setError] = useState<string | null>(null);
  const { speaking, stop } = voice;
  const [fallback, setFallback] = useState(() => { try { return localStorage.getItem(VOICE_FALLBACK_KEY) || ''; } catch { return ''; } });
  const providerOf = (name: string) => name.includes(':') ? name.split(':')[0] : 'local';
  const providerNames: Record<string, string> = { local: 'Qwen local', openai: 'OpenAI', qwen: 'Qwen Cloud' };
  const provider = providerOf(voice.voice);
  const providers = [...new Set([...voice.voices, ...(voice.voice ? [voice.voice] : [])].map(providerOf))];
  const label = (name: string) => VOICE_LABELS[name] ?? (name.includes(':') ? name.split(':').slice(1).join(':') : name);
  const changeFallback = (next: string) => { stop(); setFallback(next); try { localStorage.setItem(VOICE_FALLBACK_KEY, next); } catch {} };
  useEffect(() => {
    if (voice.status === 'ready' && fallback && !voice.voices.includes(fallback)) changeFallback('');
  }, [voice.status, voice.voices, fallback]);
  const sampling = speaking?.key === SAMPLE_KEY ? speaking.phase : null;

  // Đóng Cài đặt thì thôi đọc câu mẫu; tin Companion đang đọc thì để yên.
  useEffect(() => {
    if (!open && sampling) stop();
  }, [open, sampling, stop]);

  function toggle(next: boolean) {
    setError(null);
    voice.setEnabled(next);
  }

  function sample() {
    if (sampling) {
      stop();
      return;
    }
    setError(null);
    voice.speak(SAMPLE_KEY, SAMPLE_TEXT).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Chưa đọc được câu mẫu.");
    });
  }

  return (
    <section className="settings-section" aria-labelledby="voice-settings-title">
      <h3 id="voice-settings-title">Giọng nói</h3>
      <p className="settings-hint">
        Peto có thể nói thành tiếng trong Companion. Khi giọng nói chưa sẵn sàng,
        bạn vẫn nhắn chữ như thường.
      </p>

      {!voice.enabled ? (
        <div className="voice-row">
          <p className="settings-hint">Chọn giọng bạn thích và nghe Peto trả lời.</p>
          <button type="button" className="settings-button" onClick={() => toggle(true)}>
            Bật giọng nói
          </button>
        </div>
      ) : (
        <>
          <div className="voice-row">
            <p className="voice-status" role="status">
              {voice.status === "off" ? "" : STATUS_TEXT[voice.status]}
            </p>
            {voice.status === "missing" && (
              <button type="button" className="settings-button" onClick={voice.recheck}>Kiểm tra lại</button>
            )}
          </div>

          {voice.status === 'ready' && voice.voices.length > 0 && <div className="voice-provider-options">
            <label>Nguồn giọng<select value={provider} onChange={e => { stop(); changeFallback(''); voice.setVoice(voice.voices.find(name => providerOf(name) === e.target.value)!); }}>
              {providers.map(name => <option key={name} value={name} disabled={!voice.voices.some(item => providerOf(item) === name)}>{providerNames[name] ?? name}</option>)}
            </select></label>
            <label>Giọng<select value={voice.voice} onChange={e => { stop(); voice.setVoice(e.target.value); }}>
              {!voice.voices.includes(voice.voice) && <option value={voice.voice}>{label(voice.voice)} · Chưa sẵn sàng</option>}
              {voice.voices.filter(name => providerOf(name) === provider).map(name => <option key={name} value={name}>{label(name)}</option>)}
            </select></label>
            <label>Khi nguồn chính gặp lỗi<select value={fallback} onChange={e => changeFallback(e.target.value)}>
              <option value="">Không tự đổi giọng</option>
              {voice.voices.filter(name => providerOf(name) !== provider).map(name => <option key={name} value={name}>{providerNames[providerOf(name)]} · {label(name)}</option>)}
            </select></label>
            <p className="settings-hint">Giọng nói do AI tạo. Chuyển nguồn dự phòng có thể đổi chất giọng và sử dụng ngân sách của nguồn đó.</p>
          </div>}
          {voice.notice && <p role="status">{voice.notice}</p>}
          {error && <p className="voice-error" role="alert">{error}</p>}

          <div className="settings-actions voice-actions">
            {voice.status === "ready" && (
              <button type="button" className="settings-button" onClick={sample}>
                {sampling === "loading" ? "Đang chuẩn bị…" : sampling === "playing" ? "Dừng nghe thử" : "Nghe thử"}
              </button>
            )}
            <button type="button" className="settings-button" onClick={() => toggle(false)}>
              Tắt giọng nói
            </button>
          </div>
        </>
      )}
    </section>
  );
}
