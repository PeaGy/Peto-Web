import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';
import { installApi, stats, type FakeStats } from './youtubeFixture';
import type { PlayerCommand, PlayerResult } from '../src/features/companion/ytplayer/playerControl';

const shell = (page: Page) => page.locator('#companion-player');
const composer = (page: Page) => page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion', exact: true });
async function setup(page: Page, mobile: boolean) {
  await mockPeto(page); const apiRequests = await installApi(page);
  let sequence = 0;
  let command: PlayerCommand;
  let duplicate = false;
  const results: PlayerResult[] = [];
  await page.route('**/api/companion/player/commands/*/result', async route => {
    results.push(route.request().postDataJSON());
    await route.fulfill({ json: { accepted: true } });
  });
  await page.route('**/api/chat', async route => {
    expect(route.request().postDataJSON().player_control).toBe(1);
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    await route.fulfill({ contentType: 'text/event-stream', body:
      event({ type: 'meta', conversation_id: 'A', effort: 'low' })
      + event({ type: 'player_command', command }) + (duplicate ? event({ type: 'player_command', command }) : '')
      + event({ type: 'delta', text: 'Đã nhận kết quả Player.' }) + event({ type: 'done' }) });
  });
  await page.goto('/companion'); await expect(composer(page)).toBeVisible({ timeout: 20000 });
  async function hide() {
    if (await shell(page).isVisible()) await page.getByRole('button', { name: mobile ? 'Ẩn Player' : 'Thu nhỏ Player', exact: true }).click();
  }
  async function issue(action: PlayerCommand['action'], values: Partial<PlayerCommand> = {}, twice = false) {
    await hide();
    duplicate = twice; command = { id: `command-${++sequence}`, action, expires_at: Date.now() + 12000, ...values };
    const before = results.length;
    await composer(page).fill(`Control ${action} ${sequence}`);
    await page.getByRole('button', { name: 'Gửi', exact: true }).click();
    await expect.poll(() => results.length).toBe(before + (twice ? 2 : 1));
    await expect(page.locator('.companion-panel button[type="submit"]')).toHaveCount(1);
    return results.at(-1)!;
  }
  return { issue, hide, apiRequests };
}

test('chat controls the existing hidden player, acknowledges native state and deduplicates Next', async ({ page }, info) => {
  test.setTimeout(90000);
  const mobile = info.project.name === 'mobile';
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  const { issue, hide, apiRequests } = await setup(page, mobile);
  const empty = await issue('status');
  expect(empty.state?.status).toBe('empty'); expect(apiRequests()).toBe(0);
  expect((await issue('play')).ok).toBe(false);
  expect((await issue('open')).state?.window).toBe('visible');
  await page.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).fill('https://youtube.com/watch?v=Soy4jGPHr3g');
  await page.getByRole('button', { name: 'Tìm hoặc mở', exact: true }).click();
  await expect(shell(page)).toHaveAttribute('data-status', 'ready');
  await shell(page).getByRole('button', { name: mobile ? 'Tùy chọn Player' : 'File', exact: true }).click();
  const file = page.getByRole('region', { name: 'Bảng File', exact: true });
  await file.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).fill('https://youtube.com/watch?v=e1xCOsgWG0M');
  await file.getByRole('button', { name: 'Thêm vào hàng đợi', exact: true }).click();
  await hide();
  expect((await issue('status')).state).toMatchObject({ window: 'hidden', track: { title: 'Tetris' }, queue_count: 1 });
  expect((await issue('play')).state?.status).toBe('playing');
  expect((await issue('set_volume', { volume: 30 })).state?.volume).toBe(30);
  expect((await issue('mute')).state?.volume).toBe(0);
  expect((await issue('unmute')).state?.volume).toBe(30);
  expect((await issue('seek', { seconds: 45 })).state?.position).toBe(45);
  expect((await issue('set_shuffle', { enabled: true })).state?.shuffle).toBe(true);
  expect((await issue('set_shuffle', { enabled: true })).state?.shuffle).toBe(true);
  expect((await issue('set_repeat', { repeat: 'one' })).state?.repeat).toBe('one');
  const before = (await stats(page)).cues.length;
  expect((await issue('next', {}, true)).state?.track?.title).toBe('The Vampire');
  expect((await stats(page)).cues.length).toBe(before + 1);
  expect((await issue('restart')).state?.status).toBe('playing');
  expect((await issue('pause')).state?.status).toBe('paused');
  expect((await stats(page)).created).toBe(1); expect(apiRequests()).toBe(1);
  expect((await issue('hide')).state?.window).toBe('hidden');
  expect((await issue('close')).state?.window).toBe('closed');
  await expect(page.locator('.yt-youtube-container iframe')).toHaveCount(0);
  expect((await issue('status')).state?.status).toBe('suspended');
  expect((await issue('open')).state?.window).toBe('visible');
  await expect(shell(page)).toHaveAttribute('data-status', 'ready');
  await expect(shell(page)).toHaveAttribute('data-playing', 'false');
  await noPageOverflow(page); expect(errors).toEqual([]);
});

test('blocked/error and expired commands cannot claim playback success', async ({ page }, info) => {
  const mobile = info.project.name === 'mobile';
  const { issue } = await setup(page, mobile);
  await issue('open');
  await page.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).fill('https://youtube.com/watch?v=Soy4jGPHr3g');
  await page.getByRole('button', { name: 'Tìm hoặc mở', exact: true }).click();
  await expect(shell(page)).toHaveAttribute('data-status', 'ready');
  await page.evaluate(() => { (window as unknown as { __ytFake: FakeStats }).__ytFake.blocked = true; });
  const blocked = await issue('play'); expect(blocked.ok).toBe(false); expect(blocked.error).toContain('chặn');
  await page.evaluate(() => (window as unknown as { __ytFake: FakeStats }).__ytFake.fail(150));
  const failed = await issue('play'); expect(failed.ok).toBe(false); expect(failed.error).toContain('150');
  const expired = await issue('next', { expires_at: Date.now() - 1 }); expect(expired.ok).toBe(false); expect(expired.error).toContain('hết hạn');
  expect((await stats(page)).cues).toHaveLength(0);
  await issue('open');
  await shell(page).getByRole('button', { name: mobile ? 'Tùy chọn Player' : 'File', exact: true }).click();
  const file = page.getByRole('region', { name: 'Bảng File', exact: true });
  await file.getByRole('textbox', { name: 'Link hoặc tên video', exact: true }).fill('https://youtube.com/watch?v=e1xCOsgWG0M');
  await file.getByRole('button', { name: 'Thêm vào hàng đợi', exact: true }).click();
  await page.evaluate(() => { (window as unknown as { __ytFake: FakeStats }).__ytFake.blocked = false; });
  const skip = await issue('next');
  expect(skip.ok).toBe(true); expect(skip.state?.track?.title).toBe('The Vampire');
  expect(skip.state?.status).toBe('playing');
});
