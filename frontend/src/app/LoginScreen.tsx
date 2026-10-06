import type { AppInfo, AuthState } from '../shared/api/api';
import { DISCORD_LOGIN_URL, GITHUB_LOGIN_URL, GOOGLE_LOGIN_URL } from '../shared/api/api';
import { PetoAvatar, DiscordIcon, GitHubIcon, GoogleIcon } from './accountUi';

type LoginScreenProps = { auth: AuthState; appInfo: AppInfo | null; authError: string | null };

export default function LoginScreen({ auth, appInfo, authError }: LoginScreenProps) {
    return (
      <div className="login">
        <div className="login-card">
          <PetoAvatar info={appInfo} big />
          <h1>{appInfo?.name ?? "Peto"}</h1>
          <p className="login-sub">
            Đăng nhập để Peto biết bạn là ai.
          </p>

          {authError && (
            <div className="error" role="alert">
              {authError}
            </div>
          )}

          {/* Gọi /api/auth/me hỏng thì login_configured là false. Không có
              cờ này thì màn hình bày ra nút bấm không ăn thua mà chẳng báo gì —
              đúng cái bẫy làm người ta tưởng nút Google bị thiếu. */}
          {auth.login_configured ? (
            <>
              {auth.providers?.discord !== false && (
                <a className="discord-button" href={DISCORD_LOGIN_URL}>
                  <DiscordIcon />
                  Đăng nhập bằng Discord
                </a>
              )}

              {(auth.providers?.google || auth.providers?.github) && <>
              <div className="login-divider">
                <span>Đăng nhập bằng cách khác</span>
              </div>

              <div className="login-alts">
                {auth.providers?.google && (
                  <a className="alt-login" href={GOOGLE_LOGIN_URL}>
                    <GoogleIcon />
                    Google
                  </a>
                )}
                {auth.providers?.github && (
                  <a className="alt-login" href={GITHUB_LOGIN_URL}>
                    <GitHubIcon />
                    GitHub
                  </a>
                )}
              </div>
              </>}
            </>
          ) : (
            <div className="error">
              Chưa kết nối được dịch vụ đăng nhập. Thử tải lại trang hoặc báo
              người quản trị nhé.
            </div>
          )}

          <p className="login-note">
            Peto chỉ đọc tên và ảnh đại diện của bạn.
          </p>
        </div>
      </div>
    );
}
