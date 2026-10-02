import { Buffer } from 'node:buffer';
import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow, openSidebar } from './fixtures';

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');

test('Companion chèn ảnh cạnh micro, mobile tách ở góc trái; gửi và tải lại vẫn có ảnh', async ({ page }, info) => {
  const state = await mockPeto(page);
  let messages: object[] = state.companion;
  const posts: { message: string; attachments: { name: string; mime: string; data: string }[] }[] = [];
  await page.route('**/api/companion', route => route.fulfill({ json: { conversation_id: 'A', messages } }));
  await page.route('**/api/attachments/test-image', route => route.fulfill({ contentType: 'image/png', body: png }));
  await page.route('**/api/chat', async route => {
    // Mạng chậm: bóng chat có thể hiện trước khi máy chủ nhận và trả xác nhận.
    await new Promise(resolve => setTimeout(resolve, 150));
    const payload = route.request().postDataJSON(); posts.push(payload);
    const user = { id: 101, role: 'user', content: payload.message, attachments: [{
      id: 'test-image', name: payload.attachments[0].name, mime: 'image/png', kind: 'image', size: png.length, url: '/api/attachments/test-image',
    }] };
    messages = [...messages, user, { id: 102, role: 'assistant', content: 'I can see your picture.' }];
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    return route.fulfill({ contentType: 'text/event-stream', body: event({ type: 'meta', conversation_id: 'A', effort: 'low', message: user })
      + event({ type: 'delta', text: 'I can see your picture.' }) + event({ type: 'done' }) });
  });
  await page.goto('/');
  await expect(page.getByRole('textbox', { name: 'Nhắn cho Peto', exact: true })).toBeVisible();
  await openSidebar(page); await page.getByRole('button', { name: 'Companion', exact: true }).click();
  const panel = page.getByRole('region', { name: 'Trò chuyện trong Companion' });
  const composer = panel.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  const upload = panel.getByLabel('Chọn ảnh cho Companion');
  // Bấm icon mở bộ chọn tệp hệ thống, không phải một bảng mới trên sân khấu.
  const chooserEvent = page.waitForEvent('filechooser');
  await panel.getByRole('button', { name: 'Đính kèm ảnh', exact: true }).click();
  await (await chooserEvent).setFiles({ name: 'nhan-vat.png', mimeType: 'image/png', buffer: png });
  await expect(panel.getByRole('img', { name: 'Ảnh chờ gửi: nhan-vat.png' })).toBeVisible();
  const photo = await panel.getByRole('button', { name: 'Đính kèm ảnh', exact: true }).boundingBox();
  const mic = await panel.getByRole('button', { name: 'Bật nghe', exact: true }).boundingBox();
  expect(photo!.x + photo!.width).toBeLessThanOrEqual(mic!.x + 1);
  if (info.project.name === 'mobile') {
    const pill = await page.locator('.companion-composer .composer').boundingBox();
    expect(photo!.x + photo!.width).toBeLessThanOrEqual(pill!.x);
    expect(photo!.x).toBeGreaterThanOrEqual(0);
    expect(photo!.width).toBeLessThanOrEqual(40);
  }
  await composer.fill('What is in this image?');
  await noPageOverflow(page);
  await page.screenshot({ path: info.outputPath('with-image.png') });
  await panel.getByRole('button', { name: 'Gỡ nhan-vat.png' }).click();
  await expect(panel.getByRole('img', { name: /^Ảnh chờ gửi:/ })).toHaveCount(0);
  await upload.setInputFiles({ name: 'nhan-vat.png', mimeType: 'image/png', buffer: png });
  await panel.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect(panel.getByText('I can see your picture.', { exact: true })).toBeVisible();
  expect(posts[0]).toMatchObject({ message: 'What is in this image?', attachments: [{ name: 'nhan-vat.png', data: png.toString('base64') }] });
  await expect(panel.getByRole('img', { name: 'nhan-vat.png', exact: true })).toBeVisible();
  await expect(panel.getByRole('img', { name: /^Ảnh chờ gửi:/ })).toHaveCount(0);
  await page.reload();
  await expect(panel.getByRole('img', { name: 'nhan-vat.png', exact: true })).toBeVisible();
  // Chỉ gửi ảnh cũng được; không phải gõ chữ cho đủ điều kiện.
  await upload.setInputFiles({ name: 'anh-moi.png', mimeType: 'image/png', buffer: png });
  await expect(panel.getByRole('button', { name: 'Gửi', exact: true })).toBeEnabled();
  await panel.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect.poll(() => posts.length).toBe(2);
  await expect(panel.getByRole('img', { name: /^Ảnh chờ gửi:/ })).toHaveCount(0);
  await expect(panel.getByRole('img', { name: 'anh-moi.png', exact: true })).toBeVisible();
  expect(posts[1].message).toBe('');
  await noPageOverflow(page);
  if (info.project.name === 'mobile') {
    await page.setViewportSize({ width: 320, height: 740 });
    await upload.setInputFiles(Array.from({ length: 4 }, (_, i) => ({ name: `anh-${i}.png`, mimeType: 'image/png', buffer: png })));
    await expect(panel.getByRole('img', { name: /^Ảnh chờ gửi:/ })).toHaveCount(4);
    expect((await panel.getByRole('button', { name: 'Đính kèm ảnh', exact: true }).boundingBox())!.x).toBeGreaterThanOrEqual(0);
    await noPageOverflow(page);
  }
});

