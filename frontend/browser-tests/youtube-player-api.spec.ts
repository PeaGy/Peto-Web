import { expect, test, type Page } from '@playwright/test';
import { installApi, stats, type FakeStats } from './youtubeFixture';

// Đây là kiểm tra vòng đời/giao diện với API giả; không chứng minh khả năng phát hay quảng cáo trên YouTube thật.
const preview = '/prototypes/youtube-tv/';
async function ready(page: Page) {
  await expect(page.locator('.yt-player')).toHaveAttribute('data-status', 'ready');
  await expect(page.getByRole('button', { name: 'Phát video', exact: true })).toBeEnabled();
}
async function openFile(page: Page, mobile: boolean) {
  await page.getByRole('button', { name: mobile ? 'Tùy chọn Player' : 'File', exact: true }).click();
}
async function reopen(page: Page, mobile: boolean) {
  if (mobile) await page.getByRole('button', { name: 'Mở menu Companion', exact: true }).click();
  await page.getByRole('button', { name: 'Player', exact: true }).click();
  await ready(page);
}
async function closePlayer(page: Page, mobile: boolean) {
  await page.getByRole('button', { name: mobile ? 'Dừng và đóng Player' : 'Player', exact: true }).click();
}

test('API giả: Strict Mode và đổi nguồn/bố cục giữ một iframe, mở lại dùng cùng API', async ({ page }, info) => {
  const count = await installApi(page), mobile = info.project.name === 'mobile';
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(preview); await ready(page);
  const iframe = await page.locator('iframe').elementHandle();
  expect((await stats(page)).created).toBe(1);
  await openFile(page, mobile);
  await page.getByRole('textbox', { name: 'Link YouTube', exact: true }).fill('https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ');
  await page.getByRole('button', { name: 'Mở video', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('chưa hợp lệ');
  await page.getByRole('textbox', { name: 'Link YouTube', exact: true }).fill('https://youtu.be/aircAruvnKk?t=12');
  await page.getByRole('button', { name: 'Mở video', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'But what is a neural network?', exact: true })).toBeVisible();
  expect((await stats(page)).cues.at(-1)).toEqual({ videoId: 'aircAruvnKk', startSeconds: 12 });
  await page.getByRole('button', { name: 'Phát video', exact: true }).click();
  if (mobile) await page.setViewportSize({ width: 844, height: 390 });
  else {
    const handle = (await page.locator('[data-resize="se"]').boundingBox())!;
    await page.mouse.move(handle.x + 6, handle.y + 6); await page.mouse.down();
    await page.mouse.move(handle.x + 86, handle.y + 36, { steps: 5 }); await page.mouse.up();
  }
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'true');
  expect(await iframe!.evaluate(node => node.isConnected)).toBe(true);
  expect((await stats(page)).created).toBe(1);
  const size = (await page.locator('iframe').boundingBox())!;
  expect(size.width).toBeGreaterThanOrEqual(200); expect(size.height).toBeGreaterThanOrEqual(200);
  await closePlayer(page, mobile);
  await expect(page.locator('iframe')).toHaveCount(0);
  expect((await stats(page)).destroyed).toBe(1);
  await reopen(page, mobile);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  expect((await stats(page)).created).toBe(2);
  expect(count()).toBe(1);
  expect(errors).toEqual([]);
});

test('API giả: controls đồng bộ phát/pause, seek và âm lượng native', async ({ page }) => {
  await installApi(page); await page.goto(preview); await ready(page);
  await page.getByRole('button', { name: 'Phát video', exact: true }).click();
  await expect(page.locator('.yt-player')).toHaveAttribute('data-status', 'playing');
  const timeline = page.getByRole('slider', { name: 'Vị trí phát', exact: true });
  await timeline.press('End');
  await expect(timeline).toHaveValue('240');
  await page.getByRole('button', { name: 'Tạm dừng video', exact: true }).click();
  await expect(page.locator('.yt-player')).toHaveAttribute('data-status', 'paused');
  await page.evaluate(() => (window as unknown as { __ytFake: FakeStats }).__ytFake.nativeVolume(22));
  await page.getByRole('button', { name: 'Tắt tiếng', exact: true }).focus();
  const volume = page.getByRole('slider', { name: 'Âm lượng Player', exact: true });
  await expect(volume).toHaveValue('22');
  await page.getByRole('button', { name: 'Tắt tiếng', exact: true }).click();
  await expect(volume).toHaveValue('0');
  await page.getByRole('button', { name: 'Bật tiếng', exact: true }).click();
  await expect(volume).toHaveValue('22');
});

