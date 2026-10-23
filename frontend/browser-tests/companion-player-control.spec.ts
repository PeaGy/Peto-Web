import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';
import { installApi, stats, type FakeStats } from './youtubeFixture';
import type { PlayerCommand, PlayerResult } from '../src/features/companion/ytplayer/playerControl';

const shell = (page: Page) => page.locator('#companion-player');
const composer = (page: Page) => page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion', exact: true });
async function setup(page: Page, mobile: boolean, favorites: { video_id: string; title: string; artist: string }[] = []) {
  const state = await mockPeto(page); const apiRequests = await installApi(page);
  favorites.forEach(item => state.playerFavorites.set(item.video_id, item));
  let sequence = 0;
  let command: PlayerCommand;
  let duplicate = false;
  const results: PlayerResult[] = [];
  await page.route('**/api/companion/player/commands/*/result', async route => {
    results.push(route.request().postDataJSON());
    await route.fulfill({ json: { accepted: true } });
  });
  await page.route('**/api/chat', async route => {
    expect(route.request().postDataJSON().player_control).toBe(2);
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
    await expect.poll(() => results.length, { timeout: 12000 }).toBe(before + (twice ? 2 : 1));
    await expect(page.locator('.companion-panel button[type="submit"]')).toHaveCount(1);
    return results.at(-1)!;
  }
  return { issue, hide, apiRequests, state };
}

const favorites = [
  { video_id: 'Soy4jGPHr3g', title: 'Tetris', artist: 'Kasane Teto SV' },
  { video_id: 'e1xCOsgWG0M', title: 'The Vampire', artist: 'Test channel' },
  { video_id: 'aircAruvnKk', title: 'But what is a neural network?', artist: 'Test channel' },
  { video_id: 'HDz9dSuAI4s', title: 'Miku concert', artist: 'Test channel' },
];

test('library chat reads fresh favorites without opening, edits stable queue entries and reports actual loop/shuffle next', async ({ page }, info) => {
  test.setTimeout(90000);
  const { issue, apiRequests, state } = await setup(page, info.project.name === 'mobile', favorites);
  const count = await issue('list_favorites', { limit: 0 });
  expect(count).toMatchObject({ ok: true, state: { window: 'closed' }, data: { total: 4, items: [] } });
  const first = await issue('list_favorites', { limit: 2 });
  expect(first.data?.items).toHaveLength(2); expect(first.data?.next_offset).toBe(2);
  const tail = await issue('list_favorites', { offset: 2, limit: 2 });
  expect(tail.data?.items?.[0].index).toBe(3); expect(tail.data?.next_offset).toBeNull();
  expect((await issue('enqueue_favorites', {}, true)).data).toMatchObject({ added: 4, skipped_duplicates: 0, not_added_capacity: 0 });
  expect((await issue('enqueue_favorites')).data).toMatchObject({ added: 0, skipped_duplicates: 4 });
  expect(apiRequests()).toBe(0); await expect(shell(page)).toHaveCount(0);
  let queue = await issue('list_queue');
  expect(queue.data?.items?.map(item => item.index)).toEqual([1, 2, 3, 4]);
  const target = queue.data!.items![0];
  const played = await issue('play_queue_entry', { entry_id: target.entry_id, queue_revision: queue.data!.queue_revision });
  expect(played.ok).toBe(true); expect(played.state?.track?.video_id).toBe(target.video_id); expect(played.state?.status).toBe('playing');
  const playing = played.state!.track!.video_id;
  expect((await issue('set_favorite', { enabled: false })).data?.favorite).toBe(false);
  expect(state.playerFavorites.has(playing)).toBe(false);
  for (let i = 0; i < 2; i++) expect((await issue('set_favorite', { enabled: true })).data?.favorite).toBe(true);
  expect(state.playerFavorites.size).toBe(4);
  queue = await issue('list_queue');
  await issue('set_shuffle', { enabled: true });
  const stale = await issue('remove_queue_entry', { entry_id: queue.data!.items![2].entry_id, queue_revision: queue.data!.queue_revision });
  expect(stale.ok).toBe(false); expect(stale.state?.queue_count).toBe(3);
  queue = await issue('list_queue');
  const third = queue.data!.items![2];
  expect((await issue('remove_queue_entry', { entry_id: third.entry_id, queue_revision: queue.data!.queue_revision })).data?.target?.video_id).toBe(third.video_id);
  const remaining = await issue('list_queue'); expect(remaining.data?.total).toBe(2);
  const moved = remaining.data!.items![1];
  const reorder = await issue('move_queue_entry', { entry_id: moved.entry_id, queue_revision: remaining.data!.queue_revision, position: 1 });
  expect(reorder.ok).toBe(true); expect(reorder.state?.shuffle).toBe(false);
  await issue('set_repeat', { repeat: 'one' });
  const loop = await issue('next_track');
  expect(loop.data?.automatic?.video_id).toBe(playing); expect(loop.data?.on_skip?.video_id).toBe(moved.video_id);
  await issue('set_repeat', { repeat: 'all' }); await issue('set_shuffle', { enabled: true });
  for (let i = 0; i < 6; i++) {
    const next = await issue('next_track'); const before = (await stats(page)).cues.length;
    await page.evaluate(() => (window as unknown as { __ytFake: FakeStats }).__ytFake.end());
    await expect.poll(async () => (await stats(page)).cues.length).toBe(before + 1);
    expect((await issue('status')).state?.track?.video_id).toBe(next.data?.automatic?.video_id);
  }
  expect((await stats(page)).created).toBe(1); expect(apiRequests()).toBe(1);
});

test('favorites failure stays a failure; 500-item bulk reports partial capacity without playback or per-item lookups', async ({ page }, info) => {
  test.setTimeout(60000);
  let metadata = 0; page.on('request', request => { if (request.url().includes('/player/videos/')) metadata++; });
  const items = Array.from({ length: 500 }, (_, i) => ({ video_id: `video${String(i).padStart(6, '0')}`, title: `Favorite ${i}`, artist: 'Account' }));
  const { issue, apiRequests } = await setup(page, info.project.name === 'mobile', items);
  await page.route('**/api/companion/player/favorites', route => route.fulfill({ status: 503, json: { detail: 'Offline favorites' } }));
  const error = await issue('list_favorites'); expect(error.ok).toBe(false); expect(error.error).toContain('Offline');
  expect(error.data?.total).toBeUndefined();
  await page.unroute('**/api/companion/player/favorites');
  expect((await issue('list_favorites', { limit: 0 })).data?.total).toBe(500);
  const added = await issue('enqueue_favorites');
  expect(added.data).toMatchObject({ added: 200, skipped_duplicates: 0, not_added_capacity: 300 });
  expect(added.state).toMatchObject({ window: 'closed', status: 'empty', queue_count: 200 });
  const full = await issue('enqueue_favorites');
  expect(full.data).toMatchObject({ added: 0, skipped_duplicates: 200, not_added_capacity: 300 });
  expect(apiRequests()).toBe(0); expect(metadata).toBe(0); await expect(shell(page)).toHaveCount(0);
});

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
