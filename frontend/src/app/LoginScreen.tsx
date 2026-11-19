import { useEffect, useRef, useState, type JSX } from 'react';
import type { AuthState } from '../shared/api/api';
import { DISCORD_LOGIN_URL, GITHUB_LOGIN_URL, GOOGLE_LOGIN_URL, emailLoginStatus, sendLoginEmail } from '../shared/api/api';
import { DiscordIcon, GitHubIcon, GoogleIcon } from './accountUi';
import { onSignedInElsewhere } from './emailLink';

type LoginScreenProps = {
  auth: AuthState;
  authError: string | null;
  /** Bấm một lối OAuth: nhớ bookmark chat trước khi trang chuyển đi. */
  onSignIn?: () => void;
  /** Thư đăng nhập đã được bấm (ở trình duyệt này hay máy khác): máy chủ đã đặt phiên, App đọc lại trạng thái. */
  onSignedIn?: () => Promise<void> | void;
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
/** Trang "Kiểm tra hộp thư" hỏi máy chủ bấy nhiêu ms một lần, và thôi hỏi sau 15 phút (thư hết hạn sau 10 phút). */
const POLL_MS = 3000;
const POLL_FOR_MS = 15 * 60 * 1000;

/**
 * Trang đăng nhập theo mẫu AIRI (chủ web chọn "Như AIRI", bỏ Steam, ngày 19/11/2026): ô email và nút Tiếp tục, vạch
 * "hoặc", các nút Discord, Google, GitHub xếp dọc, dòng Điều khoản ở cuối. Email: máy chủ gửi thư có nút đăng nhập;
 * trang "Kiểm tra hộp thư" (gọn như AIRI) tự tiếp tục khi nút được bấm, ở trình duyệt này hay trên máy khác.
 */
export default function LoginScreen({ auth, authError, onSignIn, onSignedIn }: LoginScreenProps) {
  const providers = auth.providers;
  const emailEnabled = auth.login_configured && providers?.email === true;
  const oauth = [
    providers?.discord !== false && { name: 'Discord', href: DISCORD_LOGIN_URL, icon: <DiscordIcon /> },
    providers?.google && { name: 'Google', href: GOOGLE_LOGIN_URL, icon: <GoogleIcon /> },
    providers?.github && { name: 'GitHub', href: GITHUB_LOGIN_URL, icon: <GitHubIcon /> },
  ].filter((item): item is { name: string; href: string; icon: JSX.Element } => !!item);

  const [step, setStep] = useState<'email' | 'sent'>('email');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const sentTitleRef = useRef<HTMLHeadingElement>(null);

  // Chuyển bước thì đưa con trỏ tới bước mới. Lúc mới mở trang thì không: trên điện thoại bàn phím bật lên sẽ che các
  // nút Discord, Google, GitHub.
  const shownStep = useRef(step);
  useEffect(() => {
    if (shownStep.current === step) return;
    shownStep.current = step;
    (step === 'sent' ? sentTitleRef : emailRef).current?.focus();
  }, [step]);

  // Chờ nút trong thư được bấm. Máy chủ biết thư nào của trình duyệt này qua cookie yêu cầu đặt lúc gửi thư; khi thư
  // được bấm (cùng trình duyệt, hoặc xác nhận từ máy khác) thì lần hỏi kế tiếp nhận phiên. Hỏi vài giây một lần khi tab
  // đang hiện, hỏi ngay khi tab mở từ thư báo qua BroadcastChannel hoặc khi người dùng quay lại tab.
  useEffect(() => {
    if (step !== 'sent') return;
    let stopped = false;
    let checking = false;
    const check = async (force = false) => {
      if (stopped || checking || (!force && document.visibilityState === 'hidden')) return;
      checking = true;
      try {
        const { state } = await emailLoginStatus();
        if (stopped || state === 'waiting') return;
        stopped = true;
        if (state === 'signed_in') {
          await onSignedIn?.();
          return;
        }
        setError(state === 'denied'
          ? 'Yêu cầu đăng nhập đã bị từ chối từ thư. Gửi lại nếu đó là bạn.'
          : 'Đường dẫn đăng nhập đã hết hạn. Gửi lại thư nhé.');
        setStep('email');
      } catch { /* Lần sau hỏi lại. */ } finally {
        checking = false;
      }
    };
    const timer = window.setInterval(() => void check(), POLL_MS);
    const deadline = window.setTimeout(() => { stopped = true; window.clearInterval(timer); }, POLL_FOR_MS);
    const unsubscribe = onSignedInElsewhere(() => void check(true));
    const onVisible = () => void check();
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      window.clearTimeout(deadline);
      unsubscribe();
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
    };
  }, [step, onSignedIn]);

  async function requestEmail() {
    const address = email.trim();
    if (!EMAIL_PATTERN.test(address)) {
      setError('Email chưa đúng dạng. Kiểm tra lại giúp mình nhé.');
      emailRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await sendLoginEmail(address);
      setStep('sent');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Chưa gửi được thư. Thử lại nhé.');
    } finally {
      setBusy(false);
    }
  }

  const shownError = error ?? authError;
  const errorBox = shownError && <div className="error" role="alert">{shownError}</div>;

  if (step === 'sent') {
    return (
      <div className="login">
        <div className="login-panel login-notice-panel">
          <h1 ref={sentTitleRef} tabIndex={-1}>Kiểm tra hộp thư</h1>
          <p className="login-message">
            Mình đã gửi đường dẫn đăng nhập tới {email.trim()}. Mở thư để hoàn tất — trang này sẽ tự tiếp tục sau khi bạn
            bấm đường dẫn.
          </p>
          <button type="button" className="login-back" onClick={() => setStep('email')}>Quay lại đăng nhập</button>
        </div>
      </div>
    );
  }

  return (
    <div className="login">
      <div className="login-panel">
        <h1>Đăng nhập</h1>
        <p className="login-sub">
          {emailEnabled ? 'Nhập email để đăng nhập hoặc tạo tài khoản.' : 'Chọn cách đăng nhập hoặc tạo tài khoản.'}
        </p>

        {/* Gọi /api/auth/me hỏng thì login_configured là false. Không có cờ này thì màn hình bày ra nút bấm không ăn
            thua mà chẳng báo gì — đúng cái bẫy làm người ta tưởng nút Google bị thiếu. */}
        {auth.login_configured ? (
          <>
            {emailEnabled && (
              <form className="login-stack" noValidate onSubmit={event => { event.preventDefault(); void requestEmail(); }}>
                <div className="login-field">
                  <label htmlFor="login-email">Email</label>
                  <input
                    ref={emailRef}
                    id="login-email"
                    className="login-input"
                    type="email"
                    autoComplete="email"
                    placeholder="ban@vidu.com"
                    value={email}
                    aria-invalid={!!error}
                    readOnly={busy}
                    onChange={event => setEmail(event.target.value)}
                  />
                </div>
                {errorBox}
                <button className="login-button" type="submit" disabled={busy}>{busy ? 'Đang gửi…' : 'Tiếp tục'}</button>
              </form>
            )}
            {!emailEnabled && errorBox}
            {emailEnabled && oauth.length > 0 && <div className="login-divider"><span>hoặc</span></div>}
            {oauth.length > 0 && (
              <div className="login-stack">
                {oauth.map(item => (
                  <a key={item.name} className="login-button" href={item.href} onClick={onSignIn}
                    aria-label={`Đăng nhập bằng ${item.name}`}>
                    {item.icon}
                    {item.name}
                  </a>
                ))}
              </div>
            )}
          </>
        ) : (
          <>
            {errorBox}
            <div className="error">
              Chưa kết nối được dịch vụ đăng nhập. Thử tải lại trang hoặc báo người quản trị nhé.
            </div>
          </>
        )}

        <p className="login-terms">
          Khi tiếp tục, bạn đồng ý với <a href="/docs/dieu-khoan/" target="_blank" rel="noreferrer">Điều khoản</a> và{' '}
          <a href="/docs/quyen-rieng-tu/" target="_blank" rel="noreferrer">Chính sách quyền riêng tư</a> của Peto.
        </p>
      </div>
    </div>
  );
}
