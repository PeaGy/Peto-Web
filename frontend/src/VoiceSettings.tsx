import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { VOICE_LABELS, voiceLabel, type FallbackChoice, type LocalVoice, type VoiceSourceId } from "./LocalVoice";
import {
  KEY_PROVIDERS,
  keyReady,
  listKeyVoices,
  modelOf,
  voiceOf,
  type KeyConfig,
  type KeyProvider,
  type VoiceOption,
} from "./voiceProviders";

/** Giọng nào cũng nói tiếng Anh tốt nhất, nên câu nghe thử mặc định bằng tiếng Anh. */
const SAMPLE_TEXT = "Hi! I'm Peto. Nice to see you again.";
const SAMPLE_KEY = "voice-sample";
/** Một câu trả lời ngắn của Companion dài chừng này ký tự; chỉ để ước lượng số câu còn lại. */
const SHORT_REPLY_CHARS = 120;

const CLOUD_NAMES: Record<string, string> = { stepfun: "StepFun", openai: "OpenAI", qwen: "Qwen" };
const RELAY_REASON: Partial<Record<KeyProvider["id"], string>> = {
  stepfun: "StepFun không cho trình duyệt gọi thẳng",
  qwen: "Qwen Cloud trả âm thanh ở một địa chỉ trình duyệt không tải được",
};

type Tone = "neutral" | "official" | "free" | "relay";

interface Card {
  id: VoiceSourceId;
  name: string;
  desc: string;
  badges: [string, Tone][];
  status?: { text: string; on: boolean };
  locked?: boolean;
}

/**
 * Mục Giọng nói trong Cài đặt (phương án A chủ web chọn ngày 2026-09-24): bật tắt, rồi chọn nguồn giọng bằng thẻ.
 * "Không cần khóa" là Giọng Peto (khóa của chủ web, lượt miễn phí mỗi tháng) và Máy nhà của Peto; "Khóa của bạn" là
 * các nhà cung cấp dùng khóa riêng, lưu trên trình duyệt này. Khung chi tiết nằm ngay sau thẻ đang chọn, nên trên
 * điện thoại nó hiện ngay dưới thẻ. Nút tắt tiếng không ở đây mà ở cột chat của Companion.
 */
