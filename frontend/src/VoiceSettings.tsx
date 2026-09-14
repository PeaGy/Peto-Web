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

          {voice.status === "ready" && voice.voices.length > 0 && (
            <div className="theme-options voice-options" role="radiogroup" aria-label="Giọng của Peto">
              {voice.voices.map((name) => (
                <label key={name} className={voice.voice === name ? "theme-option selected" : "theme-option"}>
                  <input
                    type="radio"
                    name="peto-voice"
                    value={name}
                    checked={voice.voice === name}
                    onChange={() => voice.setVoice(name)}
                  />
                  <strong>{VOICE_LABELS[name] ?? name}</strong>
                </label>
              ))}
            </div>
          )}

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
