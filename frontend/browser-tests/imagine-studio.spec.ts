import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
const image = (id: string) => ({ id, mime: 'image/png', url: `/api/imagine/images/${id}` });

test('nhiều ảnh tham chiếu, tải lại lượt đang tạo và so sánh trước sau', async ({ page }, testInfo) => {
  await mockPeto(page, { preservePreferences: true });
  const original = { id: 'original', prompt: 'Bức ảnh đã lưu', quality: 'medium', resolution: '1k', aspect_ratio: 'auto', created_at: 1, images: [image('old-image')] };
  let posts = 0;
  let accepted: typeof original & { status: string; n: number; source_images: ReturnType<typeof image>[]; source_image: ReturnType<typeof image> } | null = null;
  let complete = false;
  await page.route('**/api/imagine**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/imagine/images/')) return route.fulfill({ contentType: 'image/png', body: Buffer.from(png, 'base64') });
    if (request.method() === 'POST') {
      posts++;
      const body = request.postDataJSON();
      expect(body.background).toBe(true);
      expect(body.source_images).toEqual([{ image_id: 'old-image' }, { data: png }, { data: png }]);
      accepted = { ...original, id: 'new-job', prompt: body.prompt, status: 'running', n: 1, images: [], source_images: [image('copy-old'), image('copy-one'), image('copy-two')], source_image: image('copy-old') };
      return route.fulfill({ status: 202, json: { job: accepted } });
    }
    if (url.pathname === '/api/imagine') return route.fulfill({ json: { jobs: accepted ? [accepted, original] : [original] } });
    if (url.pathname === '/api/imagine/new-job') return route.fulfill({ json: { job: complete ? { ...accepted, status: 'complete', images: [image('result')] } : accepted } });
    return route.fulfill({ status: 404 });
  });
  await page.goto('/#imagine');
  await expect(page.getByLabel('Bức ảnh bạn muốn tạo')).toBeVisible();
  await page.getByLabel('Chọn ảnh để sửa').setInputFiles([
    { name: 'anh-1.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') },
    { name: 'anh-2.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') },
  ]);
  await expect(page.getByRole('img', { name: 'Ảnh tham chiếu 2' })).toBeVisible();
  await page.getByRole('button', { name: 'Từ thư viện' }).click();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh', exact: true });
  await library.getByRole('button', { name: 'Chọn', exact: true }).click();
  await library.getByRole('button', { name: 'Chọn ảnh: Bức ảnh đã lưu' }).click();
  await library.getByRole('button', { name: 'Dùng làm tham chiếu' }).click();
  await page.getByRole('button', { name: 'Đặt làm ảnh đầu' }).last().click();
  await page.getByLabel('Bạn muốn sửa gì trong ảnh?').fill('Lấy chủ thể ảnh 1 và nền ảnh 2');
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('references.png') });
  await page.getByRole('button', { name: 'Sửa ảnh', exact: true }).click();
  await expect(page.getByText('Peto đang tạo ảnh…', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('Peto đang tạo ảnh…', { exact: true })).toBeVisible();
  expect(posts).toBe(1);
  complete = true;
  await page.getByRole('button', { name: 'Xem ảnh 1: Lấy chủ thể ảnh 1 và nền ảnh 2' }).click();
  await page.getByRole('button', { name: 'So sánh trước / sau' }).click();
  await page.getByLabel('Chọn ảnh gốc để so sánh').selectOption('1');
  await expect(page.getByRole('img', { name: 'Ảnh gốc 2', exact: true })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Ảnh gốc 2', exact: true })).toHaveAttribute('src', '/api/imagine/images/copy-one');
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('comparison.png') });
  expect(posts).toBe(1);
});