export default function VoiceSettings({ voice, open }: { voice: LocalVoice; open: boolean }) {
  const [error, setError] = useState<string | null>(null);
  const [sampleText, setSampleText] = useState(SAMPLE_TEXT);
  const { speaking, stop, source, health } = voice;
  const sampling = speaking?.key === SAMPLE_KEY ? speaking.phase : null;
  const fallbackId = useId();

  // Đóng Cài đặt thì thôi đọc câu mẫu; tin Companion đang đọc thì để yên.
  useEffect(() => {
    if (!open && sampling) stop();
  }, [open, sampling, stop]);

  useEffect(() => setError(null), [source]);

  function sample() {
    if (sampling) {
      stop();
      return;
    }
    setError(null);
    // Nghe thử chỉ dùng nguồn đang chọn: chuyển sang giọng dự phòng sẽ che mất lỗi của khóa vừa nhập.
    voice.speak(SAMPLE_KEY, sampleText.trim() || SAMPLE_TEXT, { fallback: false }).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Chưa đọc được câu mẫu.");
    });
  }

  const official = health?.official;
  const officialOpen = Boolean(official?.voices.length);
  const officialProviders = [...new Set((official?.voices ?? []).map((name) => CLOUD_NAMES[name.split(":")[0]] ?? name.split(":")[0]))];
  const free: Card[] = [
    {
      id: "official",
      name: "Giọng Peto",
      desc: officialProviders.length ? `Có sẵn, không cần khóa · chạy bằng ${officialProviders.join(", ")}` : "Có sẵn, không cần khóa",
      badges: [["Chính thức", "official"], ["Miễn phí mỗi tháng", "free"]],
      locked: Boolean(health && (!officialOpen || !official?.allowed)),
    },
    {
      id: "home",
      name: "Máy nhà của Peto",
      desc: "Qwen3-TTS chạy trên máy của chủ Peto",
      badges: [["Miễn phí", "free"], ["Khi máy bật", "neutral"]],
      status: health ? { text: health.home.online ? "Đang bật" : "Đang tắt", on: health.home.online } : undefined,
    },
  ];
  const byok: Card[] = KEY_PROVIDERS.map((provider) => ({
    id: provider.id,
    name: provider.name,
    desc: provider.desc,
    badges: [provider.route === "relay" ? ["Qua máy chủ Peto", "relay"] : ["Gọi thẳng", "neutral"]],
    status: keyReady(provider, voice.keys[provider.id])
      ? { text: provider.keyOptional ? "Đã lưu" : "Đã lưu khóa", on: true }
      : undefined,
  }));

  const sampleReady = !voice.problem;
  const detail = (card: Card) => (
    <div className="voice-detail" role="group" aria-label={card.name} key={`${card.id}-detail`}>
      <strong className="voice-detail-title">{card.name}</strong>
      {card.id === "official" ? <OfficialDetail voice={voice} />
        : card.id === "home" ? <HomeDetail voice={voice} />
        : <KeyDetail voice={voice} provider={KEY_PROVIDERS.find((item) => item.id === card.id)!} />}
      {/* Nguồn của máy chủ chưa dùng được thì ở đây không làm gì cho nó nói được; khóa riêng thì nút sáng lên khi nhập đủ. */}
      {(sampleReady || KEY_PROVIDERS.some((item) => item.id === card.id)) && (
        <SampleRow
          text={sampleText}
          onText={setSampleText}
          ready={sampleReady}
          sampling={sampling}
          onSample={sample}
        />
      )}
      {voice.notice && <p className="voice-note" role="status">{voice.notice}</p>}
      {error && <p className="voice-error" role="alert">{error}</p>}
    </div>
  );
  const cards = (list: Card[]) => list.flatMap((card) => {
    const selected = card.id === source;
    const button = (
      <SourceCard key={card.id} card={card} selected={selected} onPick={() => { if (!selected) voice.setSource(card.id); }} />
    );
    return selected ? [button, detail(card)] : [button];
  });

  const offerHome = source !== "home";
  const offerOfficial = source !== "official" && officialOpen && official?.allowed;
  const fallback: FallbackChoice = (voice.fallback === "home" && offerHome) || (voice.fallback === "official" && offerOfficial)
    ? voice.fallback : "";

  return (
    <section className="settings-section" aria-labelledby="voice-settings-title">
      <div className="voice-head">
        <h3 id="voice-settings-title">Giọng nói</h3>
        <label className="voice-switch">
          <span aria-hidden="true">{voice.enabled ? "Đang bật" : "Đang tắt"}</span>
          <input
            type="checkbox"
            role="switch"
            aria-label="Bật giọng nói"
            checked={voice.enabled}
            onChange={(event) => { setError(null); voice.setEnabled(event.target.checked); }}
          />
        </label>
      </div>
      <p className="settings-hint">
        {voice.enabled
          ? "Peto nói thành tiếng trong Companion. Chọn nguồn giọng bên dưới; đổi lúc nào cũng được, chữ vẫn hiện như thường."
          : "Peto có thể nói thành tiếng trong Companion. Bật lên để chọn nguồn giọng; khi tắt, Peto chỉ nhắn chữ."}
      </p>

      {voice.enabled && (
        <>
          <div className="voice-group"><strong>Không cần khóa</strong></div>
          <div className="voice-cards">{cards(free)}</div>

          <div className="voice-group">
            <strong>Khóa của bạn</strong>
            <span>Khóa lưu trên trình duyệt này, tính tiền vào tài khoản của bạn</span>
          </div>
          <div className="voice-cards">{cards(byok)}</div>

          <div className="voice-field voice-fallback">
            <label htmlFor={fallbackId}>Khi nguồn chính không nói được</label>
            <select id={fallbackId} value={fallback} onChange={(event) => voice.setFallback(event.target.value as FallbackChoice)}>
              {offerHome && <option value="home">Dùng Máy nhà của Peto nếu đang bật</option>}
              {offerOfficial && <option value="official">Dùng Giọng Peto nếu còn lượt</option>}
              <option value="">Chỉ hiện chữ</option>
            </select>
            <small>Giọng nói do AI tạo. Giọng dự phòng có thể khác chất giọng; Giọng Peto dự phòng cũng trừ lượt tháng này.</small>
          </div>
        </>
      )}
    </section>
  );
}

