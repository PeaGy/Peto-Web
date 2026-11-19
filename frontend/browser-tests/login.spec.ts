import { test, expect, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

const TOKEN = 'TokenGia_' + 'x'.repeat(34);

type MailState = { authenticated: boolean; approved: boolean; claimed: boolean; sent: string[]; links: unknown[] };

/** Máy chủ giả cho đăng nhập bằng email. Trạng thái dùng chung giữa các tab (và cả "điện thoại") như một máy chủ thật;
 * `sameBrowser` cho biết trang này có cookie yêu cầu của lần gửi thư hay không. Không gửi thư thật. */
async function mockEmailLogin(page: Page, state: MailState, sameBrowser: boolean) {
  await page.route('**/api/auth/me', route => route.fulfill({ json: state.authenticated
    ? { authenticated: true, login_configured: true, providers: { discord: true, google: true, github: true, email: true },
      user: { id: 'acc-mail', provider: 'email', username: '', display_name: 'an•••@vidu.com', avatar_url: '' } }
    : { authenticated: false, login_configured: true, providers: { discord: true, google: true, github: true, email: true } },
  }));
  await page.route('**/api/auth/email/send', route => {
    state.sent.push(route.request().postDataJSON().email);
    return route.fulfill({ json: { ok: true, resend_after: 60, expires_in: 600 } });
  });
  await page.route('**/api/auth/email/status', route => {
    if (!state.approved || state.claimed) return route.fulfill({ json: { state: 'waiting' } });
    state.claimed = true;
    state.authenticated = true;
    return route.fulfill({ json: { state: 'signed_in' } });
  });
  await page.route('**/api/auth/email/link', route => {
    const body = route.request().postDataJSON();
    state.links.push(body);
    if (body.token !== TOKEN || state.approved) {
      return route.fulfill({ status: 400, json: { detail: 'Đường dẫn đăng nhập đã hết hạn hoặc đã được dùng.' } });
    }
    if (!sameBrowser && !body.confirm) {
      return route.fulfill({ json: { state: 'confirm', device: 'Chrome trên Windows', requested_at: 1795067460 } });
    }
    state.approved = true;
    // Máy chủ thật đặt phiên cho chính trình duyệt mở đường dẫn.
    state.authenticated = true;
    return route.fulfill({ json: { state: 'signed_in', same_browser: sameBrowser } });
  });
}

const fresh = (): MailState => ({ authenticated: false, approved: false, claimed: false, sent: [], links: [] });

test('đăng nhập như AIRI: gửi thư, bấm nút trong thư ở tab mới, tab cũ tự vào app', async ({ page, context }) => {
  await mockPeto(page);
  const state = fresh();
  await mockEmailLogin(page, state, true);
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
  await expect(page.getByRole('link', { name: 'Đăng nhập bằng Google' })).toContainText('Google');

  await email.fill('sai-dang');
  await page.getByRole('button', { name: 'Tiếp tục' }).click();
  await expect(page.getByRole('alert')).toHaveText('Email chưa đúng dạng. Kiểm tra lại giúp mình nhé.');
  expect(state.sent).toEqual([]);

  await email.fill('an@vidu.com');
  await email.press('Enter');
  await expect(page.getByRole('heading', { name: 'Kiểm tra hộp thư' })).toBeFocused();
  expect(state.sent).toEqual(['an@vidu.com']);
  await noPageOverflow(page);
  await expect(page).toHaveScreenshot('login-inbox.png');

  // Bấm nút trong thư: trình duyệt mở tab mới ở /#email_token=…; tab đó đăng nhập, tab cũ tự tiếp tục.
  const mailTab = await context.newPage();
  await mockPeto(mailTab);
  await mockEmailLogin(mailTab, state, true);
  await mailTab.goto(`/#email_token=${TOKEN}`);
  await expect(mailTab.getByRole('heading', { name: 'Email đã xác nhận' })).toBeVisible();
  expect(new URL(mailTab.url()).hash).toBe('');
  await noPageOverflow(mailTab);
  await expect(mailTab).toHaveScreenshot('login-verified.png');

  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/chat\/A\?source=bookmark$/);

  await mailTab.getByRole('button', { name: 'Mở Peto' }).click();
  await expect(mailTab.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
});

test('đăng nhập: mở thư trên điện thoại, xác nhận thì máy tính đang chờ tự vào', async ({ page, browser }) => {
  await mockPeto(page);
  const state = fresh();
  await mockEmailLogin(page, state, true);
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill('an@vidu.com');
  await page.getByRole('button', { name: 'Tiếp tục' }).click();
  await expect(page.getByRole('heading', { name: 'Kiểm tra hộp thư' })).toBeVisible();

  // Điện thoại là một trình duyệt khác hẳn (context riêng, không chung cookie).
  const phoneContext = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
    colorScheme: 'dark', reducedMotion: 'reduce', locale: 'vi-VN', timezoneId: 'Asia/Ho_Chi_Minh' });
  const phone = await phoneContext.newPage();
  await mockPeto(phone);
  await mockEmailLogin(phone, state, false);
  await phone.goto(`/#email_token=${TOKEN}`);
  await expect(phone.getByRole('heading', { name: 'Xác nhận đăng nhập' })).toBeVisible();
  await expect(phone.getByText(/Cho phép Chrome trên Windows đăng nhập vào Peto \(yêu cầu lúc 12:51\)/)).toBeVisible();
  await noPageOverflow(phone);
  await expect(phone).toHaveScreenshot('login-confirm.png');
  await expect(page.getByRole('heading', { name: 'Kiểm tra hộp thư' })).toBeVisible();

  await phone.getByRole('button', { name: 'Xác nhận' }).click();
  await expect(phone.getByText('Thiết bị kia sẽ tự tiếp tục.', { exact: false })).toBeVisible();
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  await phoneContext.close();
});

test('đăng nhập: màn hình thấp vẫn cuộn tới tiêu đề; quay lại giữ email; đường dẫn hỏng báo lỗi', async ({ page }) => {
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
  await page.getByRole('button', { name: 'Quay lại đăng nhập' }).click();
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue('an@vidu.com');
  await expect(page.getByLabel('Email', { exact: true })).toBeFocused();

  // Tải lại hẳn trang (đổi mỗi phần # thì trình duyệt không tải lại).
  await page.goto('about:blank');
  await page.goto(`/#email_token=${'y'.repeat(43)}`);
  await expect(page.getByRole('alert')).toHaveText('Đường dẫn đăng nhập đã hết hạn hoặc đã được dùng.');
  await page.getByRole('button', { name: 'Quay lại đăng nhập' }).click();
  await expect(page.getByRole('heading', { name: 'Đăng nhập' })).toBeVisible();
});
