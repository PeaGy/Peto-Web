import { describe, expect, it } from 'vitest';
import { daySlot, fillName, greetingKey, greetingOptions, pickGreeting } from '../src/timeGreeting';

// 11/9/2026 là thứ Sáu; 6/9 là Chủ nhật, 8/9 là thứ Ba, 12/9 là thứ Bảy.
const at = (hour: number, minute = 0, day = 11) => new Date(2026, 8, day, hour, minute);

describe('Lời chào theo giờ', () => {
  it('chia buổi theo giờ trên máy', () => {
    const cases = [[0, 0, 'khuya'], [4, 59, 'khuya'], [5, 0, 'sang'], [10, 59, 'sang'],
      [11, 0, 'trua'], [13, 59, 'trua'], [14, 0, 'chieu'], [17, 59, 'chieu'],
      [18, 0, 'toi'], [21, 59, 'toi'], [22, 0, 'dem'], [23, 59, 'dem']] as const;
    for (const [hour, minute, slot] of cases) expect(daySlot(at(hour, minute))).toBe(slot);
  });

  it('câu nào cũng có chỗ điền tên, ở mọi giờ trong mọi thứ', () => {
    for (let day = 6; day <= 12; day += 1) {
      for (let hour = 0; hour < 24; hour += 1) {
        for (const option of greetingOptions(at(hour, 0, day))) expect(option).toContain('{name}');
      }
    }
  });

  it('câu theo thứ chỉ thêm vào ban ngày', () => {
    const friday = 'Thứ Sáu rồi, {name} ơi!';
    expect(greetingOptions(at(9))).toContain(friday);
    expect(greetingOptions(at(21))).toContain(friday);
    expect(greetingOptions(at(23))).not.toContain(friday);
    expect(greetingOptions(at(3))).not.toContain(friday);
    expect(greetingOptions(at(9, 0, 8)).join()).not.toContain('Thứ Sáu');
    expect(greetingOptions(at(9, 0, 12))).toContain('Cuối tuần vui chứ, {name}?');
  });

  it('chọn theo số ngẫu nhiên, không vượt ra ngoài danh sách', () => {
    const options = greetingOptions(at(8));
    expect(pickGreeting(at(8), () => 0)).toBe(options[0]);
    expect(pickGreeting(at(8), () => 0.999999)).toBe(options[options.length - 1]);
    expect(pickGreeting(at(8), () => 1)).toBe(options[options.length - 1]);
  });

  it('điền tên vào câu', () => {
    expect(fillName('Trưa rồi, {name} ăn gì chưa?', 'Peargy')).toBe('Trưa rồi, Peargy ăn gì chưa?');
  });

  it('chỉ đổi khóa khi sang buổi khác hoặc sang ngày khác', () => {
    expect(greetingKey(at(8))).toBe(greetingKey(at(10, 59)));
    expect(greetingKey(at(10, 59))).not.toBe(greetingKey(at(11)));
    expect(greetingKey(at(20, 0, 11))).not.toBe(greetingKey(at(20, 0, 12)));
  });
});
