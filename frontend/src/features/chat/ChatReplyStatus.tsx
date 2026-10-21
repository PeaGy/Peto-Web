import { useEffect, useRef, useState } from 'react';
import type { Message } from '../../shared/api/api';

/** Chỉ đọc mốc bắt đầu/kết thúc; không đưa từng token hoặc cả lịch sử vào live region. */
export function ChatReplyStatus({ busy, stopping, scope, last }: {
  busy: boolean; stopping: boolean; scope: string; last?: Message;
}) {
  const previous = useRef({ scope, busy: false });
  const latest = useRef(last);
  latest.current = last;
  const [announcement, setAnnouncement] = useState('');
  useEffect(() => {
    const old = previous.current;
    previous.current = { scope, busy };
    if (old.scope !== scope) { setAnnouncement(''); return; }
    if (busy) setAnnouncement(stopping ? 'Đang dừng câu trả lời.' : 'Peto đang trả lời.');
    else if (old.busy) {
      const reply = latest.current;
      setAnnouncement(reply?.stopped ? 'Đã dừng theo yêu cầu của bạn.'
        : reply?.role === 'assistant' && reply.status !== 'incomplete' ? 'Peto đã trả lời xong.'
        : 'Lượt chưa hoàn tất. Phần đã nhận được giữ lại.');
    }
  }, [busy, stopping, scope]);
  return <span className="sr-only" role="status" aria-label="Trạng thái câu trả lời" aria-live="polite" aria-atomic="true">{announcement}</span>;
}

/** Không cướp focus nếu người dùng đã chuyển sang code, nguồn, menu hoặc một dialog khác. */
export function focusComposerIfOwned(textarea: HTMLTextAreaElement | null) {
  if (!textarea) return;
  const active = document.activeElement;
  if (!active || active === document.body || active === textarea || active.matches('.composer .send, .composer .stop')) {
    textarea.focus({ preventScroll: true });
  }
}
