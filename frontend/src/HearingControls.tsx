/**
 * Giao diện phần Peto nghe trong Companion (phương án A chủ web chọn ngày 2026-09-24, giống AIRI): nút micro ở góc
 * trái ô nhắn, bảng Micro bật lên ngay trên ô nhắn trên máy tính, và một thanh trạng thái gọn trên điện thoại. Bảng
 * nằm trong cột chat, không nổi trên sân khấu: sân khấu chỉ dành cho nhân vật.
 */
import { useEffect, useId, useRef, useState, type CSSProperties, type RefObject } from "react";
import {
  setHearingSetting,
  startListening,
  stopListening,
  useHearing,
  useHearingLevel,
  type HearingSource,
  type HearingState,
} from "./hearingEngine";
import { listMicrophones, type Microphone } from "./hearingCapture";
import { hearingProvider } from "./hearingProviders";
import { Dropdown, Field } from "./voiceUi";

export function MicIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

export function MicOffIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 9v2a3 3 0 0 0 5.1 2.1M15 9.3V6a3 3 0 0 0-5.7-1.3" />
      <path d="M5 11a7 7 0 0 0 11.4 5.4M19 11a7 7 0 0 1-.6 2.8M12 18v3M3 3l18 18" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" aria-hidden="true">
      <path d="M9 5v14M15 5v14" />
    </svg>
  );
}

export function sourceName(source: HearingSource): string {
  return source === "browser" ? "Có sẵn trong trình duyệt" : hearingProvider(source)?.name ?? source;
}

export function phaseTitle(state: HearingState): string {
  switch (state.phase) {
    case "starting": return "Đang mở micro…";
    case "waiting": return "Đang nghe";
    case "speaking": return "Bạn đang nói";
    case "transcribing": return "Đang chép lời…";
    case "paused": return "Tạm không nghe";
    default: return "Micro đang tắt";
  }
}

function phaseHint(state: HearingState): string {
  switch (state.phase) {
    case "starting": return "Trình duyệt có thể hỏi quyền dùng micro.";
    case "waiting":
    case "speaking":
      return state.source === "browser"
        ? "Nói đi, chữ hiện dần trong ô nhắn. Ngừng một chút là xong câu."
        : "Nói đi. Ngừng một chút là câu đó được chép vào ô nhắn.";
    case "transcribing": return "Chữ sẽ vào ô nhắn ngay.";
    case "paused": return "Peto đang trả lời. Peto nói xong thì nghe tiếp.";
    default: return "Bấm nút để Peto nghe bạn nói.";
  }
}

/** Chữ gợi ý trong ô nhắn theo trạng thái nghe. */
export function hearingPlaceholder(state: HearingState): string | null {
  if (!state.listening || state.testing) return null;
  if (state.phase === "paused") return "Peto đang trả lời, tạm không nghe…";
  if (state.phase === "transcribing") return "Đang chép lời…";
  if (state.phase === "starting") return "Đang mở micro…";
  return "Peto đang nghe…";
}

// Độ cao tương đối của từng vạch, để thanh âm lượng trông như sóng thay vì một khối.
const WAVE = [0.35, 0.6, 0.85, 0.55, 1, 0.75, 0.45, 0.9, 0.65, 0.4, 0.8, 0.5];

/** Thanh âm lượng: cao theo âm lượng micro lúc này. */
export function LevelBars({ count, className = "", threshold }: { count: number; className?: string; threshold?: number }) {
  const level = useHearingLevel();
  return (
    <span className={`hearing-levels ${className}`} aria-hidden="true">
      {Array.from({ length: count }, (_, index) => {
        const height = Math.max(10, Math.round(level * WAVE[index % WAVE.length] * 100));
        const on = level > 0.02 && (threshold === undefined || level >= threshold * 0.9);
        return <i key={index} className={on ? "on" : ""} style={{ height: `${height}%` }} />;
      })}
      {threshold !== undefined && <b className="hearing-threshold" style={{ left: `${threshold * 100}%` }} />}
    </span>
  );
}

/** Nút micro ở góc trái ô nhắn Companion; vòng sáng quanh nút lớn theo âm lượng. */
export function MicButton({ onClick, buttonRef }: { onClick: () => void; buttonRef?: RefObject<HTMLButtonElement | null> }) {
  const hearing = useHearing();
  const level = useHearingLevel();
  const on = hearing.listening && !hearing.testing;
  const label = on ? "Tắt nghe" : "Bật nghe";
  return (
    <button
      ref={buttonRef}
      type="button"
      className={on ? `hearing-mic on ${hearing.phase}` : "hearing-mic"}
      aria-label={label}
      aria-pressed={on}
      title={label}
      style={{ "--hearing-level": on && hearing.phase !== "paused" ? level : 0 } as CSSProperties}
      onClick={onClick}
    >
      {on ? <MicIcon /> : <MicOffIcon />}
      {on && hearing.phase === "paused" && <span className="hearing-mic-badge"><PauseIcon /></span>}
    </button>
  );
}

