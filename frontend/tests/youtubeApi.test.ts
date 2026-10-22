import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { YouTubeApi } from '../src/features/companion/ytplayer/youtubeApi';

beforeEach(() => { vi.resetModules(); vi.useFakeTimers(); delete window.YT; delete window.onYouTubeIframeAPIReady; });
afterEach(() => { document.querySelectorAll('#peto-youtube-iframe-api').forEach(node => node.remove()); delete window.YT; delete window.onYouTubeIframeAPIReady; vi.useRealTimers(); });
const api = { Player: vi.fn() } as unknown as YouTubeApi;

it('nạp một script cho các lần gọi đồng thời, giữ callback có trước', async () => {
  const previous = vi.fn();
  window.onYouTubeIframeAPIReady = previous;
  const { loadYouTubeApi } = await import('../src/features/companion/ytplayer/youtubeApi');
  const first = loadYouTubeApi(), second = loadYouTubeApi();
  expect(second).toBe(first);
  expect(document.querySelectorAll('#peto-youtube-iframe-api')).toHaveLength(1);
  window.YT = api;
  window.onYouTubeIframeAPIReady?.();
  expect(await first).toBe(api);
  expect(previous).toHaveBeenCalledTimes(1);
  expect(window.onYouTubeIframeAPIReady).toBe(previous);
  expect(await loadYouTubeApi()).toBe(api);
});
it('dùng API có sẵn mà không thêm script', async () => {
  window.YT = api;
  const { loadYouTubeApi } = await import('../src/features/companion/ytplayer/youtubeApi');
  expect(await loadYouTubeApi()).toBe(api);
  expect(document.querySelector('#peto-youtube-iframe-api')).toBeNull();
});
it('lỗi mạng xóa script lỗi và cho phép nạp lại', async () => {
  const { loadYouTubeApi } = await import('../src/features/companion/ytplayer/youtubeApi');
  const first = loadYouTubeApi();
  const failed = expect(first).rejects.toThrow('Không tải được');
  document.querySelector('#peto-youtube-iframe-api')!.dispatchEvent(new Event('error'));
  await failed;
  expect(document.querySelector('#peto-youtube-iframe-api')).toBeNull();
  const retry = loadYouTubeApi();
  window.YT = api; window.onYouTubeIframeAPIReady?.();
  expect(await retry).toBe(api);
});
it('hết giờ kể cả script đã load nhưng callback chưa sẵn sàng', async () => {
  const { loadYouTubeApi } = await import('../src/features/companion/ytplayer/youtubeApi');
  const request = loadYouTubeApi();
  const failed = expect(request).rejects.toThrow('Không tải được');
  document.querySelector('#peto-youtube-iframe-api')!.dispatchEvent(new Event('load'));
  await vi.advanceTimersByTimeAsync(15000);
  await failed;
  expect(document.querySelector('#peto-youtube-iframe-api')).toBeNull();
  expect(window.onYouTubeIframeAPIReady).toBeUndefined();
});
