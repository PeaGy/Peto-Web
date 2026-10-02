import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { beginCompanionTiming, clearCompanionTimings, elapsed, getCompanionTimings } from '../src/features/companion/speech/companionTiming';
import CompanionTimingPanel from '../src/features/companion/speech/CompanionTimingPanel';

let time = 0;
beforeEach(() => { clearCompanionTimings(); time = 0; vi.spyOn(performance, 'now').mockImplementation(() => time); });
afterEach(() => vi.restoreAllMocks());
const begin = () => beginCompanionTiming({ input: 'text', voiceSource: 'official', search: false });

it('mỗi mốc chỉ ghi lần đầu; dừng khóa lượt cũ nhưng lượt mới vẫn đo được', () => {
  const old = begin(); time = 100; old.mark('firstText'); time = 200; old.mark('firstText');
  expect(getCompanionTimings()[0].marks.firstText).toBe(100);
  old.finish('stopped'); const saved = getCompanionTimings()[0];
  const newer = begin(); time = 300; old.mark('playing'); old.finish('complete'); newer.mark('firstText');
  expect(getCompanionTimings()[1]).toBe(saved);
  expect(getCompanionTimings()[0].marks.firstText).toBe(300);
});

it('xóa làm vô hiệu kết quả đang chờ, giữ tối đa năm lượt và không lưu nội dung', () => {
  const old = begin(); clearCompanionTimings(); old.mark('playing'); old.finish('complete');
  expect(getCompanionTimings()).toEqual([]);
  for (let index = 0; index < 8; index++) begin();
  expect(getCompanionTimings()).toHaveLength(5);
  expect(Object.keys(getCompanionTimings()[0]).sort()).toEqual(['hearing', 'id', 'input', 'marks', 'search', 'sentAt', 'status', 'voiceSource']);
});

it('tra web thay nháp thì đo lại chữ đầu của bản chốt; không phát tiếng không báo thành công', () => {
  const trace = begin(); time = 100; trace.mark('firstText'); trace.replace();
  time = 200; trace.mark('firstText'); trace.finish('complete');
  expect(getCompanionTimings()[0]).toMatchObject({ marks: { firstText: 200 }, status: 'text-only' });
  expect(elapsed(undefined, 200)).toBeNull(); expect(elapsed(300, 200)).toBeNull(); expect(elapsed(0, 0)).toBe(0);
});

it('bảng kiểm tra hiển thị đủ các khoảng chờ, ghi rõ mốc thiếu và xóa được', () => {
  time = 800;
  const trace = beginCompanionTiming({ input: 'voice', hearingSource: 'browser', voiceSource: 'official', search: false,
    hearing: { endedAt: 0, finalizedAt: 100 } });
  time = 1000; trace.mark('firstText'); time = 1200; trace.mark('textReady');
  time = 1201; trace.mark('synthesis'); time = 2200; trace.mark('playing'); trace.finish('complete');
  render(<CompanionTimingPanel />);
  fireEvent.click(screen.getByText('Kiểm tra tốc độ Companion'));
  const row = (label: string) => within(screen.getByText(label).parentElement!);
  expect(row('Ngừng nói → chốt lời').getByText('0.10 giây')).toBeTruthy();
  expect(row('Chốt lời → gửi').getByText('0.70 giây')).toBeTruthy();
  expect(row('Gửi → chữ đầu tiên').getByText('0.20 giây')).toBeTruthy();
  expect(row('Ngừng nói → bắt đầu phát').getByText('2.20 giây')).toBeTruthy();
  act(() => { time = 2300; begin(); });
  expect(row('Gửi → bắt đầu phát').getByText('Chưa đo được')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Xóa kết quả đo' }));
  expect(screen.getByText(/Chưa có lượt đo/)).toBeTruthy();
});
