import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { resetAvatar, uploadAvatar, UnauthorizedError, type AvatarInfo } from '../../shared/api/api';
import { SettingsIcon } from './settingsUi';

/** Menu ảnh đại diện: tải một ảnh riêng hoặc khôi phục ảnh từ tài khoản đăng nhập. */
export default function ProfileAvatar({ avatar, custom, onChanged, onUnauthorized }: {
  avatar: ReactNode; custom: boolean; onChanged: (avatar: AvatarInfo) => void; onUnauthorized: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const menuId = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  const working = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus({ preventScroll: true });
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);
  function close() { setOpen(false); trigger.current?.focus({ preventScroll: true }); }
  async function change(file?: File) {
    if (working.current) return;
    setError('');
    if (file && (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024)) {
      setError('Chọn ảnh PNG, JPEG hoặc WebP, tối đa 10 MB nhé.');
      return;
    }
    working.current = true; setBusy(true);
    try {
      const result = await (file ? uploadAvatar(file) : resetAvatar());
      if (mounted.current) onChanged(result);
    } catch (err) {
      if (!mounted.current) return;
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setError(err instanceof Error ? err.message : 'Chưa đổi được ảnh. Thử lại nhé.');
    } finally { working.current = false; if (mounted.current) setBusy(false); }
  }
  return <div className="profile-avatar-control">
    <div ref={root} className="profile-avatar-menu" onBlur={event => {
      if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
    }}>
      <button ref={trigger} type="button" className="profile-avatar-trigger" aria-label="Đổi ảnh đại diện"
        aria-haspopup="menu" aria-expanded={open} aria-controls={menuId} disabled={busy}
        onClick={() => setOpen(value => !value)} onKeyDown={event => {
          if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); setOpen(true); }
        }}>
        {avatar}<span className="profile-avatar-edit"><SettingsIcon name="pencil" size={19} /></span>
      </button>
      {open && <div id={menuId} role="menu" aria-label="Ảnh đại diện" className="profile-avatar-options" onKeyDown={event => {
        const list = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')];
        const at = list.indexOf(document.activeElement as HTMLButtonElement);
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? list.length - 1 : at + (event.key === 'ArrowDown' ? 1 : -1);
          list[(next + list.length) % list.length]?.focus();
        } else if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
        else if (event.key === 'Tab') setOpen(false);
      }}>
        <button type="button" role="menuitem" onClick={() => { close(); picker.current?.click(); }}><SettingsIcon name="photo" />Tải ảnh lên</button>
        <button type="button" role="menuitem" disabled={!custom} onClick={() => { close(); void change(); }}><SettingsIcon name="reset" />Về mặc định</button>
      </div>}
      <input ref={picker} type="file" accept="image/png,image/jpeg,image/webp" hidden aria-label="Chọn ảnh đại diện"
        onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void change(file); }} />
    </div>
    {busy && <span className="profile-avatar-status" role="status">Đang lưu ảnh…</span>}
    {error && <span className="profile-avatar-error" role="alert">{error}</span>}
  </div>;
}