test('API giả: lỗi tải có nút thử lại', async ({ page }) => {
  const count = await installApi(page, { failFirst: true });
  await page.goto(preview);
  await expect(page.getByRole('alert')).toContainText('Không tải được YouTube');
  await expect(page.getByRole('button', { name: 'Phát video', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Thử lại YouTube', exact: true }).click(); await ready(page);
  expect(count()).toBe(2); await expect(page.locator('iframe')).toHaveCount(1);
});

test('API giả: video cấm nhúng, lỗi nguồn nhúng và autoplay bị chặn có hướng xử lý', async ({ page }) => {
  await installApi(page); await page.goto(preview); await ready(page);
  for (const [code, text] of [[101, 'không cho phép'], [150, 'không cho phép'], [153, 'nguồn nhúng']] as const) {
    await page.evaluate(code => (window as unknown as { __ytFake: FakeStats }).__ytFake.fail(code), code);
    await expect(page.getByRole('alert')).toContainText(text);
    await expect(page.getByRole('button', { name: 'Phát video', exact: true })).toBeDisabled();
    await page.getByRole('button', { name: 'Thử lại YouTube', exact: true }).click(); await ready(page);
    await expect(page.locator('iframe')).toHaveCount(1);
  }
  await page.evaluate(() => { (window as unknown as { __ytFake: FakeStats }).__ytFake.blocked = true; });
  await page.getByRole('button', { name: 'Phát video', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('bấm nút Phát trực tiếp');
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  await page.evaluate(() => { (window as unknown as { __ytFake: FakeStats }).__ytFake.blocked = false; });
  await page.frameLocator('iframe').getByRole('button', { name: 'Phát trong YouTube giả', exact: true }).click();
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'true');
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('API giả: ẩn trang/pagehide gỡ iframe, quay lại giữ trạng thái dừng', async ({ page }) => {
  await installApi(page); await page.goto(preview); await ready(page);
  await page.getByRole('button', { name: 'Phát video', exact: true }).click();
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(page.locator('iframe')).toHaveCount(0);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-status', 'suspended');
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await ready(page); await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
  await expect(page.locator('iframe')).toHaveCount(0);
  await page.evaluate(() => window.dispatchEvent(new Event('pageshow')));
  await ready(page); await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  expect((await stats(page)).destroyed).toBe(2);
});

test('API giả: đóng lúc script còn tải không tạo iframe muộn', async ({ page }, info) => {
  const count = await installApi(page, { delay: 1200 }), mobile = info.project.name === 'mobile';
  await page.goto(preview);
  await expect(page.getByRole('button', { name: 'Phát video', exact: true })).toBeDisabled();
  await closePlayer(page, mobile);
  await page.waitForFunction(() => !!(window as Window & { __ytFake?: FakeStats }).__ytFake);
  expect((await stats(page)).created).toBe(0); await expect(page.locator('iframe')).toHaveCount(0);
  await reopen(page, mobile);
  expect((await stats(page)).created).toBe(1); expect(count()).toBe(1);
});

test('API giả: mobile ẩn Player nhường chỗ chat, phát tiếp và mở lại cùng iframe', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'Ẩn giao diện dành cho mobile.');
  await installApi(page); await page.goto(preview); await ready(page);
  await page.getByRole('button', { name: 'Phát video', exact: true }).click();
  const iframe = await page.locator('iframe').elementHandle();
  const chatArea = await page.locator('.yp-chat').boundingBox();
  await page.getByRole('button', { name: 'Ẩn Player', exact: true }).click();
  const shell = page.locator('.yt-player');
  await expect(shell).toBeHidden();
  await expect(shell).toHaveAttribute('hidden', '');
  await expect(shell).toHaveAttribute('inert', '');
  await expect(page.getByRole('dialog', { name: 'Peto Media Player', exact: true })).toHaveCount(0);
  await expect(shell).toHaveAttribute('data-playing', 'true');
  await expect(shell).toHaveAttribute('data-active', 'false');
  expect(await page.locator('.yp-chat').boundingBox()).toEqual(chatArea);
  expect((await stats(page)).created).toBe(1); expect((await stats(page)).destroyed).toBe(0);
  const chat = page.getByRole('textbox', { name: 'Nhắn thử trong Companion', exact: true });
  await chat.fill('Vừa xem vừa trò chuyện');
  await expect(chat).toHaveValue('Vừa xem vừa trò chuyện');
  await chat.press('Space');
  await expect(chat).toHaveValue('Vừa xem vừa trò chuyện ');
  await chat.press('Tab');
  await expect(page.getByRole('button', { name: 'Gửi tin nhắn mẫu', exact: true })).toBeFocused();
  for (const [width, height] of [[320, 640], [844, 390], [390, 844]]) {
    await page.setViewportSize({ width, height });
    await expect(shell).toBeHidden();
    await expect(page.locator('iframe')).toBeHidden();
    await expect(chat).toBeInViewport();
    expect(await chat.evaluate(node => {
      const box = node.getBoundingClientRect();
      return document.elementFromPoint(box.x + 8, box.y + box.height / 2) === node;
    })).toBe(true);
    await expect(shell).toHaveAttribute('data-playing', 'true');
    expect(await iframe!.evaluate(node => node.isConnected)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  }
  await page.getByRole('button', { name: 'Mở menu Companion', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Player', exact: true })).toHaveAttribute('aria-expanded', 'false');
  await page.getByRole('button', { name: 'Player', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Peto Media Player', exact: true })).toBeVisible();
  await expect(shell).toBeVisible();
  expect(await iframe!.evaluate(node => node.isConnected)).toBe(true);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'true');
  await page.getByRole('button', { name: 'Tạm dừng video', exact: true }).click();
  await expect(shell).toHaveAttribute('data-playing', 'false');
  await closePlayer(page, true);
  await expect(page.locator('iframe')).toHaveCount(0); expect((await stats(page)).destroyed).toBe(1);
});

test('API giả: mobile ẩn khi API đang tải vẫn giữ phiên, mở lại không tự phát', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'Ẩn giao diện dành cho mobile.');
  const count = await installApi(page, { delay: 1200 });
  await page.goto(preview);
  await page.getByRole('button', { name: 'Ẩn Player', exact: true }).click();
  await expect(page.locator('.yt-player')).toBeHidden();
  await expect(page.locator('.yt-player')).toHaveAttribute('data-status', 'ready');
  expect((await stats(page)).created).toBe(1);
  await reopen(page, true);
  expect((await stats(page)).created).toBe(1); expect(count()).toBe(1);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
});

test('API giả: Space trong iframe do iframe nhận, bấm ra ngoài trả phím cho Companion', async ({ page }, info) => {
  test.skip(info.project.name !== 'pc', 'Phím tắt desktop.');
  await installApi(page); await page.goto(preview); await ready(page);
  const native = page.frameLocator('iframe').getByRole('button', { name: 'Phát trong YouTube giả', exact: true });
  await native.click(); await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'true');
  await native.press('Space'); await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  expect((await stats(page)).nativeSpace).toBe(1);
  await expect(page.getByText('Đang giữ để nói · mô phỏng', { exact: true })).toHaveCount(0);
  const area = (await page.getByTestId('player-bounds').boundingBox())!;
  await page.mouse.click(area.x + area.width - 24, area.y + 18);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-active', 'false');
  await page.keyboard.down('Space');
  await expect(page.getByText('Đang giữ để nói · mô phỏng', { exact: true })).toBeVisible();
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  await page.keyboard.up('Space');
});
