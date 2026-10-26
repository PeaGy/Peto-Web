/**
 * Vuốt bóng chat sang trái để trả lời, như gestures/swipeable.vue và history-message-frame.vue của AIRI (commit 74ddd90):
 * điện thoại kéo bằng ngón tay, máy tính vuốt ngang hai ngón trên touchpad. Quá 48px thì thả ra là trả lời (rung nhẹ lúc
 * vừa qua ngưỡng). Bóng càng kéo xa càng nặng tay, tiến dần tới một phần tư bề ngang mà không chạm hẳn. Kéo dọc vẫn là
 * cuộn bình thường. Không dùng thư viện wheel-gestures của AIRI: hết vuốt là lúc touchpad ngưng gửi sự kiện 140 ms.
 */
import { useEffect, useRef, useState, type RefObject } from 'react';

/** AIRI: threshold, startDistance. */
export const SWIPE_THRESHOLD = 48;
const START_DISTANCE = 8;
const WHEEL_IDLE_MS = 140;

export interface SwipeState {
  /** Độ lệch ngang của bóng chat (âm là sang trái), px. */
  offset: number;
  /** Đang kéo theo chiều ngang. */
  active: boolean;
}

export function useSwipeReply(ref: RefObject<HTMLElement | null>, options: {
  enabled: boolean;
  input: 'touch' | 'wheel';
  onCommit: () => void;
}): SwipeState {
  const [state, setState] = useState<SwipeState>({ offset: 0, active: false });
  const latest = useRef(options);
  latest.current = options;

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    let crossed = false;
    let frame = 0;
    let pendingOffset = 0;
    // Chạm: đợi 8px để biết kéo ngang hay dọc; đã rõ thì giữ tới lúc nhấc tay.
    let pointer = -1, startX = 0, startY = 0;
    let intent: 'pending' | 'horizontal' | 'vertical' = 'pending';
    // Touchpad.
    let wheelIntent: 'pending' | 'horizontal' | 'vertical' = 'pending';
    let wheelX = 0, wheelY = 0, wheelDistance = 0, wheelTimer = 0;

    // Đường cong của AIRI: dốc 1:1 lúc đầu, rồi nặng dần, tiến tới một phần tư bề ngang.
    const visible = (distance: number) => {
      const room = element.clientWidth / 4;
      return room > 0 ? room * -Math.expm1(-distance / room) : distance;
    };
    const setDistance = (distance: number) => {
      const positive = Math.max(0, distance);
      pendingOffset = -visible(positive);
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; setState({ offset: pendingOffset, active: true }); });
      const over = positive >= SWIPE_THRESHOLD;
      if (over && !crossed) navigator.vibrate?.(10);
      crossed = over;
    };
    const reset = () => {
      cancelAnimationFrame(frame);
      frame = 0;
      crossed = false;
      setState({ offset: 0, active: false });
    };

    const down = (event: PointerEvent) => {
      if (!latest.current.enabled || latest.current.input !== 'touch' || event.pointerType !== 'touch' || !event.isPrimary) return;
      pointer = event.pointerId;
      startX = event.clientX;
      startY = event.clientY;
      intent = 'pending';
    };
    const move = (event: PointerEvent) => {
      if (event.pointerId !== pointer || intent === 'vertical') return;
      const dx = event.clientX - startX, dy = event.clientY - startY;
      const distance = -dx;
      if (intent === 'pending') {
        if (Math.max(Math.abs(dx), Math.abs(dy)) < START_DISTANCE) return;
        if (Math.abs(dy) >= Math.abs(dx)) { intent = 'vertical'; reset(); return; }
        if (distance <= 0) return;
        intent = 'horizontal';
      }
      setDistance(distance);
    };
    const up = (event: PointerEvent) => {
      if (event.pointerId !== pointer) return;
      pointer = -1;
      const commit = event.type === 'pointerup' && intent === 'horizontal' && crossed && latest.current.enabled;
      intent = 'pending';
      reset();
      if (commit) latest.current.onCommit();
    };

    const endWheel = () => {
      const commit = wheelIntent === 'horizontal' && crossed && latest.current.enabled;
      wheelIntent = 'pending';
      wheelX = wheelY = wheelDistance = 0;
      reset();
      if (commit) latest.current.onCommit();
    };
    const wheel = (event: WheelEvent) => {
      if (!latest.current.enabled || latest.current.input !== 'wheel' || event.ctrlKey || event.deltaMode !== 0) return;
      window.clearTimeout(wheelTimer);
      wheelTimer = window.setTimeout(endWheel, WHEEL_IDLE_MS);
      if (wheelIntent === 'vertical') return;
      if (wheelIntent === 'pending') {
        wheelX += event.deltaX;
        wheelY += event.deltaY;
        // Một mẫu sát ngưỡng rung tay chưa nói được hướng: gom tới hai lần khoảng khởi đầu. Lệch chéo thì chờ thêm.
        if (Math.max(Math.abs(wheelX), Math.abs(wheelY)) < START_DISTANCE * 2) return;
        if (Math.abs(wheelY) >= Math.abs(wheelX) * 1.5 || (wheelX <= 0 && Math.abs(wheelX) >= Math.abs(wheelY) * 1.5)) {
          wheelIntent = 'vertical';
          return;
        }
        if (wheelX < Math.abs(wheelY) * 1.5) return;
        wheelIntent = 'horizontal';
        wheelDistance = Math.max(0, wheelX);
      } else {
        wheelDistance = Math.max(0, wheelDistance + event.deltaX);
      }
      // Chặn cử chỉ lùi/tới trang của trình duyệt khi đã chắc là vuốt để trả lời.
      if (event.cancelable) event.preventDefault();
      setDistance(wheelDistance);
    };

    element.addEventListener('pointerdown', down, { passive: true });
    element.addEventListener('pointermove', move, { passive: true });
    element.addEventListener('pointerup', up, { passive: true });
    element.addEventListener('pointercancel', up, { passive: true });
    element.addEventListener('wheel', wheel, { passive: false });
    return () => {
      element.removeEventListener('pointerdown', down);
      element.removeEventListener('pointermove', move);
      element.removeEventListener('pointerup', up);
      element.removeEventListener('pointercancel', up);
      element.removeEventListener('wheel', wheel);
      window.clearTimeout(wheelTimer);
      cancelAnimationFrame(frame);
    };
  }, [ref]);

  return state;
}
