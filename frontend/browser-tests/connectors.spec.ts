import { test, expect } from '@playwright/test';
import { mockPeto, openSidebar, noPageOverflow } from './fixtures';

async function setup(page: Parameters<typeof mockPeto>[0], connected = true) {
  await mockPeto(page);
  const state = { connected, disconnects: 0, checks: 0 };
  await page.route('**/api/connectors**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const item = { id: 'github', name: 'GitHub', configured: true, status: state.connected ? 'connected' : 'not_connected',
      login: state.connected ? 'nguoi-kiem-thu' : null, updated_at: 1, install_url: 'https://github.com/apps/peto-test/installations/new' };
    if (path === '/api/connectors/github/connect') return route.fulfill({ json: { authorize_url: 'https://github.com/login/oauth/authorize?client_id=test&state=test' } });
    if (path === '/api/connectors/github/check') { state.checks++; return route.fulfill({ json: item }); }
    if (path === '/api/connectors/github' && request.method() === 'DELETE') {
      state.disconnects++; state.connected = false;
      return route.fulfill({ json: { disconnected: true } });
    }
    return route.fulfill({ json: { connectors: [item] } });
  });
  return state;
}

async function settings(page: Parameters<typeof mockPeto>[0]) {
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button', { name: 'Tài khoản · Người kiểm thử' }).click();
  await page.getByRole('menuitem', { name: 'Cài đặt', exact: true }).click();
  await page.getByRole('button', { name: 'Kết nối', exact: true }).click();
  return page.getByRole('dialog', { name: 'Cài đặt', exact: true });
}

test('quản lý GitHub, kiểm tra và ngắt kết nối trên PC/mobile', async ({ page }) => {
  const state = await setup(page);
  await page.goto('/');
  const dialog = await settings(page);
  await expect(dialog.getByText('@nguoi-kiem-thu')).toBeVisible();
  await noPageOverflow(page);
  await expect(dialog).toHaveScreenshot('github-connected.png', { maxDiffPixelRatio: 0 });
  await dialog.getByRole('button', { name: 'Quản lý', exact: true }).click();
  await dialog.getByRole('button', { name: 'Kiểm tra kết nối' }).click();
  await expect(dialog.getByText('Kết nối GitHub đang hoạt động.')).toBeVisible();
  expect(state.checks).toBe(1);
  await expect(dialog.getByRole('link', { name: /Quản lý repo/ })).toHaveAttribute('href', 'https://github.com/apps/peto-test/installations/new');
  await dialog.getByRole('button', { name: 'Ngắt kết nối', exact: true }).click();
  await dialog.getByRole('button', { name: 'Giữ kết nối' }).click();
  expect(state.disconnects).toBe(0);
  await dialog.getByRole('button', { name: 'Ngắt kết nối', exact: true }).click();
  await dialog.getByRole('button', { name: 'Xác nhận ngắt kết nối' }).click();
  await expect(dialog.getByText('Bạn chưa kết nối ứng dụng nào.')).toBeVisible();
  expect(state.disconnects).toBe(1);
  await dialog.getByRole('button', { name: 'Khám phá kết nối' }).click();
  await expect(dialog.getByRole('tabpanel', { name: 'Khám phá' }).getByRole('button', { name: 'Kết nối', exact: true })).toBeVisible();
  await noPageOverflow(page);
});

test('khám phá GitHub và quay về đúng trang sau cấp quyền', async ({ page }) => {
  await setup(page, false);
  await page.goto('/?connector_result=connected');
  const dialog = page.getByRole('dialog', { name: 'Cài đặt', exact: true });
  await expect(dialog.getByRole('heading', { name: 'Kết nối', exact: true })).toBeVisible();
  await expect(dialog.getByText('Bạn chưa kết nối ứng dụng nào.')).toBeVisible();
  expect(new URL(page.url()).searchParams.has('connector_result')).toBe(false);
  await dialog.getByRole('tab', { name: 'Khám phá', exact: true }).click();
  await expect(dialog.getByRole('tabpanel', { name: 'Khám phá' }).getByRole('button', { name: 'Kết nối', exact: true })).toBeVisible();
  await dialog.getByRole('searchbox', { name: 'Tìm kết nối' }).fill('GitHub');
  await noPageOverflow(page);
  // Chặn chuyển hướng tới GitHub để kiểm tra nút kết nối mà không gọi tài khoản thật.
  await page.route('https://github.com/login/oauth/authorize**', route => route.fulfill({ body: '<h1>Cấp quyền GitHub giả</h1>', contentType: 'text/html' }));
  await dialog.getByRole('tabpanel', { name: 'Khám phá' }).getByRole('button', { name: 'Kết nối', exact: true }).click();
  await expect(page).toHaveURL(/github\.com\/login\/oauth\/authorize/);
});

test('tiến trình GitHub gọn và mở được chi tiết tệp chưa đọc trên PC/mobile', async ({ page }, testInfo) => {
  await setup(page);
  const issue = 'Không tìm thấy “src/old-module/very-long-file-name.ts” trong nguoi-test/Peto ở nhánh mặc định. Thư mục gốc vẫn đọc được.';
  await page.route('**/api/chat', route => {
    const events: object[] = [{type: 'meta', conversation_id: 'github-test', effort: 'low'}];
    for (let i = 0; i < 12; i++) {
      events.push({type: 'connector_lookup', text: 'Đang đọc GitHub…', live: true},
        {type: 'connector_lookup', text: i === 4 ? issue : 'Đã đọc GitHub', live: false});
    }
    events.push({type: 'delta', text: 'Đã khảo sát các tệp đọc được.'}, {type: 'done'});
    return route.fulfill({contentType: 'text/event-stream', body: events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('')});
  });
  await page.goto('/');
  await page.getByLabel('Nhắn cho Peto', {exact: true}).fill('Khảo sát repo của tôi');
  await page.getByRole('button', {name: 'Gửi', exact: true}).click();
  await expect(page.getByText('Đã khảo sát các tệp đọc được.')).toBeVisible();
  await page.getByRole('button', {name: /Đã làm trong \d+ giây/}).click();
  await expect(page.getByText('GitHub · 11 mục đã đọc · 1 mục chưa đọc được')).toBeVisible();
  await expect(page.locator('.work-steps > li')).toHaveCount(3);
  await expect(page.getByText(issue)).not.toBeVisible();
  await page.getByText('Xem mục chưa đọc được', {exact: true}).click();
  await expect(page.getByText(issue)).toBeVisible();
  await noPageOverflow(page);
  await page.locator('.work-log').screenshot({path: testInfo.outputPath('github-progress.png')});
});
