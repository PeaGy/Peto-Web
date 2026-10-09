import { test, expect, type Page } from '@playwright/test';
import { chatMessages, mockPeto, noPageOverflow, openChat } from './fixtures';

const names = ['Cảnh biển.png', 'Ảnh dọc.png'];
async function openImageChat(page: Page, broken = false) {
  const state = await mockPeto(page);
  // Tải xuống của Chromium không đi qua route giả. Ảnh fixture dùng data URL
  // để kiểm tra được cả dữ liệu tải thật mà không cần chạy backend hoặc API ngoài.
  const imageSource = (index: number) => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${index ? 1000 : 1600}" height="${index ? 1600 : 1000}" viewBox="0 0 1600 1000"><rect width="1600" height="1000" fill="#528c9b"/><circle cx="1240" cy="225" r="100" fill="#f6d999"/><path d="M-200 1000 540 300 1000 1000M500 1000 1220 480 1800 1000" fill="#234f60"/><path d="M0 780Q700 640 1600 850V1000H0" fill="#b2d7ce"/></svg>`;
    return `data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`;
  };
  await page.route('**/api/attachments/preview-*', route => route.fulfill({ status: 404, body: 'Ảnh không còn tồn tại.' }));
  await page.route('**/api/conversations/A/messages', route => route.fulfill({ json: {
    messages: chatMessages.map((message, i) => i ? message : { ...message,
      attachments: names.map((name, index) => ({ id: `preview-${index}`, name, mime: 'image/png', kind: 'image', size: 20480, url: broken ? `/api/attachments/preview-${index}` : imageSource(index) })),
    }),
  } }));
  await openChat(page);
  return state;
}

test('mở ảnh trong chat, zoom, tải, chuyển ảnh và đóng giữ nguyên URL, bản nháp và vị trí cuộn', async ({ page }, info) => {
  const state = await openImageChat(page);
  const draft = page.getByLabel('Nhắn cho Peto', { exact: true });
  await draft.fill('Bản nháp đang viết vẫn còn khi đóng ảnh.');
  const thumbnail = page.locator('.message-image-link').first();
  await thumbnail.scrollIntoViewIfNeeded();
  const scroll = await page.locator('.messages').evaluate(node => node.scrollTop);
  const url = page.url(), length = await page.evaluate(() => history.length), pages = page.context().pages().length;
  await thumbnail.click();
  const dialog = page.getByRole('dialog', { name: 'Xem ảnh đính kèm' });
  const image = dialog.getByRole('img');
  const zoom = dialog.getByRole('combobox', { name: 'Mức phóng ảnh' });
  await expect(zoom).toBeEnabled();
  await expect(image).toHaveAttribute('alt', names[0]);
  expect(page.url()).toBe(url);
  expect(await page.evaluate(() => history.length)).toBe(length);
  expect(page.context().pages().length).toBe(pages);
  const fit = await image.boundingBox();
  const viewport = await dialog.locator('.chat-image-stage').boundingBox();
  expect(fit!.width).toBeLessThanOrEqual(viewport!.width);
  expect(fit!.height).toBeLessThanOrEqual(viewport!.height);
  // Native dialog giữ focus trong khung xem; chat phía sau không nhận bàn phím.
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press('Tab');
    expect(await dialog.evaluate(node => node.contains(document.activeElement))).toBe(true);
  }
  await page.screenshot({ path: info.outputPath('chat-image-viewer.png') });
  await zoom.selectOption('1');
  await expect.poll(async () => (await image.boundingBox())!.width).toBeCloseTo(1600, 0);
  await zoom.selectOption('fit');
  await expect.poll(async () => (await image.boundingBox())!.width).toBeCloseTo(fit!.width, 0);
  if (info.project.name === 'pc') {
    await page.mouse.move(viewport!.x + viewport!.width / 2, viewport!.y + viewport!.height / 2);
    await page.mouse.wheel(0, -120);
    await expect.poll(async () => (await image.boundingBox())!.width).toBeGreaterThan(fit!.width);
  }
  const downloadEvent = page.waitForEvent('download');
  await dialog.getByRole('link', { name: 'Tải ảnh xuống' }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe(names[0]);
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks).toString()).toContain('<svg');
  await dialog.getByRole('button', { name: 'Ảnh tiếp theo' }).click();
  await expect(zoom).toBeEnabled();
  await expect(image).toHaveAttribute('alt', names[1]);
  await expect(zoom).toHaveValue('fit');
  await expect(dialog.getByRole('button', { name: 'Ảnh tiếp theo' })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Đóng ảnh' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(draft).toHaveValue('Bản nháp đang viết vẫn còn khi đóng ảnh.');
  expect(await page.locator('.messages').evaluate(node => node.scrollTop)).toBe(scroll);
  await expect(thumbnail).toBeFocused();
  expect(page.url()).toBe(url);
  expect(state.posts).toBe(0);
  await page.keyboard.press('Enter');
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await noPageOverflow(page);
});

