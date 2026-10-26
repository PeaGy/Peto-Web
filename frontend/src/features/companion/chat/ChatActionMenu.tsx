/**
 * Menu thao tác của một tin, như action-menu/index.vue của AIRI (commit 74ddd90):
 * - máy tính: nút "…" hiện bên ngoài bóng chat khi rê chuột hay có tiêu điểm (trái bóng của người dùng, phải bóng của
 *   nhân vật); bóng cao hơn khung thì nút trôi theo để luôn thấy được;
 * - chuột phải lên bóng chat, hay giữ ngón tay 250 ms trên điện thoại (bóng thu nhỏ lại khi giữ), mở cùng menu ngay chỗ
 *   bấm. Điện thoại không có nút "…", như AIRI trên web di động.
 * Sao chép xong thì nút "…" thành dấu tích một giây. Menu mở bằng hiệu ứng nảy 220 ms, đóng 120 ms.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { CheckIcon, DotsIcon } from './chatIcons';

export type ChatAction = 'listen' | 'reply' | 'copy' | 'delete';

export interface ChatActionItem {
  action: ChatAction;
  label: string;
  icon: ReactNode;
  danger?: boolean;
}

/** AIRI: contextMenuPressOpenDelay. */
const PRESS_OPEN_MS = 250;
/** AIRI: PRESS_CANCEL_DISTANCE_PX. */
const PRESS_CANCEL_PX = 8;
/** Thả ngón tay ngay sau khi menu mở không được tính là bấm mục nằm dưới ngón tay. */
const TOUCH_CLICK_GUARD_MS = 400;
const TRIGGER_SIZE = 32;
const EDGE = 8;
const CLOSE_MS = 120;

type Anchor = { kind: 'trigger' } | { kind: 'point'; x: number; y: number };

