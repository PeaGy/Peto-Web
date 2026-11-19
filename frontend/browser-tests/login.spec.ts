import { test, expect, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

const TOKEN = 'TokenGia_' + 'x'.repeat(34);
const RESET = 'ResetGia_' + 'r'.repeat(34);
const PASSWORD = 'mat-khau-8';

type MailState = {
  authenticated: boolean; approved: boolean; claimed: boolean; accounts: Record<string, string | null>;
  signups: unknown[]; resets: string[]; newPasswords: string[];
};

const fresh = (accounts: Record<string, string | null> = {}): MailState =>
  ({ authenticated: false, approved: false, claimed: false, accounts, signups: [], resets: [], newPasswords: [] });

/** Máy chủ giả cho đăng nhập bằng email và mật khẩu. Trạng thái dùng chung giữa các tab (và cả "điện thoại") như một
 * máy chủ thật; `sameBrowser` cho biết trang này có cookie yêu cầu của lần gửi thư hay không. Không gửi thư thật. */
async function mockEmailLogin(page: Page, state: MailState, sameBrowser: boolean) {
  const providers = { discord: true, google: true, github: true, email: true };
  await page.route('**/api/auth/me', route => route.fulfill({ json: state.authenticated
    ? { authenticated: true, login_configured: true, providers,
      user: { id: 'acc-mail', provider: 'email', username: '', display_name: 'an', avatar_url: '' } }
    : { authenticated: false, login_configured: true, providers },
  }));
  await page.route('**/api/auth/email/check', route => {
    const { email } = route.request().postDataJSON();
    const known = email in state.accounts;
    return route.fulfill({ json: { state: !known ? 'new' : state.accounts[email] ? 'password' : 'no_password' } });
  });
  await page.route('**/api/auth/email/signup', route => {
    state.signups.push(route.request().postDataJSON());
    return route.fulfill({ json: { ok: true } });
  });
  await page.route('**/api/auth/email/password', route => {
    const { email, password } = route.request().postDataJSON();
    if (state.accounts[email] !== password) {
      return route.fulfill({ status: 400, json: { detail: 'Email hoặc mật khẩu không đúng.' } });
    }
    state.authenticated = true;
    return route.fulfill({ json: { ok: true } });
  });
  await page.route('**/api/auth/email/reset', route => {
    state.resets.push(route.request().postDataJSON().email);
    return route.fulfill({ json: { ok: true } });
  });
  await page.route('**/api/auth/email/reset/confirm', route => {
    const { token, password } = route.request().postDataJSON();
    if (token !== RESET) return route.fulfill({ status: 400, json: { detail: 'Đường dẫn đặt lại mật khẩu đã hết hạn.' } });
    state.newPasswords.push(password);
    return route.fulfill({ json: { ok: true } });
  });
  await page.route('**/api/auth/email/status', route => {
    if (!state.approved || state.claimed) return route.fulfill({ json: { state: 'waiting' } });
    state.claimed = true;
    state.authenticated = true;
    return route.fulfill({ json: { state: 'signed_in' } });
  });
  await page.route('**/api/auth/email/link', route => {
    const body = route.request().postDataJSON();
    if (body.token !== TOKEN || state.approved) {
      return route.fulfill({ status: 400, json: { detail: 'Đường dẫn xác nhận đã hết hạn hoặc đã được dùng.' } });
    }
    if (!sameBrowser && !body.confirm) {
      return route.fulfill({ json: { state: 'confirm', device: 'Chrome trên Windows', requested_at: 1795067460 } });
    }
    state.approved = true;
    state.authenticated = true;
    return route.fulfill({ json: { state: 'signed_in', same_browser: sameBrowser } });
  });
}

test('tạo tài khoản như AIRI: email mới, đặt mật khẩu, bấm thư xác nhận ở tab mới, tab cũ tự vào app', async ({ page, context }) => {
  await mockPeto(page);
  const state = fresh();
  await mockEmailLogin(page, state, true);
  await page.goto('/chat/A?source=bookmark');

  await expect(page.getByRole('heading', { name: 'Đăng nhập' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Steam/ })).toHaveCount(0);
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('login.png');
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
  await expect(page).toHaveScreenshot('login-light.png');
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });

  const email = page.getByLabel('Email', { exact: true });
  await email.fill('sai-dang');
  await page.getByRole('button', { name: 'Tiếp tục' }).click();
  await expect(page.getByRole('alert')).toHaveText('Email chưa đúng dạng. Kiểm tra lại giúp mình nhé.');

  await email.fill('an@vidu.com');
  await email.press('Enter');
  await expect(page.getByRole('heading', { name: 'Tạo tài khoản' })).toBeVisible();
  await expect(page.getByLabel('Tên hiển thị')).toBeFocused();
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('login-signup.png');
  await page.getByLabel('Tạo mật khẩu').fill(PASSWORD);
  await page.getByLabel('Nhập lại mật khẩu').fill('khac-roi-nha');
  await page.getByRole('button', { name: 'Tạo tài khoản' }).click();
  await expect(page.getByRole('alert')).toHaveText('Hai mật khẩu chưa khớp.');
  await page.getByLabel('Nhập lại mật khẩu').fill(PASSWORD);
  await page.getByRole('button', { name: 'Tạo tài khoản' }).click();
  await expect(page.getByRole('heading', { name: 'Kiểm tra hộp thư' })).toBeFocused();
  expect(state.signups).toEqual([{ email: 'an@vidu.com', password: PASSWORD, display_name: '' }]);
  await expect(page).toHaveScreenshot('login-inbox.png');

  const mailTab = await context.newPage();
  await mockPeto(mailTab);
  await mockEmailLogin(mailTab, state, true);
  await mailTab.goto(`/#email_token=${TOKEN}`);
  await expect(mailTab.getByRole('heading', { name: 'Email đã xác nhận' })).toBeVisible();
  expect(new URL(mailTab.url()).hash).toBe('');
  await expect(mailTab).toHaveScreenshot('login-verified.png');

  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/chat\/A\?source=bookmark$/);
});

