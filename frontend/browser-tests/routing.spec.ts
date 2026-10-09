import { expect, test, type Page } from '@playwright/test';
import { mockPeto, openSidebar, title } from './fixtures';

async function go(page: Page, label: string) {
  if (!await page.locator('.sidebar').isVisible()) {
    await page.getByRole('button', { name: /^(Mở menu|Mở danh sách hội thoại)$/ }).click();
  }
  await expect(page.locator('.sidebar')).toBeVisible();
  await page.locator('.app-nav').getByRole('button', { name: label, exact: true }).click();
}

async function images(page: Page) {
  const image = (id: string) => ({ id, mime: 'image/png', url: `/api/imagine/images/${id}` });
  const root = { id: 'root-job', prompt: 'Ảnh kiểm tra routing', quality: 'low', resolution: '1k',
    aspect_ratio: '1:1', status: 'complete', created_at: 1, images: [image('root')] };
  const child = { ...root, id: 'child-job', root_image_id: 'root', edit_parent_image_id: 'root',
    created_at: 2, images: [image('version')] };
  let reads = 0;
  await page.route('**/api/imagine**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/imagine') return route.fulfill({ json: { jobs: [root] } });
    if (path === '/api/imagine/images/root/workspace') {
      reads++;
      return route.fulfill({ json: { root_image_id: 'root', root_job: root, jobs: [child] } });
    }
    if (path === '/api/imagine/images/root' || path === '/api/imagine/images/version') return route.fulfill({
      contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64'),
    });
    return route.fulfill({ status: 404 });
  });
  return () => reads;
}

test('nháp từng Chat sống qua F5/Back/Forward, chat mới riêng và tab mới không lấy nháp', async ({ page, context }) => {
  const state = await mockPeto(page, { preservePreferences: true });
  await page.goto('/');
  const input = page.getByLabel('Nhắn cho Peto', { exact: true });
  await input.fill('Nháp chat mới');
  await openSidebar(page);
  await page.getByRole('button', { name: title, exact: true }).click();
  await expect(input).toHaveValue('');
  await input.fill('Nháp A vừa gõ');
  // F5 ngay sau nhập: chưa cần đợi debounce ghi storage.
  await page.reload();
  await expect(input).toHaveValue('Nháp A vừa gõ');
  await openSidebar(page);
  await page.getByRole('button', { name: 'Một hội thoại khác', exact: true }).click();
  await expect(input).toHaveValue('');
  await input.fill('Nháp B');
  await page.goBack();
  await expect(input).toHaveValue('Nháp A vừa gõ');
  await page.goBack();
  await expect(input).toHaveValue('Nháp chat mới');
  await page.goForward();
  await expect(input).toHaveValue('Nháp A vừa gõ');
  await page.goForward();
  await expect(input).toHaveValue('Nháp B');
  const other = await context.newPage();
  await mockPeto(other, { preservePreferences: true });
  await other.goto('/chat/A');
  await expect(other.getByLabel('Nhắn cho Peto', { exact: true })).toHaveValue('');
  await other.close();
  expect(state.posts).toBe(0);
});

test('F5 giữ nháp chat mới đúng dự án và gửi đúng projectId', async ({ page }) => {
  await mockPeto(page, { preservePreferences: true });
  await page.route('**/api/projects', route => route.fulfill({ json: { projects: ['P', 'Q'].map(id =>
    ({ id, name: id, created_at: 1, updated_at: 1 })) } }));
  await page.goto('/');
  const input = page.getByLabel('Nhắn cho Peto', { exact: true });
  await input.fill('Nháp không có dự án');
  await openSidebar(page);
  await page.getByRole('button', { name: 'P', exact: true }).hover();
  await page.getByRole('button', { name: 'Chat mới trong dự án P' }).click();
  await input.fill('Nháp dự án P');
  await openSidebar(page);
  await page.getByRole('button', { name: 'Q', exact: true }).hover();
  await page.getByRole('button', { name: 'Chat mới trong dự án Q' }).click();
  await expect(input).toHaveValue('');
  await input.fill('Nháp dự án Q');
  await openSidebar(page);
  await page.getByRole('button', { name: 'P', exact: true }).hover();
  await page.getByRole('button', { name: 'Chat mới trong dự án P' }).click();
  await expect(input).toHaveValue('Nháp dự án P');
  const length = await page.evaluate(() => history.length);
  await page.reload();
  await expect(input).toHaveValue('Nháp dự án P');
  expect(await page.evaluate(() => history.length)).toBe(length);
  const request = page.waitForRequest('**/api/chat');
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  expect((await request).postDataJSON()).toMatchObject({ message: 'Nháp dự án P', project_id: 'P' });
  await expect(input).toHaveValue('');
  await page.reload();
  await expect(input).toHaveValue('');
});

