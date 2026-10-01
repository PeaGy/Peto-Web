import { test, expect } from '@playwright/test';
import { mockPeto, openChat, openSidebar, noPageOverflow, title } from './fixtures';

test('sidebar và menu hội thoại gọn, chỉ hiện nút tùy chọn', async ({ page }) => {
  await mockPeto(page);
  await openChat(page);
  await openSidebar(page);
  await page.locator('.conv').first().hover();
  expect(await page.locator('.conv-hover-actions button').first().evaluate(node => getComputedStyle(node).backgroundColor))
    .toBe('rgba(0, 0, 0, 0)');
  await expect(page.locator('.conv-hover-actions button')).toHaveCount(2);
  await page.getByRole('button', { name: `Tùy chọn ${title}`, exact: true }).click();
  await expect(page.getByRole('button', { name: 'Đổi tên', exact: true })).toBeVisible();
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('sidebar-menu.png');
});

test('giá tiền, bảng, công thức và sửa tin nhắn không phá bố cục', async ({ page }) => {
  await mockPeto(page);
  await openChat(page);
  await expect(page.locator('.bubble strong').filter({ hasText: '$0.40' })).toBeVisible();
  await expect(page.locator('.katex')).toHaveCount(1);
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('chat-markdown.png');
  await page.locator('.bubble.user').hover();
  await page.getByRole('button', { name: 'Sửa tin nhắn', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Sửa tin nhắn', exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot('chat-editor.png');
  await page.getByRole('button', { name: 'Hủy', exact: true }).click();
});

test('chat dài giữ ô nhập và nút xuống cuối ổn định', async ({ page }, info) => {
  await mockPeto(page, { long: true });
  await page.goto('/');
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button', { name: title, exact: true }).click();
  await expect(page.locator('.bubble')).toHaveCount(40);
  await page.locator('.messages').evaluate(node => { node.scrollTop = 0; });
  const jump = page.getByRole('button', { name: 'Tin mới nhất', exact: true });
  await expect(jump).toBeVisible();
  const before = await jump.boundingBox();
  await page.mouse.move(before!.x + before!.width / 2, before!.y + before!.height / 2);
  await page.mouse.down();
  const held = await jump.boundingBox();
  expect(held?.x).toBeCloseTo(before!.x, 0);
  expect(held?.y).toBeCloseTo(before!.y, 0);
  await page.mouse.move(1, 1);
  await page.mouse.up();
  await page.getByLabel('Nhắn cho Peto', { exact: true }).fill('Bản nháp mới vẫn nhập được.');
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('long-chat.png');
  if (info.project.name === 'mobile') {
    await page.setViewportSize({ width: 390, height: 500 });
    await page.getByLabel('Nhắn cho Peto', { exact: true }).focus();
    await expect(page.getByRole('button', { name: 'Gửi', exact: true })).toBeInViewport();
    await noPageOverflow(page);
    await expect(page).toHaveScreenshot('chat-keyboard.png');
  }
});

test('Companion giữ khoảng cách bóng chat khi khung điện thoại thấp lại', async ({ page }, info) => {
  await mockPeto(page);
  await page.goto('/#companion');
  await expect(page.getByText('Make yourself comfortable.', { exact: false })).toBeVisible();
  const bubbles = page.locator('.companion-messages .bubble');
  await expect(bubbles).toHaveCount(4);
  if (info.project.name === 'mobile') {
    const boxes = await bubbles.evaluateAll(nodes => nodes.map(node => ({ top: node.getBoundingClientRect().top, bottom: node.getBoundingClientRect().bottom })));
    for (let i = 1; i < boxes.length; i++) expect(boxes[i].top - boxes[i - 1].bottom).toBeLessThanOrEqual(10);
  }
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('companion.png');
  if (info.project.name === 'mobile') {
    // Thu khung để mô phỏng không gian còn lại khi bàn phím mở, không giả lập IME của Android.
    await page.setViewportSize({ width: 390, height: 500 });
    await page.getByLabel('Nhắn cho Peto trong Companion').fill('Bản nháp trên điện thoại');
    await expect(page.getByRole('button', { name: 'Gửi', exact: true })).toBeInViewport();
    await noPageOverflow(page);
    await expect(page).toHaveScreenshot('companion-keyboard.png');
  }
});
