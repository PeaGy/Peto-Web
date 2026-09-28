import { useSyncExternalStore } from 'react';

/**
 * Companion có được tra web không. Chủ web chọn ngày 2026-09-28: mặc định tắt như mô-đun Web Search của AIRI, bật ở
 * Cài đặt → Tra web. Lưu theo trình duyệt như các tùy chọn Companion khác; tab Trò chuyện có công tắc riêng ở menu +.
 */
const KEY = 'peto-companion-web-search';
const EVENT = 'peto-companion-web-search-change';
// Trình duyệt chặn localStorage thì vẫn giữ lựa chọn cho phiên này.
let session: boolean | null = null;

export function readCompanionSearch(): boolean {
  try {
    return localStorage.getItem(KEY) === '1';
  } catch {
    return session ?? false;
  }
}

export function writeCompanionSearch(on: boolean) {
  session = on;
  try { localStorage.setItem(KEY, on ? '1' : '0'); } catch { /* Chỉ giữ trong phiên này. */ }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(update: () => void) {
  const stored = (event: StorageEvent) => { if (event.key === KEY || event.key === null) update(); };
  window.addEventListener(EVENT, update);
  window.addEventListener('storage', stored);
  return () => {
    window.removeEventListener(EVENT, update);
    window.removeEventListener('storage', stored);
  };
}

export function useCompanionSearch(): boolean {
  return useSyncExternalStore(subscribe, readCompanionSearch, () => false);
}