test('Back/Forward giữ tab, lịch sử và bản nháp; bấm lại tab không thêm history', async ({ page }) => {
  const state = await mockPeto(page);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button', { name: title, exact: true }).click();
  await expect(page.locator('.table-scroll')).toBeVisible();
  await page.getByLabel('Nhắn cho Peto', { exact: true }).fill('Bản nháp chat còn nguyên');
  const chat = (await page.locator('.chat-layout').elementHandle())!;
  const length = await page.evaluate(() => history.length);

  await go(page, 'Companion');
  await expect(page).toHaveURL(/\/companion$/);
  // Bản build tải renderer thật; chờ gỡ khóa nhập trước khi gõ bản nháp.
  await expect(page.locator('.companion-panel')).not.toHaveAttribute('inert', '');
  await page.getByLabel('Nhắn cho Peto trong Companion').fill('Bản nháp Companion');
  const companion = (await page.locator('main.companion').elementHandle())!;
  await go(page, 'Companion');
  expect(await page.evaluate(() => history.length)).toBe(length + 1);
  await expect(page.getByLabel('Nhắn cho Peto trong Companion')).toHaveValue('Bản nháp Companion');

  await go(page, 'Tạo ảnh');
  await expect(page).toHaveURL(/\/imagine$/);
  expect(await companion.evaluate(element => element.isConnected)).toBe(true);
  await page.getByLabel('Bức ảnh bạn muốn tạo').fill('Bản nháp tạo ảnh');
  const imagine = (await page.locator('main.imagine').elementHandle())!;
  await go(page, 'Tạo ảnh');
  expect(await page.evaluate(() => history.length)).toBe(length + 2);

  await page.goBack();
  await expect(page).toHaveURL(/\/companion$/);
  await expect(page.getByLabel('Nhắn cho Peto trong Companion')).toHaveValue('Bản nháp Companion');
  await page.goBack();
  await expect(page).toHaveURL(/\/chat\/A$/);
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toHaveValue('Bản nháp chat còn nguyên');
  await expect(page.locator('.table-scroll')).toBeVisible();
  await page.goForward();
  await expect(page).toHaveURL(/\/companion$/);
  await expect(page.getByLabel('Nhắn cho Peto trong Companion')).toHaveValue('Bản nháp Companion');
  await page.goForward();
  await expect(page.getByLabel('Bức ảnh bạn muốn tạo')).toHaveValue('Bản nháp tạo ảnh');
  for (const node of [chat, companion, imagine]) expect(await node.evaluate(element => element.isConnected)).toBe(true);
  expect(state.posts).toBe(0);
  expect(errors).toEqual([]);
});

