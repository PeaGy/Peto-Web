/**
 * Giao diện phần Peto nghe trong Companion (phương án A chủ web chọn ngày 2026-09-24, giống AIRI): nút micro ở góc
 * trái ô nhắn, bảng Micro bật lên ngay trên ô nhắn trên máy tính, và một thanh trạng thái gọn trên điện thoại. Bảng
 * nằm trong cột chat, không nổi trên sân khấu: sân khấu chỉ dành cho nhân vật.
 *
 * Giữ để nói (biến thể "Bật rồi giữ" chủ web chọn ngày 13/10/2026, như AIRI): nút micro vẫn là công tắc. Bật lên thì
 * máy tính giữ Space (khi không gõ chữ) hoặc giữ chính nút micro, điện thoại giữ nút lớn "Giữ để nói" phía trên ô nhắn.
 * Bấm nhanh nút micro là tắt.
 */
import {
  useEffect, useId, useRef, useState, useSyncExternalStore,
  type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type RefObject,
} from "react";
import {
  beginHold,
  cancelHold,
  endHold,
  flashHearingHint,
  HOLD_TOO_SHORT,
  setHearingSetting,
  startListening,
  stopListening,
  useHearing,
  useHearingLevel,
  type HearingSource,
  type HearingState,
} from "./hearingEngine";
import { COMPACT_QUERY } from "../characters/characterView";
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
    case "ready": return "Giữ để nói";
    case "starting": return "Đang kết nối nguồn nghe…";
    case "waiting": return "Đang nghe";
    case "speaking": return "Bạn đang nói";
    case "transcribing": return "Đang chép lời…";
    case "paused": return "Tạm không nghe";
    default: return "Micro đang tắt";
  }
}

