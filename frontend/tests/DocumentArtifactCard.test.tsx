import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import DocumentArtifactCard from '../src/features/documents/DocumentArtifactCard';
import type { DocumentArtifact } from '../src/shared/api/api';

const artifact: DocumentArtifact = { id: 'D1', title: 'Bài nghị luận', filename: 'Bài nghị luận.docx', format: 'docx', style: 'essay', pages: 3, version: 1 };

it('mở đúng tệp và phiên bản trong panel, vẫn tải trực tiếp được', () => {
  const edit = vi.fn();
  const open = vi.fn();
  render(<DocumentArtifactCard artifact={artifact} onEdit={edit} onOpen={open} />);
  expect(screen.getByRole('link', { name: 'Tải Bài nghị luận.docx' }).getAttribute('href')).toBe('/api/documents/D1/export/docx?version=1');
  fireEvent.click(screen.getByRole('button', { name: 'Mở rộng Bài nghị luận.docx' }));
  expect(open).toHaveBeenCalledWith(artifact);
  fireEvent.click(screen.getByRole('button', { name: 'Sửa nội dung' }));
  expect(edit).toHaveBeenCalledWith(artifact);
  expect(screen.queryByRole('dialog')).toBeNull();
});

it('lỗi ảnh xem trước không làm mất nút tải tài liệu', () => {
  render(<DocumentArtifactCard artifact={artifact} onEdit={() => {}} onOpen={() => {}} />);
  fireEvent.error(screen.getByRole('img'));
  expect(screen.getByRole('alert').textContent).toContain('Chưa mở được');
  expect(screen.getByRole('link', { name: 'Tải Bài nghị luận.docx' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
  expect(screen.getByRole('img').getAttribute('src')).toContain('retry=1');
});

it('bài thuyết trình hiện số slide, tải PPTX hoặc PDF, không có nút sửa tay', () => {
  const edit = vi.fn();
  const slides: DocumentArtifact = { id: 'P1', title: 'Thư viện số', filename: 'Thư viện số.pptx', format: 'pptx', style: 'academic', pages: 6, version: 2 };
  render(<DocumentArtifactCard artifact={slides} onEdit={edit} onOpen={() => {}} />);
  expect(screen.getByRole('region', { name: 'Bài thuyết trình Thư viện số.pptx' })).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Tải Thư viện số.pptx' }).getAttribute('href')).toBe('/api/documents/P1/export/pptx?version=2');
  expect(screen.getByRole('link', { name: 'Tải PDF' }).getAttribute('href')).toBe('/api/documents/P1/export/pdf?version=2');
  expect(screen.getByRole('button', { name: /Xem slide/ }).textContent).toContain('6 slide');
  expect(screen.queryByRole('button', { name: 'Sửa nội dung' })).toBeNull();
});
