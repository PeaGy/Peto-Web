import { useEffect, useState } from 'react';
import { openEmailLink, type EmailLinkResult } from '../shared/api/api';
import { announceSignedIn } from './emailLink';

type Props = {
  token: string;
  /** Đã đăng nhập: App đọc lại trạng thái đăng nhập. */
  onSignedIn: () => Promise<void> | void;
  /** Bấm "Mở Peto" hoặc "Quay lại đăng nhập". */
  onDone: () => void;
};

type View =
  | { kind: 'checking' }
  | { kind: 'confirm'; device: string; requestedAt: number }
  | { kind: 'done'; sameBrowser: boolean }
  | { kind: 'denied' }
  | { kind: 'failed'; error: string };

// StrictMode chạy effect hai lần; mỗi token chỉ gửi đúng một yêu cầu đầu tiên.
const firstAnswers = new Map<string, Promise<EmailLinkResult>>();

const timeOf = (seconds: number) =>
  new Date(seconds * 1000).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });

/**
 * Trang mở từ nút trong thư, gọn như "Email verified" của AIRI. Mở trên máy khác với máy đang chờ thì hỏi lại một lần
 * (thiết bị và giờ yêu cầu) trước khi cho máy kia vào: thư có thể đến từ người lạ gõ email của bạn.
 */
export default function EmailLinkScreen({ token, onSignedIn, onDone }: Props) {
  const [view, setView] = useState<View>({ kind: 'checking' });
  const [busy, setBusy] = useState(false);

  async function show(result: EmailLinkResult) {
    if (result.state === 'confirm') {
      setView({ kind: 'confirm', device: result.device || 'một thiết bị khác', requestedAt: result.requested_at ?? 0 });
    } else if (result.state === 'denied') {
      setView({ kind: 'denied' });
    } else {
      announceSignedIn();
      await onSignedIn();
      setView({ kind: 'done', sameBrowser: result.same_browser === true });
    }
  }

  const fail = (reason: unknown) =>
    setView({ kind: 'failed', error: reason instanceof Error ? reason.message : 'Chưa đăng nhập được. Thử lại nhé.' });

  useEffect(() => {
    let alive = true;
    let request = firstAnswers.get(token);
    if (!request) {
      request = token ? openEmailLink(token)
        : Promise.reject(new Error('Đường dẫn đăng nhập không hợp lệ. Gửi lại thư từ trang đăng nhập nhé.'));
      firstAnswers.set(token, request);
    }
    request.then(result => { if (alive) void show(result); }, reason => { if (alive) fail(reason); });
    return () => { alive = false; };
    // show/fail chỉ đổi state của chính trang này.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function answer(action: 'confirm' | 'deny') {
    setBusy(true);
    try {
      await show(await openEmailLink(token, action));
    } catch (reason) {
      fail(reason);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login-panel login-notice-panel" aria-live="polite">
        {view.kind === 'checking' && <h1>Đang đăng nhập…</h1>}
        {view.kind === 'confirm' && <>
          <h1>Xác nhận đăng nhập</h1>
          <p className="login-message">
            Cho phép {view.device} đăng nhập vào Peto (yêu cầu lúc {timeOf(view.requestedAt)})? Chỉ xác nhận nếu chính bạn
            vừa yêu cầu trên thiết bị đó.
          </p>
          <button className="login-button login-primary" type="button" disabled={busy}
            onClick={() => void answer('confirm')}>Xác nhận</button>
          <button className="login-back" type="button" disabled={busy}
            onClick={() => void answer('deny')}>Không phải mình</button>
        </>}
        {view.kind === 'done' && <>
          <h1>Email đã xác nhận</h1>
          <p className="login-message">
            {view.sameBrowser
              ? 'Email của bạn đã được xác nhận và bạn đã đăng nhập. Bạn có thể đóng tab này.'
              : 'Thiết bị kia sẽ tự tiếp tục. Thiết bị này cũng đã đăng nhập; bạn có thể đóng tab này.'}
          </p>
          <button className="login-back" type="button" onClick={onDone}>Mở Peto</button>
        </>}
        {view.kind === 'denied' && <>
          <h1>Đã từ chối</h1>
          <p className="login-message">Không ai được đăng nhập bằng đường dẫn này. Bạn có thể đóng tab này.</p>
          <button className="login-back" type="button" onClick={onDone}>Quay lại đăng nhập</button>
        </>}
        {view.kind === 'failed' && <>
          <h1>Không đăng nhập được</h1>
          <p className="login-message" role="alert">{view.error}</p>
          <button className="login-back" type="button" onClick={onDone}>Quay lại đăng nhập</button>
        </>}
      </div>
    </div>
  );
}
