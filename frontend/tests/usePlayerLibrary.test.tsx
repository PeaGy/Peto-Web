import { StrictMode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { usePlayerLibrary } from '../src/features/companion/ytplayer/usePlayerLibrary';
import { mediaFromId } from '../src/features/companion/ytplayer/playerApi';

const api = vi.hoisted(() => ({ list: vi.fn(), save: vi.fn(), info: vi.fn(), search: vi.fn(), playlist: vi.fn() }));
vi.mock('../src/features/companion/ytplayer/playerApi', async original => ({ ...(await original<object>()),
  listFavorites: api.list, saveFavorite: api.save, getVideoInfo: api.info,
  searchVideos: api.search, getPlaylist: api.playlist,
}));
const saved = mediaFromId('Soy4jGPHr3g', 'Tetris', 'Kasane Teto SV');
beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); api.list.mockResolvedValue([]); api.save.mockResolvedValue([saved]); api.info.mockResolvedValue({ video_id: saved.videoId, title: saved.title, artist: saved.artist });
  api.search.mockResolvedValue({ tracks: [saved], nextPageToken: '' }); api.playlist.mockResolvedValue({ tracks: [saved], skipped: 0, truncated: false }); });

it('clear all cancels a late playlist, keeps account favorites and undo restores stopped', async () => {
  api.list.mockResolvedValue([saved]);
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  act(() => { view.result.current.select(saved); view.result.current.append([saved, saved]); });
  let resolve!: (value: { tracks: typeof saved[]; skipped: number; truncated: boolean }) => void;
  api.playlist.mockReturnValue(new Promise(done => { resolve = done; }));
  act(() => { view.result.current.importPlaylist('https://youtube.com/playlist?list=PLtest123456'); });
  act(() => { view.result.current.clearAll(); });
  await act(async () => { resolve({ tracks: [saved], skipped: 0, truncated: false }); });
  expect(view.result.current.track).toBeNull(); expect(view.result.current.queue).toEqual([]);
  expect(view.result.current.favorites).toEqual([saved]); expect(view.result.current.canUndo).toBe(true);
  act(() => { view.result.current.undo(); });
  expect(view.result.current.queue).toHaveLength(2); expect(view.result.current.source?.autoplay).toBe(false);
  expect(view.result.current.canUndo).toBe(false); expect(api.save).not.toHaveBeenCalled();
});

it('remount restores this account stopped, with position, modes, duplicate entries and no Undo; restart uses the original start', async () => {
  const first = renderHook(() => usePlayerLibrary('account-A'), { wrapper: StrictMode });
  await waitFor(() => expect(first.result.current.loadingFavorites).toBe(false));
  act(() => {
    first.result.current.select({ ...saved, startSeconds: 5 }); first.result.current.append([saved, saved]);
    first.result.current.setRepeat('all'); first.result.current.toggleShuffle();
  });
  act(() => { first.result.current.rememberPlayback(first.result.current.currentEntryKey, 42, 27, true); });
  const oldOrder = first.result.current.queue.map(e => e.track.videoId); first.unmount();
  const next = renderHook(() => usePlayerLibrary('account-A'), { wrapper: StrictMode });
  await waitFor(() => expect(next.result.current.loadingFavorites).toBe(false));
  expect(next.result.current.source).toMatchObject({ videoId: saved.videoId, startSeconds: 42, autoplay: false });
  expect(next.result.current.queue.map(e => e.track.videoId)).toEqual(oldOrder);
  expect(next.result.current).toMatchObject({ initialVolume: 27, repeat: 'all', shuffle: true, canUndo: false });
  const currentKey = next.result.current.currentEntryKey;
  act(() => { next.result.current.append([saved]); });
  expect(new Set([currentKey, ...next.result.current.queue.map(e => e.key)]).size).toBe(4);
  act(() => { next.result.current.restart(); });
  expect(next.result.current.source).toMatchObject({ startSeconds: 5, autoplay: true });
  next.unmount();
  const other = renderHook(() => usePlayerLibrary('account-B'));
  expect(other.result.current.source).toBeNull(); expect(other.result.current.queue).toEqual([]);
});

it('Clear All is persisted immediately, ignores a late old checkpoint, and an explicit Undo may save it again', async () => {
  const first = renderHook(() => usePlayerLibrary('account-A'));
  await waitFor(() => expect(first.result.current.loadingFavorites).toBe(false));
  act(() => { first.result.current.select(saved); first.result.current.append([saved]); });
  const oldKey = first.result.current.currentEntryKey;
  act(() => { first.result.current.clearAll(); first.result.current.rememberPlayback(oldKey, 80, 50, true); });
  const empty = renderHook(() => usePlayerLibrary('account-A'));
  expect(empty.result.current.track).toBeNull(); expect(empty.result.current.queue).toEqual([]); empty.unmount();
  act(() => { first.result.current.undo(); }); first.unmount();
  const restored = renderHook(() => usePlayerLibrary('account-A'));
  expect(restored.result.current.source?.autoplay).toBe(false); expect(restored.result.current.queue).toHaveLength(1);
});

