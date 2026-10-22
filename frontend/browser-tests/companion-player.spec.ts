import { expect, test, type Page } from '@playwright/test';
import { Buffer } from 'node:buffer';
import { mockPeto, noPageOverflow } from './fixtures';
import { installApi, stats } from './youtubeFixture';

const video = 'https://www.youtube.com/watch?v=Soy4jGPHr3g';
const chat = (page: Page) => page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion', exact: true });
test.use({ permissions: ['microphone'], launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] } });
async function openSidebar(page: Page) {
  if (!await page.locator('.sidebar').isVisible()) {
    await page.getByRole('button', { name: /^(Mở menu|Mở danh sách hội thoại)$/ }).first().click();
  }
  await expect(page.locator('.sidebar')).toBeVisible();
}
async function openPlayer(page: Page, mobile: boolean) {
  if (mobile) await page.getByRole('button', { name: 'Mở menu', exact: true }).click();
  await page.getByRole('button', { name: 'Player', exact: true }).click();
  await expect(page.locator('.yt-player')).toBeVisible();
}
async function chooseVideo(page: Page) {
  await page.getByRole('textbox', { name: 'Link YouTube', exact: true }).fill(video);
  await page.getByRole('button', { name: 'Mở video', exact: true }).click();
  await expect(page.locator('.yt-player')).toHaveAttribute('data-status', 'ready');
}

test('Companion thật: chỉ tải YouTube khi có link, đổi nguồn giữ iframe và đóng/mở không tự phát', async ({ page }, info) => {
  await mockPeto(page);
  const requests = await installApi(page), mobile = info.project.name === 'mobile';
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/companion'); await expect(chat(page)).toBeVisible();
  expect(requests()).toBe(0);
  const chatBefore = await chat(page).boundingBox();
  await openPlayer(page, mobile);
  expect(requests()).toBe(0);
  await page.getByRole('textbox', { name: 'Link YouTube', exact: true }).fill('https://youtube.com.evil.example/watch?v=Soy4jGPHr3g');
  await page.getByRole('button', { name: 'Mở video', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('chưa hợp lệ');
  expect(requests()).toBe(0);
  await chooseVideo(page);
  const iframe = await page.locator('.yt-player iframe').elementHandle();
  expect((await stats(page)).created).toBe(1);
  if (!mobile) {
    const frame = (await page.locator('.yt-player').boundingBox())!;
    const panel = (await page.locator('.companion-panel').boundingBox())!;
    expect(frame.x + frame.width).toBeLessThanOrEqual(panel.x);
    const title = (await page.locator('.yt-window-head').boundingBox())!;
    expect((await page.locator('.yt-menu-bar').boundingBox())!.height).toBeLessThan(title.height);
  }
  await page.getByRole('button', { name: mobile ? 'Tùy chọn Player' : 'File', exact: true }).click();
  await page.getByRole('textbox', { name: 'Link YouTube', exact: true }).fill('https://youtu.be/aircAruvnKk?t=12');
  await page.getByRole('button', { name: 'Mở video', exact: true }).click();
  expect((await stats(page)).cues.at(-1)).toEqual({ videoId: 'aircAruvnKk', startSeconds: 12 });
  expect(await iframe!.evaluate(node => node.isConnected)).toBe(true);
  await page.getByRole('button', { name: 'Phát video', exact: true }).click();
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'true');
  await noPageOverflow(page); await page.screenshot({ path: info.outputPath('companion-player.png') });
  if (!mobile) {
    await page.setViewportSize({ width: 800, height: 760 });
    await expect(page.locator('.yt-player')).toHaveCSS('width', '800px');
    expect((await page.locator('.yt-player iframe').boundingBox())!.width).toBeGreaterThanOrEqual(200);
    expect(await iframe!.evaluate(node => node.isConnected)).toBe(true);
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(page.locator('.yt-window-head')).toBeVisible();
  }
  if (mobile) {
    await page.getByRole('button', { name: 'Ẩn Player', exact: true }).click();
    await expect(page.locator('.yt-player')).toBeHidden();
    await expect(page.locator('.yt-player')).toHaveAttribute('inert', '');
    await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'true');
    expect(await iframe!.evaluate(node => node.isConnected)).toBe(true);
    expect(await chat(page).boundingBox()).toEqual(chatBefore);
    await chat(page).fill('Tiếp tục trò chuyện khi đang nghe nhạc');
    await openPlayer(page, true);
    expect(await iframe!.evaluate(node => node.isConnected)).toBe(true);
    await page.setViewportSize({ width: 844, height: 390 });
    await expect(page.locator('.yt-player')).toHaveCSS('width', '844px');
    const full = (await page.locator('.yt-player').boundingBox())!;
    expect(full.x).toBe(0); expect(full.y).toBe(0); expect(full.height).toBe(390);
    const size = (await page.locator('.yt-player iframe').boundingBox())!;
    expect(size.x).toBeGreaterThanOrEqual(0);
    expect(size.width).toBeGreaterThanOrEqual(200); expect(size.height).toBeGreaterThanOrEqual(200);
    await noPageOverflow(page);
    await page.setViewportSize({ width: 390, height: 844 });
  }
  await page.getByRole('button', { name: mobile ? 'Dừng và đóng Player' : 'Đóng Player', exact: true }).click();
  await expect(page.locator('.yt-player iframe')).toHaveCount(0);
  expect((await stats(page)).destroyed).toBe(1);
  await openPlayer(page, mobile);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-status', 'ready');
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  expect(requests()).toBe(1);
  expect((await stats(page)).created).toBe(2);
  expect(errors).toEqual([]);
});

