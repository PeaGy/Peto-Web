import { useEffect, useRef, useState, type FormEvent, type JSX, type ReactNode } from 'react';
import type { AuthState } from '../shared/api/api';
import {
  DISCORD_LOGIN_URL, GITHUB_LOGIN_URL, GOOGLE_LOGIN_URL, checkEmail, emailLoginStatus, requestPasswordReset,
  signInWithPassword, signUpWithEmail,
} from '../shared/api/api';
import { DiscordIcon, GitHubIcon, GoogleIcon } from './accountUi';
import { onSignedInElsewhere } from './emailLink';
import { PASSWORD_MIN, passwordProblem } from './passwordRules';

type LoginScreenProps = {
  auth: AuthState;
  authError: string | null;
  /** Bấm một lối OAuth: nhớ bookmark chat trước khi trang chuyển đi. */
  onSignIn?: () => void;
  /** Đã đăng nhập bằng email (mật khẩu đúng, hoặc thư xác nhận đã được bấm): App đọc lại trạng thái, không chuyển trang. */
  onSignedIn?: () => Promise<void> | void;
};

type Step = 'email' | 'signup' | 'sent' | 'password' | 'forgot' | 'forgot-sent';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
/** Trang "Kiểm tra hộp thư" hỏi máy chủ bấy nhiêu ms một lần, và thôi hỏi sau 15 phút (thư hết hạn sau 10 phút). */
const POLL_MS = 3000;
const POLL_FOR_MS = 15 * 60 * 1000;

const reasonText = (reason: unknown, fallback: string) => reason instanceof Error ? reason.message : fallback;

/**
 * Trang đăng nhập theo các trang của AIRI (chủ web gửi mẫu ngày 19/11/2026): "Đăng nhập" (email, Tiếp tục, vạch "hoặc",
 * Discord, Google, GitHub), rồi "Tạo tài khoản" (email mới; thư xác nhận và "Kiểm tra hộp thư") hoặc "Chào mừng trở lại"
 * (mật khẩu), và "Đặt lại mật khẩu". Trang "Đặt mật khẩu mới" mở từ thư nằm ở ResetPasswordScreen.
 */