it('Clear Queue stays cleared after remount without losing the current track', async () => {
  const first = renderHook(() => usePlayerLibrary('account-A'));
  await waitFor(() => expect(first.result.current.loadingFavorites).toBe(false));
  act(() => { first.result.current.select(saved); first.result.current.append([saved]); first.result.current.clearQueue(); }); first.unmount();
  const next = renderHook(() => usePlayerLibrary('account-A'));
  expect(next.result.current.track?.videoId).toBe(saved.videoId); expect(next.result.current.queue).toEqual([]);
});

it('keeps the unsaved-session error visible across throttled checkpoints until a real write succeeds', async () => {
  const view = renderHook(() => usePlayerLibrary('account-A'));
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  act(() => { view.result.current.select(saved); });
  const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('full'); });
  try {
    act(() => { view.result.current.append([saved]); });
    expect(view.result.current.error).toContain('chưa lưu được');
    act(() => { view.result.current.rememberPlayback(view.result.current.currentEntryKey, 10, 23); });
    expect(view.result.current.error).toContain('chưa lưu được');
    write.mockRestore();
    act(() => { view.result.current.rememberPlayback(view.result.current.currentEntryKey, 10, 23, true); });
    expect(view.result.current.error).toBe('');
  } finally { write.mockRestore(); }
});

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

it('chat sets a desired favorite instead of toggling and never treats a failed refresh as an empty account', async () => {
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  await act(async () => { await view.result.current.setFavorite(saved, true); await view.result.current.setFavorite(saved, true); });
  expect(api.save.mock.calls.map(call => call[1])).toEqual([true, true]);
  expect(view.result.current.favorites).toEqual([saved]);
  api.list.mockRejectedValueOnce(new Error('Offline favorites'));
  await act(async () => { await expect(view.result.current.readFavorites(new AbortController().signal)).rejects.toThrow('Offline'); });
  expect(view.result.current.favorites).toEqual([saved]); expect(view.result.current.loadingFavorites).toBe(false);
});

it('bulk favorites skip duplicate video IDs, fill remaining capacity, keep playback and avoid per-item metadata requests', async () => {
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  const other = mediaFromId('e1xCOsgWG0M', 'Vampire');
  act(() => { view.result.current.select(saved); view.result.current.append(Array.from({ length: 198 }, () => other)); });
  const before = view.result.current.source;
  const tracks = [saved, other, ...Array.from({ length: 5 }, (_, i) => mediaFromId(`item000000${i}`))];
  api.info.mockClear();
  let counts: ReturnType<typeof view.result.current.appendFavorites>;
  act(() => { counts = view.result.current.appendFavorites(tracks); });
  expect(counts!).toMatchObject({ added: 2, skipped_duplicates: 2, not_added_capacity: 3 });
  expect(view.result.current.queue).toHaveLength(200); expect(view.result.current.source).toBe(before);
  expect(api.info).not.toHaveBeenCalled();
  act(() => { counts = view.result.current.appendFavorites(tracks); });
  expect(counts!).toMatchObject({ added: 0, skipped_duplicates: 4, not_added_capacity: 3 });
});

it('chat playlist append preserves duplicates, applies remaining capacity atomically and keeps the current source', async () => {
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  act(() => { view.result.current.select(saved); view.result.current.append(Array.from({ length: 198 }, () => saved)); });
  const before = view.result.current.source;
  let counts!: ReturnType<typeof view.result.current.appendControlled>;
  act(() => { counts = view.result.current.appendControlled([saved, saved, saved]); });
  expect(counts).toMatchObject({ added: 2, not_added_capacity: 1 });
  expect(new Set(counts.keys).size).toBe(2);
  expect(view.result.current.queue).toHaveLength(200); expect(view.result.current.source).toBe(before);
  expect(view.result.current.queue.slice(-2).map(entry => entry.track.videoId)).toEqual([saved.videoId, saved.videoId]);
});

