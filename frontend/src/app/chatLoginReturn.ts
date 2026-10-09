import { chatId, chatRoute } from './routes';

const KEY = 'peto-chat-login-return';

/** Chỉ nhớ chat khi người dùng bắt đầu đăng nhập; không lưu tin nhắn hay thông tin xác thực. */
export function rememberChatLogin() {
  const id = chatId(window.location.pathname);
  if (!id) return;
  try { sessionStorage.setItem(KEY, chatRoute(id) + window.location.search); } catch { /* Vẫn đăng nhập được khi bộ nhớ bị chặn. */ }
}

/** Đọc một lần sau đăng nhập; chỉ chấp nhận URL chat cùng nguồn gốc. */
export function takeChatLogin(): string | null {
  try {
    const saved = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    if (!saved) return null;
    const url = new URL(saved, window.location.origin);
    const id = chatId(url.pathname);
    return url.origin === window.location.origin && id ? chatRoute(id) + url.search : null;
  } catch { return null; }
}
