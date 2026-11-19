import { test, expect, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

/** Máy chủ giả cho lối đăng nhập bằng mã email: mã 000000 sai, mã khác đúng. Không gửi thư thật. */
async function mockEmailLogin(page: Page) {
  const state = { authenticated: false, sent: [] as string[], verified: [] as string[] };
  await page.route('**/api/auth/me', route => route.fulfill({ json: state.authenticated
    ? { authenticated: true, login_configured: true, providers: { discord: true, google: true, github: true, email: true },
      user: { id: 'acc-mail', provider: 'email', username: '', display_name: 'an•••@vidu.com', avatar_url: '' } }
    : { authenticated: false, login_configured: true, providers: { discord: true, google: true, github: true, email: true } },
  }));
  await page.route('**/api/auth/email/send', route => {
    state.sent.push(route.request().postDataJSON().email);
    return route.fulfill({ json: { ok: true, resend_after: 60, expires_in: 600 } });
  });
  await page.route('**/api/auth/email/verify', route => {
    const { code } = route.request().postDataJSON();
    state.verified.push(code);
    if (code === '000000') return route.fulfill({ status: 400, json: { detail: 'Mã không đúng. Còn 4 lần thử.' } });
    state.authenticated = true;
    return route.fulfill({ json: { ok: true } });
  });
  return state;
}

test('đăng nhập như AIRI: email, mã 6 số, sáng/tối trên PC và mobile', async ({ page }) => {
  await mockPeto(page);
  const state = await mockEmailLogin(page);
  await page.goto('/chat/A?source=bookmark');

  const email = page.getByLabel('Email', { exact: true });
  await expect(page.getByRole('heading', { name: 'Đăng nhập' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Đăng nhập bằng Discord' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Steam/ })).toHaveCount(0);
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('login.png');
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
  await expect(page).toHaveScreenshot('login-light.png');
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });

  // Nhãn của nút là tên ngắn, tên đầy đủ ("Đăng nhập bằng …") cho trình đọc màn hình.
  await expect(page.getByRole('link', { name: 'Đăng nhập bằng Google' })).toContainText('Google');

  await email.fill('sai-dang');
  await page.getByRole('button', { name: 'Tiếp tục' }).click();
  await expect(page.getByRole('alert')).toHaveText('Email chưa đúng dạng. Kiểm tra lại giúp mình nhé.');
  expect(state.sent).toEqual([]);

  await email.fill('an@vidu.com');
  await email.press('Enter');
  const code = page.getByLabel('Mã đăng nhập');
  await expect(page.getByRole('heading', { name: 'Nhập mã' })).toBeVisible();
  await expect(code).toBeFocused();
  await expect(page.getByRole('button', { name: /Gửi lại mã sau \d+ giây/ })).toBeDisabled();
  expect(state.sent).toEqual(['an@vidu.com']);
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('login-code.png', { mask: [page.getByRole('button', { name: /Gửi lại mã/ })] });

  await code.fill('000000');
  await expect(page.getByRole('alert')).toHaveText('Mã không đúng. Còn 4 lần thử.');
  await expect(code).toHaveAttribute('aria-invalid', 'true');

  // Gõ đủ 6 số là tự gửi; vào app ngay tại bookmark, không qua trang nào khác.
  await code.fill('482913');
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/chat\/A\?source=bookmark$/);
  expect(state.verified).toEqual(['000000', '482913']);
});

test('đăng nhập: màn hình thấp vẫn cuộn tới tiêu đề, Đổi email giữ địa chỉ đã gõ', async ({ page }) => {
  await mockPeto(page);
  await mockEmailLogin(page);
  await page.setViewportSize({ width: 390, height: 480 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Đăng nhập' })).toBeInViewport();
  await page.getByText('Chính sách quyền riêng tư').scrollIntoViewIfNeeded();
  await expect(page.getByRole('link', { name: 'Chính sách quyền riêng tư' })).toHaveAttribute('href', '/docs/quyen-rieng-tu/');
  await noPageOverflow(page);

  await page.getByLabel('Email', { exact: true }).fill('an@vidu.com');
  await page.getByRole('button', { name: 'Tiếp tục' }).click();
  await page.getByRole('button', { name: 'Đổi email' }).click();
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue('an@vidu.com');
  await expect(page.getByLabel('Email', { exact: true })).toBeFocused();
});
