import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';
import type { ImagineJob } from '../src/shared/api/api';

// Ảnh giả chỉ phục vụ kiểm thử giao diện, không có lời gọi tạo ảnh thật.
const picture = '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1536" viewBox="0 0 1024 1536"><rect width="1024" height="1536" fill="#c9bda7"/><path d="M0 1030h1024v506H0Z" fill="#a38c6c"/><ellipse cx="490" cy="1100" rx="300" ry="45" fill="#7a6956"/><path d="M680 600h90a145 145 0 0 1 0 290h-90" fill="none" stroke="#eee8df" stroke-width="55"/><path d="M270 570h440v355a145 145 0 0 1-145 145H415a145 145 0 0 1-145-145Z" fill="#f7f2e8"/><ellipse cx="490" cy="570" rx="220" ry="45" fill="#735039"/></svg>';
const image = (id: string) => ({ id, mime: 'image/svg+xml', url: `/api/imagine/images/${id}` });
const base: ImagineJob = { id: 'generation', prompt: 'Cốc trà bằng gốm trắng trên bàn gỗ', quality: 'medium', resolution: '2k', aspect_ratio: '2:3',
  created_at: Math.floor(Date.now() / 1000), n: 2, images: [], status: 'running' };

test('giữ ô ảnh qua tải lại, đổi tab và lúc hiện kết quả; không gửi lại lượt', async ({ page }, testInfo) => {
  test.setTimeout(45000);
  await mockPeto(page, { preservePreferences: true });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  let done = false;
  let posts = 0;
  await page.route('**/api/imagine**', route => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST') { posts++; return route.fulfill({ status: 500 }); }
    if (url.pathname.startsWith('/api/imagine/images/')) return route.fulfill({ contentType: 'image/svg+xml', body: picture });
    const job = done ? { ...base, status: 'complete', images: [image('one'), image('two')] } : base;
    return route.fulfill({ json: url.pathname === '/api/imagine' ? { jobs: [job] } : { job } });
  });
  await page.goto('/imagine');
  await expect(page.getByText('Đang tạo 2 ảnh…', { exact: true })).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('0 ảnh', { exact: true })).toHaveCount(0);
  const tiles = page.locator('.generation-tile');
  await expect(tiles).toHaveCount(2);
  const before = await tiles.first().boundingBox();
  expect(before!.width / before!.height).toBeCloseTo(2 / 3, 1);
  await expect.poll(() => page.locator('.generation-drift > span').first().evaluate(node => node.getAnimations().filter(a => a.playState === 'running').length)).toBeGreaterThan(0);
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('generation-pending.png') });
  await page.reload();
  await expect(page.getByText('Đang tạo 2 ảnh…', { exact: true })).toBeVisible();
  // Điều hướng thật trong Peto: Imagine vẫn được giữ khi sang trò chuyện.
  if (testInfo.project.name === 'mobile') await page.getByRole('button', { name: 'Mở menu', exact: true }).click();
  await page.locator('.sidebar').getByRole('button', { name: 'Trò chuyện', exact: true }).click();
  await expect(page.locator('.imagine')).toBeHidden();
  await expect(page.locator('.generation-preview')).toHaveAttribute('data-paused', 'true');
  await page.goBack();
  await expect(page.getByText('Đang tạo 2 ảnh…', { exact: true })).toBeVisible();
  done = true;
  await expect(tiles.first()).toHaveAttribute('data-ready', 'true');
  await expect(page.getByText('Đang tạo 2 ảnh…', { exact: true })).toHaveCount(0);
  const after = await tiles.first().boundingBox();
  expect(after!.width).toBeCloseTo(before!.width, 0);
  expect(after!.height).toBeCloseTo(before!.height, 0);
  await page.screenshot({ path: testInfo.outputPath('generation-complete.png') });
  await page.getByRole('button', { name: `Xem ảnh 1: ${base.prompt}`, exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Xem ảnh đã tạo' })).toBeVisible();
  expect(posts).toBe(0);
});

test('tạo thêm đúng cấu hình cũ, giữ bản nháp và tải lại ảnh lỗi không tạo thêm lượt AI', async ({ page }, testInfo) => {
  test.setTimeout(45000);
  await mockPeto(page);
  const old: ImagineJob = { ...base, status: 'complete', source_images: [image('reference')], source_image: image('reference'), images: [image('one'), image('two')] };
  const posts: Record<string, unknown>[] = [];
  let broken = true;
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/imagine**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith('/api/imagine/images/')) return broken && url.pathname.endsWith('/one')
      ? route.fulfill({ status: 503 }) : route.fulfill({ contentType: 'image/svg+xml', body: picture });
    if (route.request().method() === 'POST') {
      posts.push(route.request().postDataJSON());
      await waiting;
      return route.fulfill({ status: 202, json: { job: { ...base, id: 'another' } } });
    }
    return route.fulfill({ json: url.pathname === '/api/imagine' ? { jobs: [old] } : { job: { ...base, id: 'another' } } });
  });
  await page.goto('/imagine');
  await expect(page.getByText('Chưa tải được ảnh', { exact: true })).toBeVisible({ timeout: 20000 });
  broken = false;
  await page.getByRole('button', { name: 'Tải lại ảnh', exact: true }).click();
  await expect(page.locator('.generation-tile').first()).toHaveAttribute('data-ready', 'true');
  expect(posts).toHaveLength(0);
  const input = page.getByLabel('Bức ảnh bạn muốn tạo');
  await input.fill('Bản nháp cho lần sau');
  await page.getByRole('button', { name: 'Tạo thêm', exact: true }).click();
  await expect(page.getByText('Đang gửi yêu cầu…', { exact: true })).toBeVisible();
  expect(posts).toHaveLength(1);
  expect(posts[0]).toMatchObject({ prompt: old.prompt, quality: 'medium', resolution: '2k', aspect_ratio: '2:3', n: 2, source_image_id: 'reference', background: true });
  expect(posts[0].edit_parent_image_id).toBeUndefined();
  await expect(page.locator('.imagine-result-actions button')).toBeDisabled();
  await expect(input).toHaveValue('Bản nháp cho lần sau');
  release();
  await expect(page.getByText('Đang tạo 2 ảnh…', { exact: true })).toBeVisible();
  await expect(input).toHaveValue('Bản nháp cho lần sau');
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('generation-repeat.png') });
  expect(posts).toHaveLength(1);
});

