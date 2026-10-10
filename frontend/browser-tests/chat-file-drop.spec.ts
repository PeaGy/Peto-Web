import { test, expect } from '@playwright/test';
import { mockPeto, noPageOverflow, openChat } from './fixtures';

test('toàn vùng chat nhận nhiều tệp, lớp phủ không phủ sidebar và hợp hai theme', async ({ page }, info) => {
  const state = await mockPeto(page);
  await openChat(page);
  // Điện thoại đang mở drawer từ fixture; đóng để nhìn vùng chat thực tế.
  if (await page.locator('.sidebar-backdrop').isVisible()) await page.locator('.sidebar-backdrop').click({ position: { x: 360, y: 300 } });
  const textarea = page.getByLabel('Nhắn cho Peto', { exact: true });
  await textarea.fill('Nháp giữ nguyên khi thêm tệp');
  const files = await page.evaluateHandle(() => {
    const data = new DataTransfer();
    data.items.add(new File(['Tài liệu'], 'ghi-chu.txt', { type: 'text/plain' }));
    data.items.add(new File(['# Báo cáo'], 'bao-cao.md', { type: 'text/markdown' }));
    const png = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='), char => char.charCodeAt(0));
    data.items.add(new File([png], 'anh.png', { type: 'image/png' }));
    return data;
  });
  const history = page.locator('.messages');
  await history.dispatchEvent('dragenter', { dataTransfer: files });
  await history.dispatchEvent('dragover', { dataTransfer: files });
  const overlay = page.locator('.chat-file-drop-overlay');
  await expect(overlay).toBeVisible();
  await expect(overlay).toContainText('Thêm ảnh và tệp');
  const bounds = await overlay.boundingBox();
  const layout = await page.locator('.chat-layout').boundingBox();
  expect(bounds).toEqual(layout);
  if (info.project.name === 'pc') {
    const sidebar = await page.locator('.sidebar').boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(sidebar!.x + sidebar!.width - 1);
  }
  expect(await overlay.evaluate(node => getComputedStyle(node).pointerEvents)).toBe('none');
  await noPageOverflow(page);
  await page.screenshot({ path: info.outputPath('chat-file-drop-dark.png') });
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
  await page.screenshot({ path: info.outputPath('chat-file-drop-light.png') });
  await history.dispatchEvent('drop', { dataTransfer: files });
  await expect(overlay).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Gỡ ghi-chu.txt' })).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'Gỡ bao-cao.md' })).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'Gỡ anh.png' })).toHaveCount(1);
  await expect.poll(() => page.locator('.attach-chip img').evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(1);
  await expect(textarea).toHaveValue('Nháp giữ nguyên khi thêm tệp');
  expect(state.posts).toBe(0);
  // Kéo lần nữa vào ô nhập vẫn dùng cùng luồng chống trùng tệp.
  await textarea.dispatchEvent('dragenter', { dataTransfer: files });
  await textarea.dispatchEvent('drop', { dataTransfer: files });
  await expect(page.locator('.attach-chip')).toHaveCount(3);
  await files.dispose();
});

test('bỏ kéo hoặc chuyển sang sidebar không thêm tệp, kéo chữ không bật lớp phủ', async ({ page }) => {
  await mockPeto(page);
  await openChat(page);
  const files = await page.evaluateHandle(() => {
    const data = new DataTransfer();
    data.items.add(new File(['hello'], 'test.txt', { type: 'text/plain' }));
    return data;
  });
  const chat = page.locator('.chat-layout');
  await chat.dispatchEvent('dragenter', { dataTransfer: files });
  await expect(page.locator('.chat-file-drop-overlay')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('.chat-file-drop-overlay')).toHaveCount(0);
  const url = page.url();
  await page.locator('.sidebar').dispatchEvent('dragover', { dataTransfer: files });
  await page.locator('.sidebar').dispatchEvent('drop', { dataTransfer: files });
  await expect(page.locator('.attach-chip')).toHaveCount(0);
  expect(page.url()).toBe(url);
  const text = await page.evaluateHandle(() => {
    const data = new DataTransfer(); data.setData('text/plain', 'Một đoạn chữ'); return data;
  });
  await chat.dispatchEvent('dragenter', { dataTransfer: text });
  await expect(page.locator('.chat-file-drop-overlay')).toHaveCount(0);
  await files.dispose(); await text.dispose();
});

test('bảng tài liệu desktop vẫn nhận tệp, bảng modal điện thoại không nhận tệp vào chat phía sau', async ({ page }, info) => {
  const state = await mockPeto(page);
  await openChat(page);
  await page.getByRole('button', { name: 'Mở bảng tài liệu', exact: true }).click();
  const panel = page.locator('.document-panel');
  await expect(panel).toBeVisible();
  const files = await page.evaluateHandle(() => {
    const data = new DataTransfer(); data.items.add(new File(['hello'], 'panel.txt', { type: 'text/plain' })); return data;
  });
  await panel.dispatchEvent('dragenter', { dataTransfer: files });
  await panel.dispatchEvent('dragover', { dataTransfer: files });
  if (info.project.name === 'pc') {
    const overlay = page.locator('.chat-file-drop-overlay');
    await expect(overlay).toBeVisible();
    expect(await overlay.boundingBox()).toEqual(await page.locator('.chat-layout').boundingBox());
    await page.screenshot({ path: info.outputPath('chat-file-drop-panel.png') });
    await panel.dispatchEvent('drop', { dataTransfer: files });
    await expect(page.getByRole('button', { name: 'Gỡ panel.txt' })).toHaveCount(1);
  } else {
    await expect(page.locator('.chat-file-drop-overlay')).toHaveCount(0);
    await panel.dispatchEvent('drop', { dataTransfer: files });
    await expect(page.locator('.attach-chip')).toHaveCount(0);
  }
  expect(state.posts).toBe(0);
  await noPageOverflow(page);
  await files.dispose();
});
