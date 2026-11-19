import { useEffect, useRef, useState, type FormEvent, type JSX } from 'react';
import type { AuthState } from '../shared/api/api';
import { DISCORD_LOGIN_URL, GITHUB_LOGIN_URL, GOOGLE_LOGIN_URL, getAuthState, sendLoginEmail, verifyEmailCode } from '../shared/api/api';
import { DiscordIcon, GitHubIcon, GoogleIcon } from './accountUi';
import { onSignedInElsewhere } from './emailLink';

type LoginScreenProps = {
  auth: AuthState;
  authError: string | null;
  /** Bấm một lối OAuth: nhớ bookmark chat trước khi trang chuyển đi. */
  onSignIn?: () => void;
  /** Đăng nhập email xong (bấm nút trong thư ở trình duyệt này, hoặc gõ mã): App đọc lại trạng thái, không chuyển trang. */
  onSignedIn?: () => Promise<void> | void;
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
/** Tab "Kiểm tra hộp thư" hỏi lại máy chủ bấy nhiêu ms một lần, và thôi hỏi sau 15 phút (thư hết hạn sau 10 phút). */
const POLL_MS = 3000;
const POLL_FOR_MS = 15 * 60 * 1000;

/**
 * Trang đăng nhập theo mẫu AIRI (chủ web chọn "Như AIRI", bỏ Steam, ngày 19/11/2026): ô email và nút Tiếp tục, vạch
 * "hoặc", các nút Discord, Google, GitHub xếp dọc, dòng Điều khoản ở cuối. Email: máy chủ gửi thư có nút đăng nhập (như
 * AIRI, chủ web đổi từ mã sang đường dẫn cùng ngày) kèm mã 6 số. Bấm nút trong trình duyệt này thì tab "Kiểm tra hộp
 * thư" tự tiếp tục; mở thư trên máy khác thì gõ mã.
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
  const [code, setCode] = useState('');
  const [codeOpen, setCodeOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [expiresIn, setExpiresIn] = useState(600);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const emailRef = useRef<HTMLInputElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);
  const sentTitleRef = useRef<HTMLHeadingElement>(null);
  const wait = Math.max(0, Math.ceil((resendAt - now) / 1000));

  useEffect(() => {
    if (resendAt <= Date.now()) return;
    const timer = window.setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= resendAt) window.clearInterval(timer);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [resendAt]);

  // Chuyển bước thì đưa con trỏ tới bước mới. Lúc mới mở trang thì không: trên điện thoại bàn phím bật lên sẽ che các
  // nút Discord, Google, GitHub.
  const shownStep = useRef(step);
  useEffect(() => {
    if (shownStep.current === step) return;
    shownStep.current = step;
    (step === 'sent' ? sentTitleRef : emailRef).current?.focus();
  }, [step]);

  useEffect(() => {
    if (codeOpen) codeRef.current?.focus();
  }, [codeOpen]);

  // Chờ người dùng bấm nút trong thư. Bấm trong trình duyệt này thì cookie phiên mới dùng chung cho mọi tab, nên chỉ
  // cần hỏi lại /api/auth/me: tab vừa mở từ thư báo ngay qua BroadcastChannel, còn lại cứ vài giây hỏi một lần (bỏ qua
  // khi tab đang ẩn) và hỏi ngay khi người dùng quay lại tab.
  useEffect(() => {
    if (step !== 'sent' || !onSignedIn) return;
    let stopped = false;
    let checking = false;
    const check = async (force = false) => {
      if (stopped || checking || (!force && document.visibilityState === 'hidden')) return;
      checking = true;
      try {
        const state = await getAuthState();
        if (!stopped && state.authenticated) {
          stopped = true;
          await onSignedIn();
        }
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

  async function requestEmail(again: boolean) {
    const address = email.trim();
    if (!EMAIL_PATTERN.test(address)) {
      setError('Email chưa đúng dạng. Kiểm tra lại giúp mình nhé.');
      emailRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const sent = await sendLoginEmail(address);
      setExpiresIn(sent.expires_in);
      setResendAt(Date.now() + sent.resend_after * 1000);
      setNow(Date.now());
      setCode('');
      setStep('sent');
      if (again) setNotice('Đã gửi thư mới. Nút và mã trong thư cũ không dùng được nữa.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Chưa gửi được thư. Thử lại nhé.');
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(value: string) {
    if (busy) return;
    if (!/^\d{6}$/.test(value)) {
      setError('Mã gồm đúng 6 chữ số.');
      codeRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await verifyEmailCode(email.trim(), value);
      await onSignedIn?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Chưa đăng nhập được. Thử lại nhé.');
      setBusy(false);
      codeRef.current?.select();
    }
  }

  function changeEmail() {
    setStep('email');
    setCode('');
    setCodeOpen(false);
    setError(null);
    setNotice(null);
  }

  const shownError = error ?? authError;
  const errorBox = shownError && <div className="error" role="alert">{shownError}</div>;

  if (step === 'sent') {
    return (
      <div className="login">
        <div className="login-panel">
          <h1 ref={sentTitleRef} tabIndex={-1}>Kiểm tra hộp thư</h1>
          <p className="login-sub login-message">
            Mình vừa gửi đường dẫn đăng nhập tới <strong>{email.trim()}</strong>. Mở thư và bấm nút trong đó; trang này
            sẽ tự tiếp tục khi bạn bấm. Thư dùng được trong {Math.round(expiresIn / 60)} phút.
          </p>
          {notice && <p className="login-notice" role="status">{notice}</p>}
          {codeOpen ? (
            <form className="login-stack" onSubmit={(event: FormEvent) => { event.preventDefault(); void submitCode(code); }}>
              <div className="login-field">
                <label htmlFor="login-code">Mã 6 số trong thư</label>
                <input
                  ref={codeRef}
                  id="login-code"
                  className="login-input login-code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  placeholder="······"
                  value={code}
                  aria-invalid={!!error}
                  readOnly={busy}
                  onChange={event => {
                    const digits = event.target.value.replace(/\D/g, '').slice(0, 6);
                    setCode(digits);
                    if (digits.length === 6) void submitCode(digits);
                  }}
                />
              </div>
              {errorBox}
              <button className="login-button login-primary" type="submit" disabled={busy}>
                {busy ? 'Đang kiểm tra…' : 'Đăng nhập'}
              </button>
            </form>
          ) : (
            <>
              {errorBox}
              <button type="button" className="login-link login-center" onClick={() => setCodeOpen(true)}>
                Mở thư trên máy khác? Nhập mã trong thư
              </button>
            </>
          )}
          <p className="login-hint">Không thấy thư? Xem cả mục Spam hoặc Quảng cáo.</p>
          <div className="login-links">
            <button type="button" className="login-link" onClick={changeEmail} disabled={busy}>Quay lại đăng nhập</button>
            <button type="button" className="login-link" onClick={() => void requestEmail(true)} disabled={busy || wait > 0}>
              {wait > 0 ? `Gửi lại thư sau ${wait} giây` : 'Gửi lại thư'}
            </button>
          </div>
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
              <form className="login-stack" noValidate onSubmit={event => { event.preventDefault(); void requestEmail(false); }}>
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
