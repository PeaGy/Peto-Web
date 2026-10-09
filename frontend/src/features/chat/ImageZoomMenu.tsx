import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import './effortMenu.css';

const ZOOM_PRESETS = [0.25, 0.5, 1, 1.5, 2, 4, 8];

/** Menu zoom dùng cùng kiểu và cách điều khiển bàn phím với menu model của Chat. */
export default function ImageZoomMenu({ scale, fit, disabled, onZoom, onFit }: {
  scale: number; fit: boolean; disabled: boolean; onZoom: (scale: number) => void; onFit: () => void;
}) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const selected = fit ? ZOOM_PRESETS.length : ZOOM_PRESETS.findIndex(value => Math.abs(value - scale) < 0.00001);

  function close() {
    setOpen(false);
    trigger.current?.focus({ preventScroll: true });
  }

  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => {
    if (!open) return;
    items.current[selected < 0 ? 0 : selected]?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) close();
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);

  function onMenuKey(event: KeyboardEvent<HTMLDivElement>) {
    const list = items.current.filter((item): item is HTMLButtonElement => item !== null);
    const at = list.indexOf(document.activeElement as HTMLButtonElement);
    const move = (to: number) => {
      event.preventDefault();
      list[(to + list.length) % list.length]?.focus();
    };
    // Phím mũi tên trong menu không được chuyển sang ảnh khác ở khung xem.
    if (event.key !== 'Tab') event.stopPropagation();
    if (event.key === 'ArrowDown') move(at + 1);
    else if (event.key === 'ArrowUp') move(at - 1);
    else if (event.key === 'Home') move(0);
    else if (event.key === 'End') move(list.length - 1);
    else if (event.key === 'Escape') { event.preventDefault(); close(); }
    else if (event.key === 'Tab') close();
  }

  function check(on: boolean) {
    return on && <svg className="effort-check" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m5 12.5 4.5 4.5L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>;
  }

  return <div ref={root} className="effort-menu chat-image-zoom" onBlur={event => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
  }}>
    <button ref={trigger} type="button" className="chat-image-zoom-trigger" disabled={disabled}
      aria-label="Mức phóng ảnh" aria-haspopup="menu" aria-expanded={open} aria-controls={menuId}
      onClick={() => setOpen(value => !value)} onKeyDown={event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setOpen(true); }
      }}>
      <span>{Math.round(scale * 100)}%</span>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
    {open && <div id={menuId} className="effort-options chat-image-zoom-options" role="menu" aria-label="Mức phóng ảnh" onKeyDown={onMenuKey}>
      {ZOOM_PRESETS.map((value, index) => <button key={value} ref={element => { items.current[index] = element; }}
        type="button" role="menuitemradio" tabIndex={-1} aria-checked={!fit && selected === index} className="effort-option"
        onClick={() => { onZoom(value); close(); }}>
        <span className="effort-option-label">{value * 100}%</span>{check(!fit && selected === index)}
      </button>)}
      <div className="chat-image-zoom-separator" role="separator" />
      <button ref={element => { items.current[ZOOM_PRESETS.length] = element; }} type="button" role="menuitemradio"
        tabIndex={-1} aria-checked={fit} className="effort-option" onClick={() => { onFit(); close(); }}>
        <span className="effort-option-label">Vừa màn hình</span>{check(fit)}
      </button>
    </div>}
  </div>;
}
