import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import TooltipLayer from '../src/shared/ui/TooltipLayer';

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); });

function setup() {
  render(<>
    <button type="button" aria-label="Tìm kiếm hội thoại" data-tip data-tip-kbd="Ctrl+K"><svg /></button>
    <button type="button" aria-label="Thu gọn thanh bên" data-tip="Thu gọn" data-tip-side="right">x</button>
    <button type="button" aria-label="Mở menu" aria-haspopup="menu" aria-expanded="true" data-tip>m</button>
    <TooltipLayer />
  </>);
  return {
    tip: () => screen.getByRole('tooltip', { hidden: true }),
    button: (name: string) => screen.getByRole('button', { name }),
  };
}

it('hiện tên nút và phím tắt sau một nhịp chờ, ẩn ngay khi bấm', () => {
  const { tip, button } = setup();
  fireEvent.pointerOver(button('Tìm kiếm hội thoại'), { pointerType: 'mouse' });
  expect(tip().hidden).toBe(true);
  act(() => { vi.advanceTimersByTime(450); });
  expect(tip().hidden).toBe(false);
  expect(tip().querySelector('span')?.textContent).toBe('Tìm kiếm hội thoại');
  expect(tip().querySelector('kbd')?.textContent).toBe('Ctrl+K');
  fireEvent.pointerDown(button('Tìm kiếm hội thoại'), { pointerType: 'mouse' });
  expect(tip().hidden).toBe(true);
  // Vẫn trên nút vừa bấm: không hiện lại cho tới khi rời nút.
  fireEvent.pointerOver(button('Tìm kiếm hội thoại').querySelector('svg')!, { pointerType: 'mouse' });
  act(() => { vi.advanceTimersByTime(1000); });
  expect(tip().hidden).toBe(true);
});

it('rê sang nút bên cạnh thì đổi ngay không chờ, dùng chữ riêng của data-tip', () => {
  const { tip, button } = setup();
  fireEvent.pointerOver(button('Tìm kiếm hội thoại'), { pointerType: 'mouse' });
  act(() => { vi.advanceTimersByTime(450); });
  fireEvent.pointerOut(button('Tìm kiếm hội thoại'), { pointerType: 'mouse', relatedTarget: button('Thu gọn thanh bên') });
  fireEvent.pointerOver(button('Thu gọn thanh bên'), { pointerType: 'mouse' });
  expect(tip().hidden).toBe(false);
  expect(tip().textContent).toBe('Thu gọn');
  expect(tip().className).toContain('instant');
});

it('không hiện khi chạm, và không che menu đang mở của chính nút', () => {
  const { tip, button } = setup();
  fireEvent.pointerOver(button('Tìm kiếm hội thoại'), { pointerType: 'touch' });
  act(() => { vi.advanceTimersByTime(1000); });
  expect(tip().hidden).toBe(true);
  fireEvent.pointerOver(button('Mở menu'), { pointerType: 'mouse' });
  act(() => { vi.advanceTimersByTime(1000); });
  expect(tip().hidden).toBe(true);
});
