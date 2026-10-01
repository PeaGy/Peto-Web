import { test, expect } from '@playwright/test';
import { mockPeto, openChat, openSidebar, title, noPageOverflow, chatMessages } from './fixtures';

test('tệp scan báo số trang đã đọc, mở chi tiết và giữ trạng thái khi tải lại', async ({ page }, info) => {
  await mockPeto(page);
  const files = [
    {id: 'scan', name: 'Kế hoạch.pdf', mime: 'application/pdf', kind: 'file', size: 2000, url: '/api/attachments/scan',
      document: {status: 'ready', characters: 1000, pages: 2, pages_read: 2, ocr_pages: 2, reading_method: 'ocr',
        notice: 'Đã đọc chữ ở 2/2 trang. OCR có thể nhận sai chữ và số; kiểm tra bản gốc khi cần trích chính xác.'}},
    {id: 'mixed', name: 'Báo cáo nhiều trang.pdf', mime: 'application/pdf', kind: 'file', size: 4000, url: '/api/attachments/mixed',
      document: {status: 'partial', characters: 500, pages: 3, pages_read: 1, ocr_pages: 1, reading_method: 'mixed',
        notice: 'Đã đọc chữ ở 1/3 trang. 2 trang chưa có chữ đọc được đầy đủ; hãy chia nhỏ hoặc gửi bản rõ hơn.'}},
  ];
  await page.route('**/api/conversations/A/messages', route => route.fulfill({json: {
    messages: chatMessages.map((message, index) => index ? message : {...message, attachments: files}),
  }}));
  await openChat(page);
  const ready = page.getByText('Đã đọc bằng OCR · 2/2 trang', {exact: true});
  await expect(ready).toBeVisible();
  await expect(page.getByText('Đọc được một phần · 1/3 trang · có OCR', {exact: true})).toBeVisible();
  await ready.click();
  await expect(page.getByText(/OCR có thể nhận sai chữ và số;/)).toBeVisible();
  await page.getByText('Đọc được một phần · 1/3 trang · có OCR', {exact: true}).click();
  await expect(page.getByText(/2 trang chưa có chữ đọc được đầy đủ;/)).toBeVisible();
  await noPageOverflow(page);
  await page.screenshot({path: info.outputPath('document-reading.png'), fullPage: true});
  await page.reload();
  // Dữ liệu giả xóa localStorage ở mỗi lần tải, nên mở lại hội thoại từ danh sách.
  await expect(page.getByLabel('Nhắn cho Peto', {exact: true})).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button', {name: title, exact: true}).click();
  await expect(ready).toBeVisible();
  await expect(page.locator('.document-details[open]')).toHaveCount(0);
});