export default function LoginScreen({ auth, authError, onSignIn, onSignedIn }: LoginScreenProps) {
  const providers = auth.providers;
  const emailEnabled = auth.login_configured && providers?.email === true;
  const oauth = [
    providers?.discord !== false && { name: 'Discord', href: DISCORD_LOGIN_URL, icon: <DiscordIcon /> },
    providers?.google && { name: 'Google', href: GOOGLE_LOGIN_URL, icon: <GoogleIcon /> },
    providers?.github && { name: 'GitHub', href: GITHUB_LOGIN_URL, icon: <GitHubIcon /> },
  ].filter((item): item is { name: string; href: string; icon: JSX.Element } => !!item);

  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Email này có tài khoản nhưng chưa đặt mật khẩu (thường là Google/GitHub đã gộp email): hiện lối đặt mật khẩu.
  const [noPassword, setNoPassword] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const address = email.trim();

  // Chuyển bước thì đưa con trỏ tới ô đầu của bước mới (hoặc tiêu đề). Lúc mới mở trang thì không: trên điện thoại bàn
  // phím bật lên sẽ che các nút Discord, Google, GitHub.
  const shownStep = useRef(step);
  useEffect(() => {
    if (shownStep.current === step) return;
    shownStep.current = step;
    const panel = panelRef.current;
    (panel?.querySelector<HTMLElement>('input') ?? panel?.querySelector<HTMLElement>('h1'))?.focus();
  }, [step]);

  // Chờ nút "Xác nhận email" trong thư được bấm. Máy chủ biết thư nào của trình duyệt này qua cookie yêu cầu đặt lúc
  // gửi thư; khi thư được bấm (cùng trình duyệt, hoặc xác nhận từ máy khác) thì lần hỏi kế tiếp nhận phiên.
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
          ? 'Yêu cầu tạo tài khoản đã bị từ chối từ thư. Thử lại nếu đó là bạn.'
          : 'Đường dẫn xác nhận đã hết hạn. Tạo tài khoản lại nhé.');
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

  function go(next: Step) {
    setError(null);
    setPassword('');
    setAgain('');
    setStep(next);
  }

  async function run(work: () => Promise<void>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (reason) {
      setError(reasonText(reason, fallback));
    } finally {
      setBusy(false);
    }
  }

  function validEmail(): boolean {
    if (EMAIL_PATTERN.test(address)) return true;
    setError('Email chưa đúng dạng. Kiểm tra lại giúp mình nhé.');
    panelRef.current?.querySelector<HTMLElement>('input')?.focus();
    return false;
  }

  const onContinue = (event: FormEvent) => {
    event.preventDefault();
    setNoPassword(false);
    if (!validEmail()) return;
    void run(async () => {
      const { state } = await checkEmail(address);
      if (state === 'new') go('signup');
      else if (state === 'password') go('password');
      else {
        setNoPassword(true);
        throw new Error('Email này đã có tài khoản nhưng chưa đặt mật khẩu. Đăng nhập bằng Google hoặc GitHub bên dưới, '
          + 'hoặc đặt mật khẩu qua email.');
      }
    }, 'Chưa kiểm tra được email. Thử lại nhé.');
  };

  const onSignup = (event: FormEvent) => {
    event.preventDefault();
    const problem = passwordProblem(password, again);
    if (problem) {
      setError(problem);
      return;
    }
    void run(async () => {
      await signUpWithEmail(address, password, name.trim());
      go('sent');
    }, 'Chưa tạo được tài khoản. Thử lại nhé.');
  };

  const onPassword = (event: FormEvent) => {
    event.preventDefault();
    if (!password) {
      setError('Nhập mật khẩu của bạn nhé.');
      return;
    }
    void run(async () => {
      await signInWithPassword(address, password);
      await onSignedIn?.();
    }, 'Chưa đăng nhập được. Thử lại nhé.');
  };

  const onForgot = (event: FormEvent) => {
    event.preventDefault();
    if (!validEmail()) return;
    void run(async () => {
      await requestPasswordReset(address);
      go('forgot-sent');
    }, 'Chưa gửi được thư. Thử lại nhé.');
  };

  const shownError = error ?? (step === 'email' ? authError : null);
  const errorLine = shownError && <p className="login-error" role="alert">{shownError}</p>;
  const terms = (
    <p className="login-terms">
      Khi tiếp tục, bạn đồng ý với <a href="/docs/dieu-khoan/" target="_blank" rel="noreferrer">Điều khoản</a> và{' '}
      <a href="/docs/quyen-rieng-tu/" target="_blank" rel="noreferrer">Chính sách quyền riêng tư</a> của Peto.
    </p>
  );
  const back = (label = 'Quay lại đăng nhập') => (
    <button type="button" className="login-back" onClick={() => go('email')}>{label}</button>
  );
  const field = (id: string, label: ReactNode, input: JSX.Element) => (
    <div className="login-field">
      <label htmlFor={id}>{label}</label>
      {input}
    </div>
  );
  const passwordInput = (id: string, value: string, set: (value: string) => void, placeholder: string,
    autoComplete: string) => (
    <input id={id} className="login-input" type="password" autoComplete={autoComplete} placeholder={placeholder}
      value={value} readOnly={busy} onChange={event => set(event.target.value)} />
  );
  const shell = (children: ReactNode, notice = false) => (
    <div className="login">
      <div ref={panelRef} className={notice ? 'login-panel login-notice-panel' : 'login-panel'}>{children}</div>
    </div>
  );

  if (step === 'signup') {
    return shell(<>
      <h1>Tạo tài khoản</h1>
      <p className="login-sub">Peto sẽ tạo tài khoản mới cho {address}.</p>
      {errorLine}
      <form className="login-stack" noValidate onSubmit={onSignup}>
        {field('login-name', 'Tên hiển thị',
          <input id="login-name" className="login-input" autoComplete="nickname" maxLength={40} readOnly={busy}
            placeholder="Không bắt buộc, mặc định là phần trước @ của email" value={name}
            onChange={event => setName(event.target.value)} />)}
        {field('login-new-password', 'Tạo mật khẩu',
          passwordInput('login-new-password', password, setPassword, `Ít nhất ${PASSWORD_MIN} ký tự`, 'new-password'))}
        {field('login-again', 'Nhập lại mật khẩu',
          passwordInput('login-again', again, setAgain, 'Nhập lại mật khẩu của bạn', 'new-password'))}
        <button className="login-button" type="submit" disabled={busy}>{busy ? 'Đang tạo…' : 'Tạo tài khoản'}</button>
      </form>
      <div className="login-links login-links-end">{back('Dùng email khác')}</div>
      {terms}
    </>);
  }

  if (step === 'sent') {
    return shell(<>
      <h1 tabIndex={-1}>Kiểm tra hộp thư</h1>
      <p className="login-message">
        Mình đã gửi đường dẫn xác nhận tới {address}. Mở thư để hoàn tất tạo tài khoản — trang này sẽ tự tiếp tục sau khi
        bạn bấm đường dẫn.
      </p>
      {back()}
    </>, true);
  }

  if (step === 'password') {
    return shell(<>
      <h1>Chào mừng trở lại</h1>
      <p className="login-sub">Tiếp tục với {address}.</p>
      {errorLine}
      <form className="login-stack" noValidate onSubmit={onPassword}>
        {field('login-password', 'Mật khẩu',
          passwordInput('login-password', password, setPassword, 'Mật khẩu của bạn', 'current-password'))}
        <button className="login-button" type="submit" disabled={busy}>{busy ? 'Đang đăng nhập…' : 'Đăng nhập'}</button>
      </form>
      <div className="login-links">
        <button type="button" className="login-back" onClick={() => go('forgot')}>Quên mật khẩu?</button>
        {back('Dùng email khác')}
      </div>
      {terms}
    </>);
  }

  if (step === 'forgot') {
    return shell(<>
      <h1 className="login-title-small">Đặt lại mật khẩu</h1>
      <p className="login-message">Nhập email của tài khoản, mình sẽ gửi đường dẫn đặt lại mật khẩu.</p>
      {errorLine}
      <form className="login-stack" noValidate onSubmit={onForgot}>
        {field('login-forgot-email', <>Email <span className="login-required" aria-hidden="true">*</span></>,
          <input id="login-forgot-email" className="login-input" type="email" autoComplete="email" required
            placeholder="ban@vidu.com" value={email} readOnly={busy} onChange={event => setEmail(event.target.value)} />)}
        <button className="login-button" type="submit" disabled={busy}>
          {busy ? 'Đang gửi…' : 'Gửi đường dẫn đặt lại'}
        </button>
      </form>
      {back()}
    </>, true);
  }

  if (step === 'forgot-sent') {
    return shell(<>
      <h1 className="login-title-small" tabIndex={-1}>Đặt lại mật khẩu</h1>
      <p className="login-message">Nếu {address} khớp với một tài khoản, đường dẫn đặt lại đang được gửi tới.</p>
      {back()}
    </>, true);
  }

  return shell(<>
    <h1>Đăng nhập</h1>
    <p className="login-sub">
      {emailEnabled ? 'Nhập email để đăng nhập hoặc tạo tài khoản.' : 'Chọn cách đăng nhập hoặc tạo tài khoản.'}
    </p>
    {errorLine}

    {/* Gọi /api/auth/me hỏng thì login_configured là false. Không có cờ này thì màn hình bày ra nút bấm không ăn thua mà
        chẳng báo gì — đúng cái bẫy làm người ta tưởng nút Google bị thiếu. */}
    {auth.login_configured ? (
      <>
        {emailEnabled && (
          <form className="login-stack" noValidate onSubmit={onContinue}>
            {field('login-email', 'Email',
              <input id="login-email" className="login-input" type="email" autoComplete="email" placeholder="ban@vidu.com"
                value={email} aria-invalid={!!error} readOnly={busy}
                onChange={event => { setEmail(event.target.value); setNoPassword(false); }} />)}
            <button className="login-button" type="submit" disabled={busy}>{busy ? 'Đang kiểm tra…' : 'Tiếp tục'}</button>
            {noPassword && (
              <button type="button" className="login-back" onClick={() => go('forgot')}>Đặt mật khẩu qua email</button>
            )}
          </form>
        )}
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
      <div className="error">Chưa kết nối được dịch vụ đăng nhập. Thử tải lại trang hoặc báo người quản trị nhé.</div>
    )}

    {terms}
  </>);
}
