/**
 * Chặn lỗi cho phần giao diện tải riêng (Tạo ảnh, Companion, Cài đặt). Tệp của phần đó có thể tải hỏng: mất mạng, hay
 * chủ web vừa deploy nên tệp cũ trang đang giữ đã bị xóa khỏi máy chủ. Không có lớp này thì React gỡ cả ứng dụng và
 * người dùng thấy trang trắng; có nó thì chỉ phần đó báo lỗi, chat vẫn dùng được.
 */
import { Component, type ReactNode } from "react";

export default class LazyBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="view-loading" role="alert">
        <p>Chưa tải được phần này. Có thể mạng chập chờn, hoặc Peto vừa được cập nhật.</p>
        <button type="button" className="settings-button" onClick={() => window.location.reload()}>Tải lại trang</button>
      </div>
    );
  }
}
