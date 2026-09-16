import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import DocumentWorkspace from '../src/DocumentWorkspace';
import * as api from '../src/documentApi';

vi.mock('../src/documentApi', async original => ({ ...await original<typeof import('../src/documentApi')>(), listDocuments: vi.fn(), getDocument: vi.fn(), saveDocument: vi.fn(), downloadDocument: vi.fn(), deleteDocument: vi.fn() }));
const draft = { key: 1, conversationId: 'C1', content: '# Kế hoạch\n\nNội dung **quan trọng**.' };
const saved: api.SavedDocument = { id: 'D1', conversation_id: 'C1', title: 'Kế hoạch', content: draft.content, version: 1, created_at: 1, versions: [{ version: 1, title: 'Kế hoạch', created_at: 1 }] };
const unauthorized = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [] });
  vi.mocked(api.saveDocument).mockResolvedValue(saved);
  vi.mocked(api.getDocument).mockResolvedValue(saved);
  vi.mocked(api.downloadDocument).mockResolvedValue(new Blob(['pdf']));
  URL.createObjectURL = vi.fn(() => 'blob:document'); URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
});

it('xem bản nháp, sửa nội dung rồi lưu trước khi xuất tệp', async () => {
  render(<DocumentWorkspace request={draft} onUnauthorized={unauthorized} />);
  const dialog = within(await screen.findByRole('dialog', { name: 'Bản nháp từ Peto' }));
  expect(dialog.getByRole('article', { name: 'Nội dung tài liệu' }).textContent).toContain('quan trọng');
  fireEvent.click(dialog.getByRole('button', { name: 'Chỉnh nội dung' }));
  fireEvent.change(dialog.getByLabelText('Tên tài liệu'), { target: { value: 'Kế hoạch mới' } });
  expect(dialog.getByLabelText('Nội dung')).toHaveProperty('value', '# Kế hoạch mới\n\nNội dung **quan trọng**.');
  fireEvent.change(dialog.getByLabelText('Nội dung'), { target: { value: 'Bản đã sửa' } });
  const revised = { ...saved, title: 'Kế hoạch mới', content: 'Bản đã sửa' }; vi.mocked(api.saveDocument).mockResolvedValue(revised);
  fireEvent.click(dialog.getByRole('button', { name: 'Tải PDF' }));
  await waitFor(() => expect(api.downloadDocument).toHaveBeenCalledWith(revised, 'pdf'));
  expect(api.saveDocument).toHaveBeenCalledWith({ title: 'Kế hoạch mới', content: 'Bản đã sửa' }, 'C1', null);
});

it('đóng bản nháp chưa lưu phải cho người dùng giữ lại', async () => {
  render(<DocumentWorkspace request={draft} onUnauthorized={unauthorized} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Đóng tài liệu' }));
  expect(screen.getByText('Bạn có thay đổi chưa lưu.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Tiếp tục sửa' }));
  expect(screen.getByRole('dialog')).toBeTruthy();
  expect(api.saveDocument).not.toHaveBeenCalled();
});

it('lỗi lưu giữ bản nháp và không tải bản cũ', async () => {
  vi.mocked(api.saveDocument).mockRejectedValue(new Error('Mất kết nối'));
  render(<DocumentWorkspace request={draft} onUnauthorized={unauthorized} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Tải DOCX' }));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Mất kết nối');
  expect(api.downloadDocument).not.toHaveBeenCalled();
  expect(screen.getByRole('article').textContent).toContain('quan trọng');
});

it('mở lại tài liệu đã lưu và tải đúng phiên bản cũ đang xem', async () => {
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [{ ...saved, version: 2 }] });
  const old = { ...saved, versions: [{ version: 2, title: 'Mới', created_at: 2 }, ...saved.versions] };
  vi.mocked(api.getDocument).mockResolvedValueOnce({ ...old, version: 2, title: 'Mới' }).mockResolvedValueOnce(old);
  render(<DocumentWorkspace request={null} selection={{ id: 'D1', version: 2, key: 1 }} onUnauthorized={unauthorized} />);
  fireEvent.change(await screen.findByLabelText('Phiên bản tài liệu'), { target: { value: '1' } });
  await waitFor(() => expect(screen.getByLabelText('Phiên bản tài liệu')).toHaveProperty('value', '1'));
  fireEvent.click(screen.getByRole('button', { name: 'Tải DOCX' }));
  await waitFor(() => expect(api.downloadDocument).toHaveBeenCalledWith(old, 'docx'));
  expect(api.saveDocument).not.toHaveBeenCalled();
});
