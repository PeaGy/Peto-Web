import { useEffect, useRef, useState } from 'react';
import { GlobeIcon } from './WebSources';

export default function ComposerMenu({ disabled, webDisabled, onToggleWeb, onAttach }: {
  disabled: boolean;
  webDisabled: boolean;
  onToggleWeb: () => void;
  onAttach: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const firstItem = useRef<HTMLButtonElement>(null);

  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => {
    if (!open) return;
    firstItem.current?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [open]);

  function close() { setOpen(false); trigger.current?.focus(); }

  return <div ref={root} className="composer-menu" onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
  }}>
    <button ref={trigger} type="button" className="icon-btn composer-plus" disabled={disabled}
      aria-label="Thêm ảnh và tùy chọn" aria-expanded={open} aria-controls="composer-options"
      title={webDisabled ? 'Thêm ảnh và tùy chọn · Tìm web đang tắt' : 'Thêm ảnh và tùy chọn'} onClick={() => setOpen((value) => !value)}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
      {webDisabled && <span className="web-off-dot" aria-hidden="true" />}
    </button>
    {open && <div id="composer-options" className="composer-options" role="group" aria-label="Tùy chọn tin nhắn">
      <button ref={firstItem} type="button" onClick={() => { close(); onAttach(); }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4" stroke="currentColor" strokeWidth="1.6" /><circle cx="8" cy="8" r="1.5" fill="currentColor" /><path d="m4 17 5-5 4 4 3-3 5 5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /></svg>
        <span><strong>Thêm ảnh hoặc tệp</strong><small>Chọn từ thiết bị của bạn</small></span>
      </button>
      <button type="button" onClick={() => { onToggleWeb(); close(); }}>
        <GlobeIcon /><span><strong>{webDisabled ? 'Bật tìm kiếm web' : 'Tắt tìm kiếm web'}</strong><small>{webDisabled ? 'Đang tắt · bật lại để tự động tra cứu' : 'Đang tự động tìm khi cần'}</small></span>
      </button>
    </div>}
  </div>;
}
