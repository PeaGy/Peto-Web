import { useEffect, useRef, useState } from 'react';
import { GlobeIcon } from './WebSources';

/** Mục "Chế độ nhập vai": chỉ có khi hội thoại chưa bắt đầu, vì chế độ được giữ suốt hội thoại. */
export interface RoleplayOption {
  active: boolean;
  /** Lý do không bật được (tài khoản khách); null thì bật được. */
  unavailable: string | null;
  onToggle: () => void;
}

function MaskIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M4 6c2.5-1.3 5.2-2 8-2s5.5.7 8 2v5c0 5-3.6 9-8 9s-8-4-8-9V6Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    <path d="M8.5 11c.8-.6 1.7-.6 2.5 0M13 11c.8-.6 1.7-.6 2.5 0M9.5 15c1.5 1.1 3.5 1.1 5 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>;
}

export default function ComposerMenu({ disabled, webDisabled, onToggleWeb, onAttach, roleplay }: {
  disabled: boolean;
  webDisabled: boolean;
  onToggleWeb: () => void;
  onAttach: () => void;
  roleplay?: RoleplayOption;
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
      {roleplay && <button type="button" aria-pressed={roleplay.active} disabled={roleplay.unavailable !== null}
        onClick={() => { close(); roleplay.onToggle(); }}>
        <MaskIcon /><span><strong>{roleplay.active ? 'Tắt chế độ nhập vai' : 'Chế độ nhập vai'}</strong>
          <small>{roleplay.unavailable ?? (roleplay.active ? 'Đang bật cho hội thoại mới này' : 'Peto nhập vai như bot Discord')}</small></span>
      </button>}
    </div>}
  </div>;
}
