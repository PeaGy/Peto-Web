import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import UserMessageFold, { FOLD_LIMIT } from '../src/features/chat/UserMessageFold';

// jsdom không dàn trang: giả chiều cao nội dung để kiểm logic gập.
function withHeight(height: number) {
  return vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(height);
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('UserMessageFold', () => {
  it('tin ngắn hiện đủ, không có nút', () => {
    withHeight(FOLD_LIMIT);
    const { container } = render(<UserMessageFold text="ngắn"><p>ngắn</p></UserMessageFold>);
    expect(screen.queryByRole('button')).toBeNull();
    const box = container.querySelector('.user-fold')!;
    expect(box.classList.contains('folded')).toBe(false);
    expect(box.hasAttribute('data-unmeasured')).toBe(false);
  });

  it('tin dài gập lại, Xem thêm mở ra và Thu gọn gập lại', () => {
    withHeight(FOLD_LIMIT + 1);
    const { container } = render(<UserMessageFold text="dài"><p>dài</p></UserMessageFold>);
    const box = container.querySelector('.user-fold')!;
    const toggle = screen.getByRole('button', { name: 'Xem thêm' });
    expect(box.classList.contains('folded')).toBe(true);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(toggle.getAttribute('aria-controls')).toBe(box.id);
    fireEvent.click(toggle);
    expect(box.classList.contains('folded')).toBe(false);
    expect(screen.getByRole('button', { name: 'Thu gọn' }).getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'Thu gọn' }));
    expect(box.classList.contains('folded')).toBe(true);
  });

  it('đã mở thì đổi cỡ cửa sổ không tự gập lại', () => {
    withHeight(FOLD_LIMIT + 400);
    const { container } = render(<UserMessageFold text="dài"><p>dài</p></UserMessageFold>);
    fireEvent.click(screen.getByRole('button', { name: 'Xem thêm' }));
    fireEvent(window, new Event('resize'));
    expect(container.querySelector('.user-fold')!.classList.contains('folded')).toBe(false);
  });
});