/** Danh sách micro; đọc lại khi cắm, rút micro hay khi vừa được cho phép (lúc đó trình duyệt mới cho biết tên). */
export function useMicrophones(enabled: boolean): Microphone[] {
  const [list, setList] = useState<Microphone[]>([]);
  const listening = useHearing().listening;
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    const refresh = () => {
      void listMicrophones().then((found) => {
        if (alive) setList(found);
      });
    };
    refresh();
    navigator.mediaDevices?.addEventListener?.("devicechange", refresh);
    return () => {
      alive = false;
      navigator.mediaDevices?.removeEventListener?.("devicechange", refresh);
    };
  }, [enabled, listening]);
  return list;
}

export function MicrophoneSelect({ id, microphones }: { id: string; microphones: Microphone[] }) {
  const hearing = useHearing();
  const known = !hearing.deviceId || microphones.some((microphone) => microphone.id === hearing.deviceId);
  return (
    <Dropdown
      id={id}
      value={hearing.deviceId}
      onChange={(value) => setHearingSetting("deviceId", value)}
      options={[
        { value: "", label: "Micro mặc định" },
        ...(known ? [] : [{ value: hearing.deviceId, label: "Micro đã chọn (chưa thấy)" }]),
        ...microphones.map((microphone) => ({ value: microphone.id, label: microphone.label })),
      ]}
    />
  );
}

/** Bảng Micro trên máy tính, bật lên ngay trên ô nhắn khi bấm micro. Bấm ra ngoài hay Esc thì đóng, vẫn nghe tiếp. */
export function HearingPopover({ anchorRef, onClose, onOpenSettings }: {
  anchorRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  onOpenSettings?: () => void;
}) {
  const hearing = useHearing();
  const ref = useRef<HTMLDivElement>(null);
  const microphones = useMicrophones(true);
  const micId = useId();
  const on = hearing.listening && !hearing.testing;

  useEffect(() => {
    const pointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (ref.current?.contains(target) || anchorRef.current?.contains(target)) return;
      onClose();
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("pointerdown", pointer);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", pointer);
      document.removeEventListener("keydown", key);
    };
  }, [anchorRef, onClose]);

  return (
    <div ref={ref} className="hearing-popover" role="dialog" aria-label="Micro">
      <div className="hearing-popover-head">
        <button
          type="button"
          className={on ? "hearing-big on" : "hearing-big"}
          aria-pressed={on}
          aria-label={on ? "Tắt nghe" : "Bật nghe"}
          onClick={() => (on ? stopListening() : void startListening())}
        >
          {on ? <MicIcon size={26} /> : <MicOffIcon size={26} />}
        </button>
        <div className="hearing-popover-text" role="status">
          <strong>{phaseTitle(hearing)}</strong>
          <span>{phaseHint(hearing)}</span>
        </div>
      </div>
      <LevelBars count={24} className="hearing-popover-levels" />
      <label className="hearing-toggle">
        <span>
          <strong>Tự gửi</strong>
          <small>Nói xong là gửi luôn. Tắt thì chữ nằm trong ô để bạn sửa trước.</small>
        </span>
        <input
          type="checkbox"
          role="switch"
          aria-label="Tự gửi"
          checked={hearing.autoSend}
          onChange={(event) => setHearingSetting("autoSend", event.target.checked)}
        />
      </label>
      <Field
        id={micId}
        label="Micro"
        hint={hearing.source === "browser" ? "Nguồn trong trình duyệt luôn nghe bằng micro mặc định của máy." : undefined}
      >
        <MicrophoneSelect id={micId} microphones={microphones} />
      </Field>
      <p className="hearing-source">
        Nguồn nghe: {sourceName(hearing.source)}
        {onOpenSettings && <> · <button type="button" className="voice-link" onClick={onOpenSettings}>đổi trong Cài đặt</button></>}
      </p>
    </div>
  );
}

/** Thanh trạng thái gọn trên điện thoại, nằm ngay trên ô nhắn trong lúc nghe. */
export function HearingBar() {
  const hearing = useHearing();
  if (!hearing.listening || hearing.testing) return null;
  return (
    <div className="hearing-bar">
      <span className={`hearing-dot ${hearing.phase}`} aria-hidden="true" />
      <span className="hearing-bar-title" role="status">{phaseTitle(hearing)}</span>
      <LevelBars count={9} className="hearing-bar-levels" />
      <label className="hearing-bar-toggle">
        <span>Tự gửi</span>
        <input
          type="checkbox"
          role="switch"
          aria-label="Tự gửi khi nói xong"
          checked={hearing.autoSend}
          onChange={(event) => setHearingSetting("autoSend", event.target.checked)}
        />
      </label>
    </div>
  );
}