test('pinch hai ngón chỉ zoom ảnh, kéo sau khi thả và đổi hướng không mất nút đóng', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'Kiểm tra hai ngón trên cấu hình cảm ứng.');
  await openImageChat(page);
  await page.locator('.message-image-link').first().click();
  const dialog = page.getByRole('dialog', { name: 'Xem ảnh đính kèm' });
  await expect(dialog.getByRole('combobox')).toBeEnabled();
  const image = dialog.getByRole('img');
  const stage = dialog.locator('.chat-image-stage');
  const frame = (await stage.boundingBox())!;
  const before = (await image.boundingBox())!;
  const center = { x: frame.x + frame.width / 2, y: frame.y + frame.height / 2 };
  const cdp = await page.context().newCDPSession(page);
  const touches = (gap: number) => [{ x: center.x - gap, y: center.y, id: 0 }, { x: center.x + gap, y: center.y, id: 1 }];
  // Trình duyệt tạo sự kiện pointer từ hai điểm chạm thật của giao thức kiểm thử,
  // thay vì tự gọi handler hoặc sửa style để giả hiệu ứng zoom.
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: touches(40) });
  for (const gap of [50, 70, 90, 120]) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: touches(gap) });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await expect.poll(async () => (await image.boundingBox())!.width / before.width).toBeCloseTo(3, 1);
  expect(await page.evaluate(() => visualViewport?.scale)).toBe(1);
  const afterPinch = (await image.boundingBox())!;
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ ...center, id: 0 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: center.x + 50, y: center.y, id: 0 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await expect.poll(async () => (await image.boundingBox())!.x - afterPinch.x).toBeCloseTo(50, 0);
  expect((await image.boundingBox())!.width).toBeCloseTo(afterPinch.width, 0);
  await page.screenshot({ path: info.outputPath('chat-image-pinch.png') });
  await dialog.getByRole('combobox').selectOption('fit');
  await page.setViewportSize({ width: 844, height: 390 });
  await expect(dialog.getByRole('button', { name: 'Đóng ảnh' })).toBeInViewport();
  await expect.poll(async () => (await image.boundingBox())!.height).toBeLessThan(390);
  await noPageOverflow(page);
  await dialog.getByRole('button', { name: 'Đóng ảnh' }).click();
  await expect(dialog).toHaveCount(0);
  await cdp.detach();
});

test('ảnh lỗi có thể thử lại và đóng ngay, không chuyển khỏi chat', async ({ page }) => {
  await openImageChat(page, true);
  const url = page.url();
  await page.locator('.message-image-link').first().click();
  const dialog = page.getByRole('dialog', { name: 'Xem ảnh đính kèm' });
  await expect(dialog.getByRole('status')).toContainText('Không tải được ảnh.');
  await dialog.getByRole('button', { name: 'Thử lại' }).click();
  await expect(dialog.getByRole('status')).toContainText('Không tải được ảnh.');
  await dialog.getByRole('button', { name: 'Đóng ảnh' }).click();
  await expect(dialog).toHaveCount(0);
  expect(page.url()).toBe(url);
});
