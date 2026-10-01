import { test, expect } from '@playwright/test';
import { mockPeto, openChat, noPageOverflow } from './fixtures';

for (const companion of [false, true]) {
  test(`đồng bộ ${companion ? 'Companion' : 'Trò chuyện'} sau khi luồng ngắt, không gửi trùng`, async ({ page, context }) => {
    const state = await mockPeto(page, { broken: true });
    if (companion) {
      await page.goto('/#companion');
      await expect(page.getByText('Hi! It is nice to see you today.', { exact: true })).toBeVisible();
    } else await openChat(page);
    const draft = page.getByLabel(companion ? 'Nhắn cho Peto trong Companion' : 'Nhắn cho Peto', { exact: true });
    const pane = page.locator(companion ? '.companion-panel' : '.chat');
    await draft.fill('Tin kiểm tra phục hồi');
    await page.getByRole('button', { name: 'Gửi', exact: true }).click();
    await expect(page.getByText('Phần đang nhận', { exact: true })).toBeVisible();
    await context.setOffline(true);
    await expect(pane.getByText('Bạn đang ngoại tuyến.', { exact: false })).toBeVisible();
    await draft.fill('Bản nháp tiếp theo');
    await expect(pane.getByRole('button', { name: 'Gửi', exact: true })).toBeDisabled();
    await noPageOverflow(page);
    await expect(page).toHaveScreenshot(`${companion ? 'companion' : 'chat'}-offline.png`);
    state.recoveryReady = true;
    await context.setOffline(false);
    await expect(page.getByText('Câu trả lời đã được lưu đầy đủ.', { exact: true })).toBeVisible();
    await expect(pane.getByText('Đã đồng bộ câu trả lời từ máy chủ.', { exact: true })).toBeVisible();
    await expect(draft).toHaveValue('Bản nháp tiếp theo');
    expect(state.posts).toBe(1);
    await expect(page.locator('.bubble').filter({ hasText: 'Tin kiểm tra phục hồi' })).toHaveCount(1);
  });
}
