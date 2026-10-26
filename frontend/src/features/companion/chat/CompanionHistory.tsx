/**
 * Lịch sử trò chuyện Companion theo history.vue của AIRI (commit 74ddd90), chủ web chọn đưa về ngày 26/10/2026:
 * - nhãn giờ giữa các tin cách nhau từ 5 phút, bấm để xem ngày giờ đầy đủ;
 * - bóng người dùng bên phải (điện thoại: bên trái như AIRI), bóng nhân vật bên trái kèm tên nhân vật;
 * - menu "…" (Nghe lại, Trả lời, Sao chép, Xóa), vuốt sang trái để trả lời, trích dẫn tin được trả lời;
 * - tự cuộn theo tin mới khi đang ở cuối; đã cuộn lên, hay đang rê chuột, đặt tiêu điểm, bôi chữ ở tin cũ thì đứng yên;
 * - điện thoại: tin ở mép trên mờ dần trong 20% chiều cao khung (mask đặt trên từng bóng, không đặt trên cả khung, để
 *   hiệu ứng làm mờ nền của bóng vẫn chạy).
 * Không hiện dòng suy nghĩ của model (chủ web chọn: có thể lộ bí mật trò chơi trong ghi chú riêng).
 */
import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react';
import type { Message } from '../../../shared/api/api';
import { GlobeIcon } from '../../chat/WebSources';
import { CompanionMessageImages } from '../CompanionImages';
import { ChatActionMenu, type ChatAction, type ChatActionItem } from './ChatActionMenu';
import { fullTime, readableTime, timeSeparators } from './chatTime';
import { CompanionMarkdown } from './CompanionMarkdown';
import { CopyIcon, ListenIcon, ReplyIcon, StopSquareIcon, TrashIcon } from './chatIcons';
import { ReplyQuote, type ReplyTarget } from './Reply';
import { useSwipeReply } from './useSwipeReply';

/** AIRI: isNearTail chừa 24px cho chênh lệch dưới một điểm ảnh, đổi phông và nội dung về muộn. */
const TAIL_TOLERANCE = 24;
/** Điện thoại: tin trong 20% trên cùng của khung mờ dần (topFadeRatio của AIRI). */
const TOP_FADE_RATIO = 0.2;
export const USER_LABEL = 'Bạn';

export interface HistoryAction {
  action: ChatAction;
  message: Message;
  index: number;
}

function TimeSeparator({ time, now }: { time: number; now: number }) {
  const [full, setFull] = useState(false);
  const iso = new Date(time * 1000).toISOString();
  return (
    <div className="cchat-time">
      <button type="button" aria-pressed={full} data-tip={full ? undefined : fullTime(time)} onClick={() => setFull(value => !value)}>
        <time dateTime={iso}>{full ? fullTime(time) : readableTime(time, now)}</time>
      </button>
    </div>
  );
}

