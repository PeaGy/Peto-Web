import type { useReplyRecovery } from './useReplyRecovery';
import './replyRecovery.css';

export function ReplyRecoveryNotice({ recovery }: { recovery: ReturnType<typeof useReplyRecovery> }) {
  const text = !recovery.online ? 'Bạn đang ngoại tuyến. Bản nháp và phần trả lời đang có được giữ lại.'
    : recovery.status === 'waiting' || recovery.status === 'syncing' ? 'Đang kiểm tra phần trả lời đã lưu…'
    : recovery.status === 'recovered' ? 'Đã đồng bộ câu trả lời từ máy chủ.'
    : recovery.status === 'partial' ? 'Đã đồng bộ phần trả lời được lưu. Lượt này chưa hoàn tất.'
    : recovery.status === 'failed' ? 'Chưa lấy được câu trả lời đã lưu. Phần chữ đang có vẫn được giữ lại.' : null;
  if (!text) return null;
  return <div className="reply-recovery" role="status">
    <span>{text}</span>
    {recovery.online && recovery.status === 'failed' && <button type="button" onClick={recovery.retry}>Kiểm tra lại</button>}
    {recovery.online && !recovery.pending && <button type="button" aria-label="Đóng thông báo đồng bộ" onClick={recovery.cancel}>×</button>}
  </div>;
}
