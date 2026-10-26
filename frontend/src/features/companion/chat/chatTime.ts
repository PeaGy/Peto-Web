/**
 * Nhãn giờ giữa các tin Companion, như history.vue và history-time-separator.vue của AIRI (commit 74ddd90): hiện ở tin
 * đầu và mỗi khi tin cách tin trước từ 5 phút. Hôm nay chỉ ghi giờ, hôm qua và hôm kia ghi chữ, xa hơn ghi ngày; bấm vào
 * nhãn thì hiện ngày giờ đầy đủ. ``created_at`` của máy chủ tính bằng giây.
 */

/** AIRI: 5 * 60 * 1000 ms. */
export const SEPARATOR_GAP_SECONDS = 5 * 60;
const LOCALE = 'vi-VN';

/** Mốc giờ cần hiện nhãn trước mỗi tin (``undefined``: không hiện). Tin chưa có giờ hợp lệ thì bỏ qua. */
export function timeSeparators(messages: readonly { created_at?: number }[]): (number | undefined)[] {
  let previous: number | undefined;
  return messages.map(message => {
    const time = message.created_at;
    if (time == null || !Number.isFinite(time) || Number.isNaN(new Date(time * 1000).getTime())) return undefined;
    const show = previous == null || time - previous >= SEPARATOR_GAP_SECONDS;
    previous = time;
    return show ? time : undefined;
  });
}

function calendarDaysBetween(earlier: Date, later: Date): number {
  const start = new Date(earlier.getFullYear(), earlier.getMonth(), earlier.getDate());
  const end = new Date(later.getFullYear(), later.getMonth(), later.getDate());
  return Math.round((end.getTime() - start.getTime()) / 86_400_000);
}

const capitalize = (text: string) => text.charAt(0).toLocaleUpperCase(LOCALE) + text.slice(1);

/** "12:42", "Hôm qua 12:42", "Hôm kia 12:42", "6 thg 10 12:42" (khác năm thì kèm năm). */
export function readableTime(seconds: number, now: number = Date.now()): string {
  const date = new Date(seconds * 1000);
  const today = new Date(now);
  const time = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit' }).format(date);
  const days = calendarDaysBetween(date, today);
  if (days === 0) return time;
  if (days === 1 || days === 2) {
    return `${capitalize(new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' }).format(-days, 'day'))} ${time}`;
  }
  const day = new Intl.DateTimeFormat(LOCALE, {
    year: date.getFullYear() === today.getFullYear() ? undefined : 'numeric', month: 'short', day: 'numeric',
  }).format(date);
  return `${day} ${time}`;
}

/** Ngày giờ đầy đủ khi bấm vào nhãn. */
export function fullTime(seconds: number): string {
  return new Intl.DateTimeFormat(LOCALE, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(seconds * 1000));
}