export function ChatActionMenu({ items, placement, compact, copyText, label = 'Thao tác tin nhắn', scrollRef, onAction, children }: {
  items: ChatActionItem[];
  placement: 'left' | 'right';
  /** Điện thoại: không có nút "…", chỉ giữ ngón tay hay chuột phải. */
  compact: boolean;
  copyText: string;
  label?: string;
  /** Khung cuộn của lịch sử, để nút "…" của bóng cao trôi theo phần đang thấy. */
  scrollRef?: RefObject<HTMLElement | null>;
  onAction: (action: ChatAction) => void;
  children: ReactNode;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const measured = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const [closing, setClosing] = useState(false);
  const [position, setPosition] = useState<{ left: number; top: number; origin: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [pressing, setPressing] = useState(false);
  const [triggerTop, setTriggerTop] = useState<number | null>(null);
  const openedAt = useRef(0);
  const openedByTouch = useRef(false);
  const focusFirst = useRef(false);
  const press = useRef<{ id: number; x: number; y: number; timer: number } | null>(null);
  const copyTimer = useRef(0);
  const closeTimer = useRef(0);
  const open = anchor !== null && !closing;

  const close = useCallback((restoreFocus = false) => {
    if (!anchor || closing) return;
    setClosing(true);
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => { setAnchor(null); setClosing(false); setPosition(null); }, CLOSE_MS);
    // Chỉ trả tiêu điểm về nút "…" khi menu mở từ nút đó; mở bằng chuột phải thì để yên chỗ người dùng đang ở.
    if (restoreFocus && anchor.kind === 'trigger') trigger.current?.focus({ preventScroll: true });
  }, [anchor, closing]);

  const show = useCallback((next: Anchor, options: { touch?: boolean; keyboard?: boolean } = {}) => {
    if (!items.length) return;
    window.clearTimeout(closeTimer.current);
    openedAt.current = performance.now();
    openedByTouch.current = Boolean(options.touch);
    focusFirst.current = Boolean(options.keyboard);
    setClosing(false);
    setPosition(null);
    setAnchor(next);
  }, [items.length]);

  useEffect(() => () => {
    window.clearTimeout(copyTimer.current);
    window.clearTimeout(closeTimer.current);
    if (press.current) window.clearTimeout(press.current.timer);
  }, []);

  // Đặt menu sau khi đo được kích thước: dưới nút "…" và canh mép phải theo nút (align end), hết chỗ thì lật lên trên;
  // mở bằng chuột phải hay giữ ngón tay thì đặt ngay chỗ bấm. Luôn cách mép màn hình 8px.
  useLayoutEffect(() => {
    if (!anchor || !menu.current) return;
    const box = menu.current.getBoundingClientRect();
    const width = box.width, height = box.height;
    let left: number, top: number, originX: string, originY: string;
    if (anchor.kind === 'trigger' && trigger.current) {
      const rect = trigger.current.getBoundingClientRect();
      left = rect.right - width;
      top = rect.bottom + 6;
      originX = 'right';
      originY = 'top';
      if (top + height > window.innerHeight - EDGE && rect.top - 6 - height >= EDGE) { top = rect.top - 6 - height; originY = 'bottom'; }
    } else {
      const point = anchor.kind === 'point' ? anchor : { x: 0, y: 0 };
      left = point.x;
      top = point.y;
      originX = 'left';
      originY = 'top';
      if (left + width > window.innerWidth - EDGE) { left = point.x - width; originX = 'right'; }
      if (top + height > window.innerHeight - EDGE) { top = point.y - height; originY = 'bottom'; }
    }
    left = Math.min(Math.max(EDGE, left), Math.max(EDGE, window.innerWidth - width - EDGE));
    top = Math.min(Math.max(EDGE, top), Math.max(EDGE, window.innerHeight - height - EDGE));
    setPosition({ left, top, origin: `${originX} ${originY}` });
  }, [anchor]);

  useEffect(() => {
    if (!position || !focusFirst.current) return;
    focusFirst.current = false;
    menu.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus({ preventScroll: true });
  }, [position]);

  // Bấm ra ngoài, cuộn hay đổi cỡ cửa sổ thì đóng (menu đứng yên theo màn hình, không theo bóng chat).
  useEffect(() => {
    if (!anchor || closing) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (menu.current?.contains(target) || trigger.current?.contains(target)) return;
      close();
    };
    const dismiss = () => close();
    // Mở bằng chuột phải hay giữ ngón tay thì tiêu điểm còn ở chỗ cũ: Esc vẫn đóng, mũi tên đưa tiêu điểm vào menu.
    const keys = (event: KeyboardEvent) => {
      if (menu.current?.contains(document.activeElement)) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        close(true);
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        const entries = menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]');
        if (!entries?.length) return;
        event.preventDefault();
        entries[event.key === 'ArrowDown' ? 0 : entries.length - 1].focus();
      }
    };
    document.addEventListener('keydown', keys, true);
    document.addEventListener('pointerdown', outside, true);
    window.addEventListener('resize', dismiss);
    const scroller = scrollRef?.current;
    scroller?.addEventListener('scroll', dismiss, { passive: true });
    return () => {
      document.removeEventListener('keydown', keys, true);
      document.removeEventListener('pointerdown', outside, true);
      window.removeEventListener('resize', dismiss);
      scroller?.removeEventListener('scroll', dismiss);
    };
  }, [anchor, closing, close, scrollRef]);

  // Nút "…" của bóng cao hơn khung: đứng ở đầu bóng khi đầu bóng còn thấy, ở cuối khi chỉ cuối còn thấy, còn không thì
  // ở giữa phần đang thấy (sentinel trên/dưới của AIRI).
  const placeTrigger = useCallback(() => {
    const bubble = measured.current?.getBoundingClientRect();
    const view = scrollRef?.current?.getBoundingClientRect();
    if (!bubble || !view) return setTriggerTop(null);
    if (bubble.top >= view.top) return setTriggerTop(null);
    const room = Math.max(bubble.height - TRIGGER_SIZE, 0);
    if (bubble.bottom <= view.bottom) return setTriggerTop(room);
    setTriggerTop(Math.min(Math.max(view.top + view.height / 2 - TRIGGER_SIZE / 2 - bubble.top, 0), room));
  }, [scrollRef]);
  const [hovered, setHovered] = useState(false);
  useEffect(() => {
    if (compact || !hovered) return;
    placeTrigger();
    const scroller = scrollRef?.current;
    scroller?.addEventListener('scroll', placeTrigger, { passive: true });
    return () => scroller?.removeEventListener('scroll', placeTrigger);
  }, [compact, hovered, placeTrigger, scrollRef]);

  async function run(item: ChatActionItem) {
    if (openedByTouch.current && performance.now() - openedAt.current < TOUCH_CLICK_GUARD_MS) return;
    close(item.action !== 'reply' && item.action !== 'delete');
    if (item.action === 'copy') {
      if (!copyText.trim()) return;
      try {
        await navigator.clipboard.writeText(copyText);
        setCopied(true);
        window.clearTimeout(copyTimer.current);
        copyTimer.current = window.setTimeout(() => setCopied(false), 1000);
      } catch { /* trình duyệt chặn bộ nhớ tạm: không báo đã chép */ }
      return;
    }
    onAction(item.action);
  }

  function menuKeys(event: React.KeyboardEvent) {
    const entries = [...(menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])];
    const index = entries.indexOf(document.activeElement as HTMLButtonElement);
    const move = (next: number) => { event.preventDefault(); entries[(next + entries.length) % entries.length]?.focus(); };
    if (event.key === 'ArrowDown') move(index + 1);
    else if (event.key === 'ArrowUp') move(index < 0 ? entries.length - 1 : index - 1);
    else if (event.key === 'Home') move(0);
    else if (event.key === 'End') move(entries.length - 1);
    else if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); }
    else if (event.key === 'Tab') close();
  }

  // Giữ ngón tay: bóng thu dần về 95% trong 250 ms rồi mở menu (rung nhẹ nếu máy có); kéo quá 8px là thôi.
  function pressStart(event: React.PointerEvent) {
    if (event.pointerType !== 'touch' || !event.isPrimary || !items.length) return;
    cancelPress();
    const start = { id: event.pointerId, x: event.clientX, y: event.clientY, timer: 0 };
    start.timer = window.setTimeout(() => {
      press.current = null;
      setPressing(false);
      navigator.vibrate?.(10);
      show({ kind: 'point', x: start.x, y: start.y }, { touch: true });
    }, PRESS_OPEN_MS);
    press.current = start;
    setPressing(true);
  }
  function pressMove(event: React.PointerEvent) {
    const current = press.current;
    if (current && event.pointerId === current.id && Math.hypot(event.clientX - current.x, event.clientY - current.y) > PRESS_CANCEL_PX) cancelPress();
  }
  function cancelPress() {
    if (press.current) window.clearTimeout(press.current.timer);
    press.current = null;
    setPressing(false);
  }

  return (
    <>
      <div ref={wrap} className={`cchat-action ${placement}`} data-open={open || undefined} data-pressing={pressing || undefined}
        onPointerEnter={() => setHovered(true)} onPointerLeave={() => setHovered(false)}
        onFocus={() => { if (!compact) placeTrigger(); }}
        onPointerDown={pressStart} onPointerMove={pressMove} onPointerUp={cancelPress} onPointerCancel={cancelPress}
        onContextMenu={event => {
          if (!items.length) return;
          event.preventDefault();
          cancelPress();
          if (!open) show({ kind: 'point', x: event.clientX, y: event.clientY }, { touch: compact });
        }}>
        {!compact && items.length > 0 && (
          <button ref={trigger} type="button" className="cchat-action-trigger" data-copied={copied || undefined}
            aria-label={label} aria-haspopup="menu" aria-expanded={open}
            style={triggerTop === null ? undefined : { top: triggerTop, bottom: 'auto' }}
            onClick={() => (open ? close() : show({ kind: 'trigger' }))}
            onKeyDown={event => {
              if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                show({ kind: 'trigger' }, { keyboard: true });
              }
            }}>
            {copied ? <CheckIcon /> : <DotsIcon />}
          </button>
        )}
        <div ref={measured} className="cchat-action-target">{children}</div>
      </div>
      {anchor && createPortal(
        <div ref={menu} role="menu" aria-label={label} className="popup-menu cchat-menu" data-state={closing ? 'closed' : 'open'}
          style={{ left: position?.left ?? -9999, top: position?.top ?? -9999, transformOrigin: position?.origin,
            visibility: position ? undefined : 'hidden' }}
          onKeyDown={menuKeys}>
          {items.map(item => (
            <button key={item.action} type="button" role="menuitem" tabIndex={-1}
              className={item.danger ? 'danger-button' : undefined} onClick={() => void run(item)}>
              {item.icon}<span>{item.label}</span>
            </button>
          ))}
        </div>,
        document.body,
      )}
    </>
  );
}
