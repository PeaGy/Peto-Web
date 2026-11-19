import { useEffect, useState } from 'react';
import { openEmailLink } from '../shared/api/api';
import { announceSignedIn } from './emailLink';

type Props = {
  token: string;
  /** Đã đăng nhập: App đọc lại trạng thái đăng nhập. */
  onSignedIn: () => Promise<void> | void;
  /** Bấm "Mở Peto" hoặc "Về trang đăng nhập". */
  onDone: () => void;
};

// StrictMode chạy effect hai lần; token chỉ dùng được một lần nên mỗi token chỉ gửi đúng một yêu cầu.
const requests = new Map<string, Promise<void>>();

/** Trang mở từ nút trong thư, như "Email verified" của AIRI. */
export default function EmailLinkScreen({ token, onSignedIn, onDone }: Props) {
  const [state, setState] = useState<'checking' | 'done' | 'failed'>('checking');
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    let request = requests.get(token);
    if (!request) {
      request = token
        ? openEmailLink(token)
        : Promise.reject(new Error('Đường dẫn đăng nhập không hợp lệ. Gửi lại thư từ trang đăng nhập nhé.'));
      requests.set(token, request);
    }
    request
      .then(async () => {
        announceSignedIn();
        await onSignedIn();
        if (alive) setState('done');
      })
      .catch(reason => {
        if (!alive) return;
        setError(reason instanceof Error ? reason.message : 'Chưa đăng nhập được. Thử lại nhé.');
        setState('failed');
      });
    return () => { alive = false; };
  }, [token, onSignedIn]);

  return (
    <div className="login">
      <div className="login-panel" aria-live="polite">
        {state === 'checking' && <>
          <h1>Đang đăng nhập…</h1>
          <p className="login-sub">Đợi một chút nhé.</p>
        </>}
        {state === 'done' && <>
          <h1>Đã đăng nhập</h1>
          <p className="login-sub login-message">
            Email của bạn đã được xác nhận và bạn đã đăng nhập. Nếu trang đăng nhập còn mở ở tab khác, nó đã tự tiếp tục;
            bạn có thể đóng tab này.
          </p>
          <button className="login-button login-primary" type="button" onClick={onDone}>Mở Peto</button>
        </>}
        {state === 'failed' && <>
          <h1>Chưa đăng nhập được</h1>
          <div className="error" role="alert">{error}</div>
          <button className="login-button" type="button" onClick={onDone}>Về trang đăng nhập</button>
        </>}
      </div>
    </div>
  );
}