function phaseHint(state: HearingState): string {
  switch (state.phase) {
    case "starting": return "Đang chờ nguồn nghe sẵn sàng. Trình duyệt có thể hỏi quyền dùng micro.";
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
  if (state.mode === "hold") {
    if (state.holding) return state.phase === "starting" ? "Đang mở micro…" : "Đang nghe… thả ra để xong";
    return state.phase === "transcribing" ? "Đang chép lời…" : null;
  }
  if (state.phase === "paused") return "Peto đang trả lời, tạm không nghe…";
  if (state.phase === "transcribing") return "Đang chép lời…";
  if (state.phase === "starting") return "Đang kết nối nguồn nghe…";
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

/** Giữ để nói bằng chuột hay ngón tay trên một nút: nhấn là mở micro, thả là chốt câu. */
function useHoldPointer(onShort: () => void) {
  const pointer = useRef<number | null>(null);
  const skipClick = useRef(false);
  return {
    skipClick,
    handlers: {
      onPointerDown(event: ReactPointerEvent<HTMLButtonElement>) {
        if (event.button !== 0 || pointer.current !== null) return;
        // Không mở được (lần trước còn đang chép): để cú bấm đi theo đường thường.
        if (!beginHold()) return;
        try { event.currentTarget.setPointerCapture(event.pointerId); } catch { /* con trỏ đã mất */ }
        pointer.current = event.pointerId;
      },
      onPointerUp(event: ReactPointerEvent<HTMLButtonElement>) {
        if (pointer.current !== event.pointerId) return;
        pointer.current = null;
        skipClick.current = true;
        if (endHold() === "short") onShort();
      },
      onPointerCancel() {
        if (pointer.current === null) return;
        pointer.current = null;
        cancelHold();
      },
    },
  };
}

/** Space trên chính nút đang có tiêu điểm cũng là giữ để nói (Enter vẫn là bấm). */
function holdKeys(onShort: () => void) {
  return {
    onKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
      if (event.key !== " ") return;
      event.preventDefault();
      if (!event.repeat) beginHold();
    },
    onKeyUp(event: ReactKeyboardEvent<HTMLButtonElement>) {
      if (event.key !== " ") return;
      event.preventDefault();
      if (endHold() === "short") onShort();
    },
  };
}

/**
 * Nút micro ở góc trái ô nhắn Companion; vòng sáng quanh nút lớn theo âm lượng. Ở Giữ để nói, đã bật thì giữ nút (hay
 * giữ Space khi nút có tiêu điểm) là nói, bấm nhanh là tắt.
 */
export function MicButton({ onClick, buttonRef }: { onClick: () => void; buttonRef?: RefObject<HTMLButtonElement | null> }) {
  const hearing = useHearing();
  const level = useHearingLevel();
  const on = hearing.listening && !hearing.testing;
  const holdMode = hearing.mode === "hold";
  const armed = on && holdMode;
  const hold = useHoldPointer(onClick);
  const label = holdMode ? (on ? "Giữ để nói, bấm để tắt" : "Bật Giữ để nói") : on ? "Tắt nghe" : "Bật nghe";
  const lit = on && hearing.phase !== "paused" && (!holdMode || hearing.holding);
  return (
    <button
      ref={buttonRef}
      type="button"
      className={on ? `hearing-mic on ${hearing.phase}${holdMode ? " hold" : ""}${hearing.holding ? " holding" : ""}` : "hearing-mic"}
      aria-label={label}
      aria-pressed={on}
      data-tip
      style={{ "--hearing-level": lit ? level : 0 } as CSSProperties}
      {...(armed ? hold.handlers : {})}
      {...(armed ? holdKeys(() => flashHearingHint(HOLD_TOO_SHORT)) : {})}
      onContextMenu={armed ? (event) => event.preventDefault() : undefined}
      onClick={(event) => {
        if (hold.skipClick.current) {
          hold.skipClick.current = false;
          return;
        }
        const arming = holdMode && !on;
        onClick();
        // Safari không tự đặt tiêu điểm vào nút khi bấm chuột: đặt tay để Space ngay sau đó là giữ để nói. Màn cảm ứng
        // không có Space, mà tiêu điểm làm hiện chú thích che công tắc Tự gửi.
        if (arming && window.matchMedia?.("(pointer: coarse)")?.matches !== true) event.currentTarget.focus({ preventScroll: true });
      }}
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
  const browser = hearing.source === "browser";
  const known = !hearing.deviceId || microphones.some((microphone) => microphone.id === hearing.deviceId);
  return (
    <Dropdown
      id={id}
      value={browser ? "" : hearing.deviceId}
      disabled={browser}
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
          onClick={() => (on ? stopListening({ keepInterim: true }) : void startListening())}
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
  if (!hearing.listening || hearing.testing || hearing.mode === "hold") return null;
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

function subscribeCompact(listener: () => void) {
  const query = window.matchMedia?.(COMPACT_QUERY);
  query?.addEventListener?.("change", listener);
  return () => query?.removeEventListener?.("change", listener);
}

/** Đang ở bố cục điện thoại (cùng mốc 720px với CSS). */
function useCompact(): boolean {
  return useSyncExternalStore(subscribeCompact, () => window.matchMedia?.(COMPACT_QUERY)?.matches === true, () => false);
}

function clock(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function HoldAutoSend() {
  const hearing = useHearing();
  return (
    <label className="hearing-bar-toggle hearing-hold-autosend">
      <span>Tự gửi</span>
      <input
        type="checkbox"
        role="switch"
        aria-label="Tự gửi"
        checked={hearing.autoSend}
        onChange={(event) => setHearingSetting("autoSend", event.target.checked)}
      />
    </label>
  );
}

/** Nút lớn "Giữ để nói" trên điện thoại. */
function HoldPad() {
  const hearing = useHearing();
  const level = useHearingLevel();
  const short = () => flashHearingHint(HOLD_TOO_SHORT);
  const hold = useHoldPointer(short);
  const content = hearing.holding
    ? <><LevelBars count={7} className="hearing-pad-levels" /><span>{hearing.phase === "starting" ? "Đang mở micro…" : "Đang nghe · thả tay để xong"}</span></>
    : hearing.phase === "transcribing" ? <span>Đang chép lời…</span>
      : <><MicIcon /><span>Giữ để nói</span></>;
  return (
    <button
      type="button"
      className={hearing.holding ? "hearing-pad on" : "hearing-pad"}
      aria-label="Giữ để nói"
      style={{ "--hearing-level": hearing.holding ? level : 0 } as CSSProperties}
      {...hold.handlers}
      {...holdKeys(short)}
      onKeyDown={(event) => {
        if (event.key === "Enter") event.preventDefault();
        holdKeys(short).onKeyDown(event);
      }}
      onContextMenu={(event) => event.preventDefault()}
      onClick={() => { hold.skipClick.current = false; }}
    >
      {content}
    </button>
  );
}

/**
 * Giữ để nói đã bật: máy tính có một thanh nhắc ngay trên ô nhắn (giữ Space hay nút micro, đồng hồ lúc đang giữ, Tự
 * gửi); điện thoại có nút lớn "Giữ để nói" và công tắc Tự gửi.
 */
export function HoldControls() {
  const hearing = useHearing();
  const compact = useCompact();
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!hearing.holding) return;
    setNow(performance.now());
    const timer = window.setInterval(() => setNow(performance.now()), 250);
    return () => window.clearInterval(timer);
  }, [hearing.holding]);
  if (!hearing.listening || hearing.testing || hearing.mode !== "hold") return null;
  if (compact) {
    return (
      <div className="hearing-pad-wrap">
        {hearing.hint && <p className="hearing-pad-hint" role="status">{hearing.hint}</p>}
        <HoldPad />
        <HoldAutoSend />
      </div>
    );
  }
  const busy = hearing.holding || hearing.phase === "transcribing";
  const title = hearing.hint ? hearing.hint
    : hearing.holding ? (hearing.phase === "starting" ? "Đang mở micro…" : "Đang nghe")
      : hearing.phase === "transcribing" ? "Đang chép lời…"
        : <>Giữ <kbd>Space</kbd> hay micro để nói</>;
  return (
    <div className={busy ? "hearing-strip on" : "hearing-strip"} role="status">
      <span className="hearing-strip-dot" aria-hidden="true" />
      <span className="hearing-strip-title">{title}</span>
      {hearing.holding && (
        <>
          <LevelBars count={12} className="hearing-strip-levels" />
          <span className="hearing-strip-time">{clock(now - hearing.holdStartedAt)}</span>
        </>
      )}
      <HoldAutoSend />
    </div>
  );
}
