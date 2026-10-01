import type { AccountUser, AppInfo } from '../shared/api/api';

/** Avatar của Peto: ảnh thật từ Discord application, chữ cái đầu nếu chưa có. */
export function DiscordIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M20.317 4.37a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.292a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.099.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
  </svg>;
}

export function GoogleIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M21.6 12.2c0-.7-.06-1.4-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.5h3.24c1.89-1.74 2.98-4.3 2.98-7.35Z" fill="#4285F4" />
    <path d="M12 22c2.7 0 4.965-.9 6.62-2.43l-3.24-2.51c-.9.6-2.05.96-3.38.96-2.6 0-4.8-1.76-5.59-4.12H3.06v2.59A10 10 0 0 0 12 22Z" fill="#34A853" />
    <path d="M6.41 13.9a6 6 0 0 1 0-3.83V7.48H3.06a10 10 0 0 0 0 9.01l3.35-2.6Z" fill="#FBBC05" />
    <path d="M12 5.95c1.47 0 2.78.5 3.82 1.5l2.86-2.86C16.96 2.99 14.7 2 12 2a10 10 0 0 0-8.94 5.48l3.35 2.6C7.2 7.7 9.4 5.95 12 5.95Z" fill="#EA4335" />
  </svg>;
}

export function GuestIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="12" cy="8" r="3.6" stroke="currentColor" strokeWidth="1.7" />
    <path d="M4.8 20a7.2 7.2 0 0 1 14.4 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
  </svg>;
}

/** Avatar người dùng. Khách không có ảnh nên rơi về chữ cái đầu. */
export function AccountAvatar({ user, size }: { user?: AccountUser; size: number }) {
  if (user?.avatar_url) {
    return <img className="account-avatar avatar-image" src={user.avatar_url}
      alt="" width={size} height={size} />;
  }
  return <span className="account-avatar account-initial" style={{ width: size, height: size }} aria-hidden="true">
    {(user?.display_name || "?").charAt(0).toUpperCase()}
  </span>;
}

/**
 * Dòng phụ dưới tên ở ô tài khoản, như chữ "Plus" của ChatGPT. Tài khoản Google có tên người dùng trùng tên hiển thị,
 * nên ghi nơi đăng nhập thay vào.
 */
export function accountSubtitle(user?: AccountUser): string {
  if (user?.provider === "guest") return "Tài khoản khách";
  if (user?.provider === "google") return "Google";
  return user?.username ? `@${user.username}` : "Discord";
}

/** Dòng dưới tên trong mục Tài khoản của Cài đặt. */
export function accountLine(user?: AccountUser): string {
  if (user?.provider === "guest") return "Tài khoản khách, chỉ có trên trình duyệt này";
  if (user?.provider === "google") return "Đăng nhập bằng Google";
  return `${user?.username ? `@${user.username} · ` : ""}Đăng nhập bằng Discord`;
}

export function PetoAvatar({ info, big }: { info: AppInfo | null; big?: boolean }) {
  const className = big ? "avatar big" : "avatar";
  if (info?.avatar_url) {
    return (
      <img
        className={`${className} avatar-image`}
        src={info.avatar_url}
        alt={info.name}
        width={big ? 56 : 34}
        height={big ? 56 : 34}
      />
    );
  }
  return <span className={className}>{(info?.name ?? "Peto").charAt(0)}</span>;
}

