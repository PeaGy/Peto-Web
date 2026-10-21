import { test, expect } from '@playwright/test';
import { mockPeto, openChat, openSidebar, noPageOverflow } from './fixtures';

test('Chat gửi header bình thường, không cần công tắc hay metadata trong JSON', async ({ page }, testInfo) => {
  await mockPeto(page);
  await openChat(page);
  const requestReady = page.waitForRequest(request => new URL(request.url()).pathname === '/api/chat'
    && request.method() === 'POST');
  await page.getByLabel('Nhắn cho Peto', { exact: true }).fill('Mock: cho biết OS và trình duyệt');
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  const request = await requestReady;
  expect(request.headers()['user-agent']).toBeTruthy();
  const body = request.postDataJSON();
  expect(body).not.toHaveProperty('share_device_context');
  expect(body).not.toHaveProperty('client_environment');
  expect(body).not.toHaveProperty('user_agent');
  await expect(page.getByText('Câu trả lời đã được lưu đầy đủ.', { exact: true })).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button', { name: 'Tài khoản · Người kiểm thử' }).click();
  await page.getByRole('menuitem', { name: 'Cài đặt', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Cài đặt', exact: true });
  await dialog.getByRole('button', { name: 'Tài khoản', exact: true }).click();
  await expect(dialog.getByRole('switch', { name: 'Chia sẻ hệ điều hành và trình duyệt' })).toHaveCount(0);
  await noPageOverflow(page);
  await testInfo.attach('Tài khoản không có công tắc thiết bị', { body: await dialog.screenshot(), contentType: 'image/png' });
});