test('URL từng chat, Back/Forward, chat mới và quay về từ Imagine giữ ô nhập', async ({ page }) => {
  const state = await mockPeto(page);
  let reads = 0;
  await page.route('**/api/conversations/*/messages', route => {
    reads++;
    const id = route.request().url().split('/').at(-2);
    return route.fulfill({ json: { messages: [{ id: 1, role: 'user', content: `Nội dung riêng của ${id}` }] } });
  });
  await page.goto('/');
  const input = page.getByLabel('Nhắn cho Peto', { exact: true });
  await expect(input).toBeVisible();
  const node = (await input.elementHandle())!;
  const length = await page.evaluate(() => history.length);
  await openSidebar(page);
  await page.getByRole('button', { name: title, exact: true }).click();
  await expect(page).toHaveURL(/\/chat\/A$/);
  await expect(page.getByText('Nội dung riêng của A', { exact: true })).toBeVisible();
  await input.fill('Nháp vẫn còn');
  await openSidebar(page);
  await page.getByRole('button', { name: title, exact: true }).click();
  expect(reads).toBe(1);
  expect(await page.evaluate(() => history.length)).toBe(length + 1);
  await openSidebar(page);
  await page.getByRole('button', { name: 'Một hội thoại khác', exact: true }).click();
  await expect(page).toHaveURL(/\/chat\/B$/);
  await expect(page.getByText('Nội dung riêng của B', { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/chat\/A$/);
  await expect(page.getByText('Nội dung riêng của A', { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/:5179\/$/);
  await expect(page.getByText('Nội dung riêng của A', { exact: true })).not.toBeVisible();
  await page.goForward();
  await expect(page).toHaveURL(/\/chat\/A$/);
  await expect(page.getByText('Nội dung riêng của A', { exact: true })).toBeVisible();
  const beforeTab = reads;
  await go(page, 'Tạo ảnh');
  await go(page, 'Trò chuyện');
  await expect(page).toHaveURL(/\/chat\/A$/);
  expect(reads).toBe(beforeTab);
  await expect(input).toHaveValue('Nháp vẫn còn');
  expect(await node.evaluate(element => element.isConnected)).toBe(true);
  await go(page, 'Trò chuyện');
  await expect(page).toHaveURL(/:5179\/$/);
  await expect(page.getByText('Nội dung riêng của A', { exact: true })).not.toBeVisible();
  await page.goBack();
  await expect(page.getByText('Nội dung riêng của A', { exact: true })).toBeVisible();
  expect(state.posts).toBe(0);
});

test('bookmark chat ngoài danh sách gần đây, F5 và tab mới đọc đúng nội dung cùng thiết lập', async ({ page, context }) => {
  const setup = async (target: Page) => {
    await mockPeto(target);
    await target.route('**/api/conversations/old-thread/messages', route => route.fulfill({ json: {
      archived: true, persona: 'roleplay', messages: [{ id: 1, role: 'user', content: 'Hội thoại trong bookmark' }],
    } }));
  };
  await setup(page);
  await page.goto('/chat/old-thread?source=bookmark');
  await expect(page.getByText('Hội thoại trong bookmark', { exact: true })).toBeVisible();
  await expect(page.locator('.archived-chat-notice')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Hội thoại trong bookmark', { exact: true })).toBeVisible();
  const tab = await context.newPage();
  await setup(tab);
  await tab.goto(page.url());
  await expect(tab.getByText('Hội thoại trong bookmark', { exact: true })).toBeVisible();
  await expect(tab.locator('.archived-chat-notice')).toBeVisible();
  await tab.close();
});

test('tin đầu cấp URL bằng replace, giữ phản hồi và không tự tải lại tin', async ({ page }) => {
  const state = await mockPeto(page);
  let reads = 0;
  page.on('request', request => { if (request.url().endsWith('/messages')) reads++; });
  await page.goto('/?source=bookmark');
  await page.getByLabel('Nhắn cho Peto', { exact: true }).fill('Tin đầu kiểm tra URL');
  const length = await page.evaluate(() => history.length);
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect(page).toHaveURL(/\/chat\/A\?source=bookmark$/);
  await expect(page.getByText('Câu trả lời đã được lưu đầy đủ.', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => history.length)).toBe(length);
  expect(reads).toBe(0);
  expect(state.posts).toBe(1);
  await page.reload();
  await expect(page.getByText('Câu trả lời đã được lưu đầy đủ.', { exact: true })).toBeVisible();
  expect(reads).toBe(1);
});

test('chat không tồn tại hoặc không có quyền không hiện chat cũ và không cho gửi', async ({ page }) => {
  const state = await mockPeto(page);
  await page.route('**/api/conversations/private-thread/messages', route => route.fulfill({
    status: 404, json: { detail: 'Không tìm thấy hội thoại' },
  }));
  await page.goto('/chat/private-thread');
  await expect(page.getByText('Chưa tải được nội dung hội thoại.', { exact: true })).toBeVisible();
  await expect(page.locator('.table-scroll')).toHaveCount(0);
  await page.getByLabel('Nhắn cho Peto', { exact: true }).fill('Không gửi nhầm');
  await expect(page.getByRole('button', { name: 'Gửi', exact: true })).toBeDisabled();
  expect(state.posts).toBe(0);
});

test('deep link khi chưa đăng nhập chỉ hiện đăng nhập và không đọc lịch sử', async ({ page }) => {
  await mockPeto(page);
  let reads = 0;
  page.on('request', request => { if (request.url().endsWith('/messages')) reads++; });
  await page.route('**/api/auth/me', route => route.fulfill({ json: {
    authenticated: false, login_configured: true, providers: { discord: true },
  } }));
  await page.goto('/chat/private-thread');
  await expect(page.getByRole('link', { name: /Discord/ })).toBeVisible();
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toHaveCount(0);
  expect(reads).toBe(0);
});

test('đăng nhập từ bookmark chat quay về đúng URL sau callback về trang chủ', async ({ page }) => {
  // Mô phỏng chuyển hướng đăng nhập phải giữ sessionStorage như trình duyệt thật.
  await mockPeto(page, { preservePreferences: true });
  let authenticated = false;
  await page.route('**/api/auth/me', route => route.fulfill({ json: authenticated
    ? { authenticated: true, login_configured: true, user: { id: 'test-account', display_name: 'Người kiểm thử' } }
    : { authenticated: false, login_configured: true, providers: { discord: true } },
  }));
  await page.route('**/api/auth/discord/login', route => {
    authenticated = true;
    return route.fulfill({ status: 302, headers: { location: '/' } });
  });
  await page.goto('/chat/A?source=bookmark');
  await page.getByRole('link', { name: /Discord/ }).click();
  await expect(page).toHaveURL(/\/chat\/A\?source=bookmark$/);
  await expect(page.locator('.table-scroll')).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('peto-chat-login-return'))).toBeNull();
});

for (const [path, label] of [['/companion', 'Nhắn cho Peto trong Companion'], ['/imagine', 'Bức ảnh bạn muốn tạo']]) {
  test(`deep link, F5 và tab mới tại ${path}`, async ({ page, context }) => {
    await mockPeto(page);
    await page.goto(path);
    await expect(page.getByLabel(label, { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByLabel(label, { exact: true })).toBeVisible();
    const tab = await context.newPage();
    await mockPeto(tab);
    await tab.goto(page.url());
    await expect(tab.getByLabel(label, { exact: true })).toBeVisible();
    await tab.close();
  });
}

test('URL hash cũ giữ query, thay entry hiện tại và không giữ một bước Back thừa', async ({ page }) => {
  await mockPeto(page);
  await page.goto('/');
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  const length = await page.evaluate(() => history.length);
  await page.goto('/?source=bookmark#companion');
  await expect(page).toHaveURL(/\/companion\?source=bookmark$/);
  await expect(page.getByLabel('Nhắn cho Peto trong Companion')).toBeVisible();
  expect(await page.evaluate(() => history.length)).toBe(length + 1);
  await go(page, 'Tạo ảnh');
  await expect(page).toHaveURL(/\/imagine\?source=bookmark$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/companion\?source=bookmark$/);
  await page.goBack();
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
});

test('dọn lỗi đăng nhập giữ deep link và các query khác', async ({ page }) => {
  await mockPeto(page);
  await page.goto('/?auth_error=Thu-lai&source=bookmark#imagine');
  await expect(page).toHaveURL(/\/imagine\?source=bookmark$/);
  await expect(page.getByLabel('Bức ảnh bạn muốn tạo')).toBeVisible();
  await go(page, 'Companion');
  await page.goBack();
  await expect(page).toHaveURL(/\/imagine\?source=bookmark$/);
});

test('URL phiên bản cũ, F5, Back/Forward và đóng ảnh không tải lại ứng dụng', async ({ page }) => {
  await mockPeto(page);
  const reads = await images(page);
  await page.goto('/#imagine/root/version');
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  const picture = viewer.locator('.workspace-picture img');
  await expect(page).toHaveURL(/\/imagine\/root\/version$/);
  await expect(picture).toHaveAttribute('src', '/api/imagine/images/version');
  await page.reload();
  await expect(picture).toHaveAttribute('src', '/api/imagine/images/version');
  await viewer.getByRole('button', { name: 'Ảnh chính', exact: true }).click();
  await expect(page).toHaveURL(/\/imagine\/root\/root$/);
  await expect(picture).toHaveAttribute('src', '/api/imagine/images/root');
  const beforeBack = reads();
  await page.goBack();
  await expect(picture).toHaveAttribute('src', '/api/imagine/images/version');
  expect(reads() - beforeBack).toBe(1);
  await page.goForward();
  await expect(picture).toHaveAttribute('src', '/api/imagine/images/root');
  await viewer.getByRole('button', { name: 'Quay lại', exact: true }).click();
  await expect(page).toHaveURL(/\/imagine$/);
  await expect(viewer).not.toBeVisible();
  await page.goBack();
  await expect(picture).toHaveAttribute('src', '/api/imagine/images/root');
});

test('fallback của bản build giữ API, Docs và asset thiếu ngoài trang ứng dụng', async ({ request }, testInfo) => {
  test.skip(!testInfo.config.configFile?.endsWith('playwright.routing.config.ts'), 'Chỉ chạy với backend phục vụ bản build.');
  for (const path of ['/chat/A', '/companion', '/imagine', '/imagine/root/version']) {
    const response = await request.get(path);
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('text/html');
    expect(response.headers()['cache-control']).toBe('no-cache');
  }
  const health = await request.get('/api/routing-health');
  expect(await health.json()).toEqual({ ok: true });
  for (const path of ['/api/not-found', '/assets/not-found.js', '/docs/not-found/', '/imagine/root', '/chat', '/chat/A/extra', '/unknown']) {
    expect((await request.get(path)).status()).toBe(404);
  }
  expect((await request.get('/docs')).status()).toBe(200);
});
