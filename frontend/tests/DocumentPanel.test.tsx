import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import DocumentPanel from '../src/DocumentPanel';
import * as api from '../src/documentApi';
vi.mock('../src/documentApi', async original => ({ ...await original<typeof import('../src/documentApi')>(), listDocuments: vi.fn(), getDocument: vi.fn() }));
const one: api.SavedDocument = { id: 'D1', conversation_id: 'C1', title: 'Bài văn', version: 1, created_at: 1, content: '# Bài văn\nNội dung', format: 'docx', pages: 3, versions: [{ version: 2, title: 'Bản mới', created_at: 2 }, { version: 1, title: 'Bài văn', created_at: 1 }] };
const two: api.SavedDocument = { ...one, id: 'D2', title: 'Kế hoạch', format: 'pdf', pages: 1 };
const props = { conversationId: 'C1', open: true, expanded: false, selection: null, refreshKey: 0, onClose: vi.fn(), onExpand: vi.fn(), onEdit: vi.fn(), onUnauthorized: vi.fn() };
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [one, two] });
  vi.mocked(api.getDocument).mockImplementation(async id => id === 'D1' ? one : two);
});
it('liệt kê tệp, chuyển tệp, tìm tên và tải đúng phiên bản đang xem', async () => {
  render(<DocumentPanel {...props} />);
  const panel = within(screen.getByRole('complementary', { name: 'Tài liệu trong hội thoại' }));
  expect(await panel.findByRole('img', { name: 'Bài văn — trang 1' })).toBeTruthy();
  fireEvent.click(panel.getByRole('button', { name: 'Trang sau' }));
  expect(panel.getByRole('img').getAttribute('src')).toContain('version=1&page=2');
  expect(panel.getByRole('link', { name: 'Tải Bài văn.docx', exact: true }).getAttribute('href')).toContain('/D1/export/docx?version=1');
  fireEvent.click(panel.getByRole('button', { name: 'Mở Kế hoạch.pdf' }));
  expect(await panel.findByRole('img', { name: 'Kế hoạch — trang 1' })).toBeTruthy();
  expect(panel.getByRole('button', { name: 'Trang sau' })).toHaveProperty('disabled', true);
  fireEvent.change(panel.getByRole('searchbox', { name: 'Tìm tài liệu' }), { target: { value: 'kế hoạch' } });
  expect(panel.queryByRole('button', { name: 'Mở Bài văn.docx' })).toBeNull();
  fireEvent.click(panel.getByRole('button', { name: 'Sửa nội dung' }));
  expect(props.onEdit).toHaveBeenCalledWith(two);
});
it('thẻ trong chat mở bản cũ, có thể chọn lại bản mới đã sửa', async () => {
  vi.mocked(api.getDocument).mockResolvedValueOnce(one).mockResolvedValueOnce({ ...one, version: 2, content: '# Bản sửa\nNội dung đã sửa', format: null, pages: null });
  render(<DocumentPanel {...props} selection={{ id: 'D1', version: 1, key: 1 }} />);
  await screen.findByRole('img');
  expect(api.getDocument).toHaveBeenCalledWith('D1', 1, expect.any(AbortSignal));
  fireEvent.change(screen.getByRole('combobox', { name: 'Phiên bản xem trước' }), { target: { value: '2' } });
  expect((await screen.findByRole('article', { name: 'Nội dung tài liệu' })).textContent).toContain('Nội dung đã sửa');
  expect(screen.getByRole('link', { name: 'Tải Bài văn.docx', exact: true }).getAttribute('href')).toContain('version=2');
});
it('không hiển thị phản hồi đến muộn của tệp trước khi đã chọn tệp khác', async () => {
  let resolve!: (value: api.SavedDocument) => void;
  vi.mocked(api.getDocument).mockImplementation(id => id === 'D1' ? new Promise(done => { resolve = done; }) : Promise.resolve(two));
  render(<DocumentPanel {...props} />);
  await waitFor(() => expect(api.getDocument).toHaveBeenCalled());
  fireEvent.click(await screen.findByRole('button', { name: 'Mở Kế hoạch.pdf' }));
  await screen.findByRole('img', { name: 'Kế hoạch — trang 1' });
  await act(async () => resolve(one));
  expect(screen.queryByRole('img', { name: 'Bài văn — trang 1' })).toBeNull();
});
it('danh sách lỗi có thể thử lại, không làm mất lối đóng panel', async () => {
  vi.mocked(api.listDocuments).mockRejectedValueOnce(new Error('Offline'));
  render(<DocumentPanel {...props} />);
  const error = await screen.findByRole('alert');
  fireEvent.click(within(error).getByRole('button', { name: 'Thử lại' }));
  expect(await screen.findByRole('button', { name: 'Mở Bài văn.docx' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Đóng bảng tài liệu' }));
  expect(props.onClose).toHaveBeenCalled();
});
it('giao diện điện thoại dùng hộp thoại, chọn tệp xong nhường màn hình cho trang xem', async () => {
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  try {
    render(<DocumentPanel {...props} />);
    expect(screen.getByRole('dialog', { name: 'Tài liệu trong hội thoại' }).getAttribute('aria-modal')).toBe('true');
    fireEvent.click(await screen.findByRole('button', { name: 'Mở Kế hoạch.pdf' }));
    await screen.findByRole('img', { name: 'Kế hoạch — trang 1' });
    expect(screen.queryByRole('navigation', { name: 'Danh sách tài liệu' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Hiện danh sách tệp' }));
    expect(screen.getByRole('navigation', { name: 'Danh sách tài liệu' })).toBeTruthy();
  } finally { vi.unstubAllGlobals(); }
});
