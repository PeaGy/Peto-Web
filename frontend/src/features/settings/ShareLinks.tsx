import { useEffect, useState } from 'react';
import { deleteShare, listShares, shareUrl, UnauthorizedError, type ShareLink } from '../../shared/api/api';
import './archive.css';
import { NEW_TAB } from '../../shared/ui/newTab';

const day = (seconds: number) => {
  const date = new Date(seconds * 1000);
  return `${date.getDate()}/${date.getMonth() + 1}/${date.getFullYear()}`;
};

/**
 * Cài đặt → Link chia sẻ (28/11/2026): mọi link đang mở được, mở xem, chép hay xóa (thu hồi). Xóa xong link hết mở được
 * ngay; hội thoại gốc giữ nguyên.
 */
export default function ShareLinks({ open, onUnauthorized }: { open: boolean; onUnauthorized: () => void }) {
  const [items, setItems] = useState<ShareLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true); setError('');
    void listShares(controller.signal).then(list => { if (!controller.signal.aborted) setItems(list); }).catch(err => {
      if (controller.signal.aborted) return;
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setError('Chưa tải được danh sách link. Hãy thử lại.');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [open, revision, onUnauthorized]);
  useEffect(() => { if (!open) setConfirm(null); }, [open]);

  async function remove(item: ShareLink) {
    setBusy(true); setError('');
    try {
      await deleteShare(item.id);
      setItems(current => current.filter(row => row.id !== item.id));
      setConfirm(null);
    } catch (err) {
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setError(err instanceof Error && !(err instanceof TypeError) ? err.message : 'Chưa xóa được link. Hãy thử lại.');
    } finally { setBusy(false); }
  }

  async function copy(item: ShareLink) {
    try { await navigator.clipboard.writeText(shareUrl(item.id)); setCopied(item.id); }
    catch { setError('Chưa chép được link.'); }
  }

  return <div className="archive-settings share-links">
    <p className="settings-hint">Ai có link đều xem được bản chụp cuộc trò chuyện, không cần đăng nhập. Xóa link thì link
      hết mở được ngay; cuộc trò chuyện của bạn vẫn giữ nguyên.</p>
    {error && <div role="alert"><p>{error}</p><button className="settings-button" disabled={busy} onClick={() => setRevision(n => n + 1)}>Thử lại</button></div>}
    {!loading && !error && !items.length && <p className="empty-hint">Bạn chưa chia sẻ cuộc trò chuyện nào.</p>}
    <ul className="archive-list" aria-label="Danh sách link chia sẻ">
      {items.map(item => <li key={item.id}>
        <a className="archive-open" href={shareUrl(item.id)} {...NEW_TAB} title={item.title}>
          {item.title || 'Chưa có tiêu đề'}<small> · {day(item.updated_at)}{item.include_images ? ' · có ảnh' : ''}</small></a>
        {confirm === item.id ? <div className="archive-confirm" role="group" aria-label={`Xác nhận xóa link: ${item.title}`}>
          <p>Xóa link này? Ai đang giữ link sẽ không mở được nữa.</p>
          <button className="settings-button" disabled={busy} onClick={() => setConfirm(null)}>Hủy</button>
          <button className="settings-button danger" disabled={busy} onClick={() => void remove(item)}>Xóa link</button>
        </div> : <div className="archive-actions">
          <button className="settings-button" disabled={busy} aria-label={`Chép link: ${item.title}`} onClick={() => void copy(item)}>
            {copied === item.id ? 'Đã chép' : 'Chép link'}</button>
          <button className="settings-button danger" disabled={busy} aria-label={`Xóa link: ${item.title}`} onClick={() => setConfirm(item.id)}>Xóa</button>
        </div>}
      </li>)}
    </ul>
  </div>;
}
