import { StrictMode } from 'react';
import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useYouTubePlayer } from '../src/features/companion/ytplayer/useYouTubePlayer';
import type { YouTubeOptions } from '../src/features/companion/ytplayer/youtubeApi';
import { parseYouTubeUrl, youtubeSourceKey, type YouTubePlaybackSource } from '../src/features/companion/ytplayer/youtubeUrl';

const load = vi.hoisted(() => vi.fn());
vi.mock('../src/features/companion/ytplayer/youtubeApi', () => ({ loadYouTubeApi: load }));
const players: FakePlayer[] = [];
class FakePlayer {
  options: YouTubeOptions;
  iframe = document.createElement('iframe');
  time = 0; duration = 240; volume = 60; muted = false;
  constructor(element: HTMLElement, options: YouTubeOptions) { this.options = options; element.replaceWith(this.iframe); players.push(this); }
  cueVideoById = vi.fn((source: { startSeconds: number }) => { this.time = source.startSeconds; this.state(5); });
  loadVideoById = vi.fn((source: { startSeconds: number }) => { this.time = source.startSeconds; this.state(1); });
  playVideo = vi.fn(() => this.state(1));
  pauseVideo = vi.fn(() => this.state(2));
  stopVideo = vi.fn();
  seekTo = vi.fn((time: number) => { this.time = time; });
  setVolume = vi.fn((volume: number) => { this.volume = volume; });
  getVolume = () => this.volume;
  mute = vi.fn(() => { this.muted = true; });
  unMute = vi.fn(() => { this.muted = false; });
  isMuted = () => this.muted;
  getCurrentTime = () => this.time;
  getDuration = () => this.duration;
  getIframe = () => this.iframe;
  destroy = vi.fn(() => this.iframe.remove());
  state(data: number) { this.options.events.onStateChange({ target: this, data }); }
  ready() { this.options.events.onReady({ target: this }); }
}
let player: ReturnType<typeof useYouTubePlayer>;
const first = parseYouTubeUrl('https://youtu.be/Soy4jGPHr3g')!;
const second = parseYouTubeUrl('https://youtu.be/aircAruvnKk?t=20')!;
function Harness({ source = first, enabled = true, background = false }: { source?: YouTubePlaybackSource | null; enabled?: boolean; background?: boolean }) {
  player = useYouTubePlayer(source, enabled, background);
  return <div ref={player.container} />;
}
async function mount() {
  const view = render(<StrictMode><Harness /></StrictMode>);
  await act(async () => {});
  act(() => players[0].ready());
  return view;
}
beforeEach(() => {
  vi.useFakeTimers(); players.length = 0;
  Object.defineProperty(document, 'hidden', { configurable: true, value: false });
  load.mockReset().mockResolvedValue({ Player: FakePlayer });
});
afterEach(() => { vi.useRealTimers(); delete (document as unknown as Record<string, unknown>).hidden; });

it('chưa có link thì không tải API; nhập link mới tạo player, bỏ nguồn thì giải phóng', async () => {
  const view = render(<StrictMode><Harness source={null} /></StrictMode>);
  await act(async () => {});
  expect(load).not.toHaveBeenCalled();
  expect(players).toHaveLength(0);
  view.rerender(<StrictMode><Harness source={first} /></StrictMode>);
  await act(async () => {});
  act(() => players[0].ready());
  expect(players).toHaveLength(1);
  expect(players[0].playVideo).not.toHaveBeenCalled();
  view.rerender(<StrictMode><Harness source={null} /></StrictMode>);
  expect(players[0].destroy).toHaveBeenCalledOnce();
  expect(document.querySelector('iframe')).toBeNull();
  expect(player.ready).toBe(false);
});

