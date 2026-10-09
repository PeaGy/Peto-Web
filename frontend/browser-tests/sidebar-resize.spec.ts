import { test, expect, type Locator, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow, openSidebar, title } from './fixtures';

async function openLongSidebar(page: Page) {
  const state = await mockPeto(page, { long: true, preservePreferences: true });
  await page.route('**/api/conversations?*', route => route.fulfill({ json: { has_more: false, conversations: [
    { id: 'A', title, created_at: 1, updated_at: 2, message_count: 40, title_state: 'generated' },
    ...Array.from({ length: 39 }, (_, index) => ({ id: `sidebar-${index}`, title: `Hội thoại ${index + 2}: ${'Nội dung kiểm tra '.repeat(3)}`, created_at: 1, updated_at: 1, message_count: 2, title_state: 'generated' })),
  ] } }));
  await page.goto('/chat/A');
  await expect(page.locator('.bubble')).toHaveCount(40);
  await openSidebar(page);
  await expect(page.locator('.conversation-list .conv')).toHaveCount(40);
  return state;
}

async function dragHandle(page: Page, handle: Locator, delta: number, whileDragging?: () => Promise<void>) {
  const box = (await handle.boundingBox())!;
  const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(point.x, point.y);
  await page.mouse.down();
  await page.mouse.move(point.x + delta, point.y, { steps: 8 });
  await whileDragging?.();
  await page.mouse.up();
}

test('kéo mép sidebar, cuộn gần mép có khe, giữ chat và nhớ độ rộng khi F5/thu gọn', async ({ page }, info) => {
  test.skip(info.project.name !== 'pc', 'Ngăn kéo mobile giữ kích thước hiện tại.');
  const state = await openLongSidebar(page);
  const sidebar = page.locator('.sidebar'), history = page.locator('.sidebar-history');
  const handle = page.getByRole('separator', { name: 'Đổi độ rộng thanh bên' });
  const draft = page.getByLabel('Nhắn cho Peto', { exact: true });
  await draft.fill('Bản nháp không mất khi kéo thanh bên.');
  await history.evaluate(node => { node.scrollTop = 150; });
  await page.locator('.messages').evaluate(node => { node.scrollTop = 100; });
  const url = page.url(), length = await page.evaluate(() => window.history.length);
  const originalGap = await sidebar.evaluate(node => node.getBoundingClientRect().right - node.querySelector('.sidebar-history')!.getBoundingClientRect().right);
  expect(originalGap).toBeCloseTo(4, 0);
  expect(await history.evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true);
  await dragHandle(page, handle, 80, async () => {
    expect((await sidebar.boundingBox())!.width).toBe(340);
    expect(await sidebar.evaluate(node => getComputedStyle(node).transitionDuration)).toBe('0s');
    expect(await page.evaluate(() => localStorage.getItem('peto-sidebar-width'))).toBeNull();
  });
  await expect(handle).toHaveAttribute('aria-valuenow', '340');
  expect(await page.evaluate(() => localStorage.getItem('peto-sidebar-width'))).toBe('340');
  await expect(draft).toHaveValue('Bản nháp không mất khi kéo thanh bên.');
  expect(await history.evaluate(node => node.scrollTop)).toBe(150);
  expect(await page.locator('.messages').evaluate(node => node.scrollTop)).toBe(100);
  expect(page.url()).toBe(url);
  expect(await page.evaluate(() => window.history.length)).toBe(length);
  expect(state.posts).toBe(0);
  await noPageOverflow(page);
  await page.mouse.move(600, 100);
  await sidebar.screenshot({ path: info.outputPath('sidebar-resized.png') });
  await sidebar.getByRole('button', { name: 'Thu gọn thanh bên', exact: true }).click();
  expect((await sidebar.boundingBox())!.width).toBe(64);
  await expect(handle).toBeHidden();
  await sidebar.getByRole('button', { name: 'Mở rộng thanh bên', exact: true }).click();
  expect((await sidebar.boundingBox())!.width).toBe(340);
  await page.reload();
  await expect(handle).toHaveAttribute('aria-valuenow', '340');
  expect((await sidebar.boundingBox())!.width).toBe(340);
  await expect(draft).toHaveValue('Bản nháp không mất khi kéo thanh bên.');
  await handle.focus();
  await page.keyboard.press('ArrowLeft');
  expect((await sidebar.boundingBox())!.width).toBe(330);
  await handle.dblclick();
  expect((await sidebar.boundingBox())!.width).toBe(260);
});

test('giới hạn độ rộng, đổi kích thước màn hình và trở lại desktop không mất lựa chọn', async ({ page }, info) => {
  test.skip(info.project.name !== 'pc', 'Kiểm tra kéo mép trên desktop.');
  await openLongSidebar(page);
  const sidebar = page.locator('.sidebar'), handle = page.getByRole('separator', { name: 'Đổi độ rộng thanh bên' });
  await dragHandle(page, handle, 1500);
  expect((await sidebar.boundingBox())!.width).toBe(420);
  await dragHandle(page, handle, -1500);
  expect((await sidebar.boundingBox())!.width).toBe(220);
  await handle.focus();
  await page.keyboard.press('End');
  expect((await sidebar.boundingBox())!.width).toBe(420);
  await page.setViewportSize({ width: 721, height: 900 });
  await expect(handle).toHaveAttribute('aria-valuenow', '361');
  expect((await page.locator('.chat-layout').boundingBox())!.width).toBeGreaterThanOrEqual(360);
  await noPageOverflow(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await openSidebar(page);
  await expect(handle).toBeHidden();
  expect((await sidebar.boundingBox())!.width).toBe(280);
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(handle).toHaveAttribute('aria-valuenow', '420');
  expect((await sidebar.boundingBox())!.width).toBe(420);
  expect(await page.evaluate(() => document.documentElement.classList.contains('sidebar-resizing'))).toBe(false);
});

test('mobile giữ ngăn kéo và cuộn danh sách, thanh cuộn không dính mép', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'Kiểm tra ngăn kéo mobile.');
  await openLongSidebar(page);
  const sidebar = page.locator('.sidebar'), history = page.locator('.sidebar-history');
  await expect(page.getByRole('separator', { name: 'Đổi độ rộng thanh bên' })).toBeHidden();
  expect((await sidebar.boundingBox())!.width).toBe(280);
  const gap = await sidebar.evaluate(node => node.getBoundingClientRect().right - node.querySelector('.sidebar-history')!.getBoundingClientRect().right);
  expect(gap).toBeCloseTo(5, 0);
  await history.evaluate(node => { node.scrollTop = 200; });
  expect(await history.evaluate(node => node.scrollTop)).toBe(200);
  await noPageOverflow(page);
  await sidebar.screenshot({ path: info.outputPath('sidebar-mobile.png') });
  await page.getByRole('button', { name: 'Đóng danh sách hội thoại' }).click({ position: { x: page.viewportSize()!.width - 12, y: 200 } });
  await expect(sidebar).toBeHidden();
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
});
