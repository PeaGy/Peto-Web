import { useEffect, useState } from "react";
import { SpeechQueue, listVoices, speechSupported, type VoiceSettings as VoicePrefs } from "./speech";

const SAMPLE = "Chào cậu, Peto đây. Nghe rõ không?";

/**
 * Mục Giọng nói trong Cài đặt: bật tắt, chọn giọng của máy, chỉnh tốc độ.
 *
 * Danh sách giọng do hệ điều hành cấp và thường về trễ một nhịp sau khi trang mở,
 * nên phải nghe sự kiện voiceschanged chứ không đọc một lần rồi thôi.
 *
 * Nhãn gắn bằng htmlFor chứ không bọc ô nhập, cùng lý do đã ghi ở ProfileSettings.
 */
export default function VoiceSettings({ value, onChange }: {
  value: VoicePrefs;
  onChange: (next: VoicePrefs) => void;
}) {
  const supported = speechSupported();
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>(listVoices);

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

  function playSample() {
    const queue = new SpeechQueue(() => ({ ...value, on: true }));
    queue.cancel();
    queue.push(SAMPLE);
    queue.flush();
  }

  return (
    <section className="settings-section" aria-labelledby="voice-title">
      <h3 id="voice-title">Giọng nói</h3>
      <p className="settings-hint">
        Peto đọc câu trả lời bằng giọng có sẵn trong máy bạn: không tốn tiền, nhưng mỗi máy
        một giọng. Gặp khối mã thì Peto bỏ qua, chỉ nói là có mã.
      </p>
      {!supported ? (
        <p className="settings-hint" role="status">Trình duyệt này chưa đọc thành tiếng được.</p>
      ) : (
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

          <button type="button" className="voice-test" onClick={playSample}>Nghe thử</button>
        </div>
      )}
    </section>
  );
}
