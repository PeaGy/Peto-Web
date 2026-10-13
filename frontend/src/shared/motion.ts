import { useSyncExternalStore } from 'react';

/**
 * Cài đặt → Giao diện → Chuyển động (chủ web chốt ngày 13/10/2026, như Appearance → Motion trong Cài đặt của Claude).
 * Mặc định "Mượt": web vẫn có hiệu ứng kể cả khi máy bật giảm chuyển động (Windows tắt Animation effects); ai không thích
 * thì chọn "Giảm", hoặc "Theo máy" để nghe theo thiết bị. Kết quả nằm ở <html data-motion="full|reduced">: index.html gắn
 * trước khi React chạy, App giữ nó đúng khi đổi lựa chọn hay khi máy đổi cài đặt. CSS dùng :root[data-motion="reduced"]
 * thay cho @media (prefers-reduced-motion: reduce); JS hỏi isReducedMotion() hay useReducedMotion().
 */
export type MotionChoice = 'full' | 'system' | 'reduced';
export const MOTION_KEY = 'peto-motion';
const SYSTEM_QUERY = '(prefers-reduced-motion: reduce)';

export function readMotionChoice(): MotionChoice {
  try {
    const value = localStorage.getItem(MOTION_KEY);
    return value === 'system' || value === 'reduced' ? value : 'full';
  } catch {
    return 'full';
  }
}

export function systemMotionQuery(): MediaQueryList | null {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(SYSTEM_QUERY) : null;
}

export function resolveMotion(choice: MotionChoice): 'full' | 'reduced' {
  return choice === 'reduced' || (choice === 'system' && systemMotionQuery()?.matches === true) ? 'reduced' : 'full';
}

/** Giao diện đang giảm chuyển động theo cài đặt của web (không hỏi thẳng thiết bị). */
export function isReducedMotion(): boolean {
  return typeof document !== 'undefined' && document.documentElement.dataset.motion === 'reduced';
}

export function applyMotion(choice: MotionChoice) {
  document.documentElement.dataset.motion = resolveMotion(choice);
}

const listeners = new Set<() => void>();
let observer: MutationObserver | null = null;

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!observer && typeof MutationObserver !== 'undefined') {
    observer = new MutationObserver(() => listeners.forEach(notify => notify()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-motion'] });
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size) { observer?.disconnect(); observer = null; }
  };
}

/** Như isReducedMotion() nhưng vẽ lại khi người dùng đổi lựa chọn (kể cả ở tab khác) hay khi máy đổi cài đặt. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, isReducedMotion, () => false);
}
