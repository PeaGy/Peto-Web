// Định dạng số kiểu Việt Nam cho trang Quản trị. Thiếu dữ liệu (null) không bao giờ thành "0".

export const NO_DATA = 'Chưa có dữ liệu';

export function usd(value: number | null | undefined, missing = 'Chưa có đơn giá') {
  if (value === null || value === undefined) return missing;
  if (value > 0 && value < 0.01) return '< $0,01';
  return `$${value.toLocaleString('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export const num = (value: number) => value.toLocaleString('vi-VN');

export function compact(value: number | null | undefined) {
  if (value === null || value === undefined) return '—';
  if (value >= 1e6) return `${(value / 1e6).toLocaleString('vi-VN', { maximumFractionDigits: 1 })} tr`;
  if (value >= 1e4) return `${Math.round(value / 1e3).toLocaleString('vi-VN')} N`;
  return value.toLocaleString('vi-VN');
}

export function secs(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return '—';
  const value = ms / 1000;
  return `${value.toLocaleString('vi-VN', { maximumFractionDigits: 1, minimumFractionDigits: value < 10 ? 1 : 0 })} s`;
}

export function pct(value: number | null | undefined) {
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}%`;
}

export function day(epoch: number) {
  const date = new Date(epoch * 1000);
  return `${date.getDate().toString().padStart(2, '0')}/${(date.getMonth() + 1).toString().padStart(2, '0')}/${date.getFullYear()}`;
}

const SURFACES: Record<string, string> = { chat: 'Chat', companion: 'Companion', agent: 'Agent' };
export const surfaces = (items: string[]) => items.map(item => SURFACES[item] ?? item).join(' · ');