test('ảnh lớn được thu nhỏ thật trước khi xem trước, gửi và lưu trong bóng chat trên PC/mobile', async ({ page }) => {
  await mockPeto(page);
  let received: { name: string; mime: string; data: string } | undefined;
  let saved: object[] = [];
  await page.route('**/api/companion', route => route.fulfill({ json: { conversation_id: 'A', messages: saved } }));
  await page.route('**/api/attachments/resized', route => route.fulfill({ contentType: received!.mime, body: Buffer.from(received!.data, 'base64') }));
  await page.route('**/api/chat', route => {
    received = route.request().postDataJSON().attachments[0];
    const user = { role: 'user', content: '', attachments: [{ id: 'resized', name: received!.name, mime: received!.mime,
      kind: 'image', size: Buffer.from(received!.data, 'base64').length, url: '/api/attachments/resized' }] };
    saved = [user, { role: 'assistant', content: 'A lovely picture.' }];
    return route.fulfill({ contentType: 'text/event-stream', body:
      `data: ${JSON.stringify({ type: 'meta', conversation_id: 'A', effort: 'low', message: user })}\n\n`
      + 'data: {"type":"delta","text":"A lovely picture."}\n\ndata: {"type":"done"}\n\n' });
  });
  await page.goto('/#companion');
  const panel = page.getByRole('region', { name: 'Trò chuyện trong Companion' });
  await expect(panel.getByRole('button', { name: 'Đính kèm ảnh' })).toBeEnabled();
  const original = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = 4000; canvas.height = 3000;
    const context = canvas.getContext('2d')!;
    const gradient = context.createLinearGradient(0, 0, 4000, 3000);
    gradient.addColorStop(0, '#ff6699'); gradient.addColorStop(1, '#00bbff');
    context.fillStyle = gradient; context.fillRect(0, 0, 4000, 3000);
    return canvas.toDataURL('image/jpeg', 1).split(',')[1];
  });
  await panel.getByLabel('Chọn ảnh cho Companion').setInputFiles({ name: 'large.jpg', mimeType: 'image/jpeg', buffer: Buffer.from(original, 'base64') });
  const dimensions = (image: HTMLImageElement) => ({ width: image.naturalWidth, height: image.naturalHeight });
  const preview = panel.getByRole('img', { name: 'Ảnh chờ gửi: large.jpg' });
  await expect(preview).toBeVisible();
  await expect.poll(() => preview.evaluate(dimensions)).toEqual({ width: 1920, height: 1440 });
  await panel.getByRole('button', { name: 'Gửi', exact: true }).click();
  const bubble = panel.getByRole('img', { name: 'large.jpg', exact: true });
  await expect(bubble).toBeVisible();
  await expect.poll(() => bubble.evaluate(dimensions)).toEqual({ width: 1920, height: 1440 });
  expect(received!.mime).toBe('image/jpeg');
  expect(Buffer.from(received!.data, 'base64').length).toBeLessThan(Buffer.from(original, 'base64').length);
  expect(Buffer.from(received!.data, 'base64').length).toBeLessThanOrEqual(3 * 1024 * 1024);
  await page.reload();
  await expect(bubble).toBeVisible();
  await expect.poll(() => bubble.evaluate(dimensions)).toEqual({ width: 1920, height: 1440 });
  await noPageOverflow(page);
});
