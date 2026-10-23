import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';
import { installApi, stats, type FakeStats } from './youtubeFixture';

const url = (id: string) => `https://www.youtube.com/watch?v=${id}`;
const shell = (page: Page) => page.locator('#companion-player');
const primary = (page: Page) => page.getByRole('group', { name: 'Điều khiển phát', exact: true });
async function openPlayer(page: Page, mobile: boolean) {
  if (mobile) await page.getByRole('button', { name: 'Mở menu', exact: true }).click();
  await page.getByRole('button', { name: 'Player', exact: true }).click();
  await expect(shell(page)).toBeVisible();
}
async function file(page: Page, mobile: boolean) {
  await shell(page).getByRole('button', { name: mobile ? 'Tùy chọn Player' : 'File', exact: true }).click();
  return page.getByRole('region', { name: 'Bảng File', exact: true });
}
async function firstVideo(page: Page) {
  await page.getByRole('textbox', { name: 'Link YouTube', exact: true }).fill(url('Soy4jGPHr3g'));
  await page.getByRole('button', { name: 'Mở video', exact: true }).click();
  await expect(shell(page)).toHaveAttribute('data-status', 'ready');
  await expect(shell(page).locator('.yt-track-info h1')).toHaveText('Tetris');
}
async function add(page: Page, mobile: boolean, id: string) {
  const menu = await file(page, mobile);
  await menu.getByRole('textbox', { name: 'Link YouTube', exact: true }).fill(url(id));
  await menu.getByRole('button', { name: 'Thêm vào hàng đợi', exact: true }).click();
}
const end = (page: Page) => page.evaluate(() => (window as unknown as { __ytFake: FakeStats }).__ytFake.end());

test('yêu thích thật qua API, F5 giữ danh sách, không có mẫu trong app và chọn bài giữ một iframe', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile';
  const state = await mockPeto(page); await installApi(page);
  await page.goto('/companion'); await openPlayer(page, mobile);
  await expect(page.getByText('Playlist mẫu', { exact: true })).toHaveCount(0);
  await firstVideo(page);
  const heart = page.getByRole('button', { name: 'Yêu thích bài đang phát', exact: true });
  await expect(heart).toBeEnabled(); await heart.click(); await expect(heart).toHaveAttribute('aria-pressed', 'true');
  expect(state.playerFavorites.size).toBe(1);
  const menu = await file(page, mobile); await menu.locator('.yl-favorites-menu').click();
  const list = page.getByRole('list', { name: 'Các bài yêu thích', exact: true });
  await list.getByRole('button', { name: 'Phát Tetris', exact: true }).click();
  await expect(shell(page)).toHaveAttribute('data-playing', 'true'); expect((await stats(page)).created).toBe(1);
  await page.reload(); await openPlayer(page, mobile);
  await expect(shell(page)).toHaveAttribute('data-status', 'empty');
  const loaded = await file(page, mobile); await loaded.locator('.yl-favorites-menu').click();
  await expect(list.getByRole('listitem')).toHaveCount(1);
  await list.getByRole('button', { name: 'Phát Tetris', exact: true }).click();
  await expect(shell(page)).toHaveAttribute('data-playing', 'true');
  await page.getByRole('button', { name: mobile ? 'Dừng và đóng Player' : 'Đóng Player', exact: true }).click();
  await openPlayer(page, mobile); await expect(shell(page)).toHaveAttribute('data-status', 'ready');
  await expect(shell(page)).toHaveAttribute('data-playing', 'false');
  await heart.click(); await expect(heart).toHaveAttribute('aria-pressed', 'false'); expect(state.playerFavorites.size).toBe(0);
});

test('hàng đợi thật: đổi thứ tự, phát tiếp, loop/shuffle, lỗi nhúng và ẩn UI vẫn dùng đúng một iframe', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile';
  await mockPeto(page); await installApi(page);
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/companion'); await openPlayer(page, mobile); await firstVideo(page);
  await add(page, mobile, 'e1xCOsgWG0M'); await add(page, mobile, 'aircAruvnKk');
  await expect(shell(page)).toHaveAttribute('data-playing', 'false'); await expect(shell(page).locator('.yl-new-dot')).toBeVisible();
  await page.getByRole('button', { name: 'Hàng đợi', exact: true }).click();
  const list = page.getByRole('list', { name: 'Các bài tiếp theo', exact: true });
  await expect(list.getByRole('listitem')).toHaveCount(2);
  await list.getByRole('button', { name: 'Di chuyển But what is a neural network?', exact: true }).press('ArrowUp');
  await expect(list.getByRole('listitem').first()).toContainText('But what is a neural network?');
  await primary(page).getByRole('button', { name: 'Chế độ lặp: tắt', exact: true }).click();
  const shuffle = primary(page).getByRole('button', { name: 'Phát ngẫu nhiên', exact: true });
  await shuffle.click(); await expect(shuffle).toHaveAttribute('aria-pressed', 'true'); await shuffle.click();
  await page.getByRole('button', { name: 'Phát video', exact: true }).click();
  const iframe = await shell(page).locator('iframe').elementHandle();
  for (const title of ['But what is a neural network?', 'The Vampire', 'Tetris']) {
    await end(page); await expect(shell(page).locator('.yt-track-info h1')).toHaveText(title);
    await expect(shell(page)).toHaveAttribute('data-playing', 'true'); await expect(list.getByRole('listitem')).toHaveCount(2);
  }
  await primary(page).getByRole('button', { name: 'Chế độ lặp: hàng đợi', exact: true }).click();
  const before = (await stats(page)).cues.length;
  await end(page); await expect.poll(async () => (await stats(page)).cues.length).toBe(before + 1);
  await expect(shell(page).locator('.yt-track-info h1')).toHaveText('Tetris');
  await primary(page).getByRole('button', { name: 'Bài tiếp theo', exact: true }).click();
  await expect(shell(page).locator('.yt-track-info h1')).toHaveText('But what is a neural network?');
  await primary(page).getByRole('button', { name: 'Chế độ lặp: một bài', exact: true }).click();
  await page.evaluate(() => (window as unknown as { __ytFake: FakeStats }).__ytFake.fail(150));
  await expect(page.getByRole('alert')).toContainText('150');
  await primary(page).getByRole('button', { name: 'Bài tiếp theo', exact: true }).click();
  await expect(shell(page).locator('.yt-track-info h1')).toHaveText('The Vampire'); await expect(shell(page)).toHaveAttribute('data-playing', 'true');
  await add(page, mobile, 'Soy4jGPHr3g');
  await page.getByRole('button', { name: mobile ? 'Ẩn Player' : 'Thu nhỏ Player', exact: true }).click();
  await expect(shell(page)).toBeHidden(); await end(page);
  await openPlayer(page, mobile); await expect(shell(page).locator('.yt-track-info h1')).toHaveText('Tetris');
  await expect(shell(page)).toHaveAttribute('data-playing', 'true');
  expect((await stats(page)).created).toBe(1); expect(await iframe!.evaluate(node => node.isConnected)).toBe(true);
  await noPageOverflow(page); await page.screenshot({ path: info.outputPath('player-stage2.png') }); expect(errors).toEqual([]);
});
