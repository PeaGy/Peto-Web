import { useEffect, useId, useState } from "react";
import { browserSpeechSupported } from "./browserSpeech";
import {
  getHearingState,
  setHearingSetting,
  setHearingTestSink,
  startListening,
  stopListening,
  useHearing,
  type HearingSource,
} from "./hearingEngine";
import { thresholdLevel } from "./hearingAudio";
import { LevelBars, MicrophoneSelect, phaseTitle, useMicrophones } from "./HearingControls";
import {
  HEARING_PROVIDERS,
  hearingKeyReady,
  sttModelOf,
  type HearingLanguage,
  type HearingProvider,
} from "./hearingProviders";
import { updateKeyConfig, useKeyConfigs, type KeyConfig } from "./voiceProviders";
import { Field, SourceCard, type Card } from "./voiceUi";

/** Trình duyệt đang dùng gửi âm thanh đi đâu để chép lời (chỉ để nói rõ với người dùng). */
function browserNote(): string {
  const agent = navigator.userAgent;
  if (/Edg\//.test(agent)) return "Trình duyệt này là Microsoft Edge: nó gửi âm thanh tới Microsoft để chép lời.";
  if (/Chrome\//.test(agent)) return "Trình duyệt này là Chrome: nó gửi âm thanh tới Google để chép lời.";
  if (/Safari\//.test(agent)) return "Trình duyệt này là Safari: nó chép lời ngay trên máy khi có gói ngôn ngữ.";
  return "Chrome và Edge gửi âm thanh tới Google hay Microsoft để chép lời; Safari chép ngay trên máy.";
}

/**
 * Thẻ "Peto nghe" trong Cài đặt → Giọng nói (phương án A chủ web chọn ngày 2026-09-24): micro, ngôn ngữ, nguồn chép
 * lời bằng thẻ như phần Peto nói, khung Nghe thử và hai công tắc. Khóa dùng chung với phần Peto nói.
 */
export default function HearingSettings({ open }: { open: boolean }) {
  const hearing = useHearing();
  const keys = useKeyConfigs();
  const microphones = useMicrophones(open);
  const [results, setResults] = useState<string[]>([]);
  const micId = useId();
  const languageId = useId();
  const sensitivityId = useId();
  const supported = browserSpeechSupported();

  useEffect(() => {
    setHearingTestSink({ onFinal: (text) => setResults((previous) => [text, ...previous].slice(0, 5)) });
    return () => {
      setHearingTestSink(null);
      if (getHearingState().testing) stopListening();
    };
  }, []);

  // Đóng Cài đặt thì thôi nghe thử.
  useEffect(() => {
    if (!open && getHearingState().testing) stopListening();
  }, [open]);

  const provider = HEARING_PROVIDERS.find((item) => item.id === hearing.source);
  const ready = provider ? hearingKeyReady(provider, keys[provider.id]) : supported;
  const testing = hearing.listening && hearing.testing;

  function pick(source: HearingSource) {
    if (source === hearing.source) return;
    setResults([]);
    setHearingSetting("source", source);
  }

  function toggleTest() {
    if (testing) {
      stopListening();
      return;
    }
    setResults([]);
    void startListening("test");
  }

  const browserCard: Card = {
    id: "browser",
    name: "Có sẵn trong trình duyệt",
    desc: "Chrome, Edge, Safari · chưa có trên Firefox",
    badges: [["Miễn phí", "free"], ["Chữ hiện ngay lúc nói", "neutral"]],
    status: supported ? { text: "Dùng được ở đây", on: true } : { text: "Trình duyệt này chưa có", on: false },
    locked: !supported,
  };
  const keyCards: Card[] = HEARING_PROVIDERS.map((item) => ({
    id: item.id,
    name: item.name,
    desc: item.desc,
    badges: item.free ? [["Gọi thẳng", "neutral"], ["Có gói miễn phí", "free"]] : [["Gọi thẳng", "neutral"]],
    status: hearingKeyReady(item, keys[item.id]) ? { text: item.keyOptional ? "Đã lưu" : "Đã có khóa", on: true } : undefined,
  }));
  const cards = (list: Card[]) => list.flatMap((card) => {
    const selected = card.id === hearing.source;
    const button = <SourceCard key={card.id} card={card} selected={selected} onPick={() => pick(card.id as HearingSource)} />;
    if (!selected) return [button];
    const item = HEARING_PROVIDERS.find((entry) => entry.id === card.id);
    return [button, (
      <div className="voice-detail" role="group" aria-label={card.name} key={`${card.id}-detail`}>
        <strong className="voice-detail-title">{card.name}</strong>
        {item ? <KeyDetail provider={item} config={keys[item.id]} /> : (
          <>
            <p className="voice-line">
              <i className={supported ? "voice-dot on" : "voice-dot"} />
              {supported
                ? "Trình duyệt này nghe được."
                : "Trình duyệt này chưa có tính năng nghe. Dùng Chrome, Edge hoặc Safari, hoặc chọn một nguồn dùng khóa."}
            </p>
            {supported && <p className="voice-note">{browserNote()}</p>}
            <p className="voice-note">Không tốn tiền, không cần khóa. Nguồn này luôn nghe bằng micro mặc định của máy.</p>
          </>
        )}
      </div>
    )];
  });

  return (
    <>
      <p className="settings-hint">
        Peto nghe bạn nói trong Companion. Âm thanh chỉ đi tới nguồn bạn chọn bên dưới; máy chủ Peto không nhận và không lưu.
      </p>

      <div className="hearing-fields">
        <div className="voice-field">
          <label htmlFor={micId}>Micro</label>
          <MicrophoneSelect id={micId} microphones={microphones} />
        </div>
        <div className="voice-field">
          <label htmlFor={languageId}>Bạn nói bằng</label>
          <select id={languageId} value={hearing.language} onChange={(event) => setHearingSetting("language", event.target.value as HearingLanguage)}>
            <option value="en">Tiếng Anh</option>
            <option value="vi">Tiếng Việt</option>
          </select>
        </div>
      </div>

      <div className="voice-group"><strong>Không cần khóa</strong></div>
      <div className="voice-cards hearing-free">{cards([browserCard])}</div>

      <div className="voice-group">
        <strong>Khóa của bạn</strong>
        <span>Dùng chung khóa đã nhập ở phần Peto nói</span>
      </div>
      <div className="voice-cards">{cards(keyCards)}</div>

      <section className="hearing-test" aria-labelledby="hearing-test-title">
        <div className="hearing-test-head">
          <strong id="hearing-test-title">Nghe thử</strong>
          <button type="button" className="voice-primary" onClick={toggleTest} disabled={!ready && !testing}>
            {testing ? "Dừng nghe thử" : "Bắt đầu nghe thử"}
          </button>
        </div>
        <p className="voice-note">Nói vài câu để xem Peto nghe ra chữ gì. Nghe thử không gửi gì cho Peto.</p>
        {testing && <p className="voice-line" role="status">{phaseTitle(hearing)}</p>}
        {hearing.message && !hearing.listening && <p className="voice-error" role="alert">{hearing.message}</p>}
        <div className="hearing-meter">
          <span>Âm lượng</span>
          <LevelBars count={36} className="hearing-meter-levels" threshold={provider ? thresholdLevel(hearing.sensitivity) : undefined} />
        </div>
        {provider ? (
          <div className="voice-field">
            <div className="hearing-range-label">
              <label htmlFor={sensitivityId}>Độ nhạy</label>
              <span>{hearing.sensitivity < 35 ? "Ít nhạy" : hearing.sensitivity > 65 ? "Rất nhạy" : "Vừa"}</span>
            </div>
            <input
              id={sensitivityId}
              type="range"
              min="0"
              max="100"
              value={hearing.sensitivity}
              onChange={(event) => setHearingSetting("sensitivity", Number(event.target.value))}
            />
            <small>Vạch trắng là ngưỡng coi như im lặng. Phòng ồn thì giảm, nói nhỏ mà Peto không nghe thì tăng.</small>
          </div>
        ) : (
          <p className="voice-note">Nguồn trong trình duyệt tự nhận ra lúc bạn nói xong nên không cần chỉnh độ nhạy.</p>
        )}
        {(results.length > 0 || (testing && hearing.interim)) && (
          <ul className="hearing-results">
            {testing && hearing.interim && <li className="interim">{hearing.interim}</li>}
            {results.map((text, index) => <li key={`${index}-${text}`}>“{text}”</li>)}
          </ul>
        )}
      </section>

      <div className="character-effect-options hearing-options">
        <label className="character-effect-option">
          <span>
            <strong>Tự gửi khi nói xong</strong>
            <small>Im lặng khoảng một giây thì gửi luôn. Tắt thì chữ nằm trong ô nhắn để bạn sửa trước.</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            checked={hearing.autoSend}
            onChange={(event) => setHearingSetting("autoSend", event.target.checked)}
          />
        </label>
        <label className="character-effect-option">
          <span>
            <strong>Tạm không nghe khi Peto đang nói</strong>
            <small>Để Peto khỏi tự nghe giọng mình qua loa. Đeo tai nghe thì có thể tắt để nói chen ngang.</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            checked={hearing.pauseWhileSpeaking}
            onChange={(event) => setHearingSetting("pauseWhileSpeaking", event.target.checked)}
          />
        </label>
      </div>
    </>
  );
}

function KeyDetail({ provider, config }: { provider: HearingProvider; config: KeyConfig | undefined }) {
  const ids = { url: useId(), key: useId(), region: useId(), model: useId() };
  const current = config ?? {};
  const update = (patch: KeyConfig) => updateKeyConfig(provider.id, { ...current, ...patch });
  const saved = Object.values(current).some((value) => typeof value === "string" && value.trim());
  const model = sttModelOf(provider, config);
  const shared = provider.sharedWithMouth ? " Khóa này dùng chung với phần Peto nói." : "";
  return (
    <>
      {provider.needsBaseUrl && (
        <Field id={ids.url} label="Địa chỉ máy chủ" hint="Địa chỉ gốc của API, trước /audio/transcriptions.">
          <input
            id={ids.url} type="url" inputMode="url" placeholder="https://…/v1" spellCheck={false} autoComplete="off"
            value={current.baseUrl ?? ""} onChange={(event) => update({ baseUrl: event.target.value })}
          />
        </Field>
      )}
      <Field
        id={ids.key}
        label={provider.keyOptional ? "Khóa API (nếu máy chủ cần)" : `Khóa API ${provider.name}`}
        hint={(
          <span className="voice-key-hint">
            <span>{provider.keyOptional ? "Để trống nếu máy chủ không cần khóa." : `Lấy khóa ở ${provider.site}.`}{shared}</span>
            {saved && (
              <button type="button" className="voice-link" onClick={() => updateKeyConfig(provider.id, null)}>
                Xóa khóa khỏi trình duyệt
              </button>
            )}
          </span>
        )}
      >
        <input
          id={ids.key} type="password" placeholder={provider.keyHint} spellCheck={false} autoComplete="off"
          value={current.key ?? ""} onChange={(event) => update({ key: event.target.value })}
        />
      </Field>
      {provider.needsRegion && (
        <Field id={ids.region} label="Vùng" hint="Vùng của tài nguyên Speech trên Azure, ví dụ southeastasia.">
          <input
            id={ids.region} type="text" placeholder="southeastasia" spellCheck={false} autoComplete="off"
            value={current.region ?? ""} onChange={(event) => update({ region: event.target.value })}
          />
        </Field>
      )}
      {provider.modelFree ? (
        <Field id={ids.model} label="Model">
          <input
            id={ids.model} type="text" placeholder={sttModelOf(provider, undefined)} spellCheck={false} autoComplete="off"
            value={current.sttModel ?? ""} onChange={(event) => update({ sttModel: event.target.value })}
          />
        </Field>
      ) : (provider.models?.length ?? 0) > 1 && (
        <Field id={ids.model} label="Model">
          <select id={ids.model} value={model} onChange={(event) => update({ sttModel: event.target.value })}>
            {provider.models!.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </Field>
      )}
      <p className="voice-note">
        Khóa và âm thanh đi thẳng từ trình duyệt tới {provider.name}; máy chủ Peto không nhận.
        {provider.free ? " Gói miễn phí giới hạn số lần gọi mỗi phút." : ""}
      </p>
    </>
  );
}
