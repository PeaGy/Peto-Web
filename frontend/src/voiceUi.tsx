import { useId, type ReactNode } from "react";

/** Màu nhãn trên thẻ nguồn: xám, xanh chính thức, xanh lá miễn phí, vàng đi qua máy chủ Peto. */
export type Tone = "neutral" | "official" | "free" | "relay";

export interface Card<Id extends string = string> {
  id: Id;
  name: string;
  desc: string;
  badges: [string, Tone][];
  status?: { text: string; on: boolean };
  locked?: boolean;
}

/** Một thẻ nguồn (giọng nói hay nghe) trong Cài đặt → Giọng nói; bấm là chọn nguồn đó. */
export function SourceCard({ card, selected, onPick }: { card: Card; selected: boolean; onPick: () => void }) {
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

export function Field({ id, label, hint, children }: { id: string; label: string; hint?: ReactNode; children: ReactNode }) {
  // Nhãn đứng riêng, nối bằng htmlFor: iOS Safari có khi không cho sửa ô nhập nằm trong <label> (xem ProfileSettings).
  return (
    <div className="voice-field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <small>{hint}</small>}
    </div>
  );
}
