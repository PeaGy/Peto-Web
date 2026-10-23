import { StrictMode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { usePlayerLibrary } from '../src/features/companion/ytplayer/usePlayerLibrary';
import { mediaFromId } from '../src/features/companion/ytplayer/playerApi';

const api = vi.hoisted(() => ({ list: vi.fn(), save: vi.fn(), info: vi.fn() }));
vi.mock('../src/features/companion/ytplayer/playerApi', async original => ({ ...(await original<object>()),
  listFavorites: api.list, saveFavorite: api.save, getVideoInfo: api.info,
}));
const saved = mediaFromId('Soy4jGPHr3g', 'Tetris', 'Kasane Teto SV');
beforeEach(() => { vi.clearAllMocks(); api.list.mockResolvedValue([]); api.save.mockResolvedValue([saved]); api.info.mockResolvedValue({ video_id: saved.videoId, title: saved.title, artist: saved.artist }); });

it('loads account favorites and saves only after server confirmation; rapid duplicate clicks issue one request', async () => {
  const view = renderHook(() => usePlayerLibrary(), { wrapper: StrictMode });
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  act(() => view.result.current.openLink(saved.url));
  let finish!: (value: typeof saved[]) => void;
  api.save.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  act(() => { void view.result.current.toggleFavorite(); void view.result.current.toggleFavorite(); });
  expect(api.save).toHaveBeenCalledOnce(); expect(view.result.current.favorite).toBe(false);
  await act(async () => { finish([saved]); });
  expect(view.result.current.favorite).toBe(true); expect(view.result.current.favoritesBusy).toBe(false);
});
it('save failure keeps the existing favorites, allows retry, and invalid URL never requests metadata', async () => {
  api.list.mockResolvedValue([saved]); api.save.mockRejectedValueOnce(new Error('Lỗi lưu thử'));
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  let error: string | undefined;
  act(() => { error = view.result.current.openLink('https://youtube.com.evil.example/watch?v=Soy4jGPHr3g'); });
  expect(error).toContain('chưa hợp lệ'); expect(api.info).not.toHaveBeenCalled();
  act(() => view.result.current.select(saved));
  await act(async () => { await view.result.current.toggleFavorite(); });
  expect(view.result.current.favorite).toBe(true); expect(view.result.current.error).toBe('Lỗi lưu thử');
  api.save.mockResolvedValue([]);
  await act(async () => { await view.result.current.toggleFavorite(); });
  expect(view.result.current.favorite).toBe(false); expect(view.result.current.error).toBe('');
});
it('unmount aborts account requests and a late response cannot leak favorites into the next instance', async () => {
  let finish!: (value: typeof saved[]) => void;
  api.list.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  const first = renderHook(() => usePlayerLibrary());
  const signal = api.list.mock.calls[0][0] as AbortSignal;
  first.unmount(); expect(signal.aborted).toBe(true);
  const second = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(second.result.current.loadingFavorites).toBe(false));
  await act(async () => { finish([saved]); });
  expect(second.result.current.favorites).toEqual([]); expect(second.result.current.track).toBeNull();
});
