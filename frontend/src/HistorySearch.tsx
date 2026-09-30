import { useEffect, useRef, useState } from 'react';
import { listConversations, UnauthorizedError, type Conversation } from './api';

export default function HistorySearch({onClose, onSelect, onUnauthorized}: {onClose:()=>void; onSelect:(id:string)=>void; onUnauthorized:()=>void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [offset, setOffset] = useState(0);
  const [more, setMore] = useState(false);
  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => {
    let stale = false;
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const result = await listConversations(offset, 50, query.trim());
        if (!stale) { setItems(previous => offset ? [...previous, ...result.conversations] : result.conversations); setMore(result.has_more); setError(''); }
      } catch (err) {
        if (!stale) {
          if (err instanceof UnauthorizedError) onUnauthorized();
          else setError('Chưa tìm được lịch sử. Hãy thử lại.');
        }
      } finally { if (!stale) setLoading(false); }
    }, 250);
    return () => { stale = true; clearTimeout(timer); };
  }, [query, offset, onUnauthorized]);
  return <dialog ref={dialog} className="history-dialog" aria-label="Tìm kiếm hội thoại" onCancel={e => {e.preventDefault(); onClose();}}>
    <div className="history-dialog-head"><input autoFocus type="search" aria-label="Tìm trong lịch sử chat" placeholder="Tìm tiêu đề hoặc nội dung…" maxLength={200} value={query} onChange={e => {setQuery(e.target.value); setOffset(0);}}/><button onClick={onClose} aria-label="Đóng tìm kiếm">×</button></div>
    <div className="history-results">
      <p className="empty-hint">{query.trim() ? 'Kết quả tìm kiếm' : 'Hội thoại gần đây'}</p>
      {loading ? <p role="status">Đang tìm…</p> : error ? <p role="alert">{error}</p> : <>
        {items.map(item => <button className="history-result" key={item.id} onClick={() => onSelect(item.id)}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M21 11a9 9 0 0 1-13 8l-5 2 1-6A9 9 0 1 1 21 11Z"/></svg><span>{item.title || 'Chưa có tiêu đề'}</span></button>)}
        {!items.length && <p className="empty-hint">Không tìm thấy hội thoại phù hợp.</p>}
        {more && <button className="load-more" onClick={() => setOffset(n => n + 50)}>Xem thêm</button>}
      </>}
    </div>
  </dialog>;
}
