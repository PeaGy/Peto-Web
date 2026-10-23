import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';
import { installApi, stats } from './youtubeFixture';

const playlist = 'PLabcdefghijk12345';
const sample = (id: string, title: string, artist: string) => ({ video_id: id, title, artist, duration: 143 });
const tetris = sample('Soy4jGPHr3g', 'Tetris', 'Kasane Teto SV');
const vampire = sample('e1xCOsgWG0M', 'Vampire', 'DECO*27');
const neural = sample('aircAruvnKk', 'Neural network', '3Blue1Brown');
const shell = (page: Page) => page.locator('#companion-player');
async function setup(page: Page, mobile: boolean) {
  await mockPeto(page); await installApi(page); await page.goto('/companion');
  if (mobile) await page.getByRole('button', { name: 'Mở menu', exact: true }).click();
  await page.getByRole('button', { name: 'Player', exact: true }).click();
}
async function input(page: Page, value: string) {
  await page.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).fill(value);
  await page.getByRole('button', { name: 'Tìm hoặc mở', exact: true }).click();
}
async function file(page: Page, mobile: boolean) {
  await shell(page).getByRole('button', { name: mobile ? 'Tùy chọn Player' : 'File', exact: true }).click();
}

test('tìm tên chỉ khi gửi, kết quả phân trang không tự phát, cộng giữ bài và chọn dùng cùng iframe', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile';
  await setup(page, mobile);
  const queries: string[] = [];
  await page.route('**/api/companion/player/search?**', route => {
    const params = new URL(route.request().url()).searchParams; queries.push(params.get('q')!);
    return route.fulfill({ json: { tracks: params.get('page_token') ? [tetris, neural] : [tetris, vampire], next_page_token: params.get('page_token') ? '' : 'PAGE2' } });
  });
  await page.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).fill('Tetris live');
  expect(queries).toEqual([]); expect(await page.evaluate(() => '__ytFake' in window)).toBe(false);
  await page.getByRole('button', { name: 'Tìm hoặc mở', exact: true }).click();
  const results = page.getByRole('list', { name: 'Các kết quả tìm kiếm', exact: true });
  await expect(results.getByRole('listitem')).toHaveCount(2);
  await expect(shell(page)).toHaveAttribute('data-status', 'empty'); expect(await page.evaluate(() => '__ytFake' in window)).toBe(false);
  await results.getByRole('button', { name: 'Phát Tetris', exact: true }).click();
  await expect(shell(page)).toHaveAttribute('data-playing', 'true');
  await results.getByRole('button', { name: 'Thêm Vampire vào hàng đợi', exact: true }).click();
  await expect(results).toBeVisible(); await expect(shell(page).locator('.yt-track-info h1')).toHaveText('Tetris');
  await expect(shell(page).locator('.yl-new-dot')).toBeVisible();
  await page.getByRole('button', { name: 'Xem thêm', exact: true }).click();
  await expect(results.getByRole('listitem')).toHaveCount(3); expect(queries).toEqual(['Tetris live', 'Tetris live']);
  await expect(page.getByRole('button', { name: 'Xem thêm', exact: true })).toHaveCount(0);
  await noPageOverflow(page); await page.screenshot({ path: info.outputPath('search-results.png') });
  await results.getByRole('button', { name: 'Phát Neural network', exact: true }).click();
  await expect(shell(page).locator('.yt-track-info h1')).toHaveText('Neural network');
  expect((await stats(page)).created).toBe(1);
});

test('nhập playlist giữ bài đang nghe, thứ tự và bản trùng; video kèm list có lựa chọn nhập riêng', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile';
  await setup(page, mobile);
  await page.route('**/api/companion/player/playlists/**', route => route.fulfill({ json: { tracks: [vampire, tetris, vampire], skipped: 2, truncated: true } }));
  await input(page, 'https://youtu.be/Soy4jGPHr3g');
  await page.getByRole('button', { name: 'Phát video', exact: true }).click();
  await expect(shell(page)).toHaveAttribute('data-playing', 'true');
  await file(page, mobile); await input(page, `https://youtube.com/playlist?list=${playlist}`);
  const queue = page.getByRole('list', { name: 'Các bài tiếp theo', exact: true });
  await expect(queue.getByRole('listitem')).toHaveCount(3);
  await expect(queue.getByRole('listitem').first()).toContainText('Vampire');
  await expect(shell(page).locator('.yt-track-info h1')).toHaveText('Tetris'); await expect(shell(page)).toHaveAttribute('data-playing', 'true');
  await expect(page.getByRole('complementary', { name: 'Hàng đợi', exact: true }).getByText(/Bỏ qua 2 video không khả dụng/)).toBeVisible();
  expect((await stats(page)).created).toBe(1);
  await file(page, mobile);
  await page.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).fill(`https://youtu.be/Soy4jGPHr3g?list=${playlist}`);
  await page.getByRole('button', { name: 'Nhập playlist', exact: true }).click();
  await expect(queue.getByRole('listitem')).toHaveCount(6);
  await noPageOverflow(page); await page.screenshot({ path: info.outputPath('playlist-import.png') });
});

test('thiếu key/hết quota có thử lại, playlist lỗi giữ nguyên hàng đợi và bài đang phát', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile';
  await setup(page, mobile);
  let failure = true;
  await page.route('**/api/companion/player/search?**', route => failure
    ? route.fulfill({ status: 503, json: { detail: 'Tìm kiếm và playlist chưa được bật. Bạn vẫn có thể mở bằng link video.' } })
    : route.fulfill({ json: { tracks: [tetris], next_page_token: '' } }));
  await page.route('**/api/companion/player/playlists/**', route => route.fulfill({ status: 404, json: { detail: 'Không đọc được playlist này.' } }));
  await input(page, 'Tetris'); await expect(page.getByRole('alert')).toContainText('chưa được bật');
  failure = false; await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
  await page.getByRole('button', { name: 'Phát Tetris', exact: true }).click();
  await page.getByRole('button', { name: 'Thêm Tetris vào hàng đợi', exact: true }).click();
  await file(page, mobile); await input(page, `https://youtube.com/playlist?list=${playlist}`);
  await expect(page.getByRole('alert')).toContainText('Không đọc được playlist');
  await expect(page.getByRole('list', { name: 'Các bài tiếp theo', exact: true }).getByRole('listitem')).toHaveCount(1);
  await expect(shell(page)).toHaveAttribute('data-playing', 'true'); expect((await stats(page)).created).toBe(1);
});
