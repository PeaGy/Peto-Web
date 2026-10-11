import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import './tooltip.css';

/*
 * Tooltip của nút, kiểu Grok (chủ web gửi ảnh ngày 2026-10-11): ô tối bo góc, phím tắt mờ bên cạnh, hiện bên dưới
 * hoặc bên cạnh nút. Thay cho tooltip mặc định của trình duyệt (title), vốn là hộp trắng kiểu Windows hiện sau ~1 giây.
 *
 * Cách dùng: đặt `data-tip` lên nút. Không có giá trị (React ghi thành "true") thì dùng aria-label của nút; có chữ thì
 * dùng chữ đó.
 * `data-tip-kbd="Ctrl+K"` thêm phím tắt; `data-tip-side="right"` chọn phía (mặc định bên dưới, tự lật khi hết chỗ).
 * Chỉ hiện khi rê chuột hoặc bút (không hiện khi chạm), hoặc khi focus bằng bàn phím. Bấm, cuộn, Esc thì ẩn.
 * Một lớp duy nhất gắn ở App nghe sự kiện cho cả trang, nên nút mới chỉ cần thuộc tính, không cần bọc component.
 */

type Side = 'top' | 'bottom' | 'left' | 'right';
interface Tip { target: HTMLElement; text: string; kbd: string; side: Side; instant: boolean }

const SHOW_DELAY = 450;
/** Vừa có tooltip khác trong khoảng này thì hiện ngay, không chờ và không chạy hiệu ứng (rê dọc một hàng nút). */
const WARM_MS = 300;
const GAP = 8;
const EDGE = 8;
const SIDES: Side[] = ['top', 'bottom', 'left', 'right'];
const OPPOSITE: Record<Side, Side> = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' };
const MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);

function tipTarget(node: EventTarget | null): HTMLElement | null {
  return node instanceof Element ? node.closest<HTMLElement>('[data-tip]') : null;
}

function readTip(target: HTMLElement, instant: boolean): Tip | null {
  // `data-tip` không có giá trị trong JSX thành "true": khi đó, hay khi để trống, dùng aria-label của nút.
  const own = target.dataset.tip;
  const text = (own && own !== 'true' ? own : target.getAttribute('aria-label') ?? '').trim();
  if (!text) return null;
  const side = target.dataset.tipSide as Side | undefined;
  const kbd = (target.dataset.tipKbd ?? '').replace(/Ctrl\+/g, MAC ? '⌘' : 'Ctrl+');
  return { target, text, kbd, side: side && SIDES.includes(side) ? side : 'bottom', instant };
}

/** Nút bị tắt, đang mở menu của chính nó, hay nằm trong vùng inert thì không cần tooltip. */
function usable(target: HTMLElement) {
  return target.isConnected && !target.matches(':disabled, [aria-haspopup]:not([aria-haspopup="false"])[aria-expanded="true"]')
    && !target.closest('[inert]');
}

function place(node: HTMLElement, target: HTMLElement, preferred: Side) {
  const anchor = target.getBoundingClientRect();
  const width = node.offsetWidth;
  const height = node.offsetHeight;
  const room: Record<Side, number> = {
    top: anchor.top, bottom: window.innerHeight - anchor.bottom, left: anchor.left, right: window.innerWidth - anchor.right,
  };
  const need = (side: Side) => (side === 'top' || side === 'bottom' ? height : width) + GAP + EDGE;
  const side = room[preferred] >= need(preferred) || room[OPPOSITE[preferred]] < need(OPPOSITE[preferred]) ? preferred : OPPOSITE[preferred];
  let left = side === 'left' ? anchor.left - GAP - width : side === 'right' ? anchor.right + GAP : anchor.left + anchor.width / 2 - width / 2;
  let top = side === 'top' ? anchor.top - GAP - height : side === 'bottom' ? anchor.bottom + GAP : anchor.top + anchor.height / 2 - height / 2;
  left = Math.max(EDGE, Math.min(left, window.innerWidth - width - EDGE));
  top = Math.max(EDGE, Math.min(top, window.innerHeight - height - EDGE));
  node.style.left = `${Math.round(left)}px`;
  node.style.top = `${Math.round(top)}px`;
  node.dataset.side = side;
}

