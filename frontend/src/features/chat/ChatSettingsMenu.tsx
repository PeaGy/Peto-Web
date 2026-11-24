import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import type { Effort, ModelOption } from "../../shared/api/api";

type EffortOption = { value: Effort; label: string; hint: string };

const CHECK = <svg className="effort-check" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
  <path d="m5 12.5 4.5 4.5L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
</svg>;

/** Mũi tên qua lại giữa các mục của một danh sách; Home/End về hai đầu. Trả true khi đã xử lý phím. */
function moveFocus(event: KeyboardEvent, list: HTMLButtonElement[]) {
  const at = list.indexOf(document.activeElement as HTMLButtonElement);
  const to = event.key === "ArrowDown" ? at + 1 : event.key === "ArrowUp" ? at - 1
    : event.key === "Home" ? 0 : event.key === "End" ? list.length - 1 : null;
  if (to === null) return false;
  event.preventDefault();
  list[(to + list.length) % list.length]?.focus();
  return true;
}

/**
 * Một nút "Peto · Tự động ▾" trong ô nhắn, bên trái micro (máy tính; chủ web chọn mẫu B ngày 24/11/2026, kiểu Claude).
 *
 * Trước đó hai nút Model và Mức suy nghĩ nằm ở dòng dưới ô nhắn; khung dưới không có nền nên khi cuộn lên, chữ tin
 * nhắn lộ ra dưới hai nút. Menu gọn như của Claude (25/11/2026): các model, rồi một dòng "Mức suy nghĩ · Tự động ›"
 * mở menu phụ bên cạnh (bấm, rê chuột hoặc phím →). Chỉ có một model thì menu là danh sách mức suy nghĩ luôn.
 * Phím: mở ra thì con trỏ ở model đang chọn; ↑ ↓ Home End trong từng menu; → hoặc Enter mở menu phụ, ← hoặc Escape
 * quay về dòng Mức suy nghĩ; Escape ở menu chính trả về nút. Chọn xong thì đóng hết.
 */
export default function ChatSettingsMenu({ model, models, onModelChange, effort, efforts, onEffortChange, disabled }: {
  model: string; models: ModelOption[]; onModelChange: (model: string) => void;
  effort: Effort; efforts: EffortOption[]; onEffortChange: (effort: Effort) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  // Menu phụ Mức suy nghĩ: mở về phía còn chỗ (phải như Claude, hết chỗ thì sang trái).
  const [sub, setSub] = useState<null | { side: "left" | "right"; focus: boolean }>(null);
  const menuId = useId();
  const root = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const effortRow = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const subItems = useRef<(HTMLButtonElement | null)[]>([]);
  const currentModel = models.find((item) => item.key === model) ?? models[0];
  const currentEffort = efforts.find((item) => item.value === effort) ?? efforts[0];
  const modelLabel = currentModel?.label ?? "Peto";
  const choosesModel = models.length > 1;

  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => { if (!open) setSub(null); }, [open]);
  useEffect(() => {
    if (!open) return;
    const at = choosesModel ? models.findIndex((item) => item.key === model) : efforts.findIndex((item) => item.value === effort);
    items.current[Math.max(0, at)]?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  useEffect(() => {
    if (sub?.focus) subItems.current[Math.max(0, efforts.findIndex((item) => item.value === effort))]?.focus();
  }, [sub]);

  function close() { setOpen(false); trigger.current?.focus(); }

  function openSub(focus: boolean) {
    const box = menu.current?.getBoundingClientRect();
    const side = box && box.right + 8 + 248 > window.innerWidth ? "left" : "right";
    setSub({ side, focus });
  }

  function closeSub() { setSub(null); effortRow.current?.focus(); }

  function onMenuKey(event: KeyboardEvent<HTMLDivElement>) {
    const list = items.current.filter((item): item is HTMLButtonElement => item !== null);
    if (moveFocus(event, list)) return;
    if (event.key === "Escape") { event.preventDefault(); close(); }
    else if (event.key === "Tab") setOpen(false);
  }

  function onSubKey(event: KeyboardEvent<HTMLDivElement>) {
    // Không để phím nổi lên menu chính (nó sẽ di con trỏ trong danh sách model).
    event.stopPropagation();
    const list = subItems.current.filter((item): item is HTMLButtonElement => item !== null);
    if (moveFocus(event, list)) return;
    if (event.key === "Escape" || event.key === "ArrowLeft" || event.key === "ArrowRight") {
      if (event.key !== (sub?.side === "left" ? "ArrowLeft" : "ArrowRight")) { event.preventDefault(); closeSub(); }
    } else if (event.key === "Tab") setOpen(false);
  }

  const effortItems = (refs: typeof items, offset: number) => efforts.map((item, index) => {
    const on = item.value === effort;
    return <button key={item.value} ref={(element) => { refs.current[offset + index] = element; }} type="button"
      role="menuitemradio" aria-checked={on} className={on ? "effort-option on" : "effort-option"}
      data-tip={item.hint} data-tip-side="left" onClick={() => { onEffortChange(item.value); close(); }}>
      <span className="effort-option-label">{item.label}</span>
      {on && CHECK}
    </button>;
  });

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
    {open && <div ref={menu} id={menuId} className="effort-options chat-settings-options" role="menu"
      aria-label={choosesModel ? "Model và mức suy nghĩ" : "Mức suy nghĩ"} onKeyDown={onMenuKey}>
      {choosesModel ? <>
        <div role="group" aria-label="Model">
          {models.map((item, index) => {
            const on = item.key === model;
            return <button key={item.key} ref={(element) => { items.current[index] = element; }} type="button"
              role="menuitemradio" aria-checked={on} className={on ? "effort-option model-option on" : "effort-option model-option"}
              onPointerEnter={() => setSub(null)} onClick={() => { onModelChange(item.key); close(); }}>
              <span className="model-option-text">
                <span className="effort-option-label">{item.label}</span>
                <small>{item.description}</small>
              </span>
              {on && CHECK}
            </button>;
          })}
        </div>
        <div className="chat-settings-sep" role="separator" />
        <button ref={(element) => { effortRow.current = element; items.current[models.length] = element; }} type="button"
          role="menuitem" aria-haspopup="menu" aria-expanded={sub !== null} className="effort-option chat-settings-effort-row"
          onPointerEnter={(event) => { if (event.pointerType === "mouse" && !sub) openSub(false); }}
          onClick={() => (sub ? setSub(null) : openSub(true))}
          onKeyDown={(event) => {
            if (["ArrowRight", "ArrowLeft", "Enter", " "].includes(event.key)) { event.preventDefault(); openSub(true); }
          }}>
          <span className="effort-option-label">Mức suy nghĩ</span>
          <span className="chat-settings-value">{currentEffort?.label}</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="m9 6 6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {sub && <div className={`effort-options chat-settings-sub ${sub.side}`} role="menu" aria-label="Mức suy nghĩ"
          onKeyDown={onSubKey}>
          <p className="chat-settings-note">Mức cao hơn nghĩ kỹ hơn nhưng trả lời lâu hơn.</p>
          {effortItems(subItems, 0)}
        </div>}
      </> : effortItems(items, 0)}
    </div>}
  </div>;
}
