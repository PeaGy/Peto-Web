import { useState, type FormEvent } from 'react';
import { confirmPasswordReset } from '../shared/api/api';
import { PASSWORD_MIN, passwordProblem } from './passwordRules';

type Props = {
  token: string;
  /** "Đi tới đăng nhập": về trang Đăng nhập. */
  onDone: () => void;
};

/** Trang mở từ nút "Đặt lại mật khẩu" trong thư, như "Set a new password" và "Password updated" của AIRI. */
export default function ResetPasswordScreen({ token, onDone }: Props) {
  const [password, setPassword] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(token ? null
    : 'Đường dẫn đặt lại mật khẩu không hợp lệ. Gửi lại từ trang đăng nhập nhé.');
  const [done, setDone] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const problem = passwordProblem(password, again);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await confirmPasswordReset(token, password);
      setDone(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Chưa đổi được mật khẩu. Thử lại nhé.');
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="login">
        <div className="login-panel login-notice-panel">
          <h1>Đã đổi mật khẩu</h1>
          <p className="login-message">Mật khẩu của bạn đã được cập nhật. Đăng nhập bằng mật khẩu mới nhé.</p>
          <button className="login-button login-compact" type="button" onClick={onDone}>Đi tới đăng nhập</button>
        </div>
      </div>
    );
  }

  return (
    <div className="login">
      <form className="login-panel" noValidate onSubmit={event => void submit(event)}>
        <h1 className="login-title-small">Đặt mật khẩu mới</h1>
        {error && <p className="login-error" role="alert">{error}</p>}
        <div className="login-field">
          <label htmlFor="reset-password">Mật khẩu mới <span className="login-required" aria-hidden="true">*</span></label>
          <input id="reset-password" className="login-input" type="password" autoComplete="new-password" required
            placeholder={`Ít nhất ${PASSWORD_MIN} ký tự`} value={password} readOnly={busy}
            onChange={event => setPassword(event.target.value)} />
        </div>
        <div className="login-field">
          <label htmlFor="reset-again">Nhập lại mật khẩu mới <span className="login-required" aria-hidden="true">*</span></label>
          <input id="reset-again" className="login-input" type="password" autoComplete="new-password" required
            placeholder="Nhập lại mật khẩu mới" value={again} readOnly={busy}
            onChange={event => setAgain(event.target.value)} />
        </div>
        <button className="login-button" type="submit" disabled={busy || !token}>
          {busy ? 'Đang lưu…' : 'Cập nhật mật khẩu'}
        </button>
      </form>
    </div>
  );
}
