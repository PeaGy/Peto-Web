/** Phần thuần của khung chat Companion theo AIRI: nhãn giờ, phím gửi, dòng xem trước khi trả lời. */
import { describe, expect, it } from 'vitest';
import { fullTime, readableTime, SEPARATOR_GAP_SECONDS, timeSeparators } from '../src/features/companion/chat/chatTime';
import { DOUBLE_ENTER_MS, sendsOnEnter } from '../src/features/companion/chat/sendMode';
import { replyPreview } from '../src/features/companion/chat/Reply';

const at = (y: number, m: number, d: number, h: number, min: number) => new Date(y, m - 1, d, h, min).getTime() / 1000;

describe('nhãn giờ (history-time-separator của AIRI)', () => {
  it('hiện ở tin đầu và khi cách tin trước từ 5 phút; tin không có giờ thì bỏ qua', () => {
    const start = at(2026, 10, 26, 9, 0);
    expect(timeSeparators([
      { created_at: start },
      { created_at: start + 60 },
      {},
      { created_at: start + 60 + SEPARATOR_GAP_SECONDS - 1 },
      { created_at: start + 60 + SEPARATOR_GAP_SECONDS - 1 + SEPARATOR_GAP_SECONDS },
    ])).toEqual([start, undefined, undefined, undefined, start + 60 + SEPARATOR_GAP_SECONDS - 1 + SEPARATOR_GAP_SECONDS]);
  });

  it('hôm nay chỉ ghi giờ, hôm qua và hôm kia ghi chữ, xa hơn ghi ngày, khác năm thì kèm năm', () => {
    const now = new Date(2026, 9, 26, 15, 0).getTime();
    expect(readableTime(at(2026, 10, 26, 9, 5), now)).toBe('09:05');
    expect(readableTime(at(2026, 10, 25, 23, 59), now)).toBe('Hôm qua 23:59');
    expect(readableTime(at(2026, 10, 24, 8, 0), now)).toBe('Hôm kia 08:00');
    expect(readableTime(at(2026, 10, 6, 12, 42), now)).toMatch(/^6 thg 10 12:42$/);
    expect(readableTime(at(2025, 12, 31, 7, 30), now)).toMatch(/2025/);
    expect(fullTime(at(2026, 10, 6, 12, 42))).toMatch(/2026/);
  });
});

describe('phím gửi (send-button của AIRI)', () => {
  const key = (extra: Partial<{ shiftKey: boolean; ctrlKey: boolean; metaKey: boolean; isComposing: boolean }> = {}) =>
    ({ key: 'Enter', shiftKey: false, ctrlKey: false, metaKey: false, ...extra });

  it('Enter: gửi, Shift + Enter xuống dòng, đang gõ bằng bộ gõ thì không gửi', () => {
    const last = { current: 0 };
    expect(sendsOnEnter(key(), 'enter', last)).toBe(true);
    expect(sendsOnEnter(key({ shiftKey: true }), 'enter', last)).toBe(false);
    expect(sendsOnEnter(key({ isComposing: true }), 'enter', last)).toBe(false);
    expect(sendsOnEnter({ ...key(), key: 'a' }, 'enter', last)).toBe(false);
  });

  it('Ctrl + Enter: chỉ Ctrl (hay Cmd) + Enter mới gửi', () => {
    const last = { current: 0 };
    expect(sendsOnEnter(key(), 'ctrl-enter', last)).toBe(false);
    expect(sendsOnEnter(key({ ctrlKey: true }), 'ctrl-enter', last)).toBe(true);
    expect(sendsOnEnter(key({ metaKey: true }), 'ctrl-enter', last)).toBe(true);
  });

  it('nhấn Enter hai lần: lần đầu xuống dòng, lần hai trong 300ms thì gửi, chậm hơn thì tính lại từ đầu', () => {
    const last = { current: 0 };
    expect(sendsOnEnter(key(), 'double-enter', last, 1000)).toBe(false);
    expect(sendsOnEnter(key(), 'double-enter', last, 1000 + DOUBLE_ENTER_MS - 1)).toBe(true);
    expect(sendsOnEnter(key(), 'double-enter', last, 5000)).toBe(false);
    expect(sendsOnEnter(key(), 'double-enter', last, 5000 + DOUBLE_ENTER_MS + 1)).toBe(false);
  });
});

describe('dòng xem trước khi trả lời (reply.ts của AIRI)', () => {
  it('gộp khoảng trắng và cắt ở 160 ký tự kèm dấu …', () => {
    expect(replyPreview('Dòng đầu\n\n  dòng hai ')).toBe('Dòng đầu dòng hai');
    const long = replyPreview('ố'.repeat(200));
    expect(Array.from(long)).toHaveLength(160);
    expect(long.endsWith('…')).toBe(true);
  });
});
