import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';
import { installApi, stats } from './youtubeFixture';

const shell = (page: Page) => page.locator('#companion-player');
async function setup(page: Page, mobile: boolean) {
  await mockPeto(page); const apiLoads = await installApi(page);
  await page.goto('/companion'); await open(page, mobile); return apiLoads;
}
async function open(page: Page, mobile: boolean) {
  if (mobile) await page.getByRole('button', { name: 'Mở menu', exact: true }).click();
  await page.getByRole('button', { name: 'Player', exact: true }).click();
  await expect(shell(page)).toBeVisible();
}
async function submit(page: Page, value: string) {
  await page.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).fill(value);
  await page.getByRole('button', { name: 'Tìm hoặc mở', exact: true }).click();
}

test('playlist đủ 200 mục vẫn cuộn/resize, không nhân iframe hoặc vượt sức chứa', async ({ page }, info) => {
  test.setTimeout(60000);
  const mobile = info.project.name === 'mobile';
  await setup(page, mobile);
  const tracks = Array.from({ length: 200 }, (_, index) => ({ video_id: `test${String(index).padStart(7, '0')}`,
    title: `Bài ${index + 1} · テトリス — tên video dài để kiểm tra bố cục danh sách`, artist: 'Nghệ sĩ thử nghiệm', duration: 143 }));
  let metadataCalls = 0;
  await page.route('**/api/companion/player/videos/**', route => { metadataCalls++; return route.fulfill({ json: { video_id: 'Soy4jGPHr3g', title: 'Tetris', artist: 'Teto' } }); });
  await page.route('**/api/companion/player/playlists/**', route => route.fulfill({ json: { tracks, skipped: 0, truncated: false } }));
  await submit(page, 'https://youtube.com/playlist?list=PLabcdefghijk12345');
  const queue = page.getByRole('list', { name: 'Các bài tiếp theo', exact: true });
  await expect(queue.getByRole('listitem')).toHaveCount(200);
  await expect(shell(page).locator('iframe')).toHaveCount(0);
  expect(metadataCalls).toBe(0);
  await queue.getByRole('listitem').first().getByRole('button', { name: /^Phát / }).click();
  await expect(shell(page)).toHaveAttribute('data-playing', 'true');
  await expect(queue.getByRole('listitem')).toHaveCount(199);
  for (const viewport of mobile ? [{ width: 320, height: 640 }, { width: 844, height: 390 }, { width: 390, height: 844 }]
    : [{ width: 1000, height: 650 }, { width: 1440, height: 900 }]) {
    await page.setViewportSize(viewport); await noPageOverflow(page);
    const box = await shell(page).locator('iframe').boundingBox();
    expect(box!.width).toBeGreaterThanOrEqual(200); expect(box!.height).toBeGreaterThanOrEqual(200);
  }
  await queue.getByRole('listitem').last().locator('summary').click();
  await queue.getByRole('button', { name: 'Xóa khỏi hàng đợi', exact: true }).click();
  await expect(queue.getByRole('listitem')).toHaveCount(198);
  await shell(page).getByRole('button', { name: mobile ? 'Tùy chọn Player' : 'File', exact: true }).click();
  await page.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).fill('https://youtu.be/Soy4jGPHr3g');
  await page.getByRole('button', { name: 'Thêm vào hàng đợi', exact: true }).click();
  await expect(queue.getByRole('listitem')).toHaveCount(199);
  for (let attempt = 0; attempt < 2; attempt++) {
    await shell(page).getByRole('button', { name: mobile ? 'Tùy chọn Player' : 'File', exact: true }).click();
    await page.getByRole('button', { name: 'Thêm vào hàng đợi', exact: true }).click();
    await expect(queue.getByRole('listitem')).toHaveCount(200);
  }
  await expect(page.getByRole('alert')).toContainText('200 bài');
  expect((await stats(page)).created).toBe(1);
  await noPageOverflow(page); await page.screenshot({ path: info.outputPath('queue-200.png') });
});

test('mở/đóng 10 lần dọn đúng từng iframe, API chỉ nạp một lần, tim nằm giữa vùng bấm', async ({ page }, info) => {
  test.setTimeout(60000);
  const mobile = info.project.name === 'mobile'; const loads = await setup(page, mobile);
  await submit(page, 'https://youtu.be/Soy4jGPHr3g');
  await expect(shell(page)).toHaveAttribute('data-status', 'ready');
  const heart = page.getByRole('button', { name: 'Yêu thích bài đang phát', exact: true });
  const centers = await heart.evaluate(button => {
    const box = button.getBoundingClientRect(), icon = button.querySelector('svg')!.getBoundingClientRect();
    return { x: box.x + box.width / 2 - icon.x - icon.width / 2, y: box.y + box.height / 2 - icon.y - icon.height / 2 };
  });
  expect(Math.abs(centers.x)).toBeLessThan(1); expect(Math.abs(centers.y)).toBeLessThan(1);
  for (let index = 0; index < 10; index++) {
    await page.getByRole('button', { name: 'Phát video', exact: true }).click();
    await expect(shell(page)).toHaveAttribute('data-playing', 'true');
    await page.getByRole('button', { name: mobile ? 'Dừng và đóng Player' : 'Đóng Player', exact: true }).click();
    await expect(page.locator('#companion-player iframe')).toHaveCount(0);
    if (index < 9) { await open(page, mobile); await expect(shell(page)).toHaveAttribute('data-status', 'ready'); }
  }
  const counted = await stats(page);
  expect(counted.created).toBe(10); expect(counted.destroyed).toBe(10); expect(loads()).toBe(1);
});
