import { expect, test, type Page } from '@playwright/test';
import { mockPeto, openSidebar, title } from './fixtures';

// Xuất cả hội thoại từ menu ⋯ (28/11/2026): Tải Markdown cho mọi hội thoại, In / lưu PDF cho hội thoại đang mở. Bài
// kiểm tra chặn việc tải và in ngay trong trang (đọc nội dung tệp từ blob, đọc trang in từ một iframe), không tải gì thật.

async function captureExports(page: Page) {
  await page.addInitScript(() => {
    const store = { downloads: [] as { name: string; text: string }[], printed: '' };
    Object.assign(window, { exportsSeen: store });
    HTMLAnchorElement.prototype.click = function () {
      if (!this.download) return;
      void fetch(this.href).then(response => response.text()).then(text => store.downloads.push({ name: this.download, text }));
    };
    window.open = () => {
      const frame = document.createElement('iframe');
      frame.hidden = true;
      document.body.append(frame);
      const popup = frame.contentWindow!;
      popup.print = () => { store.printed = popup.document.body.innerText; };
      return popup;
    };
  });
}
const seen = (page: Page) => page.evaluate(() => (window as unknown as { exportsSeen: { downloads: { name: string; text: string }[]; printed: string } }).exportsSeen);

async function openMenu(page: Page, name: string) {
  await openSidebar(page);
  // Máy tính: nút ⋯ chỉ hiện khi rê chuột lên hàng.
  await page.locator('.conv').filter({ has: page.getByRole('button', { name, exact: true }) }).hover();
  await page.getByRole('button', { name: `Tùy chọn ${name}`, exact: true }).click();
  return page.getByRole('dialog', { name: 'Tùy chọn hội thoại' });
}

test('hội thoại đang mở: Tải Markdown có đủ tin và nguồn; In / lưu PDF dựng bản in có nhãn Bạn/Peto', async ({ page }) => {
  await mockPeto(page);
  await captureExports(page);
  await page.goto('/chat/A');
  await expect(page.getByText('Giúp tôi so sánh giá và công thức nhé.')).toBeVisible();

  let menu = await openMenu(page, title);
  await expect(menu.getByRole('button', { name: 'In / lưu PDF' })).toBeVisible();
  // Menu trọn trong khung nhìn.
  const box = (await menu.boundingBox())!;
  expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  await menu.getByRole('button', { name: 'Tải Markdown' }).click();
  await expect.poll(async () => (await seen(page)).downloads.length).toBe(1);
  const file = (await seen(page)).downloads[0];
  expect(file.name).toBe('peto-kiem-tra-giao-dien-peto.md');
  expect(file.text).toMatch(/^# Kiểm tra giao diện Peto\n\n_Xuất từ Peto ngày \d+\/\d+\/\d{4}_/);
  expect(file.text).toContain('## Bạn\n\nGiúp tôi so sánh giá và công thức nhé.');
  expect(file.text).toContain('## Peto\n\n');

  menu = await openMenu(page, title);
  await menu.getByRole('button', { name: 'In / lưu PDF' }).click();
  await expect.poll(async () => (await seen(page)).printed).toContain('Giúp tôi so sánh giá và công thức nhé.');
  const printed = (await seen(page)).printed;
  expect(printed).toContain('Kiểm tra giao diện Peto');
  expect(printed).toMatch(/Bạn[\s\S]*Peto/);
  expect(printed).not.toMatch(/Sao chép|Tạo lại câu trả lời/);
});

test('hội thoại khác: chỉ Tải Markdown, nội dung tải từ máy chủ', async ({ page }) => {
  await mockPeto(page);
  await captureExports(page);
  await page.goto('/chat/A');
  await expect(page.getByText('Giúp tôi so sánh giá và công thức nhé.')).toBeVisible();
  const menu = await openMenu(page, 'Một hội thoại khác');
  await expect(menu.getByRole('button', { name: 'In / lưu PDF' })).toHaveCount(0);
  await menu.getByRole('button', { name: 'Tải Markdown' }).click();
  await expect.poll(async () => (await seen(page)).downloads.length).toBe(1);
  const file = (await seen(page)).downloads[0];
  expect(file.name).toBe('peto-mot-hoi-thoai-khac.md');
  expect(file.text).toContain('# Một hội thoại khác');
  expect(file.text).toContain('## Bạn\n\nGiúp tôi so sánh giá và công thức nhé.');
  // Vẫn ở hội thoại đang mở.
  await expect(page).toHaveURL(/\/chat\/A$/);
});
