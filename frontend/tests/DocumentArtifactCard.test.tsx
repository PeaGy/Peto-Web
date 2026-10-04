import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { sheetGrid } from './sheetFixture';
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

afterEach(() => { vi.unstubAllGlobals(); });

it('bảng tính hiện lưới thu nhỏ từ số liệu máy chủ, tải XLSX, đếm công thức và biểu đồ', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => sheetGrid });
  vi.stubGlobal('fetch', fetchMock);
  const open = vi.fn();
  const sheet: DocumentArtifact = { id: 'S1', title: 'Bảng điểm', filename: 'Bảng điểm.xlsx', format: 'xlsx', style: 'sheet', pages: 2, version: 3 };
  render(<DocumentArtifactCard artifact={sheet} onEdit={() => {}} onOpen={open} />);
  expect(screen.getByRole('region', { name: 'Bảng tính Bảng điểm.xlsx' })).toBeTruthy();
  expect(screen.getByRole('status').textContent).toContain('Đang mở bảng tính');
  expect(await screen.findByText('Nguyễn Minh Anh')).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith('/api/documents/S1/sheet?version=3', expect.objectContaining({ signal: expect.any(AbortSignal) }));
  expect(screen.getByText('7,8').className).toBe('n');
  expect(screen.getByText('Điểm TB')).toBeTruthy();
  expect(screen.getByText(/XLSX · 2 trang tính · 5 công thức · 2 biểu đồ/)).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Tải Bảng điểm.xlsx' }).getAttribute('href')).toBe('/api/documents/S1/export/xlsx?version=3');
  fireEvent.click(screen.getByRole('button', { name: /Xem bảng tính/ }));
  expect(open).toHaveBeenCalledWith(sheet);
  expect(screen.queryByRole('button', { name: 'Sửa nội dung' })).toBeNull();
});

it('bảng tính lỗi tải số liệu vẫn giữ nút tải và thử lại được', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ detail: 'Lỗi máy chủ' }) })
    .mockResolvedValue({ ok: true, status: 200, json: async () => sheetGrid });
  vi.stubGlobal('fetch', fetchMock);
  const sheet: DocumentArtifact = { id: 'S2', title: 'Chi tiêu', filename: 'Chi tiêu.xlsx', format: 'xlsx', style: 'sheet', pages: 1, version: 1 };
  render(<DocumentArtifactCard artifact={sheet} onEdit={() => {}} onOpen={() => {}} />);
  expect((await screen.findByRole('alert')).textContent).toContain('Chưa mở được');
  expect(screen.getByRole('link', { name: 'Tải Chi tiêu.xlsx' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
  await waitFor(() => expect(screen.getByText('Trần Gia Bảo')).toBeTruthy());
  expect(fetchMock).toHaveBeenCalledTimes(2);
});
