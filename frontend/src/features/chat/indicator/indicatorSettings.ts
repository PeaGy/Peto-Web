import { useSyncExternalStore } from 'react';

/*
 * Cài đặt → Giao diện → Chỉ báo đang làm (27/11/2026, chủ web chọn từ mẫu chạy được): hình nhỏ thay mũi tên ở dòng
 * "Đang làm" khi Peto còn đang trả lời. Lưu trong trình duyệt như Chủ đề và Chuyển động; các tab cùng máy đổi theo nhau.
 */

export type IndicatorChoice = 'machine-love-1' | 'machine-love-2' | 'tetris';
export type IndicatorSize = 16 | 20 | 24 | 32;

export const INDICATOR_KEY = 'peto-indicator';
export const INDICATOR_SIZE_KEY = 'peto-indicator-size';

export const INDICATORS: { value: IndicatorChoice; label: string; hint: string }[] = [
  { value: 'machine-love-1', label: 'Machine Love - 1', hint: 'Peto pixel nhún đầu, đủ màu' },
  { value: 'machine-love-2', label: 'Machine Love - 2', hint: 'Peto pixel nhún đầu, đơn sắc theo màu chữ' },
  { value: 'tetris', label: 'Tetris', hint: 'Ô Tetris nhiều màu, đổi kiểu theo việc Peto đang làm' },
];

export const INDICATOR_SIZES: { value: `${IndicatorSize}`; label: string; hint: string }[] = [
  { value: '16', label: 'Nhỏ', hint: '16px' },
  { value: '20', label: 'Vừa', hint: '20px, vừa dòng chữ' },
  { value: '24', label: 'Lớn', hint: '24px' },
  { value: '32', label: 'Rất lớn', hint: '32px, dòng Đang làm cao hơn' },
];

export const DEFAULT_INDICATOR: IndicatorChoice = 'machine-love-1';
export const DEFAULT_INDICATOR_SIZE: IndicatorSize = 20;

function read(key: string) {
  try { return localStorage.getItem(key); } catch { return null; }
}

export function readIndicator(): IndicatorChoice {
  const value = read(INDICATOR_KEY);
  return INDICATORS.some(item => item.value === value) ? value as IndicatorChoice : DEFAULT_INDICATOR;
}

export function readIndicatorSize(): IndicatorSize {
  const value = read(INDICATOR_SIZE_KEY);
  return INDICATOR_SIZES.some(item => item.value === value) ? Number(value) as IndicatorSize : DEFAULT_INDICATOR_SIZE;
}

const listeners = new Set<() => void>();
const notify = () => listeners.forEach(listener => listener());

function write(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch {}
  notify();
}

export const setIndicator = (value: IndicatorChoice) => write(INDICATOR_KEY, value);
export const setIndicatorSize = (value: IndicatorSize) => write(INDICATOR_SIZE_KEY, String(value));

function subscribe(listener: () => void) {
  listeners.add(listener);
  // Tab khác đổi cài đặt: sự kiện storage chỉ tới các tab còn lại.
  const storage = (event: StorageEvent) => {
    if (event.key === null || event.key === INDICATOR_KEY || event.key === INDICATOR_SIZE_KEY) listener();
  };
  window.addEventListener('storage', storage);
  return () => { listeners.delete(listener); window.removeEventListener('storage', storage); };
}

/** Chỉ báo và cỡ đang chọn; đổi ở Cài đặt (tab này hay tab khác) thì vẽ lại ngay. */
export function useIndicatorSettings() {
  const indicator = useSyncExternalStore(subscribe, readIndicator);
  const size = useSyncExternalStore(subscribe, readIndicatorSize);
  return { indicator, size };
}
