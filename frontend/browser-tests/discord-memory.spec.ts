import { test, expect, type Page } from '@playwright/test';
import { mockPeto, openSidebar, noPageOverflow } from './fixtures';

async function account(page: Page) {
  await page.goto('/');
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button', { name: 'Tài khoản · Người kiểm thử' }).click();
  await page.getByRole('menuitem', { name: 'Cài đặt', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Cài đặt', exact: true });
  await dialog.getByRole('button', { name: 'Tài khoản', exact: true }).click();
  return dialog;
}

test('Discord memory switch persists across reload and a second device; failures roll back', async ({ page, browser }, info) => {
  let enabled = true, fail = false, writes = 0;
  async function mockAccount(target: Page) {
    await mockPeto(target);
    await target.route('**/api/account/discord-memory', route => {
      if (route.request().method() === 'PUT') {
        writes++;
        if (fail) return route.fulfill({ status: 503, json: { detail: 'Synthetic failure' } });
        expect(Object.keys(route.request().postDataJSON())).toEqual(['enabled']);
        enabled = route.request().postDataJSON().enabled;
      }
      return route.fulfill({ json: { enabled, available: true } });
    });
  }
  await mockAccount(page);
  let dialog = await account(page);
  let toggle = dialog.getByRole('switch', { name: 'Trí nhớ từ bot Discord' });
  await expect(toggle).toBeChecked();
  await toggle.uncheck();
  await expect.poll(() => enabled).toBe(false);
  await expect(toggle).toBeEnabled();
  await page.reload();
  dialog = await account(page);
  toggle = dialog.getByRole('switch', { name: 'Trí nhớ từ bot Discord' });
  await expect(toggle).not.toBeChecked();
  await expect(toggle).toBeEnabled();
  await dialog.screenshot({ path: info.outputPath('discord-memory-dark.png') });
  const otherContext = await browser.newContext({ viewport: page.viewportSize()!, isMobile: info.project.name === 'mobile', hasTouch: info.project.name === 'mobile' });
  try {
    const other = await otherContext.newPage(); await mockAccount(other);
    const second = await account(other);
    const secondToggle = second.getByRole('switch', { name: 'Trí nhớ từ bot Discord' });
    await expect(secondToggle).not.toBeChecked(); await expect(secondToggle).toBeEnabled();
    await secondToggle.check();
    await expect.poll(() => enabled).toBe(true);
    await expect(secondToggle).toBeEnabled();
  } finally { await otherContext.close(); }
  await dialog.getByRole('button', { name: 'Đóng cài đặt' }).click();
  // Opening Account again re-reads a change made on another device.
  dialog = await account(page); toggle = dialog.getByRole('switch', { name: 'Trí nhớ từ bot Discord' });
  await expect(toggle).toBeChecked();
  fail = true;
  await toggle.uncheck();
  await expect(dialog.getByRole('alert')).toContainText('Chưa lưu được');
  await expect(toggle).toBeChecked(); await expect(toggle).toBeEnabled();
  expect(enabled).toBe(true); expect(writes).toBe(3);
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
  await dialog.screenshot({ path: info.outputPath('discord-memory-light.png') });
  await noPageOverflow(page);
});

test('Google and GitHub accounts do not display or request the Discord-only setting', async ({ page }) => {
  await mockPeto(page);
  let provider = 'google', requests = 0;
  await page.route('**/api/auth/me', route => route.fulfill({ json: { authenticated: true, login_configured: true,
    user: { id: 'test-account', provider, username: 'demo', display_name: 'Người kiểm thử', avatar_url: '' } } }));
  await page.route('**/api/account/discord-memory', route => { requests++; return route.fulfill({ status: 403 }); });
  for (provider of ['google', 'github']) {
    const dialog = await account(page);
    await expect(dialog.getByRole('heading', { name: 'Tài khoản', exact: true })).toBeVisible();
    await expect(dialog.getByRole('switch', { name: 'Trí nhớ từ bot Discord' })).toHaveCount(0);
    await dialog.getByRole('button', { name: 'Đóng cài đặt' }).click();
  }
  expect(requests).toBe(0);
});
