import { useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { deleteAccount, UnauthorizedError, type AccountUser } from '../../shared/api/api';
import { SettingsGroup, SettingsIcon, SettingsRow } from './settingsUi';
import './accountDeletion.css';

// Xóa tài khoản (G5, 20/11/2026). Bảng xác nhận theo thiết kế chủ web gửi: tiêu đề cảnh báo, danh sách những gì mất,
// Peto ngồi bên phải, gõ "XÓA" rồi mới bấm được. Xóa ngay, không có thời gian chờ. Tài khoản quản trị bị chặn ở cả hai
// phía (máy chủ trả 403).

export const CONFIRM_WORD = 'XÓA';

/** Giống `features.accounts.deletion.confirmed` ở máy chủ: bỏ khoảng trắng, không phân biệt hoa thường, dấu tổ hợp. */
export function matchesConfirmWord(text: string): boolean {
  return text.trim().normalize('NFC').toUpperCase() === CONFIRM_WORD;
}

type Mood = 'sad' | 'down' | 'happy';
const MOODS: Mood[] = ['sad', 'down', 'happy'];

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>;
}

const ICON_CHAT = <Icon><path d="M8 11v.01M12 11v.01M16 11v.01" /><path d="M18 4a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3h-5l-5 3v-3H6a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z" /></Icon>;
const ICON_CUBE = <Icon><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" /><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" /></Icon>;
const ICON_LINK = <Icon><path d="M9 15l6-6" /><path d="M11 6l.46-.54a5 5 0 0 1 7.08 7.08l-.54.46" /><path d="M13 18l-.4.53a5.07 5.07 0 0 1-7.12 0 4.97 4.97 0 0 1 0-7.07l.52-.46" /></Icon>;
const ICON_GOOGLE = <Icon><path d="M20.94 11a9 9 0 1 1-3.28-6l-2.66 2.4a5.5 5.5 0 1 0 2.12 6.6H13v-3z" /></Icon>;
const ICON_DISCORD = <Icon><path d="M8 12a1 1 0 1 0 2 0 1 1 0 0 0-2 0M14 12a1 1 0 1 0 2 0 1 1 0 0 0-2 0" /><path d="M15.5 17c0 1 1.5 3 2 3 1.5 0 2.83-1.67 3.5-3 .67-1.67.5-5.83-1.5-11.5-1.46-1.07-3-1.4-4.5-1.5l-1 2.5M8.5 17c0 1-1.36 3-1.83 3-1.39 0-2.62-1.67-3.17-3-.6-1.67-.46-5.83 1.37-11.5C6.21 4.43 7.58 4.1 9 4l1 2.5" /><path d="M7 16.5c3.5 1 6.5 1 10 0" /></Icon>;
const ICON_WARNING = <Icon size={30}><path d="M12 9v4" /><path d="M10.36 3.59L2.26 17.13a1.91 1.91 0 0 0 1.63 2.87h16.22a1.91 1.91 0 0 0 1.63-2.87L13.64 3.59a1.91 1.91 0 0 0-3.28 0z" /><path d="M12 16h.01" /></Icon>;
const ICON_BACK = <Icon><path d="M5 12h14M5 12l6 6M5 12l6-6" /></Icon>;

/** Mục Cài đặt → Tài khoản: các hàng cũ (`children`) rồi hàng Xóa tài khoản; bấm vào thì cả mục thành bảng xác nhận. */
export default function AccountSettings({ user, disabled, onUnauthorized, onDeleted, children }: {
  user?: AccountUser;
  /** Đang trả lời hay đang xóa hội thoại: chưa cho mở bảng xóa. */
  disabled: boolean;
  onUnauthorized: () => void;
  onDeleted: () => void;
  children: ReactNode;
}) {
  const [confirming, setConfirming] = useState(false);
  if (confirming) {
    return <DeletePanel user={user} onBack={() => setConfirming(false)} onUnauthorized={onUnauthorized} onDeleted={onDeleted} />;
  }
  const admin = !!user?.is_owner;
  return (
    <SettingsGroup>
      {children}
      <SettingsRow label="Xóa tài khoản"
        desc={admin ? 'Tài khoản quản trị không xóa được ở đây.' : 'Xóa vĩnh viễn tài khoản và mọi dữ liệu của bạn trên Peto.'}>
        {!admin && (
          <button type="button" className="settings-button danger" disabled={disabled} onClick={() => setConfirming(true)}>
            Xóa tài khoản
          </button>
        )}
      </SettingsRow>
    </SettingsGroup>
  );
}

