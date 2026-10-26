/**
 * Trả lời một tin (Reply của AIRI, commit 74ddd90): reply.ts, reply-preview.vue (dải trên ô nhắn, có nút hủy) và
 * reply-quote.vue (trích dẫn ở đầu bóng chat đã gửi).
 */
import { useLayoutEffect, useRef, useState } from 'react';
import type { Message } from '../../../shared/api/api';
import { CloseCircleIcon, ReplyIcon } from './chatIcons';

/** AIRI: REPLY_PREVIEW_CHARACTER_LIMIT. */
const PREVIEW_LIMIT = 160;

/** Tin đang được trả lời và tên người viết lúc chọn (tên nhân vật, hay "Bạn"). */
export interface ReplyTarget {
  message: Message;
  label: string;
}

/** Một dòng xem trước: gộp khoảng trắng, dài quá thì cắt kèm dấu "…". */
export function replyPreview(text: string): string {
  const normalized = text.replace(/\s+/g, ' ').trim();
  const chars = Array.from(normalized);
  return chars.length <= PREVIEW_LIMIT ? normalized : `${chars.slice(0, PREVIEW_LIMIT - 1).join('').trimEnd()}…`;
}

function ReplyLines({ target }: { target: ReplyTarget }) {
  return (
    <span className="cchat-reply-lines">
      <strong>Đang trả lời {target.label}</strong>
      <span>{replyPreview(target.message.content) || 'Tin nhắn'}</span>
    </span>
  );
}

/** Trích dẫn ở đầu bóng chat của tin trả lời. */
export function ReplyQuote({ target }: { target: ReplyTarget }) {
  return (
    <div className="cchat-quote">
      <ReplyIcon size={14} />
      <ReplyLines target={target} />
    </div>
  );
}

/**
 * Dải "Đang trả lời …" ở đầu ô nhắn. Mở ra và thu lại bằng chiều cao như AIRI; lúc thu lại vẫn giữ nội dung cũ để đo.
 */
export function ReplyPreview({ target, onCancel }: { target?: ReplyTarget; onCancel: () => void }) {
  const content = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(target);
  const [height, setHeight] = useState(0);
  if (target && target !== shown) setShown(target);
  useLayoutEffect(() => {
    if (target) setHeight(content.current?.scrollHeight ?? 0);
  }, [target, shown]);
  return (
    <div className="cchat-reply-preview" style={{ maxHeight: target ? height : 0 }} data-open={target ? 'true' : 'false'}
      inert={!target}>
      <div ref={content} className="cchat-reply-preview-body" aria-hidden={!target}>
        <ReplyIcon />
        {shown && <ReplyLines target={shown} />}
        <button type="button" className="cchat-reply-cancel" aria-label="Hủy trả lời" data-tip tabIndex={target ? 0 : -1}
          onClick={onCancel}>
          <CloseCircleIcon />
        </button>
      </div>
    </div>
  );
}