for (const [aspect, n] of [['9:20', 4], ['21:9', 2], ['1:1', 1]] as const) test(`khung ${aspect}, ${n} ảnh không tràn và tuân theo giảm chuyển động`, async ({ page }) => {
  await mockPeto(page);
  await page.route('**/api/imagine**', route => route.fulfill({ json: { jobs: [{ ...base, aspect_ratio: aspect, n }] } }));
  await page.goto('/imagine');
  await expect(page.locator('.generation-tile')).toHaveCount(n);
  const tile = page.locator('.generation-tile').first();
  const rect = await tile.boundingBox();
  const [w, h] = aspect.split(':').map(Number);
  expect(rect!.width / rect!.height).toBeCloseTo(w / h, 1);
  await expect.poll(() => page.locator('.generation-drift > span').first().evaluate(node => node.getAnimations().length)).toBe(0);
  expect(await page.locator('.imagine-gallery').evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  await noPageOverflow(page);
});

test('mẫu ảnh sản phẩm chỉ điền mô tả, không tự tạo ảnh', async ({ page }) => {
  const state = await mockPeto(page);
  let posts = 0;
  await page.route('**/api/imagine', route => {
    if (route.request().method() === 'POST') posts++;
    return route.fulfill({ json: { jobs: [] } });
  });
  await page.goto('/imagine');
  await page.getByRole('button', { name: /Ảnh sản phẩm/ }).click();
  await expect(page.getByLabel('Bức ảnh bạn muốn tạo')).toHaveValue(/Ảnh chụp sản phẩm/);
  await expect(page.getByLabel('Bức ảnh bạn muốn tạo')).toBeFocused();
  await noPageOverflow(page);
  expect(posts).toBe(0);
  expect(state.posts).toBe(0);
});

test('mất kết nối chỉ dừng chuyển động, phục hồi ảnh bằng GET và không tạo lại', async ({ page }) => {
  await mockPeto(page);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  let connected = false;
  let posts = 0;
  await page.route('**/api/imagine**', route => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST') { posts++; return route.fulfill({ status: 500 }); }
    if (url.pathname.startsWith('/api/imagine/images/')) return route.fulfill({ contentType: 'image/svg+xml', body: picture });
    if (url.pathname === '/api/imagine') return route.fulfill({ json: { jobs: [base] } });
    return connected ? route.fulfill({ json: { job: { ...base, status: 'complete', images: [image('one'), image('two')] } } }) : route.fulfill({ status: 503 });
  });
  await page.goto('/imagine');
  await expect(page.getByText('Đang kết nối lại…', { exact: true })).toBeVisible();
  await expect(page.locator('.generation-preview')).toHaveAttribute('data-paused', 'true');
  await expect.poll(() => page.locator('.generation-drift > span').first().evaluate(node => node.getAnimations().every(a => a.playState === 'paused'))).toBe(true);
  connected = true;
  await expect(page.locator('.generation-tile').first()).toHaveAttribute('data-ready', 'true');
  await expect(page.getByText('Đang kết nối lại…', { exact: true })).toHaveCount(0);
  expect(posts).toBe(0);
});

test('giao diện sáng ở 375px vẫn rõ, đủ vùng chạm và có focus bàn phím', async ({ page }, testInfo) => {
  await mockPeto(page, { preservePreferences: true });
  if (testInfo.project.name === 'mobile') await page.setViewportSize({ width: 375, height: 812 });
  const job = { ...base, status: 'complete', images: [image('one'), image('two')] };
  await page.route('**/api/imagine**', route => new URL(route.request().url()).pathname.startsWith('/api/imagine/images/')
    ? route.fulfill({ contentType: 'image/svg+xml', body: picture }) : route.fulfill({ json: { jobs: [job] } }));
  await page.goto('/imagine');
  await expect(page.getByRole('button', { name: 'Tạo thêm', exact: true })).toBeVisible();
  await page.evaluate(() => localStorage.setItem('peto-theme', 'light'));
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.locator('.generation-tile').first()).toHaveAttribute('data-ready', 'true');
  const more = page.getByRole('button', { name: 'Tạo thêm', exact: true });
  if (testInfo.project.name === 'mobile') expect((await more.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await more.focus();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Shift+Tab');
  await expect(more).toBeFocused();
  await expect(more).toHaveCSS('outline-style', 'solid');
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('generation-light.png') });
});
