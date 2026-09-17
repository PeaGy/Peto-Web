import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import type { ModelOption } from "./api";

/**
 * Nút chọn model bên trái nút Gửi (chủ web chọn từ bản phác): "Peto ▾" mở menu bật lên, mỗi model một dòng kèm mô tả.
 *
 * Dùng lại kiểu của menu Mức suy nghĩ; nằm sát mép phải nên menu canh theo mép phải của nút. Cách dùng phím như
 * StudioMenu: mở ra thì con trỏ ở model đang chọn, Escape trả về nút.
 */
export default function ModelMenu({ value, options, disabled, onChange }: {
  value: string;
  options: ModelOption[];
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const current = options.find((item) => item.key === value) ?? options[0];

  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => {
    if (!open) return;
    items.current[Math.max(0, options.findIndex((item) => item.key === value))]?.focus();
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

  if (!current) return null;
  // Chỉ đóng khi focus sang một phần tử khác thật; Safari không focus nút lúc chạm nên relatedTarget rỗng.
  return <div ref={root} className="effort-menu model-menu" onBlur={(event) => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
  }}>
    <button ref={trigger} type="button" className="effort-trigger" disabled={disabled}
      aria-haspopup="menu" aria-expanded={open} aria-controls={menuId} aria-label={`Model: ${current.label}`}
      title={`Model · ${current.description}`}
      onClick={() => setOpen((value) => !value)}
      onKeyDown={(event) => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); }
      }}>
      <span>{current.label}</span>
      <svg className="effort-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
    {open && <div id={menuId} className="effort-options model-options" role="menu" aria-label="Model" onKeyDown={onMenuKey}>
      <p className="effort-heading" aria-hidden="true">Model</p>
      {options.map((item, index) => {
        const on = item.key === value;
        return <button key={item.key} ref={(element) => { items.current[index] = element; }} type="button"
          role="menuitemradio" aria-checked={on} className={on ? "effort-option model-option on" : "effort-option model-option"}
          onClick={() => { onChange(item.key); close(); }}>
          <span className="model-option-text">
            <span className="effort-option-label">{item.label}</span>
            <small>{item.description}</small>
          </span>
          {on && <svg className="effort-check" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="m5 12.5 4.5 4.5L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>}
        </button>;
      })}
    </div>}
  </div>;
}