test('đăng nhập bằng mật khẩu: Chào mừng trở lại, sai thì báo đỏ, đúng thì vào app', async ({ page }) => {
  await mockPeto(page);
  await mockEmailLogin(page, fresh({ 'an@vidu.com': PASSWORD }), true);
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill('an@vidu.com');
  await page.getByRole('button', { name: 'Tiếp tục' }).click();
  await expect(page.getByRole('heading', { name: 'Chào mừng trở lại' })).toBeVisible();
  const password = page.getByLabel('Mật khẩu', { exact: true });
  await expect(password).toBeFocused();
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('login-password.png');
  await password.fill('sai');
  await page.getByRole('button', { name: 'Đăng nhập' }).click();
  await expect(page.getByRole('alert')).toHaveText('Email hoặc mật khẩu không đúng.');
  await expect(page).toHaveScreenshot('login-password-error.png');
  await password.fill(PASSWORD);
  await password.press('Enter');
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
});

test('quên mật khẩu: gửi đường dẫn, mở thư, đặt mật khẩu mới', async ({ page }) => {
  await mockPeto(page);
  const state = fresh({ 'an@vidu.com': PASSWORD });
  await mockEmailLogin(page, state, true);
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill('an@vidu.com');
  await page.getByRole('button', { name: 'Tiếp tục' }).click();
  await page.getByRole('button', { name: 'Quên mật khẩu?' }).click();
  await expect(page.getByRole('heading', { name: 'Đặt lại mật khẩu' })).toBeVisible();
  await expect(page.getByLabel(/^Email/)).toHaveValue('an@vidu.com');
  await expect(page).toHaveScreenshot('login-forgot.png');
  await page.getByRole('button', { name: 'Gửi đường dẫn đặt lại' }).click();
  await expect(page.getByText('Nếu an@vidu.com khớp với một tài khoản, đường dẫn đặt lại đang được gửi tới.')).toBeVisible();
  expect(state.resets).toEqual(['an@vidu.com']);
  await expect(page).toHaveScreenshot('login-forgot-sent.png');

  await page.goto('about:blank');
  await page.goto(`/#reset_token=${RESET}`);
  await expect(page.getByRole('heading', { name: 'Đặt mật khẩu mới' })).toBeVisible();
  expect(new URL(page.url()).hash).toBe('');
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('login-reset.png');
  await page.getByLabel(/^Mật khẩu mới/).fill('mat-khau-moi');
  await page.getByLabel(/^Nhập lại mật khẩu mới/).fill('mat-khau-moi');
  await page.getByRole('button', { name: 'Cập nhật mật khẩu' }).click();
  await expect(page.getByRole('heading', { name: 'Đã đổi mật khẩu' })).toBeVisible();
  expect(state.newPasswords).toEqual(['mat-khau-moi']);
  await expect(page).toHaveScreenshot('login-reset-done.png');
  await page.getByRole('button', { name: 'Đi tới đăng nhập' }).click();
  await expect(page.getByRole('heading', { name: 'Đăng nhập' })).toBeVisible();
});

