import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import DocumentArtifactCard from '../src/DocumentArtifactCard';
import type { DocumentArtifact } from '../src/api';

const artifact: DocumentArtifact = { id: 'D1', title: 'Bài nghị luận', filename: 'Bài nghị luận.docx', format: 'docx', style: 'essay', pages: 3, version: 1 };

it('hiện tệp có thể tải, mở lớn và lật đúng trang của phiên bản gốc', () => {
  const edit = vi.fn();
  render(<DocumentArtifactCard artifact={artifact} onEdit={edit} />);
  expect(screen.getByRole('link', { name: 'Tải Bài nghị luận.docx' }).getAttribute('href')).toBe('/api/documents/D1/export/docx?version=1');
  fireEvent.click(screen.getByRole('button', { name: 'Mở rộng Bài nghị luận.docx' }));
  const viewer = within(screen.getByRole('dialog', { name: 'Xem Bài nghị luận.docx' }));
  fireEvent.click(viewer.getByRole('button', { name: 'Trang sau' }));
  expect(viewer.getByRole('img', { name: 'Bài nghị luận — trang 2' }).getAttribute('src')).toContain('version=1&page=2');
  fireEvent.click(viewer.getByRole('button', { name: 'Sửa nội dung' }));
  expect(edit).toHaveBeenCalledWith(artifact);
  expect(screen.queryByRole('dialog')).toBeNull();
});

it('lỗi ảnh xem trước không làm mất nút tải tài liệu', () => {
  render(<DocumentArtifactCard artifact={artifact} onEdit={() => {}} />);
  fireEvent.error(screen.getByRole('img'));
  expect(screen.getByRole('alert').textContent).toContain('Chưa mở được');
  expect(screen.getByRole('link', { name: 'Tải Bài nghị luận.docx' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
  expect(screen.getByRole('img').getAttribute('src')).toContain('retry=1');
});
