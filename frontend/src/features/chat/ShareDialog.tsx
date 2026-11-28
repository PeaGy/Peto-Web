import { useEffect, useId, useRef, useState } from 'react';
import { deleteShare, getShare, saveShare, shareUrl, UnauthorizedError, type Conversation, type ShareLink } from '../../shared/api/api';
import { useMessageCopy } from './useMessageCopy';
import './shareDialog.css';

const updatedAt = (seconds: number) => {
  const date = new Date(seconds * 1000);
  const time = `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;
  return `${time} ngày ${date.getDate()}/${date.getMonth() + 1}/${date.getFullYear()}`;
};

/**
 * Hộp "Chia sẻ cuộc trò chuyện" từ menu ⋯ (28/11/2026). Mỗi hội thoại một link; link là bản chụp lúc tạo hoặc lúc bấm
 * Cập nhật link. Ai có link đều xem được, không cần đăng nhập; mặc định không kèm ảnh người dùng gửi.
 */
export default function ShareDialog({ conversation, onClose, onUnauthorized }: {
  conversation: Pick<Conversation, 'id' | 'title'>; onClose: () => void; onUnauthorized: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const linkRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const [share, setShare] = useState<ShareLink | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [includeImages, setIncludeImages] = useState(false);
  const [error, setError] = useState('');
  const { state: copyState, copy } = useMessageCopy();

  useEffect(() => { ref.current?.showModal(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    void getShare(conversation.id).then(found => {
      if (controller.signal.aborted) return;
      setShare(found);
      setIncludeImages(Boolean(found?.include_images));
    }).catch(err => {
      if (controller.signal.aborted) return;
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setError('Chưa tải được thông tin chia sẻ. Bạn thử lại nhé.');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [conversation.id, onUnauthorized]);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError('');
    try { await action(); }
    catch (err) {
      if (err instanceof UnauthorizedError) onUnauthorized();
      else setError(err instanceof Error && !(err instanceof TypeError) ? err.message : 'Chưa làm được. Bạn thử lại nhé.');
    } finally { setBusy(false); }
  }

  const save = () => run(async () => {
    const saved = await saveShare(conversation.id, includeImages);
    setShare(saved);
    requestAnimationFrame(() => linkRef.current?.select());
  });
  const remove = () => run(async () => {
    if (!share) return;
    await deleteShare(share.id);
    setShare(null);
  });

  return <dialog ref={ref} className="text-edit-dialog share-dialog" aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <h2 id={titleId}>Chia sẻ cuộc trò chuyện</h2>
    <p className="share-title">{conversation.title || 'Chưa có tiêu đề'}</p>
    {/* Thử thật 28/11/2026: câu trả lời gọi chủ web bằng tên, nên không hứa "tên không bị chia sẻ"; link giữ nguyên văn. */}
    <p>Ai có link đều xem được cuộc trò chuyện như lúc bạn tạo link, không cần đăng nhập. Tin nhắn gửi sau không có
      trong link. Link chứa nguyên văn các tin nhắn, kể cả tên hay chi tiết riêng nếu có trong đó. Trí nhớ và hồ sơ của
      bạn không được chia sẻ.</p>
    <label className="share-option">
      <input type="checkbox" checked={includeImages} disabled={loading || busy} onChange={event => setIncludeImages(event.target.checked)} />
      Kèm ảnh bạn đã gửi
    </label>
    {share && <div className="share-link">
      <input ref={linkRef} className="text-field" readOnly aria-label="Link chia sẻ" value={shareUrl(share.id)}
        onFocus={event => event.currentTarget.select()} />
      <button type="button" className="share-copy" onClick={() => void copy(shareUrl(share.id))}>
        {copyState === 'done' ? 'Đã chép' : copyState === 'fail' ? 'Chưa chép được' : 'Chép link'}</button>
      <p className="share-meta">Bản chụp lúc {updatedAt(share.updated_at)} · {share.message_count} tin nhắn
        {share.include_images ? ' · có ảnh' : ''}</p>
    </div>}
    {error && <p className="share-error" role="alert">{error}</p>}
    <div className="share-actions">
      {share && <button type="button" className="danger" disabled={busy} onClick={() => void remove()}>Xóa link</button>}
      <span className="share-spacer" />
      <button type="button" disabled={busy} onClick={onClose}>{share ? 'Xong' : 'Hủy'}</button>
      <button type="button" className="primary" disabled={loading || busy} onClick={() => void save()}>
        {busy ? 'Đang lưu…' : share ? 'Cập nhật link' : 'Tạo link'}</button>
    </div>
  </dialog>;
}
