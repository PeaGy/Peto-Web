import { expect, test, type Page } from '@playwright/test';

const preview = '/prototypes/youtube-tv/?mode=ui';

async function openFile(page: Page, mobile: boolean) {
  await page.getByRole('button', { name: mobile ? 'Tùy chọn Player' : 'File', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Link YouTube', exact: true })).toBeVisible();
}

async function expectInlineVolume(page: Page) {
  const speaker = (await page.getByRole('button', { name: /^(Tắt tiếng|Bật tiếng)$/ }).boundingBox())!;
  const slider = (await page.getByRole('slider', { name: 'Âm lượng Player', exact: true }).boundingBox())!;
  const shell = (await page.locator('.yt-player').boundingBox())!;
  expect(slider.x).toBeGreaterThanOrEqual(speaker.x + speaker.width);
  expect(Math.abs(slider.y + slider.height / 2 - speaker.y - speaker.height / 2)).toBeLessThan(2);
  expect(slider.x + slider.width).toBeLessThanOrEqual(shell.x + shell.width);
}

test('bản giao diện tự chạy, giữ vùng xem tối thiểu và không nạp dịch vụ thật', async ({ page }) => {
  const errors: string[] = [], outside: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (!request.url().startsWith('http://127.0.0.1:5179/')) outside.push(request.url()); });
  await page.goto(preview);
  await expect(page.getByRole('heading', { name: 'Tetris', exact: true })).toBeVisible();
  const video = await page.getByLabel('Vùng xem video', { exact: true }).boundingBox();
  expect(video!.width).toBeGreaterThanOrEqual(200);
  expect(video!.height).toBeGreaterThanOrEqual(200);
  await expect(page.locator('iframe, audio, video')).toHaveCount(0);
  await expect(page.getByText('Bản xem thử giao diện · Chưa phát video hoặc âm thanh.', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  expect(errors).toEqual([]);
  expect(outside).toEqual([]);
});

test('đổi sáu mẫu trong cùng cửa sổ, menu nổi không đẩy video', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile';
  await page.goto(preview);
  for (const [label, title] of [['Miku concert', 'Magical Mirai 2023'], ['Vampire', 'The Vampire'], ['Tetris', 'Tetris'],
    ['Rick Astley', 'Never Gonna Give You Up'], ['Shape of You', 'Shape of You'], ['3Blue1Brown', 'But what is a neural network?']]) {
    const before = await page.getByLabel('Vùng xem video', { exact: true }).boundingBox();
    await openFile(page, mobile);
    const panel = await page.getByRole('region', { name: 'Bảng File', exact: true }).boundingBox();
    const video = await page.getByLabel('Vùng xem video', { exact: true }).boundingBox();
    expect(video).toEqual(before);
    const shell = await page.locator('.yt-player').boundingBox();
    expect(panel!.x).toBeGreaterThanOrEqual(shell!.x);
    expect(panel!.x + panel!.width).toBeLessThanOrEqual(shell!.x + shell!.width);
    expect(panel!.y + panel!.height).toBeLessThanOrEqual(shell!.y + shell!.height);
    await page.getByRole('button', { name: label, exact: true }).click();
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Bảng File', exact: true })).toHaveCount(0);
    await expect(page.locator('.yt-player')).toHaveCount(1);
  }
  await openFile(page, mobile);
  await page.getByRole('textbox', { name: 'Link YouTube', exact: true }).fill('https://example.com/video');
  await page.getByRole('button', { name: 'Mở video', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('sáu video mẫu');
  await page.getByRole('textbox', { name: 'Link YouTube', exact: true }).fill('https://youtu.be/Soy4jGPHr3g');
  await page.getByRole('button', { name: 'Mở video', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Tetris', exact: true })).toBeVisible();
});

test('điều khiển mẫu, âm lượng và đóng rồi mở lại ở trạng thái tạm dừng', async ({ page }, info) => {
  await page.goto(preview);
  await page.getByRole('button', { name: 'Phát bản mẫu', exact: true }).click();
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'true');
  await expect(page.getByRole('slider', { name: 'Âm lượng Player', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Tắt tiếng', exact: true }).click();
  await expect(page.getByRole('slider', { name: 'Âm lượng Player', exact: true })).toHaveValue('0');
  await expectInlineVolume(page);
  await page.getByRole('button', { name: 'Bật tiếng', exact: true }).click();
  await expect(page.getByRole('slider', { name: 'Âm lượng Player', exact: true })).toHaveValue('60');
  await page.getByRole('button', { name: 'Phát lại từ đầu', exact: true }).click();
  await expect.poll(async () => Number(await page.getByRole('slider', { name: 'Vị trí phát', exact: true }).inputValue())).toBeLessThan(3);
  await page.getByRole('button', { name: info.project.name === 'mobile' ? 'Về Companion' : 'Thu nhỏ Player', exact: true }).click();
  await expect(page.locator('.yt-player')).toHaveCount(0);
  if (info.project.name === 'mobile') {
    await page.getByRole('button', { name: 'Mở menu Companion', exact: true }).click();
    await page.getByRole('button', { name: 'Player', exact: true }).click();
  } else await page.getByRole('button', { name: 'Player', exact: true }).click();
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
});

test('desktop chuyển quyền Space, nhập chữ và menu không làm phím bị xử lý hai lần', async ({ page }, info) => {
  test.skip(info.project.name !== 'pc', 'Phím tắt và cửa sổ nổi chỉ ở desktop.');
  await page.goto(preview);
  await page.locator('.yt-player').focus();
  await page.keyboard.press('Space');
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'true');
  await page.keyboard.press('Space');
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  const stage = await page.getByTestId('player-bounds').boundingBox();
  await page.mouse.click(stage!.x + stage!.width - 24, stage!.y + 22);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-active', 'false');
  await page.keyboard.down('Space');
  await expect(page.getByText('Đang giữ để nói · mô phỏng', { exact: true })).toBeVisible();
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  await page.locator('.yt-window-head > strong').click();
  await expect(page.getByText('Đang giữ để nói · mô phỏng', { exact: true })).toHaveCount(0);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-active', 'true');
  await page.keyboard.up('Space');
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  const chat = page.getByRole('textbox', { name: 'Nhắn thử trong Companion', exact: true });
  await chat.fill('xin');
  await chat.press('Space');
  await expect(chat).toHaveValue('xin ');
  await page.getByRole('button', { name: 'Help', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Bảng Help', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('region', { name: 'Bảng Help', exact: true })).toHaveCount(0);
  await expect(page.locator('.yt-player')).toHaveCount(1);
  await page.keyboard.press('Escape');
  await expect(page.locator('.yt-player')).toHaveCount(0);
});

test('desktop kéo trong sân khấu, phóng lớn và các menu có tác dụng', async ({ page }, info) => {
  test.skip(info.project.name !== 'pc', 'Điện thoại dùng bố cục cố định.');
  await page.goto(preview);
  const stage = await page.getByTestId('player-bounds').boundingBox();
  const head = await page.locator('.yt-window-head').boundingBox();
  await page.mouse.move(head!.x + 120, head!.y + 20);
  await page.mouse.down();
  await page.mouse.move(stage!.x - 200, stage!.y - 200, { steps: 5 });
  await page.mouse.up();
  const dragged = await page.locator('.yt-player').boundingBox();
  expect(dragged!.x).toBeGreaterThanOrEqual(stage!.x + 15);
  expect(dragged!.y).toBeGreaterThanOrEqual(stage!.y + 15);
  await page.getByRole('button', { name: 'Phóng lớn Player', exact: true }).click();
  const full = await page.locator('.yt-player').boundingBox();
  expect(full!.width).toBeGreaterThan(dragged!.width);
  const chat = await page.getByRole('region', { name: 'Trò chuyện mẫu', exact: true }).boundingBox();
  expect(full!.x + full!.width).toBeLessThanOrEqual(chat!.x);
  await page.getByRole('button', { name: 'Khôi phục kích thước Player', exact: true }).click();
  await page.getByRole('button', { name: 'View', exact: true }).click();
  await page.getByRole('button', { name: 'Nhỏ', exact: true }).click();
  expect((await page.locator('.yt-player').boundingBox())!.width).toBe(480);
  await page.getByRole('button', { name: 'Play', exact: true }).click();
  await page.getByRole('button', { name: 'Phát', exact: true }).click();
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'true');
  await page.getByRole('button', { name: 'Tools', exact: true }).click();
  await page.getByRole('button', { name: 'Đặt lại', exact: true }).click();
  expect((await page.locator('.yt-player').boundingBox())!.width).toBe(640);
});

test('desktop kéo góc và mép để đổi kích thước, giữ giới hạn và vùng xem tối thiểu', async ({ page }, info) => {
  test.skip(info.project.name !== 'pc', 'Điện thoại không có vùng kéo mép.');
  await page.goto(preview);
  const shell = page.locator('.yt-player');
  const area = (await page.getByTestId('player-bounds').boundingBox())!;
  async function resize(edge: string, dx: number, dy: number) {
    const handle = (await page.locator(`[data-resize="${edge}"]`).boundingBox())!;
    await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
    await page.mouse.down();
    await page.mouse.move(handle.x + handle.width / 2 + dx, handle.y + handle.height / 2 + dy, { steps: 6 });
    await page.mouse.up();
  }
  const before = (await shell.boundingBox())!;
  await resize('se', 100, 60);
  const grown = (await shell.boundingBox())!;
  expect(grown.x).toBe(before.x);
  expect(grown.y).toBe(before.y);
  expect(grown.width).toBe(before.width + 100);
  expect(grown.height).toBeCloseTo(Math.min(before.height + 60, area.y + area.height - 16 - before.y), 0);
  await resize('nw', 70, 30);
  const inset = (await shell.boundingBox())!;
  expect(inset.x + inset.width).toBe(grown.x + grown.width);
  expect(inset.y + inset.height).toBe(grown.y + grown.height);
  expect(inset.width).toBe(grown.width - 70);
  expect(inset.height).toBe(grown.height - 30);
  await resize('e', 50, 0);
  const wide = (await shell.boundingBox())!;
  expect(wide.width).toBe(inset.width + 50);
  expect(wide.height).toBe(inset.height);
  await resize('s', 0, -20);
  const short = (await shell.boundingBox())!;
  expect(short.width).toBe(wide.width);
  expect(short.height).toBe(wide.height - 20);
  await resize('se', -1000, -1000);
  const smallest = (await shell.boundingBox())!;
  expect(smallest.width).toBe(360);
  const video = (await page.getByLabel('Vùng xem video', { exact: true }).boundingBox())!;
  expect(video.height).toBeGreaterThanOrEqual(200);
  expect(video.width).toBeGreaterThanOrEqual(200);
  await expect(page.getByRole('button', { name: 'Phát bản mẫu', exact: true })).toBeInViewport();
  await resize('se', 2000, 2000);
  const largest = (await shell.boundingBox())!;
  expect(largest.x + largest.width).toBeLessThanOrEqual(area.x + area.width - 15);
  expect(largest.y + largest.height).toBeLessThanOrEqual(area.y + area.height - 15);
  await expect(page.getByRole('button', { name: 'Player', exact: true })).toBeInViewport();
  await page.getByRole('button', { name: 'Phóng lớn Player', exact: true }).click();
  await page.getByRole('button', { name: 'Khôi phục kích thước Player', exact: true }).click();
  await expect.poll(() => shell.boundingBox()).toEqual(largest);
});

test('desktop âm lượng mở ngang bên phải loa, bấm loa tắt/bật tiếng và không xê dịch video', async ({ page }, info) => {
  test.skip(info.project.name !== 'pc', 'Hover dùng chuột desktop.');
  await page.goto(preview);
  const trigger = page.getByRole('button', { name: /^(Tắt tiếng|Bật tiếng)$/ });
  const slider = page.getByRole('slider', { name: 'Âm lượng Player', exact: true });
  const video = page.getByLabel('Vùng xem video', { exact: true });
  const before = await video.boundingBox();
  await trigger.hover();
  await expect(slider).toBeVisible();
  await expectInlineVolume(page);
  expect(await video.boundingBox()).toEqual(before);
  await slider.hover();
  await expect(slider).toBeVisible();
  await video.hover();
  await expect(slider).toHaveCount(0);
  await trigger.click();
  await expect(slider).toHaveValue('0');
  await trigger.click();
  await expect(slider).toHaveValue('60');
  await slider.focus();
  await slider.press('ArrowLeft');
  await expect(slider).toHaveValue('59');
  await page.keyboard.press('Escape');
  await expect(slider).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(page.locator('.yt-player')).toHaveCount(1);
  await trigger.click();
  await page.getByRole('textbox', { name: 'Nhắn thử trong Companion', exact: true }).click();
  await expect(slider).toHaveCount(0);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-active', 'false');
});

test('desktop nút Player bật/tắt cả khi phóng lớn và mở lại ở trạng thái dừng', async ({ page }, info) => {
  test.skip(info.project.name !== 'pc', 'Mobile dùng nút quay lại và menu Companion.');
  await page.goto(preview);
  const toggle = page.getByRole('button', { name: 'Player', exact: true });
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await page.getByRole('button', { name: 'Phát bản mẫu', exact: true }).click();
  await page.getByRole('button', { name: 'Phóng lớn Player', exact: true }).click();
  await toggle.click();
  await expect(page.locator('.yt-player')).toHaveCount(0);
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(page.locator('.yt-player')).toHaveCount(1);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
});

test('mobile cố định, vùng video không bị chat che và màn hình hẹp vẫn truy cập được controls', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'Kiểm tra màn hình Đang phát.');
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto(preview);
  await expect(page.getByRole('dialog', { name: 'Peto Media Player', exact: true })).toBeVisible();
  await expect(page.locator('.yt-window-head')).toBeHidden();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('button', { name: 'Tắt tiếng', exact: true })).toBeFocused();
  await expectInlineVolume(page);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('slider', { name: 'Âm lượng Player', exact: true })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Về Companion', exact: true })).toBeFocused();
  const video = page.getByLabel('Vùng xem video', { exact: true });
  expect(await video.evaluate(node => {
    const rect = node.getBoundingClientRect();
    return node.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
  })).toBe(true);
  expect((await video.boundingBox())!.height).toBeGreaterThanOrEqual(200);
  await page.getByRole('button', { name: 'Phát bản mẫu', exact: true }).scrollIntoViewIfNeeded();
  await expect(page.getByRole('button', { name: 'Phát bản mẫu', exact: true })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await page.setViewportSize({ width: 844, height: 390 });
  await expect(page.getByRole('dialog', { name: 'Peto Media Player', exact: true })).toBeVisible();
  await expect(page.locator('.yt-window-head')).toBeHidden();
  await expect(page.locator('.yt-player')).toHaveCount(1);
  await page.getByRole('button', { name: 'Tắt tiếng', exact: true }).click();
  await expectInlineVolume(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  expect((await video.boundingBox())!.height).toBeGreaterThanOrEqual(200);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('dialog', { name: 'Peto Media Player', exact: true })).toBeVisible();
  await expect(page.locator('.yt-player')).toHaveCount(1);
});
