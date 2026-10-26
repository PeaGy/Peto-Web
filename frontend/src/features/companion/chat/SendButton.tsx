/**
 * Nút Gửi tròn của ô nhắn Companion, như send-button.vue và use-hover-menu.ts của AIRI: bấm là gửi; rê chuột lên 600 ms,
 * chuột phải hay mũi tên lên thì mở menu chọn phím gửi; rời chuột khỏi nút và menu 300 ms thì đóng.
 */
import { useEffect, useRef, useState } from 'react';
import { ArrowUpIcon, CheckIcon } from './chatIcons';
import { SEND_MODE_LABELS, SEND_MODES, setSendMode, useSendMode } from './sendMode';

const OPEN_DELAY = 600;
const CLOSE_DELAY = 300;

export function SendButton({ disabled, className, onSend }: { disabled: boolean; className: string; onSend: () => void }) {
  const mode = useSendMode();
  const [open, setOpen] = useState(false);
  const opening = useRef(0);
  const closing = useRef(0);
  const root = useRef<HTMLDivElement>(null);
  const hoverable = typeof window.matchMedia === 'function' && window.matchMedia('(hover: hover) and (pointer: fine)').matches;

  useEffect(() => () => { window.clearTimeout(opening.current); window.clearTimeout(closing.current); }, []);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const keys = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.stopPropagation(); setOpen(false); root.current?.querySelector<HTMLButtonElement>('.cchat-send')?.focus(); }
    };
    document.addEventListener('pointerdown', outside, true);
    document.addEventListener('keydown', keys, true);
    return () => {
      document.removeEventListener('pointerdown', outside, true);
      document.removeEventListener('keydown', keys, true);
    };
  }, [open]);

  const enter = () => {
    window.clearTimeout(closing.current);
    if (!open && hoverable) opening.current = window.setTimeout(() => setOpen(true), OPEN_DELAY);
  };
  const leave = () => {
    window.clearTimeout(opening.current);
    if (open) closing.current = window.setTimeout(() => setOpen(false), CLOSE_DELAY);
  };
  const openNow = () => {
    window.clearTimeout(opening.current);
    setOpen(true);
    requestAnimationFrame(() => root.current?.querySelector<HTMLButtonElement>('[role="menuitemradio"][aria-checked="true"]')?.focus());
  };

  return (
    <div ref={root} className="cchat-send-wrap" onPointerEnter={enter} onPointerLeave={leave}>
      {/* Không có chú thích rê chuột: rê lâu là mở menu phím gửi, hai lớp nổi chồng lên nhau. */}
      <button type="button" className={`cchat-send ${className}`} disabled={disabled} aria-label="Gửi"
        onClick={() => { window.clearTimeout(opening.current); setOpen(false); onSend(); }}
        onContextMenu={event => { event.preventDefault(); openNow(); }}
        onKeyDown={event => { if (event.key === 'ArrowUp') { event.preventDefault(); openNow(); } }}>
        <ArrowUpIcon />
      </button>
      {open && (
        <div role="menu" aria-label="Phím gửi" className="popup-menu cchat-send-menu">
          <p className="cchat-send-menu-title">Phím gửi</p>
          {SEND_MODES.map(item => (
            <button key={item} type="button" role="menuitemradio" aria-checked={mode === item}
              onKeyDown={event => {
                const items = [...(root.current?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]') ?? [])];
                const index = items.indexOf(event.currentTarget);
                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                  event.preventDefault();
                  items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
                }
              }}
              onClick={() => setSendMode(item)}>
              <span>{SEND_MODE_LABELS[item]}</span>
              {mode === item && <CheckIcon />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
