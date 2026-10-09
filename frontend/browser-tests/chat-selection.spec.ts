import { test, expect, type Page } from '@playwright/test';
import { mockPeto, openSidebar } from './fixtures';

test('model/effort riêng theo chat đồng bộ giữa hai trình duyệt, F5 và Back/Forward', async ({ page, browser }) => {
  const stored: Record<string, { model: string; effort: string }> = {
    A: { model: 'peto', effort: 'auto' }, B: { model: 'luna', effort: 'none' },
  };
  const writes: object[] = [];
  async function setup(target: Page) {
    await mockPeto(target, { preservePreferences: true });
    await target.route('**/api/auth/me', route => route.fulfill({ json: { authenticated: true, login_configured: true,
      user: { id: 'test-account', provider: 'discord', username: 'demo', display_name: 'Người kiểm thử', avatar_url: '', models: [
        { key: 'peto', label: 'Peto', description: 'Mặc định', step_cost: 1, efforts: ['low', 'medium', 'high'] },
        { key: 'luna', label: '6 Luna', description: 'OpenAI', step_cost: 1, efforts: ['none', 'low', 'medium', 'high', 'xhigh', 'max'] },
        { key: 'haiku', label: 'Haiku 5.5', description: 'Claude', step_cost: 1, efforts: ['low', 'medium', 'high', 'xhigh', 'max'] },
      ] } } }));
    await target.route(/\/api\/conversations\/[AB](\/(messages|settings))?$/, route => {
      const id = new URL(route.request().url()).pathname.split('/')[3];
      if (route.request().method() === 'PATCH') {
        stored[id] = route.request().postDataJSON(); writes.push({ id, ...stored[id] });
        return route.fulfill({ json: { updated: true } });
      }
      return route.fulfill({ json: { ...stored[id], persona: 'assistant', messages: [
        { id: 1, role: 'user', content: `Lịch sử ${id}` }, { id: 2, role: 'assistant', content: 'Chào bạn', status: 'complete' },
      ] } });
    });
  }
  const secondContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5179', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const second = await secondContext.newPage();
  try {
    await setup(page); await page.goto('/chat/A');
    await expect(page.getByRole('button', { name: 'Model: Peto' })).toBeEnabled();
    await page.getByLabel('Nhắn cho Peto', { exact: true }).fill('Nháp A không đổi');
    await page.getByRole('button', { name: 'Model: Peto' }).click();
    await page.getByRole('menuitemradio', { name: /Haiku 5.5/ }).click();
    await page.getByRole('button', { name: 'Mức suy nghĩ: Tự động' }).click();
    await page.getByRole('menuitemradio', { name: 'Tối đa', exact: true }).click();
    await expect.poll(() => stored.A).toEqual({ model: 'haiku', effort: 'max' });
    await setup(second); await second.goto('/chat/A');
    await expect(second.getByRole('button', { name: 'Model: Haiku 5.5' })).toBeEnabled();
    await expect(second.getByRole('button', { name: 'Mức suy nghĩ: Tối đa' })).toBeVisible();
    expect(await second.evaluate(() => localStorage.getItem('peto-model'))).toBeNull();
    await openSidebar(page); await page.getByRole('button', { name: 'Một hội thoại khác', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Model: 6 Luna' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Mức suy nghĩ: Không suy luận' })).toBeVisible();
    await page.goBack();
    await expect(page.getByRole('button', { name: 'Model: Haiku 5.5' })).toBeEnabled();
    await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toHaveValue('Nháp A không đổi');
    await page.goForward(); await expect(page.getByRole('button', { name: 'Model: 6 Luna' })).toBeEnabled();
    await page.reload(); await expect(page.getByRole('button', { name: 'Mức suy nghĩ: Không suy luận' })).toBeEnabled();
    // Cập nhật trên thiết bị kia, rồi trở lại trang đang mở: chỉ khôi phục lựa chọn.
    await second.getByLabel('Nhắn cho Peto', { exact: true }).fill('Nháp ở điện thoại');
    await page.goto('/chat/A'); await expect(page.getByRole('button', { name: 'Model: Haiku 5.5' })).toBeEnabled();
    await page.getByRole('button', { name: 'Mức suy nghĩ: Tối đa' }).click();
    await page.getByRole('menuitemradio', { name: 'Thấp', exact: true }).click();
    await expect.poll(() => stored.A.effort).toBe('low');
    await second.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(second.getByRole('button', { name: 'Mức suy nghĩ: Thấp' })).toBeVisible();
    await expect(second.getByLabel('Nhắn cho Peto', { exact: true })).toHaveValue('Nháp ở điện thoại');
    await expect(second.getByText('Lịch sử A', { exact: true })).toBeVisible();
    expect(writes).toHaveLength(3);
    expect(stored.B).toEqual({ model: 'luna', effort: 'none' });
  } finally { await secondContext.close(); }
});