export default function TooltipLayer() {
  const ref = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const tipRef = useRef<Tip | null>(null);
  tipRef.current = tip;

  useEffect(() => {
    let timer = 0;
    let hiddenAt = -Infinity;
    /** Nút đang chờ hết thời gian trễ; rê qua biểu tượng bên trong nút không được tính lại từ đầu. */
    let pending: HTMLElement | null = null;
    /** Nút vừa bị bấm: không hiện lại tooltip cho tới khi con trỏ rời nút. */
    let pressed: HTMLElement | null = null;
    const hover = window.matchMedia?.('(hover: hover)');

    const hide = () => {
      window.clearTimeout(timer);
      pending = null;
      if (tipRef.current) hiddenAt = performance.now();
      setTip(null);
    };
    const schedule = (target: HTMLElement) => {
      if (tipRef.current?.target === target || pending === target) return;
      window.clearTimeout(timer);
      const warm = Boolean(tipRef.current) || performance.now() - hiddenAt < WARM_MS;
      const show = () => {
        pending = null;
        if (usable(target)) setTip(readTip(target, warm));
      };
      if (warm) show();
      else { pending = target; timer = window.setTimeout(show, SHOW_DELAY); }
    };

    const onOver = (event: PointerEvent) => {
      if (event.pointerType === 'touch' || hover?.matches === false) return;
      const target = tipTarget(event.target);
      if (!target || target === pressed) return;
      schedule(target);
    };
    const onOut = (event: PointerEvent) => {
      const target = tipTarget(event.target);
      if (!target || (event.relatedTarget instanceof Node && target.contains(event.relatedTarget))) return;
      if (target === pressed) pressed = null;
      if (tipRef.current?.target === target || pending === target) hide();
    };
    const onDown = (event: PointerEvent) => {
      pressed = tipTarget(event.target);
      hide();
    };
    const onFocus = (event: FocusEvent) => {
      const target = tipTarget(event.target);
      if (!target || !(event.target as Element).matches(':focus-visible')) return;
      schedule(target);
    };
    const onBlur = (event: FocusEvent) => {
      if (tipRef.current && tipRef.current.target.contains(event.target as Node)) hide();
    };
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') hide(); };

    document.addEventListener('pointerover', onOver, true);
    document.addEventListener('pointerout', onOut, true);
    document.addEventListener('pointerdown', onDown, true);
    document.addEventListener('focusin', onFocus, true);
    document.addEventListener('focusout', onBlur, true);
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('scroll', hide, true);
    window.addEventListener('resize', hide);
    window.addEventListener('blur', hide);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('pointerover', onOver, true);
      document.removeEventListener('pointerout', onOut, true);
      document.removeEventListener('pointerdown', onDown, true);
      document.removeEventListener('focusin', onFocus, true);
      document.removeEventListener('focusout', onBlur, true);
      document.removeEventListener('keydown', onKey, true);
      window.removeEventListener('scroll', hide, true);
      window.removeEventListener('resize', hide);
      window.removeEventListener('blur', hide);
    };
  }, []);

  // Lớp trên cùng (popover) để tooltip nổi trên cả hộp thoại đang mở bằng showModal; trình duyệt không có popover thì
  // vẫn là phần tử position: fixed như thường.
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const popover = typeof node.showPopover === 'function';
    if (!tip) {
      try { if (popover) node.hidePopover(); } catch { /* đã đóng sẵn */ }
      node.hidden = true;
      return;
    }
    node.hidden = false;
    try { if (popover) node.showPopover(); } catch { /* đã mở sẵn, hoặc vẫn hiện như phần tử fixed */ }
    place(node, tip.target, tip.side);
    // Nút có thể di chuyển (thanh bên co giãn) hay biến mất (menu đóng) khi tooltip đang hiện.
    let frame = 0;
    const follow = () => {
      if (!usable(tip.target)) { setTip(null); return; }
      place(node, tip.target, tip.side);
      frame = requestAnimationFrame(follow);
    };
    frame = requestAnimationFrame(follow);
    return () => cancelAnimationFrame(frame);
  }, [tip]);

  return <div ref={ref} className={tip?.instant ? 'app-tooltip instant' : 'app-tooltip'} role="tooltip" popover="manual" hidden>
    {tip && <><span>{tip.text}</span>{tip.kbd && <kbd>{tip.kbd}</kbd>}</>}
  </div>;
}