function SourceCard({ card, selected, onPick }: { card: Card; selected: boolean; onPick: () => void }) {
  const nameId = useId();
  const descId = useId();
  return (
    <button
      type="button"
      className={`voice-card${selected ? " selected" : ""}${card.locked ? " locked" : ""}`}
      aria-pressed={selected}
      aria-labelledby={nameId}
      aria-describedby={descId}
      onClick={onPick}
    >
      <span className="voice-card-top">
        <strong id={nameId}>{card.name}</strong>
        {card.status && (
          <span className="voice-card-status"><i className={card.status.on ? "voice-dot on" : "voice-dot"} />{card.status.text}</span>
        )}
      </span>
      <span id={descId} className="voice-card-desc">
        {card.desc}
        <span className="voice-badges">
          {card.badges.map(([text, tone]) => <span key={text} className={`voice-badge ${tone}`}>{text}</span>)}
        </span>
      </span>
    </button>
  );
}

function Field({ id, label, hint, children }: { id: string; label: string; hint?: ReactNode; children: ReactNode }) {
  // Nhãn đứng riêng, nối bằng htmlFor: iOS Safari có khi không cho sửa ô nhập nằm trong <label> (xem ProfileSettings).
  return (
    <div className="voice-field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <small>{hint}</small>}
    </div>
  );
}

function SampleRow({ text, onText, ready, sampling, onSample }: {
  text: string;
  onText: (value: string) => void;
  ready: boolean;
  sampling: "loading" | "playing" | null;
  onSample: () => void;
}) {
  const id = useId();
  return (
    <div className="voice-sample">
      <Field id={id} label="Câu nghe thử">
        <input id={id} type="text" value={text} maxLength={300} onChange={(event) => onText(event.target.value)} />
      </Field>
      <button type="button" className="voice-primary" onClick={onSample} disabled={!ready && !sampling}>
        {sampling === "loading" ? "Đang chuẩn bị…" : sampling === "playing" ? "Dừng nghe thử" : "Nghe thử"}
      </button>
    </div>
  );
}

/** Máy chủ Peto chưa trả lời: dùng chung cho Giọng Peto và Máy nhà. */
function ServerPending({ voice }: { voice: LocalVoice }) {
  if (voice.checking) return <p className="voice-line" role="status">Đang kiểm tra máy chủ giọng nói…</p>;
  return (
    <p className="voice-line">
      Chưa kết nối được máy chủ giọng nói.
      <button type="button" className="settings-button" onClick={voice.recheck}>Kiểm tra lại</button>
    </p>
  );
}

function OfficialDetail({ voice }: { voice: LocalVoice }) {
  const id = useId();
  const official = voice.health?.official;
  if (!official) return <ServerPending voice={voice} />;
  if (!official.voices.length) {
    return <p className="voice-line">Giọng Peto chưa mở trên máy chủ này. Bạn vẫn dùng được Máy nhà của Peto hoặc khóa của mình.</p>;
  }
  if (!official.allowed) {
    return (
      <p className="voice-line">
        Lượt miễn phí dành cho tài khoản Discord và Google. Khách vẫn dùng được Máy nhà của Peto hoặc khóa của mình.
      </p>
    );
  }
  const left = Math.max(0, official.limit - official.used);
  const [, month, date] = official.resets.split("-");
  const resets = date && month ? `ngày ${date}/${month}` : "đầu tháng sau";
  return (
    <>
      <div className="voice-quota">
        <div className="voice-quota-row">
          <span>Tháng này còn</span>
          <span>{left.toLocaleString("vi-VN")} / {official.limit.toLocaleString("vi-VN")} ký tự</span>
        </div>
        <div className="voice-quota-bar" aria-hidden="true">
          <span style={{ width: `${official.limit ? (left / official.limit) * 100 : 0}%` }} />
        </div>
        <p>
          {left ? `Khoảng ${Math.floor(left / SHORT_REPLY_CHARS)} câu trả lời ngắn` : "Đã hết lượt tháng này"}
          {` · làm mới ${resets} · nghe thử cũng tính lượt`}
        </p>
      </div>
      <Field id={id} label="Giọng">
        <select id={id} value={voice.officialVoice} onChange={(event) => { voice.stop(); voice.setOfficialVoice(event.target.value); }}>
          {official.voices.map((name) => <option key={name} value={name}>{voiceLabel(name)}</option>)}
        </select>
      </Field>
    </>
  );
}

