import { test, expect } from '@playwright/test';
import { mockPeto, openSidebar, noPageOverflow } from './fixtures';

test('hồ sơ: dropdown, ảnh riêng, khôi phục và F5 trên PC/mobile', async ({ page }) => {
  await mockPeto(page);
  let custom = false;
  const avatar = () => ({ avatar_url: custom ? '/api/profile/avatar?v=test' : '', custom_avatar: custom });
  const profile = { full_name: 'Nguyễn An', nickname: 'An', occupation: 'student', instructions: '' };
  await page.route('**/api/auth/me', route => route.fulfill({ json: { authenticated: true, login_configured: true,
    user: { id: 'test-account', provider: 'discord', username: 'demo', display_name: 'Người kiểm thử', ...avatar() } } }));
  await page.route('**/api/profile', route => route.fulfill({ json: { profile, avatar: avatar(),
    limits: { full_name: 80, nickname: 40, instructions: 1500 }, occupations: [
      { value: 'student', label: 'Học sinh, sinh viên' }, { value: 'software', label: 'Lập trình, kỹ thuật phần mềm' },
      ...Array.from({ length: 10 }, (_, i) => ({ value: `work-${i}`, label: `Công việc ${i + 1}` })),
      { value: 'other', label: 'Khác' },
    ] } }));
  // Ảnh PNG giả chỉ dùng trong kiểm thử, không gọi dịch vụ hay tài khoản thật.
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a43sAAAAASUVORK5CYII=', 'base64');
  await page.route('**/api/profile/avatar**', route => {
    if (route.request().method() === 'GET') return route.fulfill({ body: png, contentType: 'image/png' });
    custom = route.request().method() === 'PUT';
    return route.fulfill({ json: avatar() });
  });
  async function openProfile() {
    await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
    await openSidebar(page);
    await page.getByRole('button', { name: 'Tài khoản · Người kiểm thử' }).click();
    await page.getByRole('menuitem', { name: 'Hồ sơ', exact: true }).click();
    return page.getByRole('dialog', { name: 'Cài đặt', exact: true });
  }
  await page.goto('/');
  let dialog = await openProfile();
  await expect(dialog.getByLabel('Họ và tên')).toHaveValue('Nguyễn An');
  await noPageOverflow(page);
  await expect(dialog).toHaveScreenshot('profile.png');
  const occupation = dialog.getByRole('combobox', { name: 'Công việc của bạn' });
  await occupation.click();
  await expect(dialog.getByRole('listbox')).toBeVisible();
  await expect(dialog).toHaveScreenshot('profile-occupation.png');
  // Esc đóng dropdown trước, giữ nguyên hộp Cài đặt; End chọn dòng cuối trong danh sách dài.
  await occupation.press('Escape');
  await expect(dialog).toBeVisible();
  await occupation.press('ArrowDown');
  await occupation.press('End');
  await occupation.press('Enter');
  await expect(occupation).toContainText('Khác');
  await dialog.getByRole('button', { name: 'Đổi ảnh đại diện' }).click();
  await expect(dialog.getByRole('menuitem', { name: 'Về mặc định' })).toBeDisabled();
  await expect(dialog).toHaveScreenshot('profile-avatar-menu.png');
  await dialog.getByRole('menuitem', { name: 'Tải ảnh lên' }).press('Escape');
  await dialog.getByLabel('Chọn ảnh đại diện').setInputFiles({ name: 'photo.png', mimeType: 'image/png', buffer: png });
  await expect(dialog.locator('img[src="/api/profile/avatar?v=test"]')).toBeVisible();
  await expect(occupation).toContainText('Khác');
  await page.reload();
  dialog = await openProfile();
  await expect(dialog.locator('img[src="/api/profile/avatar?v=test"]')).toBeVisible();
  await dialog.getByRole('button', { name: 'Đổi ảnh đại diện' }).click();
  await dialog.getByRole('menuitem', { name: 'Về mặc định' }).click();
  await expect(dialog.locator('img[src="/api/profile/avatar?v=test"]')).toHaveCount(0);
  await noPageOverflow(page);
  // Cửa sổ thấp: menu phải lật lên và cuộn riêng, không tràn khỏi vùng Cài đặt.
  await page.setViewportSize({ width: 360, height: 568 });
  await dialog.getByRole('combobox', { name: 'Công việc của bạn' }).click();
  const list = dialog.getByRole('listbox');
  const bounds = await list.boundingBox();
  const body = await dialog.locator('.settings-page-body').boundingBox();
  expect(bounds && body && bounds.y >= body.y && bounds.y + bounds.height <= body.y + body.height).toBe(true);
  await list.getByRole('option', { name: 'Khác' }).click();
  await noPageOverflow(page);
});
