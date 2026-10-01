import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export type StudioOption<T extends string | number> = { value: T; label: string; icon?: ReactNode };

/**
 * Chip chọn một giá trị trong ô nhập Tạo ảnh (Số ảnh, Tỉ lệ), bật menu lên phía trên như Grok.
 *
 * Cách dùng phím theo EffortMenu: mở ra thì con trỏ nằm ở mục đang chọn, Escape trả về chip.
 * Menu hai cột thì lên/xuống nhảy cả hàng, trái/phải đi từng mục.
 */
export default function StudioMenu<T extends string | number>({
  label, value, options, icon, disabled, onChange, columns = 1, align = "start",
}: {
  label: string;
  value: T;
  options: StudioOption<T>[];
  icon: ReactNode;
  disabled: boolean;
  onChange: (value: T) => void;
  columns?: 1 | 2;
  align?: "start" | "end";
}) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const current = options.find((item) => item.value === value) ?? options[0];

  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => {
    if (!open) return;
    items.current[Math.max(0, options.findIndex((item) => item.value === value))]?.focus();
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
    if (event.key === "ArrowDown") move(at + columns);
    else if (event.key === "ArrowUp") move(at - columns);
    else if (event.key === "ArrowRight") move(at + 1);
    else if (event.key === "ArrowLeft") move(at - 1);
    else if (event.key === "Home") move(0);
    else if (event.key === "End") move(list.length - 1);
    else if (event.key === "Escape") { event.preventDefault(); close(); }
    else if (event.key === "Tab") setOpen(false);
  }

  // Chỉ đóng khi focus sang một phần tử khác thật. Safari không focus nút lúc chạm nên
  // relatedTarget rỗng; chạm ra ngoài đã có pointerdown ở trên lo.
  return <div ref={root} className="studio-menu" onBlur={(event) => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
  }}>
    <button ref={trigger} type="button" className="studio-chip" disabled={disabled}
      aria-haspopup="menu" aria-expanded={open} aria-controls={menuId} aria-label={`${label}: ${current.label}`}
      onClick={() => setOpen((value) => !value)}
      onKeyDown={(event) => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); }
      }}>
      {icon}<span>{current.label}</span>
    </button>
    {open && <div id={menuId} role="menu" aria-label={label} onKeyDown={onMenuKey}
      className={"effort-options studio-menu-list" + (columns === 2 ? " grid" : "") + (align === "end" ? " end" : "")}>
      {options.map((item, index) => {
        const on = item.value === value;
        return <button key={String(item.value)} ref={(element) => { items.current[index] = element; }} type="button"
          role="menuitemradio" aria-checked={on} className={on ? "effort-option on" : "effort-option"}
          onClick={() => { onChange(item.value); close(); }}>
          {item.icon}
          <span className="effort-option-label">{item.label}</span>
          {on && <svg className="effort-check" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="m5 12.5 4.5 4.5L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>}
        </button>;
      })}
    </div>}
  </div>;
}
