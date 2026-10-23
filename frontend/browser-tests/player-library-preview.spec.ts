import { expect, test, type Page } from '@playwright/test';

const preview = '/prototypes/player-library/';
const player = (page: Page) => page.locator('.yl-shell');
const transport = (page: Page) => page.getByRole('group', { name: 'Điều khiển phát', exact: true });
const source = (page: Page) => page.getByRole('textbox', { name: 'Link hoặc tên video', exact: true });
async function openFile(page: Page, mobile: boolean) {
  await page.getByRole('button', { name: mobile ? 'Tùy chọn Player' : 'File', exact: true }).click();
}
async function search(page: Page, mobile: boolean, text = 'Tetris') {
  await openFile(page, mobile);
  await source(page).fill(text);
  await page.getByRole('button', { name: 'Tìm hoặc mở', exact: true }).click();
}
async function reopen(page: Page, mobile: boolean) {
  if (mobile) await page.getByRole('button', { name: 'Mở menu Companion', exact: true }).click();
  await page.getByRole('button', { name: 'Player', exact: true }).click();
}

test('preview cô lập, không gọi dịch vụ, giữ một vùng media và bố cục danh sách đúng vị trí', async ({ page }, info) => {
  const errors: string[] = [], outside: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (!request.url().startsWith('http://127.0.0.1:5179/')) outside.push(request.url()); });
  await page.goto(preview);
  await expect(page.getByRole('heading', { name: 'Tetris', exact: true })).toBeVisible();
  await expect(page.locator('.yl-panel')).toHaveCount(0);
  if (info.project.name === 'mobile') await page.screenshot({ path: 'test-results/player-library-mobile-heart.png' });
  const media = await page.locator('.yt-video').elementHandle();
  await page.getByRole('button', { name: 'Hàng đợi', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Hàng đợi', exact: true })).toBeVisible();
  const video = (await page.locator('.yt-video').boundingBox())!;
  const panel = (await page.locator('.yl-panel').boundingBox())!;
  expect(video.width).toBeGreaterThanOrEqual(200); expect(video.height).toBeGreaterThanOrEqual(200);
  if (info.project.name === 'pc') expect(panel.x).toBeGreaterThan(video.x + video.width);
  else expect(panel.y).toBeGreaterThan(video.y + video.height);
  expect(await media!.evaluate(node => node === document.querySelector('.yt-video'))).toBe(true);
  if (info.project.name === 'mobile') {
    expect(await page.locator('.yl-panel').evaluate(node => getComputedStyle(node).color)).toBe('rgb(255, 248, 240)');
    const heart = (await page.locator('.yl-heart').boundingBox())!;
    const title = (await page.locator('.yt-track-info h1').boundingBox())!;
    const trackText = (await page.locator('.yt-track-info > div').boundingBox())!;
    const timeline = (await page.locator('.yt-timeline').boundingBox())!;
    const heartIcon = (await page.locator('.yl-heart svg').boundingBox())!;
    const duration = (await page.locator('.yt-timeline > div > span').last().boundingBox())!;
    expect(title.x + title.width).toBeLessThan(heart.x);
    expect(Math.abs(heartIcon.x + heartIcon.width / 2 - duration.x - duration.width / 2)).toBeLessThan(3);
    expect(Math.abs(heart.y + heart.height / 2 - trackText.y - trackText.height / 2)).toBeLessThan(2);
    expect(heart.y + heart.height).toBeLessThan(timeline.y);
    expect(heart.width).toBeGreaterThanOrEqual(44);
    await expect(page.locator('.yt-playback-buttons .yl-heart')).toHaveCount(0);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await expect(page.locator('iframe, audio, video')).toHaveCount(0);
  await page.screenshot({ path: `test-results/player-library-${info.project.name}-queue.png` });
  expect(errors).toEqual([]); expect(outside).toEqual([]);
});

test('tim lưu/bỏ lưu và File mở Yêu thích, dữ liệu mẫu chỉ tồn tại trong phiên', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile';
  await page.goto(preview);
  const heart = page.getByRole('button', { name: 'Yêu thích bài đang phát', exact: true });
  await expect(heart).toHaveAttribute('aria-pressed', 'false');
  await heart.click(); await expect(heart).toHaveAttribute('aria-pressed', 'true');
  await openFile(page, mobile);
  await page.getByRole('button', { name: 'Yêu thích', exact: false }).filter({ hasText: 'Yêu thích' }).click();
  const list = page.getByRole('list', { name: 'Các bài yêu thích', exact: true });
  await expect(list.getByRole('listitem')).toHaveCount(3);
  await list.getByRole('button', { name: 'Bỏ yêu thích Tetris', exact: true }).click();
  await expect(list.getByRole('listitem')).toHaveCount(2); await expect(heart).toHaveAttribute('aria-pressed', 'false');
  await list.getByRole('button', { name: 'Thêm The Vampire vào hàng đợi', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Yêu thích', exact: true })).toBeVisible();
  await expect(page.locator('.yl-new-dot')).toBeVisible();
  await page.getByRole('button', { name: 'Hàng đợi', exact: true }).click();
  await expect(page.getByRole('list', { name: 'Các bài tiếp theo', exact: true }).getByRole('listitem')).toHaveCount(4);
  await expect(page.locator('.yl-new-dot')).toBeHidden();
  await page.reload();
  await expect(heart).toHaveAttribute('aria-pressed', 'false');
  await page.getByRole('button', { name: 'Hàng đợi', exact: true }).click();
  await expect(page.getByRole('list', { name: 'Các bài tiếp theo', exact: true }).getByRole('listitem')).toHaveCount(3);
});

test('tìm tên không tự phát; cộng bài giữ danh sách, chọn kết quả và playlist mẫu hoạt động', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile';
  await page.goto(preview);
  await search(page, mobile);
  const results = page.getByRole('list', { name: 'Các kết quả mẫu', exact: true });
  await expect(results.getByRole('listitem')).toHaveCount(5);
  await expect(player(page)).toHaveAttribute('data-playing', 'false');
  await results.getByRole('button', { name: 'Thêm Tetris — piano arrange vào hàng đợi', exact: true }).click();
  await expect(results).toBeVisible(); await expect(page.locator('.yl-new-dot')).toBeVisible();
  await expect(page.locator('.yt-track-info h1')).toHaveText('Tetris');
  await results.getByRole('button', { name: 'Phát Tetris — piano arrange', exact: true }).click();
  await expect(page.locator('.yt-track-info h1')).toHaveText('Tetris — piano arrange');
  await expect(player(page)).toHaveAttribute('data-playing', 'true');
  await openFile(page, mobile);
  await page.getByRole('button', { name: 'Playlist mẫu', exact: true }).click();
  await expect(page.getByRole('list', { name: 'Các bài tiếp theo', exact: true }).getByRole('listitem')).toHaveCount(7);
  await expect(page.locator('.yt-track-info h1')).toHaveText('Tetris — piano arrange');
  await expect(player(page)).toHaveAttribute('data-playing', 'true');
  await page.getByRole('button', { name: 'Bài tiếp theo', exact: true }).click();
  await expect(page.locator('.yt-track-info h1')).toHaveText('The Vampire');
  await search(page, mobile, 'không có video này');
  await expect(page.getByText('Không có kết quả mẫu.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Tìm lại', exact: true }).click();
  await expect(source(page)).toBeFocused();
});

test('hàng đợi đổi thứ tự bằng phím/menu, xóa và chuyển bài đúng', async ({ page }) => {
  await page.goto(preview);
  await page.getByRole('button', { name: 'Hàng đợi', exact: true }).click();
  const list = page.getByRole('list', { name: 'Các bài tiếp theo', exact: true });
  await list.getByRole('button', { name: 'Di chuyển Magical Mirai 2023', exact: true }).press('ArrowUp');
  await expect(list.getByRole('listitem').first()).toContainText('Magical Mirai 2023');
  await list.locator('summary').first().click();
  await page.keyboard.press('Escape');
  await expect(list.locator('details[open]')).toHaveCount(0);
  await expect(page.locator('.yl-panel')).toBeVisible();
  await list.locator('summary').first().click();
  await list.getByRole('button', { name: 'Đưa xuống', exact: true }).first().click();
  await expect(list.getByRole('listitem').first()).toContainText('The Vampire');
  await list.locator('summary').last().click();
  await list.getByRole('button', { name: 'Xóa khỏi hàng đợi', exact: true }).last().click();
  await expect(list.getByRole('listitem')).toHaveCount(2);
  await list.getByRole('button', { name: 'Phát Magical Mirai 2023', exact: true }).click();
  await expect(page.locator('.yt-track-info h1')).toHaveText('Magical Mirai 2023');
  await expect(list.getByRole('listitem')).toHaveCount(1);
  await page.getByRole('button', { name: 'Bài tiếp theo', exact: true }).click();
  await expect(page.locator('.yt-track-info h1')).toHaveText('The Vampire');
  await expect(page.getByText('Hàng đợi đang trống.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Thêm bài', exact: true }).last().click();
  await expect(source(page)).toBeFocused();
});

test('đổi bài khi đồng hồ mẫu kết thúc, link giả không được coi là video mẫu', async ({ page }, info) => {
  await page.clock.install();
  await page.goto(preview);
  await page.getByRole('slider', { name: 'Vị trí phát', exact: true }).press('End');
  await page.getByRole('button', { name: 'Phát bản mẫu', exact: true }).click();
  await expect(page.locator('.yt-track-info h1')).toHaveText('The Vampire');
  await expect(page.getByRole('slider', { name: 'Vị trí phát', exact: true })).toHaveValue('0');
  await openFile(page, info.project.name === 'mobile');
  await source(page).fill('https://youtube.com.attacker.test/watch?v=Soy4jGPHr3g');
  await page.getByRole('button', { name: 'Tìm hoặc mở', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Bản xem thử');
  await source(page).fill('https://youtu.be/Soy4jGPHr3g');
  await page.getByRole('button', { name: 'Tìm hoặc mở', exact: true }).click();
  await expect(page.locator('.yt-track-info h1')).toHaveText('Tetris');
  await expect(player(page)).toHaveAttribute('data-playing', 'false');
});

test('Space không chen ô nhập; Esc đóng danh sách trước, ẩn giữ đồng hồ, X dừng', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile';
  await page.clock.install();
  await page.goto(preview);
  await openFile(page, mobile);
  await source(page).fill('Tetris'); await source(page).press('End'); await source(page).press('Space');
  await expect(source(page)).toHaveValue('Tetris '); await expect(player(page)).toHaveAttribute('data-playing', 'false');
  await source(page).press('Enter');
  await page.keyboard.press('Escape'); await expect(page.locator('.yl-panel')).toHaveCount(0); await expect(player(page)).toBeVisible();
  await page.getByRole('button', { name: 'Phát bản mẫu', exact: true }).click();
  await page.getByRole('button', { name: mobile ? 'Ẩn Player' : 'Thu nhỏ Player', exact: true }).click();
  await expect(player(page)).toBeHidden();
  const position = Number(await page.locator('.yt-timeline input').inputValue());
  await page.clock.fastForward(3000);
  await page.getByRole('textbox', { name: 'Nhắn thử trong Companion', exact: true }).fill('chat khi player ẩn');
  await reopen(page, mobile);
  await expect(player(page)).toHaveAttribute('data-playing', 'true');
  expect(Number(await page.locator('.yt-timeline input').inputValue())).toBeGreaterThan(position);
  await page.getByRole('button', { name: mobile ? 'Dừng và đóng Player' : 'Đóng Player', exact: true }).click();
  await expect(player(page)).toHaveCount(0);
  await reopen(page, mobile); await expect(player(page)).toHaveAttribute('data-playing', 'false');
});

test('cửa sổ hẹp và mobile nhỏ/ngang không tràn, danh sách tự cuộn', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile';
  for (const size of mobile ? [{ width: 320, height: 640 }, { width: 844, height: 390 }] : [{ width: 1120, height: 800 }]) {
    await page.setViewportSize(size); await page.goto(preview);
    if (!mobile) {
      await page.getByRole('button', { name: 'View', exact: true }).click();
      await page.getByRole('button', { name: 'Nhỏ', exact: true }).click();
    }
    await page.getByRole('button', { name: 'Hàng đợi', exact: true }).click();
    const video = (await page.locator('.yt-video').boundingBox())!;
    const panel = (await page.locator('.yl-panel').boundingBox())!;
    expect(video.width).toBeGreaterThanOrEqual(200); expect(video.height).toBeGreaterThanOrEqual(200);
    expect(panel.y).toBeGreaterThan(video.y + video.height);
    for (let i = 0; i < 3; i++) {
      await openFile(page, mobile); await page.getByRole('button', { name: 'Playlist mẫu', exact: true }).click();
    }
    expect(await page.locator('.yl-panel-scroll').evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true);
    expect(await page.locator('.yl-player-body').evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/player-library-${size.width}x${size.height}.png` });
  }
});

test('lặp đổi đủ ba chế độ, lặp một bài khi kết thúc và nút tiếp theo vẫn bỏ qua được', async ({ page }) => {
  await page.clock.install();
  await page.goto(preview);
  await page.getByRole('button', { name: 'Hàng đợi', exact: true }).click();
  const list = page.getByRole('list', { name: 'Các bài tiếp theo', exact: true });
  await expect(transport(page).getByRole('button', { name: 'Chế độ lặp: tắt', exact: true })).toHaveAttribute('aria-pressed', 'false');
  await transport(page).getByRole('button', { name: 'Chế độ lặp: tắt', exact: true }).click();
  await expect(transport(page).getByRole('button', { name: 'Chế độ lặp: hàng đợi', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.yt-track-info h1')).toHaveText('Tetris');
  await expect(player(page)).toHaveAttribute('data-playing', 'false');
  await transport(page).getByRole('button', { name: 'Chế độ lặp: hàng đợi', exact: true }).click();
  await expect(transport(page).getByRole('button', { name: 'Chế độ lặp: một bài', exact: true })).toHaveAttribute('data-repeat', 'one');
  const position = page.getByRole('slider', { name: 'Vị trí phát', exact: true });
  await position.press('End'); await position.press('ArrowLeft');
  await page.getByRole('button', { name: 'Phát bản mẫu', exact: true }).click();
  await page.clock.fastForward(1000);
  await expect(position).toHaveValue('0');
  await expect(page.locator('.yt-track-info h1')).toHaveText('Tetris');
  await expect(list.getByRole('listitem')).toHaveCount(3);
  await page.getByRole('button', { name: 'Bài tiếp theo', exact: true }).click();
  await expect(page.locator('.yt-track-info h1')).toHaveText('The Vampire');
  await expect(list.getByRole('listitem')).toHaveCount(2);
  await transport(page).getByRole('button', { name: 'Chế độ lặp: một bài', exact: true }).click();
  await expect(transport(page).getByRole('button', { name: 'Chế độ lặp: tắt', exact: true })).toHaveAttribute('aria-pressed', 'false');
});

test('shuffle giữ bài hiện tại, thứ tự hiển thị đúng thứ tự phát và kết hợp được với lặp hàng đợi', async ({ page }, info) => {
  await page.goto(preview);
  await expect(page.locator('.yl-panel')).toHaveCount(0);
  const buttons = transport(page).getByRole('button');
  await expect(buttons).toHaveCount(5);
  expect(await buttons.evaluateAll(nodes => nodes.map(node => node.getAttribute('aria-label')))).toEqual([
    'Phát ngẫu nhiên', 'Phát lại từ đầu', 'Phát bản mẫu', 'Bài tiếp theo', 'Chế độ lặp: tắt',
  ]);
  const boxes = await Promise.all((await buttons.all()).map(button => button.boundingBox()));
  for (let index = 1; index < boxes.length; index++) {
    expect(boxes[index]!.x).toBeGreaterThanOrEqual(boxes[index - 1]!.x + boxes[index - 1]!.width);
    expect(Math.abs(boxes[index]!.y + boxes[index]!.height / 2 - boxes[2]!.y - boxes[2]!.height / 2)).toBeLessThan(1);
  }
  const row = (await transport(page).boundingBox())!;
  expect(Math.abs(boxes[2]!.x + boxes[2]!.width / 2 - row.x - row.width / 2)).toBeLessThan(1);
  const shuffle = transport(page).getByRole('button', { name: 'Phát ngẫu nhiên', exact: true });
  await expect(shuffle).toHaveAttribute('aria-pressed', 'false');
  await transport(page).getByRole('button', { name: 'Chế độ lặp: tắt', exact: true }).click();
  await shuffle.click();
  await expect(shuffle).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.yt-track-info h1')).toHaveText('Tetris');
  await expect(page.getByRole('slider', { name: 'Vị trí phát', exact: true })).toHaveValue('13');
  await expect(page.locator('.yl-panel')).toHaveCount(0);
  if (info.project.name === 'mobile') {
    for (const button of [shuffle, transport(page).getByRole('button', { name: 'Chế độ lặp: hàng đợi', exact: true })]) {
      const box = (await button.boundingBox())!;
      expect(box.width).toBeGreaterThanOrEqual(44); expect(box.height).toBeGreaterThanOrEqual(44);
    }
  }
  await page.screenshot({ path: `test-results/player-library-${info.project.name}-modes.png` });
  await page.getByRole('button', { name: 'Hàng đợi', exact: true }).click();
  const list = page.getByRole('list', { name: 'Các bài tiếp theo', exact: true });
  const queueModes = page.getByRole('group', { name: 'Chế độ hàng đợi', exact: true });
  await expect(queueModes.getByRole('button', { name: 'Phát ngẫu nhiên', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(queueModes.getByRole('button', { name: 'Chế độ lặp: hàng đợi', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await queueModes.getByRole('button', { name: 'Chế độ lặp: hàng đợi', exact: true }).click();
  await expect(transport(page).getByRole('button', { name: 'Chế độ lặp: một bài', exact: true })).toHaveAttribute('data-repeat', 'one');
  await queueModes.getByRole('button', { name: 'Chế độ lặp: một bài', exact: true }).click();
  await queueModes.getByRole('button', { name: 'Chế độ lặp: tắt', exact: true }).click();
  expect(await page.locator('.yl-panel-scroll').evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  const next = (await list.getByRole('button', { name: /^Phát / }).first().getAttribute('aria-label'))!.replace(/^Phát /, '');
  await page.getByRole('button', { name: 'Bài tiếp theo', exact: true }).click();
  await expect(page.locator('.yt-track-info h1')).toHaveText(next);
  await expect(list.getByRole('listitem')).toHaveCount(3);
  await queueModes.getByRole('button', { name: 'Phát ngẫu nhiên', exact: true }).click();
  await expect(shuffle).toHaveAttribute('aria-pressed', 'false');
  await page.reload(); await page.getByRole('button', { name: 'Hàng đợi', exact: true }).click();
  await expect(shuffle).toHaveAttribute('aria-pressed', 'false');
  await expect(transport(page).getByRole('button', { name: 'Chế độ lặp: tắt', exact: true })).toBeVisible();
});
