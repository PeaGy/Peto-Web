import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ChatMessage } from '../src/features/chat/ChatMessage';
import type { ChatAttachment } from '../src/shared/api/api';

function draw(document: ChatAttachment['document']) {
  return render(<ChatMessage message={{ id: 1, role: 'user', content: '', attachments: [{
    id: 'scan', name: 'kế-hoạch.pdf', kind: 'file', mime: 'application/pdf', size: 1000,
    url: '/api/attachments/scan', document,
  }] }} live={false} writing={false} onEdit={() => {}} onPreview={() => {}} />);
}

describe('trạng thái đọc tài liệu', () => {
  it('phân biệt OCR với lớp chữ và mở chi tiết nhận dạng', () => {
    draw({status: 'ready', notice: 'OCR có thể nhận sai chữ và số.', characters: 50,
      pages: 2, pages_read: 2, ocr_pages: 2, reading_method: 'ocr'});
    const summary = screen.getByText('Đã đọc bằng OCR · 2/2 trang');
    fireEvent.click(summary);
    expect(summary.closest('details')?.open).toBe(true);
    expect(screen.getByText('OCR có thể nhận sai chữ và số.')).toBeTruthy();
    expect(screen.getByRole('link', {name: /kế-hoạch.pdf/}).getAttribute('href')).toBe('/api/attachments/scan');
  });
  it('nêu phần thiếu thay vì hiển thị đã đọc đủ', () => {
    draw({status: 'partial', notice: '2 trang scan chưa đọc được.', characters: 50,
      pages: 3, pages_read: 1, ocr_pages: 1, reading_method: 'mixed'});
    expect(screen.getByText('Đọc được một phần · 1/3 trang · có OCR')).toBeTruthy();
  });
  it('tệp cũ đã đọc đủ không hiện dòng xác nhận', () => {
    const { container } = draw({status: 'ready', notice: 'Đã đọc lớp chữ.', characters: 50, pages: 2});
    expect(container.querySelector('.document-details')).toBeNull();
    expect(screen.getByRole('link', {name: /kế-hoạch.pdf/})).toBeTruthy();
  });
  it('Excel đã đọc đủ không hiện dòng xác nhận dưới thẻ', () => {
    const { container } = draw({status: 'ready', notice: 'Đã đọc 2 trang tính, 14 hàng có dữ liệu.', characters: 900, sheets: 2, sheets_read: 2, rows: 14});
    expect(container.querySelector('.document-details')).toBeNull();
  });
  it('Word đã đọc đủ không hiện dòng xác nhận dưới thẻ', () => {
    const { container } = draw({status: 'ready', notice: 'Đã đọc phần thân văn bản, bảng biểu và 12 công thức trong Word.', characters: 900, formulas: 12});
    expect(container.querySelector('.document-details')).toBeNull();
  });
  it('Word có công thức MathType thì ghi đọc được một phần', () => {
    draw({status: 'partial', notice: 'Có 3 công thức MathType Peto không đọc được.', characters: 900, formulas: 2, formulas_unread: 3});
    expect(screen.getByText('Đọc được một phần · 2 công thức · 3 công thức MathType chưa đọc')).toBeTruthy();
  });
  it('bảng tính quá lớn chỉ đọc một phần thì ghi rõ', () => {
    draw({status: 'partial', notice: 'Bảng tính quá lớn: 3 trang tính sau chưa đọc.', characters: 9000, sheets: 33, sheets_read: 30, rows: 900});
    expect(screen.getByText('Đọc được một phần · 30/33 trang tính')).toBeTruthy();
  });
});