it('Strict Mode tạo một player, cue không tự phát và đổi video không tạo iframe mới', async () => {
  const view = await mount();
  expect(players).toHaveLength(1);
  const instance = players[0];
  expect(instance.playVideo).not.toHaveBeenCalled();
  expect(instance.options.playerVars).toMatchObject({ autoplay: 0, controls: 1, playsinline: 1, origin: location.origin });
  const iframe = document.querySelector('iframe');
  view.rerender(<StrictMode><Harness source={second} /></StrictMode>);
  expect(players).toHaveLength(1);
  expect(document.querySelector('iframe')).toBe(iframe);
  expect(instance.cueVideoById).toHaveBeenLastCalledWith({ videoId: second.videoId, startSeconds: 20 });
  expect(player.playing).toBe(false);
  view.unmount();
  expect(instance.destroy).toHaveBeenCalledTimes(1);
});
it('yêu cầu phát tiếp dùng loadVideoById trong cùng iframe, lặp cùng video vẫn nhận một yêu cầu mới', async () => {
  const view = await mount(), instance = players[0], iframe = document.querySelector('iframe');
  const queued = { ...second, playbackId: '2', autoplay: true };
  view.rerender(<StrictMode><Harness source={queued} /></StrictMode>);
  expect(instance.loadVideoById).toHaveBeenCalledExactlyOnceWith({ videoId: second.videoId, startSeconds: 20 });
  expect(player.playing).toBe(true); expect(player.sourceKey).toBe(youtubeSourceKey(queued));
  act(() => instance.state(0)); const serial = player.endedSerial;
  view.rerender(<StrictMode><Harness source={{ ...queued, playbackId: '3' }} /></StrictMode>);
  expect(instance.loadVideoById).toHaveBeenCalledTimes(2); expect(player.endedSerial).toBe(serial);
  expect(document.querySelector('iframe')).toBe(iframe);
});
it('chọn bài yêu thích trước lúc ready phát một lần, suspend rồi quay lại không tự phát lại', async () => {
  const source = { ...first, playbackId: '1', autoplay: true };
  const view = render(<StrictMode><Harness source={source} /></StrictMode>);
  await act(async () => {}); act(() => players[0].ready());
  expect(players[0].playVideo).toHaveBeenCalledOnce();
  view.rerender(<StrictMode><Harness source={source} enabled={false} /></StrictMode>);
  view.rerender(<StrictMode><Harness source={source} enabled /></StrictMode>);
  await act(async () => {}); act(() => players[1].ready());
  expect(players[1].playVideo).not.toHaveBeenCalled(); expect(player.playing).toBe(false);
});
it('load bài mới bị chặn báo blocked hữu hạn, không lặp lại autoplay hoặc bị timeout ghi đè', async () => {
  const view = await mount(), instance = players[0];
  instance.loadVideoById.mockImplementation(() => instance.options.events.onAutoplayBlocked());
  view.rerender(<StrictMode><Harness source={{ ...second, playbackId: '2', autoplay: true }} /></StrictMode>);
  expect(player.status).toBe('blocked'); expect(player.ready).toBe(true);
  await act(async () => { await vi.advanceTimersByTimeAsync(25000); });
  expect(player.status).toBe('blocked'); expect(instance.loadVideoById).toHaveBeenCalledOnce();
  act(() => player.setPlaying(true)); expect(player.playing).toBe(true);
});
it('phát, seek, volume và controls native đều đồng bộ qua API', async () => {
  await mount();
  act(() => player.setPlaying(true));
  expect(player.playing).toBe(true);
  act(() => { player.seek(42); player.setVolume(35); });
  await act(async () => { await vi.advanceTimersByTimeAsync(500); });
  expect(player.position).toBe(42);
  expect(player.volume).toBe(35);
  expect(players[0].seekTo).toHaveBeenCalledWith(42, true);
  players[0].volume = 22; players[0].muted = true;
  await act(async () => { await vi.advanceTimersByTimeAsync(500); });
  expect(player.volume).toBe(0);
  act(() => player.setVolume(80));
  expect(players[0].unMute).toHaveBeenCalled();
  act(() => players[0].state(2));
  expect(player.playing).toBe(false);
});
it('lần Phát đầu không bị cue ban đầu hoàn thành muộn đẩy về trạng thái dừng', async () => {
  class SlowCuePlayer extends FakePlayer {
    cueVideoById = vi.fn((source: { startSeconds: number }) => {
      setTimeout(() => { this.time = source.startSeconds; this.state(5); }, 500);
    });
  }
  load.mockResolvedValue({ Player: SlowCuePlayer });
  await mount();
  act(() => player.setPlaying(true));
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(player.playing).toBe(true);
  expect(players[0].cueVideoById).not.toHaveBeenCalled();
});
it('đổi nguồn trước onReady vẫn cue nguồn mới, không tạo thêm iframe', async () => {
  const view = render(<StrictMode><Harness /></StrictMode>);
  await act(async () => {});
  view.rerender(<StrictMode><Harness source={second} /></StrictMode>);
  act(() => players[0].ready());
  expect(players).toHaveLength(1);
  expect(players[0].cueVideoById).toHaveBeenCalledExactlyOnceWith({ videoId: second.videoId, startSeconds: 20 });
  expect(player.ready).toBe(true);
  expect(player.position).toBe(20);
  expect(players[0].playVideo).not.toHaveBeenCalled();
});
it('đổi bài chờ YouTube xác nhận đã cue rồi mới nhận Phát, bỏ qua trạng thái trung gian', async () => {
  const view = await mount();
  const instance = players[0];
  instance.cueVideoById.mockImplementation(source => {
    instance.state(-1);
    setTimeout(() => { instance.time = source.startSeconds; instance.state(5); }, 500);
  });
  view.rerender(<StrictMode><Harness source={second} /></StrictMode>);
  expect(player.ready).toBe(false);
  expect(player.status).toBe('loading');
  act(() => player.setPlaying(true));
  expect(instance.playVideo).not.toHaveBeenCalled();
  act(() => player.setVolume(35));
  expect(instance.getVolume()).toBe(35);
  await act(async () => { await vi.advanceTimersByTimeAsync(500); });
  expect(player.ready).toBe(true);
  act(() => player.setPlaying(true));
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(player.playing).toBe(true);
  expect(player.position).toBe(20);
});
it('đổi bài mà không nhận được xác nhận cue có lỗi hữu hạn, không tự phát', async () => {
  const view = await mount();
  players[0].cueVideoById.mockImplementation(() => {});
  view.rerender(<StrictMode><Harness source={second} /></StrictMode>);
  await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
  expect(player.status).toBe('error');
  expect(player.error).toContain('quá lâu');
  expect(player.ready).toBe(false);
  expect(players[0].playVideo).not.toHaveBeenCalled();
});
it('tắt enabled khi host vẫn mounted hủy player và không nhận lệnh sau đó', async () => {
  const view = await mount();
  act(() => player.setPlaying(true));
  view.rerender(<StrictMode><Harness enabled={false} /></StrictMode>);
  expect(document.querySelector('iframe')).toBeNull();
  expect(players[0].stopVideo).toHaveBeenCalledTimes(1);
  expect(players[0].destroy).toHaveBeenCalledTimes(1);
  act(() => player.setPlaying(true));
  expect(players[0].playVideo).toHaveBeenCalledTimes(1);
  view.rerender(<StrictMode><Harness /></StrictMode>);
  await act(async () => {});
  act(() => players[1].ready());
  expect(player.playing).toBe(false);
  expect(players[1].playVideo).not.toHaveBeenCalled();
});
it('ẩn trang và pagehide giải phóng ngay, quay lại chỉ cue ở trạng thái dừng', async () => {
  await mount();
  act(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(players[0].destroy).toHaveBeenCalledTimes(1);
  expect(player.status).toBe('suspended');
  act(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await act(async () => {});
  act(() => players[1].ready());
  expect(players[1].playVideo).not.toHaveBeenCalled();
  act(() => window.dispatchEvent(new Event('pagehide')));
  expect(document.querySelector('iframe')).toBeNull();
  expect(players[1].destroy).toHaveBeenCalledTimes(1);
  act(() => window.dispatchEvent(new Event('pageshow')));
  await act(async () => {});
  expect(players).toHaveLength(3);
});
it('đóng trong lúc nạp API không cho callback muộn tạo player', async () => {
  let resolve!: (value: { Player: typeof FakePlayer }) => void;
  load.mockReturnValue(new Promise(done => { resolve = done; }));
  const view = render(<StrictMode><Harness /></StrictMode>);
  view.rerender(<StrictMode><Harness enabled={false} /></StrictMode>);
  await act(async () => { resolve({ Player: FakePlayer }); });
  expect(players).toHaveLength(0);
});
it('desktop giữ cùng player khi ẩn trang, vẫn đồng bộ; pagehide và unmount giải phóng', async () => {
  const view = render(<StrictMode><Harness background /></StrictMode>);
  await act(async () => {});
  act(() => { players[0].ready(); player.setPlaying(true); });
  const iframe = document.querySelector('iframe');
  act(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  players[0].time = 12;
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(player.position).toBe(12);
  expect(player.playing).toBe(true);
  expect(players[0].destroy).not.toHaveBeenCalled();
  expect(document.querySelector('iframe')).toBe(iframe);
  act(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(players).toHaveLength(1);
  act(() => window.dispatchEvent(new Event('pagehide')));
  expect(players[0].destroy).toHaveBeenCalledOnce();
  act(() => window.dispatchEvent(new Event('pageshow')));
  await act(async () => {});
  act(() => players[1].ready());
  expect(players[1].playVideo).not.toHaveBeenCalled();
  view.unmount();
  expect(players[1].destroy).toHaveBeenCalledOnce();
});
it.each(['disabled', 'foreground'])('desktop đang ẩn vẫn hủy player khi chuyển sang %s', async mode => {
  const view = render(<StrictMode><Harness background /></StrictMode>);
  await act(async () => {});
  act(() => players[0].ready());
  act(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  view.rerender(<StrictMode><Harness background={mode !== 'foreground'} enabled={mode !== 'disabled'} /></StrictMode>);
  expect(players[0].destroy).toHaveBeenCalledOnce();
  expect(document.querySelector('iframe')).toBeNull();
});
it.each([[100, 'riêng tư'], [101, 'không cho phép'], [150, 'không cho phép'], [153, 'nguồn nhúng'], [5, 'không phát được']])('báo lỗi %s và phục hồi khi đổi nguồn', async (code, message) => {
  const view = await mount();
  act(() => players[0].options.events.onError({ target: players[0], data: code as number }));
  expect(player.error).toContain(message);
  expect(player.ready).toBe(false);
  view.rerender(<StrictMode><Harness source={second} /></StrictMode>);
  expect(player.error).toBe('');
  expect(player.ready).toBe(true);
});
it('autoplay bị chặn không giả báo đang phát; phát native xóa hướng dẫn chặn', async () => {
  await mount();
  act(() => players[0].options.events.onAutoplayBlocked());
  expect(player.status).toBe('blocked');
  expect(player.playing).toBe(false);
  act(() => players[0].state(1));
  expect(player.playing).toBe(true);
  expect(player.error).toBe('');
});
it('lỗi không bị sự kiện paused ghi đè, phục hồi bằng controls native tiếp tục cập nhật tiến độ', async () => {
  await mount();
  act(() => players[0].options.events.onError({ target: players[0], data: 5 }));
  act(() => players[0].state(2));
  expect(player.status).toBe('error');
  act(() => players[0].state(1));
  players[0].time = 12;
  await act(async () => { await vi.advanceTimersByTimeAsync(500); });
  expect(player.position).toBe(12);
  expect(player.ready).toBe(true);
  expect(player.error).toBe('');
});
it('API lỗi và player không ready đều có lỗi hữu hạn, thử lại không nhân đôi iframe', async () => {
  load.mockRejectedValueOnce(new Error('Không tải được API'));
  // Không dùng Strict Mode ở nhánh này để lần gọi đầu mô phỏng đúng lỗi tải chung.
  render(<Harness />);
  await act(async () => {});
  expect(player.error).toContain('Không tải được');
  act(() => player.retry());
  await act(async () => {});
  expect(document.querySelectorAll('iframe')).toHaveLength(1);
  await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
  expect(player.error).toContain('quá lâu');
  expect(document.querySelector('iframe')).toBeNull();
  act(() => player.retry());
  await act(async () => {});
  act(() => players[1].ready());
  expect(player.ready).toBe(true);
  expect(document.querySelectorAll('iframe')).toHaveLength(1);
});
