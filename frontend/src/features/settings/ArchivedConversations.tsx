import { useCallback, useEffect, useRef, useState } from 'react';
import { deleteConversation, listConversations, updateConversation, UnauthorizedError, type Conversation } from '../../shared/api/api';
import './archive.css';

export default function ArchivedConversations({open, disabled, onOpen, onChanged, onUnauthorized}: {
  open: boolean; disabled: boolean; onOpen: (id: string) => void;
  onChanged: (item: Conversation, deleted: boolean) => void; onUnauthorized: () => void;
}) {
  const [items, setItems] = useState<Conversation[]>([]);
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const mounted = useRef(true);
  const mutating = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true);
    setError('');
    const timer = setTimeout(() => {
      void listConversations(offset, 50, query.trim(), {archived: true}, controller.signal).then(result => {
        if (controller.signal.aborted) return;
        setItems(previous => offset ? [...previous, ...result.conversations] : result.conversations);
        setMore(result.has_more);
      }).catch(err => {
        if (controller.signal.aborted) return;
        if (err instanceof UnauthorizedError) onUnauthorized();
        else setError('Chưa tải được hội thoại đã lưu trữ. Hãy thử lại.');
      }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, query.trim() ? 250 : 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [open, query, offset, revision, onUnauthorized]);

  // Mở lại mục luôn đọc từ đầu để tránh nối trùng trang đã tải ở lần trước.
  useEffect(() => { if (!open) { setOffset(0); setConfirm(null); } }, [open]);

  const run = useCallback(async (item: Conversation, deleted: boolean) => {
    if (mutating.current || disabled) return;
    mutating.current = true;
    setBusy(true); setError('');
    try {
      if (deleted) await deleteConversation(item.id);
      else await updateConversation(item.id, {archived: false});
      if (!mounted.current) return;
      setItems(current => current.filter(row => row.id !== item.id));
      setConfirm(null);
      setOffset(0); setRevision(n => n + 1);
      onChanged(item, deleted);
    } catch (err) {
      if (!mounted.current) return;
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setError(err instanceof Error && !(err instanceof TypeError) ? err.message : 'Chưa lưu được thay đổi. Hãy thử lại.');
    } finally {
      mutating.current = false;
      if (mounted.current) setBusy(false);
    }
  }, [disabled, onChanged, onUnauthorized]);

  return <div className="archive-settings">
    <p className="settings-hint">Hội thoại đã lưu trữ được giữ nguyên nội dung và tệp đính kèm. Khôi phục để tiếp tục trò chuyện.</p>
    <input className="archive-search" type="search" aria-label="Tìm hội thoại đã lưu trữ" placeholder="Tìm tiêu đề hoặc nội dung…" maxLength={200} value={query} disabled={busy} onChange={e => {setQuery(e.target.value); setOffset(0); setItems([]); setConfirm(null);}} />
    {error && <div role="alert"><p>{error}</p><button className="settings-button" disabled={busy} onClick={() => {setOffset(0); setRevision(n => n + 1);}}>Thử lại</button></div>}
    <ul className="archive-list" aria-label="Danh sách hội thoại đã lưu trữ">
      {items.map(item => <li key={item.id}>
        <button className="archive-open" title={item.title} disabled={disabled || busy || loading} onClick={() => onOpen(item.id)}>{item.title || 'Chưa có tiêu đề'}</button>
        {confirm === item.id ? <div className="archive-confirm" role="group" aria-label={`Xác nhận xóa: ${item.title}`}>
          <p>Xóa vĩnh viễn hội thoại và tệp đính kèm?</p>
          <button className="settings-button" disabled={busy} onClick={() => setConfirm(null)}>Hủy</button>
          <button className="settings-button danger" disabled={disabled || busy} onClick={() => void run(item, true)}>Xóa vĩnh viễn</button>
        </div> : <div className="archive-actions">
          <button className="settings-button" disabled={disabled || busy || loading} aria-label={`Khôi phục: ${item.title}`} onClick={() => void run(item, false)}>Khôi phục</button>
          <button className="settings-button danger" disabled={disabled || busy || loading} aria-label={`Xóa: ${item.title}`} onClick={() => setConfirm(item.id)}>Xóa</button>
        </div>}
      </li>)}
    </ul>
    {loading && <p role="status">Đang tải hội thoại…</p>}
    {!loading && !error && !items.length && <p className="settings-hint">{query.trim() ? 'Không tìm thấy hội thoại phù hợp.' : 'Chưa có hội thoại đã lưu trữ.'}</p>}
    {more && !error && <button className="settings-button" disabled={loading || busy} onClick={() => setOffset(items.length)}>Xem thêm</button>}
  </div>;
}