it('aborting a chat favorites request clears busy flags and prevents a late response from replacing new data', async () => {
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  let finish!: (items: typeof saved[]) => void;
  api.list.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  const controller = new AbortController();
  let pending!: Promise<unknown>;
  act(() => { pending = view.result.current.readFavorites(controller.signal).catch(error => error); });
  controller.abort();
  await act(async () => { finish([saved]); await pending; });
  expect(view.result.current.loadingFavorites).toBe(false); expect(view.result.current.favorites).toEqual([]);
  const other = mediaFromId('e1xCOsgWG0M', 'Vampire');
  api.list.mockResolvedValueOnce([other]);
  await act(async () => { await view.result.current.readFavorites(new AbortController().signal); });
  expect(view.result.current.favorites).toEqual([other]);
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

it('search does not autoplay, supports pagination and appending keeps results and the current source', async () => {
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  api.search.mockResolvedValueOnce({ tracks: [saved], nextPageToken: 'PAGE2' });
  act(() => { view.result.current.openInput('Tetris'); });
  await waitFor(() => expect(view.result.current.discovery.busy).toBe(false));
  expect(view.result.current.source).toBeNull(); expect(view.result.current.panel).toBe('search');
  act(() => { view.result.current.append([saved]); });
  expect(view.result.current.panel).toBe('search'); expect(view.result.current.queue).toHaveLength(1);
  expect(view.result.current.newItems).toBe(true); expect(api.info).not.toHaveBeenCalled();
  const other = mediaFromId('e1xCOsgWG0M', 'Vampire', 'DECO*27');
  api.search.mockResolvedValueOnce({ tracks: [saved, other], nextPageToken: '' });
  await act(async () => { view.result.current.discovery.loadMore(); });
  expect(api.search.mock.calls[1][1]).toBe('PAGE2'); expect(view.result.current.discovery.results).toEqual([saved, other]);
  act(() => { view.result.current.select(other); });
  expect(view.result.current.source?.autoplay).toBe(true); expect(view.result.current.panel).toBe('search');
});

it('a newer query cancels the old request and ignores its late result even if fetch does not reject', async () => {
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  let finish!: (data: { tracks: typeof saved[]; nextPageToken: string }) => void;
  api.search.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  act(() => { view.result.current.openInput('old query'); });
  const signal = api.search.mock.calls[0][2] as AbortSignal;
  act(() => { view.result.current.openInput('new query'); });
  await waitFor(() => expect(view.result.current.discovery.busy).toBe(false));
  expect(signal.aborted).toBe(true);
  await act(async () => { finish({ tracks: [], nextPageToken: 'STALE' }); });
  expect(view.result.current.discovery.query).toBe('new query'); expect(view.result.current.discovery.results).toEqual([saved]);
  expect(view.result.current.discovery.nextPageToken).toBe('');
});

it('playlist import keeps playback, reports skipped/capped items and seeds metadata without per-item oEmbed', async () => {
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  act(() => { view.result.current.select(saved); });
  const source = view.result.current.source;
  api.playlist.mockResolvedValueOnce({ tracks: [saved, saved], skipped: 1, truncated: true });
  await act(async () => { view.result.current.openInput('https://youtube.com/playlist?list=PLabcdefghijk12345'); });
  expect(view.result.current.source).toBe(source); expect(view.result.current.queue).toHaveLength(2);
  expect(view.result.current.queue[0].key).not.toBe(view.result.current.queue[1].key);
  expect(view.result.current.panel).toBe('queue'); expect(view.result.current.discovery.playlistNote).toContain('Bỏ qua 1');
  expect(view.result.current.discovery.playlistNote).toContain('chưa nhập'); expect(api.info).not.toHaveBeenCalled();
  expect(api.playlist.mock.calls[0][1]).toBe(200);
});

it('cancel/close prevents a pending playlist from adding tracks later', async () => {
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  let finish!: (data: { tracks: typeof saved[]; skipped: number; truncated: boolean }) => void;
  api.playlist.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  act(() => { view.result.current.openInput('https://youtube.com/playlist?list=PLabcdefghijk12345'); });
  const signal = api.playlist.mock.calls[0][2] as AbortSignal;
  act(() => { view.result.current.cancelDiscovery(); }); expect(signal.aborted).toBe(true);
  await act(async () => { finish({ tracks: [saved], skipped: 0, truncated: false }); });
  expect(view.result.current.queue).toHaveLength(0); expect(view.result.current.discovery.busy).toBe(false);
});

it('queue changes during playlist loading cannot overflow the limit or partially add the playlist', async () => {
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  let finish!: (data: { tracks: typeof saved[]; skipped: number; truncated: boolean }) => void;
  api.playlist.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  act(() => { view.result.current.openInput('https://youtube.com/playlist?list=PLabcdefghijk12345'); });
  act(() => { view.result.current.append(Array.from({ length: 199 }, () => saved)); });
  await act(async () => { finish({ tracks: [saved, saved], skipped: 0, truncated: false }); });
  expect(view.result.current.queue).toHaveLength(199); expect(view.result.current.error).toContain('200 bài');
});

it('discovery failure leaves the queue and playing source intact, and retry can recover', async () => {
  const view = renderHook(() => usePlayerLibrary());
  await waitFor(() => expect(view.result.current.loadingFavorites).toBe(false));
  act(() => { view.result.current.select(saved); view.result.current.append([saved]); });
  const source = view.result.current.source;
  api.search.mockRejectedValueOnce(new Error('YouTube đã hết hạn mức tạm thời.'));
  await act(async () => { view.result.current.openInput('Tetris'); });
  expect(view.result.current.discovery.error).toContain('hạn mức'); expect(view.result.current.source).toBe(source);
  expect(view.result.current.queue).toHaveLength(1);
  await act(async () => { view.result.current.discovery.retry(); });
  expect(view.result.current.discovery.error).toBe(''); expect(view.result.current.discovery.results).toEqual([saved]);
});