function HomeDetail({ voice }: { voice: LocalVoice }) {
  const id = useId();
  const home = voice.health?.home;
  if (!home) return <ServerPending voice={voice} />;
  return (
    <>
      <p className="voice-line">
        <i className={home.online ? "voice-dot on" : "voice-dot"} />
        {home.online
          ? "Máy nhà đang bật. Máy nhà dùng chung cho mọi người nên có lúc phải chờ."
          : "Máy nhà đang tắt. Khi máy bật, Peto nói được ngay, không cần làm gì."}
        {!home.online && (
          <button type="button" className="settings-button" onClick={voice.recheck} disabled={voice.checking}>Kiểm tra lại</button>
        )}
      </p>
      <Field id={id} label="Giọng">
        <select id={id} value={voice.homeVoice} onChange={(event) => { voice.stop(); voice.setHomeVoice(event.target.value); }}>
          {home.voices.map((name) => <option key={name} value={name}>{VOICE_LABELS[name] ?? name}</option>)}
        </select>
      </Field>
    </>
  );
}

function KeyDetail({ voice, provider }: { voice: LocalVoice; provider: KeyProvider }) {
  const ids = { url: useId(), key: useId(), region: useId(), model: useId(), voice: useId(), list: useId() };
  const config = voice.keys[provider.id] ?? {};
  const update = (patch: KeyConfig) => {
    voice.stop();
    voice.setKeyConfig(provider.id, { ...config, ...patch });
  };
  const listed = useKeyVoices(provider, config);
  const saved = Object.values(config).some((value) => typeof value === "string" && value.trim());

  // ElevenLabs không có giọng mặc định: tải được danh sách mà chưa chọn thì lấy giọng đầu tiên.
  const firstListed = listed.voices?.[0]?.id;
  useEffect(() => {
    if (firstListed && !config.voice && provider.listsVoices) voice.setKeyConfig(provider.id, { ...config, voice: firstListed });
  }, [firstListed]);

  const currentVoice = voiceOf(provider, config);
  const currentModel = modelOf(provider, config);
  const reason = RELAY_REASON[provider.id];
  return (
    <>
      {provider.needsBaseUrl && (
        <Field id={ids.url} label="Địa chỉ máy chủ" hint="Địa chỉ gốc của API, trước /audio/speech.">
          <input
            id={ids.url} type="url" inputMode="url" placeholder="https://…/v1" spellCheck={false} autoComplete="off"
            value={config.baseUrl ?? ""} onChange={(event) => update({ baseUrl: event.target.value })}
          />
        </Field>
      )}
      <Field
        id={ids.key}
        label={provider.keyOptional ? "Khóa API (nếu máy chủ cần)" : `Khóa API ${provider.name}`}
        hint={(
          <span className="voice-key-hint">
            <span>{provider.keyOptional ? "Để trống nếu máy chủ không cần khóa." : `Lấy khóa ở ${provider.site}.`}</span>
            {saved && (
              <button type="button" className="voice-link" onClick={() => voice.forgetKey(provider.id)}>
                Xóa khóa khỏi trình duyệt
              </button>
            )}
          </span>
        )}
      >
        <input
          id={ids.key} type="password" placeholder={provider.keyHint} spellCheck={false} autoComplete="off"
          value={config.key ?? ""} onChange={(event) => update({ key: event.target.value })}
        />
      </Field>
      {provider.region?.options ? (
        <Field id={ids.region} label={provider.region.label}>
          <select id={ids.region} value={config.region || provider.region.options[0].value} onChange={(event) => update({ region: event.target.value })}>
            {provider.region.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </Field>
      ) : provider.region && (
        <Field id={ids.region} label={provider.region.label} hint="Vùng của tài nguyên Speech trên Azure.">
          <input
            id={ids.region} type="text" placeholder={provider.region.placeholder} spellCheck={false} autoComplete="off"
            value={config.region ?? ""} onChange={(event) => update({ region: event.target.value })}
          />
        </Field>
      )}
      {reason ? (
        <p className="voice-note relay">
          {reason}, nên khóa đi qua máy chủ Peto để tới {provider.name}. Máy chủ chỉ chuyển tiếp, không lưu và không ghi
          lại khóa.
        </p>
      ) : (
        <p className="voice-note">
          Khóa chỉ nằm trên trình duyệt này. Trình duyệt gọi thẳng tới {provider.name}; máy chủ Peto không nhận được khóa.
        </p>
      )}
      {provider.modelFree ? (
        <Field id={ids.model} label="Model">
          <input
            id={ids.model} type="text" placeholder="tts-1" spellCheck={false} autoComplete="off"
            value={config.model ?? ""} onChange={(event) => update({ model: event.target.value })}
          />
        </Field>
      ) : (provider.models?.length ?? 0) > 1 && (
        <Field id={ids.model} label="Model">
          <select id={ids.model} value={currentModel} onChange={(event) => update({ model: event.target.value })}>
            {provider.models!.map((model) => <option key={model} value={model}>{model}</option>)}
          </select>
        </Field>
      )}
      {provider.listsVoices ? (
        <Field
          id={ids.voice}
          label="Giọng"
          hint={listed.error && (
            <span className="voice-list-error">
              {listed.error} <button type="button" className="voice-link" onClick={listed.retry}>Thử lại</button>
            </span>
          )}
        >
          <select
            id={ids.voice} value={currentVoice} disabled={!listed.voices?.length}
            onChange={(event) => update({ voice: event.target.value })}
          >
            {!listed.voices?.length && (
              <option value={currentVoice}>
                {listed.loading ? "Đang tải danh sách giọng…" : keyReady(provider, config) ? currentVoice || "Chưa tải được danh sách giọng" : "Nhập khóa để tải danh sách giọng"}
              </option>
            )}
            {listed.voices && currentVoice && !listed.voices.some((item) => item.id === currentVoice) && (
              <option value={currentVoice}>{currentVoice}</option>
            )}
            {listed.voices?.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </Field>
      ) : provider.voiceFree ? (
        <Field id={ids.voice} label="Giọng" hint="Mã giọng của nhà cung cấp; gõ tay hoặc chọn gợi ý.">
          <input
            id={ids.voice} type="text" list={provider.voices?.length ? ids.list : undefined} spellCheck={false} autoComplete="off"
            placeholder={provider.defaultVoice || "Mã giọng"} value={config.voice ?? ""}
            onChange={(event) => update({ voice: event.target.value })}
          />
          {provider.voices?.length ? (
            <datalist id={ids.list}>{provider.voices.map((name) => <option key={name} value={name} />)}</datalist>
          ) : null}
        </Field>
      ) : (
        <Field id={ids.voice} label="Giọng">
          <select id={ids.voice} value={currentVoice} onChange={(event) => update({ voice: event.target.value })}>
            {provider.voices?.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </Field>
      )}
    </>
  );
}

/** Danh sách giọng tải bằng khóa của người dùng (ElevenLabs, Azure); chờ gõ xong nửa giây rồi mới gọi. */
function useKeyVoices(provider: KeyProvider, config: KeyConfig) {
  const [state, setState] = useState<{ voices?: VoiceOption[]; error?: string; loading?: boolean }>({});
  const [attempt, setAttempt] = useState(0);
  const latest = useRef(config);
  latest.current = config;
  const signature = provider.listsVoices && keyReady(provider, config)
    ? JSON.stringify([provider.id, config.key?.trim(), config.region?.trim()])
    : "";

  useEffect(() => {
    if (!signature) {
      setState({});
      return;
    }
    const controller = new AbortController();
    setState({ loading: true });
    const timer = window.setTimeout(() => {
      listKeyVoices(provider, latest.current, controller.signal).then(
        (voices) => { if (!controller.signal.aborted) setState({ voices: voices ?? [] }); },
        (error: unknown) => {
          if (!controller.signal.aborted) {
            setState({ error: error instanceof Error ? error.message : "Chưa tải được danh sách giọng." });
          }
        },
      );
    }, 500);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [signature, attempt]);

  return { ...state, retry: () => setAttempt((count) => count + 1) };
}
