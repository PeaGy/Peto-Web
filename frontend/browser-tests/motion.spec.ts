import { expect, test } from '@playwright/test';
import { mockPeto, openSidebar } from './fixtures';

for (const motion of ['full', 'reduced'] as const) {
  test(`Bảng + và Model trên điện thoại mở và đóng theo chế độ ${motion}`, async ({ page, isMobile }) => {
    test.skip(!isMobile);
    await mockPeto(page);
    await page.emulateMedia({ reducedMotion: motion === 'full' ? 'no-preference' : 'reduce' });
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('data-motion', motion);

    const transitions = await page.evaluateHandle(() => {
      const events: string[] = [];
      document.addEventListener('transitionend', event => {
        const sheet = event.target;
        if (sheet instanceof HTMLDialogElement && sheet.matches('.composer-sheet')) {
          events.push(`${sheet.open ? 'open' : 'closed'} ${event.pseudoElement || 'sheet'} ${event.propertyName}`);
        }
      });
      return events;
    });
    const expected = (phase: string) => [
      `${phase} sheet opacity`, `${phase} ::backdrop opacity`,
      ...(motion === 'full' ? [`${phase} sheet transform`] : []),
    ];
    for (const name of ['Thêm ảnh và tùy chọn', /^Model:/]) {
      await transitions.evaluate(events => { events.length = 0; });
      const trigger = page.getByRole('button', { name });
      await trigger.tap();
      const sheet = page.getByRole('dialog');
      await expect.poll(() => transitions.jsonValue()).toEqual(expect.arrayContaining(expected('open')));
      if (typeof name === 'string') await sheet.getByRole('button', { name: 'Đóng bảng' }).tap();
      else await sheet.getByRole('group', { name: 'Mức suy nghĩ' }).getByRole('button').last().tap();
      await expect.poll(() => transitions.jsonValue()).toEqual(expect.arrayContaining(expected('closed')));
      if (motion === 'reduced') expect(await transitions.jsonValue()).not.toContain('open sheet transform');
      await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    }
  });
}

// Cài đặt → Giao diện → Chuyển động (13/10/2026): mặc định Mượt kể cả khi máy giảm chuyển động (cấu hình chung giả lập
// máy giảm); người dùng chọn Giảm thì CSS theo :root[data-motion="reduced"] ngay, qua cả F5.
test('Chuyển động mặc định Mượt dù máy giảm chuyển động; chọn Giảm thì tắt chuyển tiếp và giữ qua F5', async ({ page }) => {
  await mockPeto(page, { preservePreferences: true });
  await page.addInitScript(() => { if (!sessionStorage.getItem('test-motion-kept')) localStorage.removeItem('peto-motion'); });
  await page.goto('/');
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  const motion = () => page.evaluate(() => document.documentElement.dataset.motion);
  // Mọi nút có chuyển tiếp lúc nhấn (interactions.css); Giảm thì bỏ.
  const buttonTransition = () => page.evaluate(() => getComputedStyle(document.querySelector('.composer button')!).transitionDuration);
  expect(await motion()).toBe('full');
  expect(await buttonTransition()).not.toMatch(/^0s(, 0s)*$/);

  await openSidebar(page);
  await page.getByRole('button', { name: /^Tài khoản · / }).click();
  await page.getByRole('menuitem', { name: 'Cài đặt', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'Cài đặt', exact: true });
  const group = settings.getByRole('radiogroup', { name: 'Chuyển động' });
  // Điện thoại: Cài đặt mở danh sách mục trước, chạm Giao diện mới tới trang có công tắc.
  if (!await group.isVisible()) await settings.getByRole('button', { name: 'Giao diện', exact: true }).click();
  await group.getByRole('radio', { name: /^Giảm/ }).check();
  expect(await motion()).toBe('reduced');
  expect(await buttonTransition()).toMatch(/^0s(, 0s)*$/);

  await page.evaluate(() => sessionStorage.setItem('test-motion-kept', '1'));
  await page.reload();
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  expect(await motion()).toBe('reduced');
  expect(await page.evaluate(() => localStorage.getItem('peto-motion'))).toBe('reduced');
});
