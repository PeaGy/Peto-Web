import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Effort, ModelOption } from "../../shared/api/api";

// Mỗi mức một hình, cùng nét mảnh với menu của Grok: lấp lánh cho Tự động,
// tia chớp cho Thấp (trả lời nhanh), bóng đèn cho Trung bình, các lớp chồng
// nhau cho Cao (đào sâu nhiều tầng).
const ICONS: Record<string, ReactNode> = {
  auto: <>
    <path d="m12 3 1.8 6.2L20 11l-6.2 1.8L12 19l-1.8-6.2L4 11l6.2-1.8L12 3Z" strokeLinejoin="round" />
    <path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z" fill="currentColor" stroke="none" />
  </>,
  low: <path d="M13 3 5 14h6l-1 7 8-11h-6l1-7Z" strokeLinejoin="round" />,
  medium: <>
    <path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1v.5h5v-.5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3Z" strokeLinejoin="round" />
    <path d="M9.5 19h5M10.5 21.5h3" strokeLinecap="round" />
  </>,
  high: <>
    <path d="M12 3 3 7.5l9 4.5 9-4.5L12 3Z" strokeLinejoin="round" />
    <path d="m3 12 9 4.5 9-4.5M3 16.5l9 4.5 9-4.5" strokeLinecap="round" strokeLinejoin="round" />
  </>,
};

function ModeIcon({ value }: { value: string }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
    {ICONS[value] ?? (value === 'none' ? ICONS.low : ICONS.high)}
  </svg>;
}

/**
 * Một nút "Peto · Tự động ▾" trong ô nhắn, bên trái micro (máy tính; chủ web chọn mẫu B ngày 24/11/2026, kiểu Claude).
 *
 * Trước đó hai nút Model và Mức suy nghĩ nằm ở dòng dưới ô nhắn; khung dưới không có nền nên khi cuộn lên, chữ tin
 * nhắn lộ ra dưới hai nút. Menu gộp cả hai nhóm, mỗi nhóm một danh sách chọn một; chọn xong thì đóng như trên điện thoại.
 * Phím như menu StudioMenu của Imagine: mở ra thì con trỏ ở model đang chọn (hoặc mức suy nghĩ khi chỉ có một model), mũi tên đi qua
 * cả hai nhóm, Escape trả về nút.
 */
export default function ChatSettingsMenu({ model, models, onModelChange, effort, efforts, onEffortChange, disabled }: {
  model: string; models: ModelOption[]; onModelChange: (model: string) => void;
  effort: Effort; efforts: { value: Effort; label: string; hint: string }[]; onEffortChange: (effort: Effort) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const currentModel = models.find((item) => item.key === model) ?? models[0];
  const currentEffort = efforts.find((item) => item.value === effort) ?? efforts[0];
  const modelLabel = currentModel?.label ?? "Peto";
  const choosesModel = models.length > 1;

  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => {
    if (!open) return;
    const at = choosesModel ? models.findIndex((item) => item.key === model)
      : efforts.findIndex((item) => item.value === effort);
    items.current[Math.max(0, at) + (choosesModel ? 0 : models.length)]?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  function close() { setOpen(false); trigger.current?.focus(); }

  function onMenuKey(event: KeyboardEvent<HTMLDivElement>) {
    const list = items.current.filter((item): item is HTMLButtonElement => item !== null);
    const at = list.indexOf(document.activeElement as HTMLButtonElement);
    const move = (to: number) => { event.preventDefault(); list[(to + list.length) % list.length]?.focus(); };
    if (event.key === "ArrowDown") move(at + 1);
    else if (event.key === "ArrowUp") move(at - 1);
    else if (event.key === "Home") move(0);
    else if (event.key === "End") move(list.length - 1);
    else if (event.key === "Escape") { event.preventDefault(); close(); }
    else if (event.key === "Tab") setOpen(false);
  }

  const check = <svg className="effort-check" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="m5 12.5 4.5 4.5L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;

  // Chỉ đóng khi focus sang một phần tử khác thật; Safari không focus nút lúc chạm nên relatedTarget rỗng.
  return <div ref={root} className="effort-menu chat-settings-menu" onBlur={(event) => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
  }}>
    <button ref={trigger} type="button" className="effort-trigger chat-settings-trigger" disabled={disabled}
      aria-haspopup="menu" aria-expanded={open} aria-controls={menuId}
      // Chỉ có một model (Peto) thì không có gì để chọn: tên nút chỉ nói về mức suy nghĩ, chữ vẫn là "Peto · Tự động".
      aria-label={choosesModel ? `Model: ${modelLabel}, Mức suy nghĩ: ${currentEffort?.label}` : `Mức suy nghĩ: ${currentEffort?.label}`}
      data-tip={currentModel ? `${currentModel.description} · ${currentEffort?.hint}` : currentEffort?.hint}
      onClick={() => setOpen((value) => !value)}
      onKeyDown={(event) => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); }
      }}>
      <span className="chat-settings-label">{modelLabel}<span className="chat-settings-effort"> · {currentEffort?.label}</span></span>
      <svg className="effort-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
    {open && <div id={menuId} className="effort-options chat-settings-options" role="menu"
      aria-label="Model và mức suy nghĩ" onKeyDown={onMenuKey}>
      {choosesModel && <div role="group" aria-label="Model">
        <p className="effort-heading" aria-hidden="true">Model</p>
        {models.map((item, index) => {
          const on = item.key === model;
          return <button key={item.key} ref={(element) => { items.current[index] = element; }} type="button"
            role="menuitemradio" aria-checked={on} className={on ? "effort-option model-option on" : "effort-option model-option"}
            onClick={() => { onModelChange(item.key); close(); }}>
            <span className="model-option-text">
              <span className="effort-option-label">{item.label}</span>
              <small>{item.description}</small>
            </span>
            {on && check}
          </button>;
        })}
      </div>}
      <div role="group" aria-label="Mức suy nghĩ">
        <p className="effort-heading" aria-hidden="true">Mức suy nghĩ</p>
        {efforts.map((item, index) => {
          const on = item.value === effort;
          return <button key={item.value} ref={(element) => { items.current[models.length + index] = element; }}
            type="button" role="menuitemradio" aria-checked={on} className={on ? "effort-option on" : "effort-option"}
            data-tip={item.hint} data-tip-side="left" onClick={() => { onEffortChange(item.value); close(); }}>
            <ModeIcon value={item.value} />
            <span className="effort-option-label">{item.label}</span>
            {on && check}
          </button>;
        })}
      </div>
    </div>}
  </div>;
}