function DeletePanel({ user, onBack, onUnauthorized, onDeleted }: {
  user?: AccountUser;
  onBack: () => void;
  onUnauthorized: () => void;
  onDeleted: () => void;
}) {
  const inputId = useId();
  const errorId = useId();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [cancelHover, setCancelHover] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const ready = matchesConfirmWord(text);
  // Peto buồn khi mở bảng, gục mặt khi đã gõ xong chữ "XÓA", vui khi con trỏ hay phím Tab đặt lên nút Hủy.
  const mood: Mood = cancelHover ? 'happy' : ready || busy ? 'down' : 'sad';
  const discord = user?.provider === 'discord';

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!ready) {
      setError(`Gõ "${CONFIRM_WORD}" để xác nhận.`);
      input.current?.focus();
      return;
    }
    setBusy(true);
    setError('');
    try {
      await deleteAccount(text);
      onDeleted();
    } catch (err) {
      setBusy(false);
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setError(err instanceof Error && !(err instanceof TypeError) ? err.message : 'Chưa xóa được tài khoản. Thử lại nhé.');
    }
  }

  return (
    <form className="account-delete" onSubmit={submit} noValidate>
      <div className="account-delete-head">
        <button type="button" className="account-delete-back" aria-label="Quay lại Tài khoản" disabled={busy} onClick={onBack}>
          {ICON_BACK}
        </button>
        <h3>Xóa tài khoản</h3>
      </div>
      <div className="account-delete-body">
        <div className="account-delete-main">
          <div className="account-delete-warning">
            <span className="account-delete-warning-icon">{ICON_WARNING}</span>
            <div>
              <h4>Bạn có chắc chắn muốn xóa tài khoản?</h4>
              <p>Hành động này là vĩnh viễn và không thể khôi phục.</p>
            </div>
          </div>
          <ul className="account-delete-list" aria-label="Những gì sẽ bị xóa">
            <li>{ICON_CHAT}<span>Hội thoại, dự án, tệp và ảnh đã tạo</span></li>
            <li>{ICON_CUBE}<span>Trí nhớ, hồ sơ và nhân vật Companion</span></li>
            <li>{ICON_LINK}<span>Kết nối GitHub, máy Peto Agent</span></li>
            {discord
              ? <li>{ICON_DISCORD}<span>Đăng nhập Discord trên Peto Web. Trí nhớ của bot Discord không bị xóa ở đây.</span></li>
              : <li>{ICON_GOOGLE}<span>Đăng nhập Google, GitHub và email đã gộp</span></li>}
          </ul>
        </div>
        <div className="account-delete-art" data-mood={mood} aria-hidden="true">
          {MOODS.map((name) => (
            <img key={name} className={name === mood ? 'on' : undefined} src={`/account-assets/peto-delete-${name}.webp`}
              alt="" width={512} height={426} draggable={false} />
          ))}
        </div>
      </div>
      <div className="account-delete-confirm">
        <label htmlFor={inputId}>Xác nhận để tiếp tục</label>
        <div className="account-delete-actions">
          <input ref={input} id={inputId} className="account-delete-input" value={text} disabled={busy}
            placeholder={`Nhập “${CONFIRM_WORD}” để xác nhận`} autoComplete="off" autoCapitalize="characters"
            spellCheck={false} aria-invalid={error ? true : undefined} aria-describedby={error ? errorId : undefined}
            onChange={(event) => { setText(event.target.value); setError(''); }} />
          <div className="account-delete-buttons">
            <button type="button" className="account-delete-cancel" disabled={busy} onClick={onBack}
              onPointerEnter={() => setCancelHover(true)} onPointerLeave={() => setCancelHover(false)}
              onFocus={() => setCancelHover(true)} onBlur={() => setCancelHover(false)}>
              Hủy
            </button>
            <button type="submit" className="account-delete-submit" disabled={!ready || busy}>
              <SettingsIcon name="trash" size={18} />
              {busy ? 'Đang xóa…' : 'Xóa tài khoản'}
            </button>
          </div>
        </div>
        {error && <p id={errorId} className="account-delete-error" role="alert">{error}</p>}
      </div>
    </form>
  );
}
