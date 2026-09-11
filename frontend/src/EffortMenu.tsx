import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

type Option<T extends string> = { value: T; label: string; hint: string };

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
    {ICONS[value]}
  </svg>;
}

/** Chọn mức suy nghĩ, dạng menu bật lên như của Grok thay cho <select> gốc. */
export default function EffortMenu<T extends string>({ value, options, disabled, onChange }: {
  value: T;
  options: Option<T>[];
  disabled: boolean;
  onChange: (value: T) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const current = options.find((item) => item.value === value) ?? options[0];

  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => {
    if (!open) return;
    // Mở ra thì đặt con trỏ bàn phím ngay vào mức đang chọn, như một select thật.
    items.current[Math.max(0, options.findIndex((item) => item.value === value))]?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);

  function close() { setOpen(false); trigger.current?.focus(); }

  function onMenuKey(event: KeyboardEvent<HTMLDivElement>) {
    const list = items.current.filter((item): item is HTMLButtonElement => item !== null);
    const at = list.indexOf(document.activeElement as HTMLButtonElement);
    const move = (to: number) => { event.preventDefault(); list[(to + list.length) % list.length]?.focus(); };
    if (event.key === 'ArrowDown') move(at + 1);
    else if (event.key === 'ArrowUp') move(at - 1);
    else if (event.key === 'Home') move(0);
    else if (event.key === 'End') move(list.length - 1);
    else if (event.key === 'Escape') { event.preventDefault(); close(); }
    else if (event.key === 'Tab') setOpen(false);
  }

  return <div ref={root} className="effort-menu" onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
  }}>
    <button ref={trigger} type="button" className="effort-trigger" disabled={disabled}
      aria-haspopup="menu" aria-expanded={open} aria-controls="effort-options"
      aria-label={`Mức suy nghĩ: ${current.label}`} title={`Mức suy nghĩ · ${current.hint}`}
      onClick={() => setOpen((value) => !value)}
      onKeyDown={(event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setOpen(true); }
      }}>
      <span>{current.label}</span>
      <svg className="effort-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
    {open && <div id="effort-options" className="effort-options" role="menu" aria-label="Mức suy nghĩ" onKeyDown={onMenuKey}>
      <p className="effort-heading" aria-hidden="true">Mức suy nghĩ</p>
      {options.map((item, index) => {
        const on = item.value === value;
        return <button key={item.value} ref={(element) => { items.current[index] = element; }} type="button"
          role="menuitemradio" aria-checked={on} className={on ? 'effort-option on' : 'effort-option'}
          title={item.hint} onClick={() => { onChange(item.value); close(); }}>
          <ModeIcon value={item.value} />
          <span className="effort-option-label">{item.label}</span>
          {on && <svg className="effort-check" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="m5 12.5 4.5 4.5L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>}
        </button>;
      })}
    </div>}
  </div>;
}
