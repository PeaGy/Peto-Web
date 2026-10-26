/**
 * Phím gửi của ô nhắn Companion, như ChatSendButton của AIRI: Enter, Ctrl + Enter, hoặc nhấn Enter hai lần. Chọn ở menu
 * của nút Gửi (rê chuột lên, chuột phải hoặc mũi tên lên); lưu theo trình duyệt.
 */
import { useSyncExternalStore } from 'react';

export type SendMode = 'enter' | 'ctrl-enter' | 'double-enter';
export const SEND_MODES: readonly SendMode[] = ['enter', 'ctrl-enter', 'double-enter'];
export const SEND_MODE_LABELS: Record<SendMode, string> = {
  'enter': 'Enter',
  'ctrl-enter': 'Ctrl + Enter',
  'double-enter': 'Nhấn Enter hai lần',
};
/** AIRI: DOUBLE_ENTER_INTERVAL_MS. */
export const DOUBLE_ENTER_MS = 300;

const KEY = 'peto-companion-send-mode';
const listeners = new Set<() => void>();

function read(): SendMode {
  try {
    const value = localStorage.getItem(KEY);
    return SEND_MODES.includes(value as SendMode) ? value as SendMode : 'enter';
  } catch {
    return 'enter';
  }
}

let current = read();

export function getSendMode(): SendMode {
  return current;
}

export function setSendMode(mode: SendMode) {
  current = mode;
  try { localStorage.setItem(KEY, mode); } catch { /* chỉ đổi trong phiên */ }
  listeners.forEach(listener => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useSendMode(): SendMode {
  return useSyncExternalStore(subscribe, getSendMode, getSendMode);
}

/**
 * Phím Enter này có gửi không. ``lastEnter`` giữ lúc nhấn Enter trước cho kiểu "nhấn hai lần"; Shift + Enter luôn xuống
 * dòng. Đang gõ bằng bộ gõ (IME) thì không gửi.
 */
export function sendsOnEnter(event: { key: string; shiftKey: boolean; ctrlKey: boolean; metaKey: boolean; isComposing?: boolean },
  mode: SendMode, lastEnter: { current: number }, now: number = Date.now()): boolean {
  if (event.key !== 'Enter' || event.isComposing) return false;
  const control = event.ctrlKey || event.metaKey;
  if (mode === 'ctrl-enter') return control;
  if (event.shiftKey || control) return false;
  if (mode === 'enter') return true;
  if (now - lastEnter.current < DOUBLE_ENTER_MS) {
    lastEnter.current = 0;
    return true;
  }
  lastEnter.current = now;
  return false;
}
