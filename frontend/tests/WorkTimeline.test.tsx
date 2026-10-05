import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import WorkTimeline, { clock, closeWork, duration } from '../src/features/chat/WorkTimeline';
import type { WorkLog, WorkStep } from '../src/shared/api/api';

afterEach(() => vi.useRealTimers());

const steps: WorkStep[] = [
  { id: 'read-1', kind: 'read', label: 'Đã đọc bang_test.xlsx', state: 'done', start: 600, end: 2200, detail: '5 trang tính · 152 công thức' },
  { id: 'think-2', kind: 'think', label: 'Đã suy nghĩ', state: 'done', start: 2200, end: 71_000,
    summary: '**Reading the rules sheet**\n\nQuy_dinh lists L1–L9.\n\n**Planning the grade sheet**\n\nE10:F10 is merged over a score.' },
  { id: 'note-3', kind: 'note', label: 'Mình sửa Bang_luong và Bang_diem trước.', state: 'done', start: 71_000, end: 71_000 },
  { id: 'compose-4', kind: 'compose', label: 'Đã soạn lệnh sửa tệp Excel', state: 'done', start: 71_000, end: 92_000 },
  { id: 'tool-5', kind: 'tool', label: 'Sửa tệp bị từ chối, chưa ghi gì', state: 'failed', start: 92_000, end: 96_000,
    problems: ['Thay đổi 9: ô F10 nằm trong vùng gộp E10:F10'] },
  { id: 'tool-6', kind: 'tool', label: 'Đã sửa bang_test.xlsx', state: 'done', start: 141_000, end: 147_000, detail: '40 thay đổi · tính lại 64 công thức' },
];

it('định dạng thời gian như mẫu đã chọn', () => {
  expect(clock(161_400)).toBe('2:41');
  expect(duration(198_000)).toBe('3 phút 18 giây');
  expect(duration(120_000)).toBe('2 phút');
  expect(duration(300)).toBe('1 giây');
});

it('đã xong: thu lại, mở ra thấy từng bước với thời gian, tóm tắt, câu dẫn và lỗi', () => {
  render(<WorkTimeline work={{ ms: 198_000, steps, complete: true }} live={false} answering />);
  const head = screen.getByRole('button', { name: 'Đã làm trong 3 phút 18 giây' });
  expect(head.getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(head);
  expect(screen.getByText('5 trang tính · 152 công thức')).toBeTruthy();
  // Tiêu đề bước suy nghĩ là đề mục cuối trong tóm tắt của Grok; mở ra thấy cả tóm tắt.
  expect(screen.getAllByText('Planning the grade sheet').length).toBeGreaterThan(0);
  expect(screen.getByText('Quy_dinh lists L1–L9.')).toBeTruthy();
  expect(screen.getByText('1 phút 9 giây')).toBeTruthy();
  expect(screen.getByText('Mình sửa Bang_luong và Bang_diem trước.').className).toBe('work-note');
  expect(screen.getByText('Thay đổi 9: ô F10 nằm trong vùng gộp E10:F10').closest('.work-problems')).toBeTruthy();
  expect(screen.getByText('40 thay đổi · tính lại 64 công thức')).toBeTruthy();
});

it('đang chạy: đồng hồ chạy cạnh chữ, bước dở có đồng hồ riêng, thu lại khi đã có chữ trả lời', () => {
  vi.useFakeTimers();
  const startedAt = performance.now() - 65_000;
  const live: WorkLog = { ms: 0, steps: [{ id: 'compose-1', kind: 'compose', label: 'Đang soạn lệnh sửa tệp Excel…', state: 'live', start: 60_000 }] };
  const { rerender } = render(<WorkTimeline work={live} live startedAt={startedAt} answering={false} />);
  expect(document.querySelector('.work-clock')?.textContent).toBe('1:05');
  expect(screen.getByText('Đang soạn lệnh sửa tệp Excel…').className).toContain('work-shimmer');
  expect(screen.getByText('0:05')).toBeTruthy();
  act(() => { vi.advanceTimersByTime(2000); });
  expect(document.querySelector('.work-clock')?.textContent).toBe('1:07');
  rerender(<WorkTimeline work={live} live startedAt={startedAt} answering />);
  expect(document.querySelector('.work-timeline')).toBeNull();
});

it('lượt dừng giữa chừng: mở sẵn, bước dở ghi "Đã dừng khi…"', () => {
  const work = closeWork({ ms: 0, steps: [
    { id: 'wait', kind: 'wait', label: 'Đang gửi và chờ máy chủ…', state: 'live', start: 0 },
    { id: 'compose-1', kind: 'compose', label: 'Đang soạn lại thay đổi…', state: 'live', start: 121_000 },
  ] }, false, 130_000)!;
  expect(work.steps.map(step => step.id)).toEqual(['compose-1']);
  render(<WorkTimeline work={work} live={false} answering={false} />);
  expect(screen.getByRole('button', { name: 'Đã dừng sau 2 phút 10 giây' }).getAttribute('aria-expanded')).toBe('true');
  expect(screen.getByText('Đã dừng khi đang soạn lại thay đổi')).toBeTruthy();
  expect(screen.getByText('9 giây')).toBeTruthy();
});

it('tự đóng khi xong mà thiếu bản chốt: "Đang …" thành "Đã …"; không có bước nào thì chỉ hiện thời gian', () => {
  const done = closeWork({ ms: 0, steps: [{ id: 'search-1', kind: 'search', label: 'Đang tìm trên web…', state: 'live', start: 0 }] }, true, 4000)!;
  expect(done.steps[0]).toMatchObject({ state: 'done', label: 'Đã tìm trên web', end: 4000 });
  render(<WorkTimeline work={{ ms: 3000, steps: [], complete: true }} live={false} answering />);
  expect(screen.queryByRole('button')).toBeNull();
  expect(screen.getByText('Đã làm trong 3 giây')).toBeTruthy();
});