/** Khung một tin: vuốt sang trái để trả lời, biểu tượng trả lời hiện dần ở mép phải theo độ kéo. */
function MessageFrame({ role, replyable, compact, onReply, children }: {
  role: string; replyable: boolean; compact: boolean; onReply: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const swipe = useSwipeReply(ref, { enabled: replyable, input: compact ? 'touch' : 'wheel', onCommit: onReply });
  const progress = Math.min(Math.abs(swipe.offset) / 48, 1);
  return (
    <div ref={ref} className="cchat-item" data-chat-message-role={role} style={{ touchAction: replyable && compact ? 'pan-y' : undefined }}>
      {replyable && (
        <span className="cchat-swipe-icon" aria-hidden="true" style={{
          opacity: progress,
          transform: `translate3d(${-Math.min(Math.abs(swipe.offset) * 0.18, 10)}px, -50%, 0) scale(${0.72 + progress * 0.28})`,
        }}><ReplyIcon /></span>
      )}
      <div className="cchat-swipe" data-swipe-active={swipe.active || undefined}
        style={swipe.offset ? { transform: `translate3d(${swipe.offset}px, 0, 0)` } : undefined}>
        {children}
      </div>
    </div>
  );
}

function Placeholder({ searching }: { searching: boolean }) {
  return searching
    ? <p className="cchat-placeholder cchat-searching" aria-hidden="true"><GlobeIcon /> Đang tra web…</p>
    : <span className="cchat-dots" aria-hidden="true"><i /><i /><i /></span>;
}

/** Theo tin mới khi đang ở cuối khung, như use-chat-history-scroll.ts của AIRI. */
function useFollowTail(list: RefObject<HTMLDivElement | null>, messages: Message[], threadKey: string, followKey: number) {
  const state = useRef({ following: true, intent: false, inspecting: false, selecting: false, thread: null as string | null });
  const toTail = () => {
    const element = list.current;
    if (element) element.scrollTop = element.scrollHeight;
  };

  useEffect(() => {
    const element = list.current;
    if (!element) return;
    const current = state.current;
    const older = (target: EventTarget | null) => {
      const item = target instanceof Element ? target.closest('.cchat-item') : null;
      if (!item || !element.contains(item)) return false;
      const items = element.querySelectorAll('.cchat-item');
      return item !== items[items.length - 1];
    };
    const scroll = () => {
      const near = element.scrollTop + element.clientHeight >= element.scrollHeight - TAIL_TOLERANCE;
      if (near) {
        current.following = true;
        current.intent = false;
        if (!current.selecting) current.inspecting = false;
      } else if (current.intent) {
        current.following = false;
      }
    };
    const intent = () => { current.intent = true; };
    const keys = (event: KeyboardEvent) => {
      if (['ArrowDown', 'ArrowUp', 'End', 'Home', 'PageDown', 'PageUp', ' '].includes(event.key)) current.intent = true;
    };
    const over = (event: Event) => { current.inspecting = older(event.target) || current.selecting; };
    const out = (event: PointerEvent | FocusEvent) => { current.inspecting = older(event.relatedTarget) || current.selecting; };
    const selection = () => {
      const node = document.getSelection()?.anchorNode ?? null;
      current.selecting = older(node instanceof Element ? node : node?.parentElement ?? null);
      if (current.selecting) current.inspecting = true;
    };
    const resized = () => { if (current.following && !current.inspecting) toTail(); };
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resized);
    observer?.observe(element);
    element.addEventListener('scroll', scroll, { passive: true });
    element.addEventListener('wheel', intent, { passive: true });
    element.addEventListener('touchmove', intent, { passive: true });
    element.addEventListener('keydown', keys);
    element.addEventListener('pointerover', over);
    element.addEventListener('pointerout', out);
    element.addEventListener('focusin', over);
    element.addEventListener('focusout', out);
    document.addEventListener('selectionchange', selection);
    return () => {
      observer?.disconnect();
      element.removeEventListener('scroll', scroll);
      element.removeEventListener('wheel', intent);
      element.removeEventListener('touchmove', intent);
      element.removeEventListener('keydown', keys);
      element.removeEventListener('pointerover', over);
      element.removeEventListener('pointerout', out);
      element.removeEventListener('focusin', over);
      element.removeEventListener('focusout', out);
      document.removeEventListener('selectionchange', selection);
    };
    // toTail chỉ đọc ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list]);

  useLayoutEffect(() => {
    const current = state.current;
    if (current.thread !== threadKey) {
      // Mạch khác (hay lần đầu): về cuối, bỏ mọi trạng thái đọc tin cũ.
      Object.assign(current, { following: true, intent: false, inspecting: false, selecting: false, thread: threadKey });
      toTail();
      return;
    }
    if (current.following && !current.inspecting) toTail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, threadKey]);

  // Người dùng vừa gửi: luôn về cuối để thấy tin của mình, kể cả đang đọc tin cũ.
  useLayoutEffect(() => {
    if (!followKey) return;
    Object.assign(state.current, { following: true, intent: false, inspecting: false });
    toTail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [followKey]);
}

/** Điện thoại: đặt điểm dừng mask cho từng bóng nằm trong 20% trên cùng của khung (useChatHistoryTopFade của AIRI). */
function useTopFade(list: RefObject<HTMLDivElement | null>, enabled: boolean, messages: Message[]) {
  useEffect(() => {
    const element = list.current;
    if (!element) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const fade = enabled ? element.clientHeight * TOP_FADE_RATIO : 0;
      const top = element.getBoundingClientRect().top;
      element.querySelectorAll<HTMLElement>('.cchat-bubble').forEach(bubble => {
        const offset = bubble.getBoundingClientRect().top - top;
        const inside = fade > 0 && offset < fade;
        bubble.style.setProperty('--cchat-fade-clear', `${inside ? -offset : -1}px`);
        bubble.style.setProperty('--cchat-fade-solid', `${inside ? fade - offset : 0}px`);
      });
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    schedule();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(schedule);
    observer?.observe(element);
    element.addEventListener('scroll', schedule, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      element.removeEventListener('scroll', schedule);
    };
  }, [list, enabled, messages]);
}

/** Giờ hiện tại, đổi mỗi phút để nhãn "hôm nay / hôm qua" đúng khi qua nửa đêm. */
function useMinuteClock(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

export const CompanionHistory = memo(function CompanionHistory({
  messages, name, compact, streaming, searching, threadKey, followKey, listRef, canListen, speakingIndex, busy, top, onAction,
}: {
  messages: Message[];
  /** Tên nhân vật ở đầu bóng chat của nhân vật (AIRI: assistantLabel). */
  name: string;
  compact: boolean;
  /** Tin cuối của nhân vật đang được viết. */
  streaming: boolean;
  searching: boolean;
  /** Mạch đang mở: đổi mạch thì cuộn về cuối. */
  threadKey: string;
  /** Tăng mỗi lần người dùng gửi tin. */
  followKey: number;
  listRef: RefObject<HTMLDivElement | null>;
  /** Giọng nói sẵn sàng: có mục Nghe lại. */
  canListen: boolean;
  /** Tin đang được đọc (vị trí trong ``messages``). */
  speakingIndex: number | null;
  /** Đang trả lời hay đang đổi mạch: chưa xóa được tin. */
  busy: boolean;
  /** Dòng đang tải / lỗi tải ở đầu khung. */
  top?: ReactNode;
  onAction: (event: HistoryAction) => void;
}) {
  const now = useMinuteClock();
  const separators = useMemo(() => timeSeparators(messages), [messages]);
  const byId = useMemo(() => new Map(messages.filter(item => item.id).map(item => [item.id!, item])), [messages]);
  useFollowTail(listRef, messages, threadKey, followKey);
  useTopFade(listRef, compact, messages);

  return (
    <div ref={listRef} className="companion-messages cchat-list" data-compact={compact || undefined}>
      {top}
      {messages.map((message, index) => {
        const user = message.role === 'user';
        const live = streaming && !user && index === messages.length - 1;
        const text = message.content;
        const stored = typeof message.id === 'number' && message.id > 0;
        const replyable = stored && !live && Boolean(text.trim());
        const target = message.quote_id ? byId.get(message.quote_id) : undefined;
        const quote: ReplyTarget | undefined = target
          ? { message: target, label: target.role === 'user' ? USER_LABEL : name } : undefined;
        const items: ChatActionItem[] = [];
        if (!user && canListen && text.trim() && !live) {
          items.push(speakingIndex === index
            ? { action: 'listen', label: 'Dừng đọc', icon: <StopSquareIcon size={16} /> }
            : { action: 'listen', label: 'Nghe lại', icon: <ListenIcon /> });
        }
        if (replyable) items.push({ action: 'reply', label: 'Trả lời', icon: <ReplyIcon /> });
        if (text.trim() && !live) items.push({ action: 'copy', label: 'Sao chép', icon: <CopyIcon /> });
        if (stored && !busy && !live) items.push({ action: 'delete', label: 'Xóa', icon: <TrashIcon />, danger: true });
        const act = (action: ChatAction) => onAction({ action, message, index });
        return (
          <div key={message.id ?? `local-${index}`} className="cchat-entry">
            {separators[index] !== undefined && <TimeSeparator time={separators[index]!} now={now} />}
            <MessageFrame role={message.role} replyable={replyable} compact={compact} onReply={() => act('reply')}>
              <div className={`cchat-row ${user ? 'user' : 'assistant'}`}>
                <ChatActionMenu items={items} placement={user ? 'left' : 'right'} compact={compact} copyText={text}
                  scrollRef={listRef} onAction={act}>
                  <article className={`cchat-bubble ${user ? 'user' : 'assistant'}`} aria-label={user ? USER_LABEL : name}>
                    {quote && <ReplyQuote target={quote} />}
                    {(!user || compact) && <span className="cchat-label">{user ? USER_LABEL : name}</span>}
                    {user && <CompanionMessageImages attachments={message.attachments} />}
                    {text ? <CompanionMarkdown text={text} /> : live && <Placeholder searching={searching} />}
                    {message.status === 'incomplete' && !live && <span className="cchat-status">Chưa trả lời xong</span>}
                  </article>
                </ChatActionMenu>
              </div>
            </MessageFrame>
          </div>
        );
      })}
    </div>
  );
});