test('tạo tài khoản rồi mở thư trên điện thoại: xác nhận thì máy tính đang chờ tự vào', async ({ page, browser }) => {
  await mockPeto(page);
  const state = fresh();
  await mockEmailLogin(page, state, true);
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill('an@vidu.com');
  await page.getByRole('button', { name: 'Tiếp tục' }).click();
  await page.getByLabel('Tạo mật khẩu').fill(PASSWORD);
  await page.getByLabel('Nhập lại mật khẩu').fill(PASSWORD);
  await page.getByRole('button', { name: 'Tạo tài khoản' }).click();
  await expect(page.getByRole('heading', { name: 'Kiểm tra hộp thư' })).toBeVisible();

  const phoneContext = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
    colorScheme: 'dark', reducedMotion: 'reduce', locale: 'vi-VN', timezoneId: 'Asia/Ho_Chi_Minh' });
  const phone = await phoneContext.newPage();
  await mockPeto(phone);
  await mockEmailLogin(phone, state, false);
  await phone.goto(`/#email_token=${TOKEN}`);
  await expect(phone.getByRole('heading', { name: 'Xác nhận đăng nhập' })).toBeVisible();
  await expect(phone.getByText(/Cho phép Chrome trên Windows đăng nhập vào Peto \(yêu cầu lúc 12:51\)/)).toBeVisible();
  await expect(phone).toHaveScreenshot('login-confirm.png');
  await phone.getByRole('button', { name: 'Xác nhận' }).click();
  await expect(phone.getByText('Thiết bị kia sẽ tự tiếp tục.', { exact: false })).toBeVisible();
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  await phoneContext.close();
});

test('đăng nhập: màn hình thấp vẫn cuộn tới tiêu đề; Dùng email khác giữ email; đường dẫn hỏng báo lỗi', async ({ page }) => {
  await mockPeto(page);
  await mockEmailLogin(page, fresh(), true);
  await page.setViewportSize({ width: 390, height: 480 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Đăng nhập' })).toBeInViewport();
  await page.getByText('Chính sách quyền riêng tư').scrollIntoViewIfNeeded();
  await expect(page.getByRole('link', { name: 'Chính sách quyền riêng tư' })).toHaveAttribute('href', '/docs/quyen-rieng-tu/');
  await noPageOverflow(page);

  await page.getByLabel('Email', { exact: true }).fill('an@vidu.com');
  await page.getByRole('button', { name: 'Tiếp tục' }).click();
  await page.getByRole('button', { name: 'Dùng email khác' }).click();
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue('an@vidu.com');
  await expect(page.getByLabel('Email', { exact: true })).toBeFocused();

  await page.goto('about:blank');
  await page.goto(`/#email_token=${'y'.repeat(43)}`);
  await expect(page.getByRole('alert')).toHaveText('Đường dẫn xác nhận đã hết hạn hoặc đã được dùng.');
  await page.getByRole('button', { name: 'Quay lại đăng nhập' }).click();
  await expect(page.getByRole('heading', { name: 'Đăng nhập' })).toBeVisible();
});