test('desktop thu nhỏ giữ video, nút icon ẩn/hiện và cửa sổ kéo được tới đáy Companion', async ({ page }, info) => {
  test.skip(info.project.name !== 'pc', 'Mobile dùng mũi tên xuống.');
  await mockPeto(page); await installApi(page);
  await page.goto('/companion'); await expect(chat(page)).toBeVisible();
  const trigger = page.getByRole('button', { name: 'Player', exact: true });
  expect(await trigger.textContent()).toBe('');
  expect((await trigger.boundingBox())!.width).toBe((await page.getByRole('button', { name: 'Bối cảnh', exact: true }).boundingBox())!.width);
  await openPlayer(page, false); await chooseVideo(page);
  const shell = page.locator('.yt-player');
  const iframe = await shell.locator('iframe').elementHandle();
  await shell.getByRole('button', { name: 'Phát video', exact: true }).click();
  await shell.getByRole('slider', { name: 'Vị trí phát', exact: true }).press('ArrowRight');
  await expect(shell.getByRole('slider', { name: 'Vị trí phát', exact: true })).toHaveValue('1');
  await shell.getByRole('button', { name: 'File', exact: true }).click();
  await shell.getByRole('button', { name: 'Thu nhỏ Player', exact: true }).click();
  await expect(shell).toBeHidden();
  await expect(shell).toHaveAttribute('inert', '');
  await expect(shell).toHaveAttribute('data-playing', 'true');
  await expect(page.locator('.yt-command-panel')).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await chat(page).fill('Tiếp tục trò chuyện');
  expect(await iframe!.evaluate(node => node.isConnected)).toBe(true);
  expect((await stats(page)).destroyed).toBe(0);
  await trigger.click(); await expect(shell).toBeVisible();
  await expect(shell).toHaveAttribute('data-playing', 'true');
  await expect(shell.getByRole('slider', { name: 'Vị trí phát', exact: true })).toHaveValue('1');
  await trigger.click(); await expect(shell).toBeHidden();
  await trigger.click(); await expect(shell).toBeVisible();
  expect(await iframe!.evaluate(node => node.isConnected)).toBe(true);
  expect((await stats(page)).created).toBe(1);
  const area = (await page.locator('.companion').boundingBox())!;
  const head = (await page.locator('.yt-window-head').boundingBox())!;
  await page.mouse.move(head.x + 120, head.y + 18); await page.mouse.down();
  await page.mouse.move(head.x + 120, area.y + area.height + 500, { steps: 6 }); await page.mouse.up();
  const moved = (await shell.boundingBox())!;
  expect(moved.y + moved.height).toBeCloseTo(area.y + area.height, 0);
  const panel = (await page.locator('.companion-panel').boundingBox())!;
  expect(moved.x + moved.width).toBeLessThanOrEqual(panel.x);
  await expect(trigger).toBeInViewport();
  await page.screenshot({ path: info.outputPath('player-at-bottom.png') });
  await shell.getByRole('button', { name: 'Phóng lớn Player', exact: true }).click();
  const full = (await shell.boundingBox())!;
  expect(full.y + full.height).toBeCloseTo(area.y + area.height, 0);
  await shell.getByRole('button', { name: 'Khôi phục kích thước Player', exact: true }).click();
  await expect.poll(() => shell.boundingBox()).toEqual(moved);
  await shell.getByRole('button', { name: 'Đóng Player', exact: true }).click();
  await expect(page.locator('.yt-player iframe')).toHaveCount(0);
  expect((await stats(page)).destroyed).toBe(1);
});

