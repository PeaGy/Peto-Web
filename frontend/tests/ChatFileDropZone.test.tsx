import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import ChatFileDropZone from '../src/features/chat/ChatFileDropZone';

function setup(enabled = true) {
  const onFiles = vi.fn();
  const props = { enabled, hidden: false, contextKey: 'A', onFiles, className: 'chat-layout' };
  const children = <><div data-testid="history">Lịch sử</div><form><textarea aria-label="Nháp" defaultValue="Đang gõ" /></form></>;
  const view = render(<><aside data-testid="sidebar">Sidebar</aside><ChatFileDropZone {...props}>{children}</ChatFileDropZone></>);
  const root = view.container.querySelector('.chat-layout')!;
  const dataTransfer = { types: ['Files'], files: [new File(['hello'], 'note.txt', { type: 'text/plain' })], dropEffect: 'none' };
  return { ...view, root, dataTransfer, onFiles, change: (next: Partial<typeof props>) => view.rerender(
    <><aside data-testid="sidebar">Sidebar</aside><ChatFileDropZone {...props} {...next}>{children}</ChatFileDropZone></>),
  };
}

it('nhận tệp ở lịch sử và ô nhập đúng một lần, không tự gửi hoặc đổi nháp', () => {
  const { root, dataTransfer, onFiles } = setup();
  fireEvent.dragEnter(root, { dataTransfer });
  fireEvent.dragOver(root, { dataTransfer });
  expect(dataTransfer.dropEffect).toBe('copy');
  expect(screen.getByRole('status').textContent).toContain('Thêm ảnh và tệp');
  fireEvent.drop(screen.getByTestId('history'), { dataTransfer });
  expect(onFiles).toHaveBeenCalledExactlyOnceWith(dataTransfer.files);
  expect(screen.queryByRole('status')).toBeNull();
  fireEvent.dragEnter(screen.getByLabelText('Nháp'), { dataTransfer });
  fireEvent.drop(screen.getByLabelText('Nháp'), { dataTransfer });
  expect(onFiles).toHaveBeenCalledTimes(2);
  expect((screen.getByLabelText('Nháp') as HTMLTextAreaElement).value).toBe('Đang gõ');
});

it('qua phần tử con vẫn giữ lớp phủ, rời hẳn vùng chat mới đóng', () => {
  const { root, dataTransfer } = setup();
  fireEvent.dragEnter(root, { dataTransfer });
  fireEvent.dragEnter(screen.getByTestId('history'), { dataTransfer });
  fireEvent.dragLeave(root, { dataTransfer });
  expect(screen.getByRole('status')).toBeTruthy();
  fireEvent.dragLeave(screen.getByTestId('history'), { dataTransfer });
  expect(screen.queryByRole('status')).toBeNull();
});

it('sidebar không nhận tệp và thả nhầm không làm trình duyệt mở tệp', () => {
  const { root, dataTransfer, onFiles } = setup();
  fireEvent.dragEnter(root, { dataTransfer });
  const sidebar = screen.getByTestId('sidebar');
  expect(fireEvent.dragOver(sidebar, { dataTransfer })).toBe(false);
  expect(dataTransfer.dropEffect).toBe('none');
  expect(screen.queryByRole('status')).toBeNull();
  expect(fireEvent.drop(sidebar, { dataTransfer })).toBe(false);
  expect(onFiles).not.toHaveBeenCalled();
});

it('không chặn kéo chữ hoặc liên kết, không coi ảnh trong lịch sử là tệp trên máy', () => {
  const { root, onFiles } = setup();
  for (const types of [['text/plain'], ['text/uri-list', 'text/html']]) {
    const dataTransfer = { types, files: [] };
    expect(fireEvent.dragEnter(root, { dataTransfer })).toBe(true);
    expect(fireEvent.dragOver(root, { dataTransfer })).toBe(true);
    expect(fireEvent.drop(root, { dataTransfer })).toBe(true);
  }
  expect(onFiles).not.toHaveBeenCalled();
  expect(screen.queryByRole('status')).toBeNull();
});

it.each(['Escape', 'dragend', 'blur', 'drop'])('hủy kéo bằng %s không để lại lớp phủ', action => {
  const { root, dataTransfer, onFiles } = setup();
  fireEvent.dragEnter(root, { dataTransfer });
  if (action === 'Escape') fireEvent.keyDown(window, { key: 'Escape' });
  else if (action === 'dragend') fireEvent.dragEnd(window);
  else if (action === 'blur') fireEvent.blur(window);
  else fireEvent.drop(document.body, { dataTransfer });
  expect(screen.queryByRole('status')).toBeNull();
  expect(onFiles).not.toHaveBeenCalled();
});

it('khóa đính kèm trong trạng thái không nhận tệp, không hiện lời mời thả', () => {
  const { root, dataTransfer, onFiles } = setup(false);
  fireEvent.dragEnter(root, { dataTransfer });
  fireEvent.dragOver(root, { dataTransfer });
  expect(dataTransfer.dropEffect).toBe('none');
  fireEvent.drop(root, { dataTransfer });
  expect(onFiles).not.toHaveBeenCalled();
  expect(screen.queryByRole('status')).toBeNull();
});

it('đổi hội thoại hoặc khóa đính kèm xóa trạng thái kéo, không remount ô nhập', () => {
  const { root, dataTransfer, change } = setup();
  const input = screen.getByLabelText('Nháp');
  fireEvent.dragEnter(root, { dataTransfer });
  change({ contextKey: 'B' });
  expect(screen.queryByRole('status')).toBeNull();
  expect(screen.getByLabelText('Nháp')).toBe(input);
  fireEvent.dragEnter(root, { dataTransfer });
  change({ enabled: false });
  expect(screen.queryByRole('status')).toBeNull();
});

it('không nhận tệp phía sau hộp thoại và không can thiệp kéo thả khi chat bị ẩn', () => {
  const { root, dataTransfer, onFiles, change } = setup();
  const modal = document.createElement('dialog');
  modal.setAttribute('open', '');
  document.body.append(modal);
  fireEvent.dragEnter(root, { dataTransfer });
  fireEvent.drop(root, { dataTransfer });
  expect(onFiles).not.toHaveBeenCalled();
  expect(screen.queryByRole('status')).toBeNull();
  modal.remove();
  change({ hidden: true });
  expect(fireEvent.dragOver(document.body, { dataTransfer })).toBe(true);
  expect(fireEvent.drop(document.body, { dataTransfer })).toBe(true);
});

it('bảng tài liệu desktop không modal vẫn cho đính kèm trong vùng chat', () => {
  const { root, dataTransfer, onFiles } = setup();
  const panel = document.createElement('dialog');
  panel.setAttribute('open', '');
  panel.setAttribute('role', 'complementary');
  document.body.append(panel);
  fireEvent.dragEnter(root, { dataTransfer });
  expect(screen.getByRole('status')).toBeTruthy();
  fireEvent.drop(root, { dataTransfer });
  expect(onFiles).toHaveBeenCalledExactlyOnceWith(dataTransfer.files);
  panel.remove();
});
