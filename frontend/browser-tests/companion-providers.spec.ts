import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

// Nhà cung cấp và Bộ não của Companion (biến thể "Như AIRI", 13/10/2026) trên trình duyệt thật: nhập và kiểm tra khóa,
// chọn bộ não, rồi lượt Companion gửi khóa trong header. API là bản giả, không gọi nhà cung cấp thật.
test('nhập khóa ở Nhà cung cấp, chọn ở Bộ não, Companion gửi khóa trong header', async ({ page }) => {
  // Giữ khóa và lựa chọn khi F5, như trình duyệt thật.
  await mockPeto(page, { preservePreferences: true });
  const checks: { key: string | undefined; body: unknown }[] = [];
  const chats: { key: string | undefined; search: string | undefined; body: Record<string, unknown> }[] = [];
  await page.route('**/api/companion/providers/check', route => {
    checks.push({ key: route.request().headers()['x-peto-provider-key'], body: route.request().postDataJSON() });
    return route.fulfill({ json: { models: ['deepseek-chat', 'deepseek-reasoner'], deployment: false } });
  });
  await page.route('**/api/chat', route => {
    const headers = route.request().headers();
    chats.push({ key: headers['x-peto-provider-key'], search: headers['x-peto-search-key'], body: route.request().postDataJSON() });
    return route.fallback();
  });

  await page.goto('/companion/settings/providers');
  const main = page.getByRole('main');
  await expect(main.getByRole('heading', { level: 1, name: 'Nhà cung cấp' })).toBeVisible();
  await expect(page.locator('.companion-provider-card')).toHaveCount(9);
  await noPageOverflow(page);
  await page.locator('.companion-provider-card', { hasText: 'DeepSeek' }).click();
  await expect(page).toHaveURL(/\/companion\/settings\/providers\/deepseek$/);
  await page.getByLabel('Khóa API DeepSeek').fill('sk-deep-12345678');
  await page.getByRole('button', { name: 'Kiểm tra kết nối' }).click();
  await expect(page.getByText('Đã kết nối · 2 model')).toBeVisible();
  expect(checks).toEqual([{ key: 'sk-deep-12345678', body: { provider: 'deepseek' } }]);
  await noPageOverflow(page);

  await page.getByRole('button', { name: 'Chọn ở Bộ não' }).click();
  await expect(page).toHaveURL(/\/companion\/settings\/modules\/brain$/);
  await page.getByRole('combobox', { name: 'Nhà cung cấp' }).click();
  await page.getByRole('option', { name: /DeepSeek/ }).click();
  await expect(page.getByText('Đang dùng khóa DeepSeek của bạn')).toBeVisible();
  // F5 giữ lựa chọn và vẫn đúng trang.
  await page.reload();
  await expect(page.getByRole('combobox', { name: 'Nhà cung cấp' })).toContainText('DeepSeek');
  await noPageOverflow(page);

  await page.goto('/companion');
  const composer = page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  await expect(composer).toBeVisible();
  await expect(page.getByText('Trả lời ngắn bằng tiếng Anh · DeepSeek')).toBeVisible();
  await composer.fill('hello with my own key');
  await composer.press('Enter');
  await expect(page.getByText('Câu trả lời đã được lưu đầy đủ.').last()).toBeVisible();
  expect(chats).toHaveLength(1);
  expect(chats[0].key).toBe('sk-deep-12345678');
  expect(chats[0].search).toBeUndefined();
  expect(chats[0].body).toMatchObject({ mode: 'companion', provider: { id: 'deepseek', model: 'deepseek-chat' } });
  expect(JSON.stringify(chats[0].body)).not.toContain('sk-deep-12345678');
});