test('Companion thật: ẩn trang, chuyển tab, mở Cài đặt và đăng xuất đều giải phóng iframe', async ({ page }, info) => {
  await mockPeto(page); await installApi(page);
  await page.route('**/api/auth/logout', route => route.fulfill({ json: { ok: true } }));
  const mobile = info.project.name === 'mobile';
  await page.goto('/companion'); await expect(chat(page)).toBeVisible();
  await openPlayer(page, mobile); await chooseVideo(page);
  await page.getByRole('button', { name: 'Phát video', exact: true }).click();
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(page.locator('.yt-player iframe')).toHaveCount(0);
  await page.evaluate(() => {
    delete (document as unknown as { hidden?: boolean }).hidden;
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(page.locator('.yt-player')).toHaveAttribute('data-status', 'ready');
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  if (mobile) await page.getByRole('button', { name: 'Ẩn Player', exact: true }).click();
  await openSidebar(page);
  await page.getByRole('button', { name: 'Trò chuyện', exact: true }).click();
  await expect(page.locator('.yt-player iframe')).toHaveCount(0);
  await expect(chat(page)).toBeHidden();
  await openSidebar(page); await page.getByRole('button', { name: 'Companion', exact: true }).click();
  await expect(chat(page)).toBeVisible();
  await expect(page.locator('.yt-player')).toHaveCount(0);
  await openPlayer(page, mobile);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-status', 'ready');
  if (mobile) await page.getByRole('button', { name: 'Ẩn Player', exact: true }).click();
  await page.getByRole('button', { name: 'Cài đặt Companion', exact: true }).click();
  await expect(page).toHaveURL(/\/companion\/settings/);
  await expect(page.locator('.yt-player iframe')).toHaveCount(0);
  await page.getByRole('button', { name: 'Quay lại Companion', exact: true }).click();
  await expect(chat(page)).toBeVisible(); await openPlayer(page, mobile);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-status', 'ready');
  if (mobile) await page.getByRole('button', { name: 'Ẩn Player', exact: true }).click();
  await openSidebar(page); await page.locator('.account').click();
  await page.getByRole('menuitem', { name: 'Đăng xuất', exact: true }).click();
  await expect(page.locator('.yt-player iframe')).toHaveCount(0);
  await expect(chat(page)).toHaveCount(0);
  const result = await stats(page);
  expect(result.destroyed).toBe(result.created);
});

test('Companion thật: micro Giữ để nói nhường Space cho Player và nhận lại khi bấm ra ngoài', async ({ page }, info) => {
  test.skip(info.project.name !== 'pc', 'Kiểm tra phím Space của desktop.');
  await mockPeto(page); await installApi(page);
  await page.addInitScript(() => {
    localStorage.setItem('peto-hearing-mode', 'hold');
    const getUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    const tracks: MediaStreamTrack[] = [];
    navigator.mediaDevices.getUserMedia = async constraints => {
      const stream = await getUserMedia(constraints); tracks.push(...stream.getTracks()); return stream;
    };
    Object.assign(window, { liveTracks: () => tracks.filter(track => track.readyState === 'live').length });
    class Recognition {
      onstart: (() => void) | null = null;
      onend: (() => void) | null = null;
      start() { setTimeout(() => this.onstart?.(), 10); }
      stop() { setTimeout(() => this.onend?.(), 10); }
      abort() {}
    }
    Object.assign(window, { SpeechRecognition: Recognition });
  });
  await page.goto('/companion'); await expect(chat(page)).toBeVisible();
  await page.getByRole('button', { name: 'Bật Giữ để nói', exact: true }).click();
  await expect(page.locator('.hearing-mic')).toHaveClass(/ready/);
  await openPlayer(page, false); await chooseVideo(page);
  await page.locator('.yt-window-head > strong').click();
  await page.keyboard.press('Space');
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'true');
  await expect(page.locator('.hearing-mic')).toHaveClass(/ready/);
  await page.frameLocator('.yt-player iframe').getByRole('button', { name: 'Phát trong YouTube giả' }).focus();
  await page.keyboard.press('Space');
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'false');
  expect((await stats(page)).nativeSpace).toBe(1);
  await expect(page.locator('.hearing-mic')).toHaveClass(/ready/);
  await page.locator('.companion-stage').click({ position: { x: 25, y: 700 } });
  await page.keyboard.down('Space');
  await expect(page.locator('.hearing-mic')).toHaveClass(/holding/);
  await expect.poll(() => page.evaluate(() => (window as unknown as { liveTracks(): number }).liveTracks())).toBeGreaterThan(0);
  // Chọn Player khi còn giữ phải bỏ lượt thu; thả phím sau đó không gửi câu nghe nhầm.
  await page.locator('.yt-window-head > strong').click();
  await expect(page.locator('.hearing-mic')).toHaveClass(/ready/);
  await page.keyboard.up('Space');
  await expect(page.locator('.hearing-mic')).toHaveClass(/ready/);
  await expect.poll(() => page.evaluate(() => (window as unknown as { liveTracks(): number }).liveTracks())).toBe(0);
  await chat(page).fill('xin chào');
  await chat(page).press('End'); await page.keyboard.press('Space');
  await expect(chat(page)).toHaveValue('xin chào ');
  await expect(page.locator('.hearing-mic')).toHaveClass(/ready/);
});

