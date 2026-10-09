import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useEffect, useState } from 'react';
import { SIDEBAR_WIDTH_KEY, useSidebarResize } from '../src/app/useSidebarResize';

function SidebarWidth({ collapsed: initialCollapsed = false, onCollapsedChange }: { collapsed?: boolean; onCollapsedChange?: (collapsed: boolean) => void }) {
  const [collapsed, setCollapsed] = useState(initialCollapsed);
  useEffect(() => setCollapsed(initialCollapsed), [initialCollapsed]);
  const { width, resizing, handleProps } = useSidebarResize(collapsed, value => { setCollapsed(value); onCollapsedChange?.(value); });
  return <><output>{width}</output><div {...handleProps} role="separator" data-resizing={resizing} /></>;
}

function pointer(node: HTMLElement, type: string, x: number) {
  const event = new MouseEvent(type, { bubbles: true, button: 0, clientX: x });
  Object.defineProperty(event, 'pointerId', { value: 7 });
  fireEvent(node, event);
}
function viewport(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
  fireEvent(window, new Event('resize'));
}
function handle() {
  const node = screen.getByRole('separator');
  Object.assign(node, { setPointerCapture: vi.fn(), hasPointerCapture: () => true, releasePointerCapture: vi.fn() });
  return node;
}

describe('độ rộng thanh bên', () => {
  const originalViewport = window.innerWidth;
  beforeEach(() => { localStorage.removeItem(SIDEBAR_WIDTH_KEY); viewport(1440); });
  afterEach(() => viewport(originalViewport));

  it('kéo có giới hạn, chỉ lưu khi thả và dọn trạng thái kéo', () => {
    render(<SidebarWidth />);
    const node = handle();
    pointer(node, 'pointerdown', 260);
    pointer(node, 'pointermove', 340);
    expect(screen.getByRole('status').textContent).toBe('340');
    expect(localStorage.getItem(SIDEBAR_WIDTH_KEY)).toBeNull();
    expect(document.documentElement.classList.contains('sidebar-resizing')).toBe(true);
    pointer(node, 'pointermove', 2000);
    expect(screen.getByRole('status').textContent).toBe('420');
    pointer(node, 'pointermove', -1000);
    expect(screen.getByRole('status').textContent).toBe('64');
    pointer(node, 'pointerup', -1000);
    expect(localStorage.getItem(SIDEBAR_WIDTH_KEY)).toBe('260');
    expect(document.documentElement.classList.contains('sidebar-resizing')).toBe(false);
  });

  it('khung hẹp tự giới hạn nhưng vẫn giữ lựa chọn khi mở rộng trở lại', () => {
    localStorage.setItem(SIDEBAR_WIDTH_KEY, '420');
    render(<SidebarWidth />);
    viewport(721);
    expect(screen.getByRole('status').textContent).toBe('361');
    expect(localStorage.getItem(SIDEBAR_WIDTH_KEY)).toBe('420');
    viewport(1440);
    expect(screen.getByRole('status').textContent).toBe('420');
  });

  it('dùng bàn phím và double click; thu gọn không thay đổi độ rộng đã chọn', () => {
    const { rerender } = render(<SidebarWidth />);
    const node = handle();
    fireEvent.keyDown(node, { key: 'ArrowRight', shiftKey: true });
    expect(localStorage.getItem(SIDEBAR_WIDTH_KEY)).toBe('280');
    rerender(<SidebarWidth collapsed />);
    fireEvent.keyDown(node, { key: 'Home' });
    expect(screen.getByRole('status').textContent).toBe('64');
    expect(localStorage.getItem(SIDEBAR_WIDTH_KEY)).toBe('280');
    rerender(<SidebarWidth />);
    fireEvent.keyDown(node, { key: 'End' });
    expect(screen.getByRole('status').textContent).toBe('420');
    fireEvent.doubleClick(node);
    expect(localStorage.getItem(SIDEBAR_WIDTH_KEY)).toBe('260');
  });

  it('kéo qua ngưỡng không chốt sớm, thu gọn giữ độ rộng cũ và kéo rail ra mở lại', () => {
    localStorage.setItem(SIDEBAR_WIDTH_KEY, '340');
    const changed = vi.fn();
    render(<SidebarWidth onCollapsedChange={changed} />);
    const node = handle();
    pointer(node, 'pointerdown', 340);
    pointer(node, 'pointermove', 170);
    expect(screen.getByRole('status').textContent).toBe('170');
    pointer(node, 'pointermove', 100);
    expect(screen.getByRole('status').textContent).toBe('100');
    expect(changed).not.toHaveBeenCalled();
    pointer(node, 'pointermove', 180);
    expect(screen.getByRole('status').textContent).toBe('180');
    pointer(node, 'pointermove', 64);
    pointer(node, 'pointerup', 64);
    expect(screen.getByRole('status').textContent).toBe('64');
    expect(changed).toHaveBeenLastCalledWith(true);
    expect(localStorage.getItem(SIDEBAR_WIDTH_KEY)).toBe('340');
    pointer(node, 'pointerdown', 64);
    pointer(node, 'pointermove', 170);
    expect(screen.getByRole('status').textContent).toBe('170');
    pointer(node, 'pointerup', 170);
    expect(screen.getByRole('status').textContent).toBe('220');
    expect(changed).toHaveBeenLastCalledWith(false);
    expect(localStorage.getItem(SIDEBAR_WIDTH_KEY)).toBe('220');
  });

  it('pointercancel hủy lần kéo, giữ lựa chọn và không chốt collapsed', () => {
    const changed = vi.fn();
    render(<SidebarWidth onCollapsedChange={changed} />);
    const node = handle();
    pointer(node, 'pointerdown', 260);
    pointer(node, 'pointermove', 100);
    pointer(node, 'pointercancel', 100);
    expect(screen.getByRole('status').textContent).toBe('260');
    expect(changed).not.toHaveBeenCalled();
    expect(localStorage.getItem(SIDEBAR_WIDTH_KEY)).toBeNull();
    expect(document.documentElement.classList.contains('sidebar-resizing')).toBe(false);
  });

  it('storage bị chặn và kết thúc kéo do blur/unmount không làm kẹt con trỏ', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Storage bị chặn'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage bị chặn'); });
    const { unmount } = render(<SidebarWidth />);
    const node = handle();
    pointer(node, 'pointerdown', 260);
    pointer(node, 'pointermove', 340);
    fireEvent(window, new Event('blur'));
    expect(screen.getByRole('status').textContent).toBe('340');
    expect(document.documentElement.classList.contains('sidebar-resizing')).toBe(false);
    pointer(node, 'pointerdown', 340);
    unmount();
    expect(document.documentElement.classList.contains('sidebar-resizing')).toBe(false);
  });
});
