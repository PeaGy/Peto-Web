/**
 * Đường dẫn trong thư có dạng `/#email_token=…` (xác nhận email khi tạo tài khoản) hoặc `/#reset_token=…` (đặt lại mật
 * khẩu). Phần sau dấu # không bao giờ tới máy chủ hay Cloudflare lúc tải trang; trang đọc nó ở đây, xóa khỏi thanh địa
 * chỉ ngay (trước cả router), rồi gửi lên bằng POST.
 */
const CHANNEL = 'peto-auth';
const stash: Record<'email' | 'reset', string | null> = { email: null, reset: null };

function take(kind: 'email' | 'reset'): string | null {
  const prefix = `#${kind}_token=`;
  try {
    if (window.location.hash.startsWith(prefix)) {
      const token = decodeURIComponent(window.location.hash.slice(prefix.length)).trim();
      window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search);
      stash[kind] = /^[A-Za-z0-9_-]{20,100}$/.test(token) ? token : '';
    }
  } catch { /* Địa chỉ lạ: coi như không có token. */ }
  return stash[kind];
}

/** Đọc token một lần từ địa chỉ và xóa nó khỏi lịch sử; gọi lại bao nhiêu lần cũng trả cùng token tới khi quên. */
export const takeEmailToken = () => take('email');
export const takeResetToken = () => take('reset');

export function forgetEmailToken() {
  stash.email = null;
}

export function forgetResetToken() {
  stash.reset = null;
}

/** Báo các tab Peto khác (đang chờ ở "Kiểm tra hộp thư") rằng trình duyệt này vừa đăng nhập. */
export function announceSignedIn() {
  try {
    const channel = new BroadcastChannel(CHANNEL);
    channel.postMessage('signed-in');
    channel.close();
  } catch { /* Trình duyệt cũ: tab chờ vẫn tự hỏi lại máy chủ vài giây một lần. */ }
}

export function onSignedInElsewhere(callback: () => void): () => void {
  try {
    const channel = new BroadcastChannel(CHANNEL);
    channel.onmessage = event => { if (event.data === 'signed-in') callback(); };
    return () => channel.close();
  } catch {
    return () => {};
  }
}