test('Companion thật: renderer Live2D và tiếng đọc thật tiếp tục khi mở/đóng Player', async ({ page }, info) => {
  test.setTimeout(60000);
  await mockPeto(page); await installApi(page);
  await page.route('**/characters/Live2DStage.tsx*', route => route.continue());
  await page.addInitScript(() => {
    localStorage.setItem('peto-local-voice', '1'); localStorage.setItem('peto-companion-muted', '0');
    const play = HTMLMediaElement.prototype.play;
    const audio: HTMLMediaElement[] = [];
    HTMLMediaElement.prototype.play = function () { audio.push(this); return play.call(this); };
    Object.assign(window, { playerSpeech: audio });
  });
  await page.route('**/api/voice/health', route => route.fulfill({ json: {
    ok: true, voices: ['stepfun:jilingshaonv'], home: { online: false, voices: [] },
    official: { allowed: true, voices: ['stepfun:jilingshaonv'], used: 0, limit: 5000 },
  } }));
  // PCM tổng hợp để chạy Audio/nhép miệng thật; không gọi dịch vụ tạo giọng hay dùng tiếng riêng tư.
  const rate = 16000, seconds = 30, wave = Buffer.alloc(44 + rate * seconds * 2);
  wave.write('RIFF', 0); wave.writeUInt32LE(wave.length - 8, 4); wave.write('WAVEfmt ', 8);
  wave.writeUInt32LE(16, 16); wave.writeUInt16LE(1, 20); wave.writeUInt16LE(1, 22);
  wave.writeUInt32LE(rate, 24); wave.writeUInt32LE(rate * 2, 28); wave.writeUInt16LE(2, 32); wave.writeUInt16LE(16, 34);
  wave.write('data', 36); wave.writeUInt32LE(wave.length - 44, 40);
  for (let index = 0; index < rate * seconds; index++) wave.writeInt16LE(Math.round(Math.sin(index * 2 * Math.PI * 220 / rate) * 2000), 44 + index * 2);
  await page.route('**/api/voice/speak', route => route.fulfill({ contentType: 'audio/wav', body: wave }));
  const mobile = info.project.name === 'mobile';
  await page.goto('/companion'); await expect(chat(page)).toBeVisible({ timeout: 30000 });
  const canvas = await page.locator('.character-canvas canvas').elementHandle();
  expect(canvas).not.toBeNull();
  await openPlayer(page, mobile); await chooseVideo(page);
  await page.getByRole('button', { name: 'Phát video', exact: true }).click();
  if (mobile) await page.getByRole('button', { name: 'Ẩn Player', exact: true }).click();
  await chat(page).fill('Hello while the video is playing');
  await page.locator('.companion-panel').getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect(page.locator('.companion-title')).toContainText('Đang nói');
  const audioState = () => page.evaluate(() => {
    const audio = (window as unknown as { playerSpeech: HTMLMediaElement[] }).playerSpeech.at(-1);
    return { paused: audio?.paused, time: audio?.currentTime ?? 0 };
  });
  await expect.poll(async () => (await audioState()).time).toBeGreaterThan(0);
  if (mobile) await openPlayer(page, true);
  await expect(page.locator('.yt-player')).toHaveAttribute('data-playing', 'true');
  expect((await audioState()).paused).toBe(false);
  await page.getByRole('button', { name: mobile ? 'Dừng và đóng Player' : 'Đóng Player', exact: true }).click();
  await expect(page.locator('.yt-player iframe')).toHaveCount(0);
  expect((await audioState()).paused).toBe(false);
  expect(await canvas!.evaluate(node => node.isConnected)).toBe(true);
  await noPageOverflow(page);
  await page.screenshot({ path: info.outputPath('live2d-after-player.png') });
  await page.locator('.companion-panel').getByRole('button', { name: 'Dừng', exact: true }).click();
});
