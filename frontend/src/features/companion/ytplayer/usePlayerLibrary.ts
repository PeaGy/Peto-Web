import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type DragEvent } from 'react';
import { getVideoInfo, listFavorites, mediaFromId, saveFavorite } from './playerApi';
import { emptyQueue, playerQueueReducer } from './playerQueue';
import { parseYouTubePlaylistUrl, parseYouTubeUrl, type YouTubePlaybackSource } from './youtubeUrl';
import { parsePlayerInput } from './playerInput';
import { usePlayerDiscovery } from './usePlayerDiscovery';
import type { LibraryPanelKind, MediaTrack, PlayerLibrary } from './playerLibraryTypes';

const seed = () => Math.floor(Math.random() * 0x100000000);
const message = (error: unknown) => error instanceof TypeError ? 'Không kết nối được thư viện Player. Bạn thử lại nhé.'
  : error instanceof Error && error.message ? error.message : 'Chưa tải hoặc lưu được yêu thích. Bạn thử lại nhé.';

/** Owned by the account-keyed Companion; no browser storage or sample catalogue. */
export function usePlayerLibrary(): PlayerLibrary & {
  source: YouTubePlaybackSource | null;
  openLink: (value: string) => string | undefined;
  ended: (request: number, serial: number) => void;
  restart: () => void;
  setRepeat: (repeat: 'off' | 'all' | 'one') => void;
  updateDuration: (videoId: string, duration: number) => void;
} {
  const [state, dispatch] = useReducer(playerQueueReducer, undefined, emptyQueue);
  const stateRef = useRef(state); stateRef.current = state;
  const discovery = usePlayerDiscovery();
  const [favorites, setFavorites] = useState<MediaTrack[]>([]);
  const [loadingFavorites, setLoadingFavorites] = useState(true);
  const [favoritesBusy, setFavoritesBusy] = useState(false);
  const [error, setError] = useState('');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [panel, setPanel] = useState<LibraryPanelKind | null>(null);
  const [newItems, setNewItems] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const [sourceRequest, setSourceRequest] = useState(0);
  const sequence = useRef(0);
  const queueButton = useRef<HTMLButtonElement>(null);
  const pendingFavorite = useRef(false);
  const requests = useRef(new Set<AbortController>());
  const metadata = useRef(new Map<string, { title: string; artist: string }>());
  const track = state.current?.track ?? null;
  const source = useMemo<YouTubePlaybackSource | null>(() => track ? {
    videoId: track.videoId, startSeconds: track.startSeconds, url: track.url, playbackId: String(state.request), autoplay: state.autoplay,
  } : null, [track?.videoId, track?.startSeconds, track?.url, state.request, state.autoplay]);

  useEffect(() => () => { requests.current.forEach(controller => controller.abort()); requests.current.clear(); }, []);
  useEffect(() => {
    const controller = new AbortController(); requests.current.add(controller); setLoadingFavorites(true);
    void listFavorites(controller.signal).then(items => {
      if (controller.signal.aborted) return;
      setFavorites(items); setError('');
      items.forEach(item => { if (item.title) metadata.current.set(item.videoId, item); });
    }).catch(reason => { if (!controller.signal.aborted) setError(message(reason)); })
      .finally(() => { requests.current.delete(controller); if (!controller.signal.aborted) setLoadingFavorites(false); });
    return () => controller.abort();
  }, [loadAttempt]);

  const readMetadata = useCallback((videoId: string) => {
    const saved = metadata.current.get(videoId);
    if (saved) { dispatch({ type: 'metadata', videoId, ...saved }); return; }
    const controller = new AbortController(); requests.current.add(controller);
    void getVideoInfo(videoId, controller.signal).then(info => {
      if (controller.signal.aborted) return;
      if (metadata.current.size >= 500) metadata.current.clear();
      metadata.current.set(videoId, info);
      dispatch({ type: 'metadata', videoId, title: info.title, artist: info.artist });
    }).catch(() => { /* Metadata is optional; playback and saving remain available. */ })
      .finally(() => requests.current.delete(controller));
  }, []);
  useEffect(() => { if (track) readMetadata(track.videoId); }, [track?.videoId, readMetadata]);

  const select = useCallback((item: MediaTrack, autoplay = true) => {
    discovery.cancel();
    if (metadata.current.size >= 500) metadata.current.clear();
    if (item.title) metadata.current.set(item.videoId, item);
    dispatch({ type: 'select', entry: { key: `selected-${++sequence.current}`, track: item }, autoplay }); setError('');
  }, [discovery.cancel]);
  const ended = useCallback((request: number, serial: number) => dispatch({ type: 'ended', request, serial, seed: seed() }), []);
  const updateDuration = useCallback((videoId: string, duration: number) => dispatch({ type: 'metadata', videoId, duration }), []);
  function openLink(value: string) {
    const parsed = parseYouTubeUrl(value);
    if (!parsed) return 'Link YouTube chưa hợp lệ. Hãy kiểm tra lại đường dẫn video.';
    select({ ...mediaFromId(parsed.videoId), ...parsed }, false); return undefined;
  }
  function append(items: MediaTrack[]) {
    if (stateRef.current.queue.length + items.length > 200) { setError('Hàng đợi tối đa 200 bài. Xóa bớt bài rồi thêm nhé.'); return false; }
    const action = { type: 'append' as const, entries: items.map(item => ({ key: `queued-${++sequence.current}`, track: item })) };
    stateRef.current = playerQueueReducer(stateRef.current, action); dispatch(action);
    if (metadata.current.size + items.length > 500) metadata.current.clear();
    items.forEach(item => { if (item.title) metadata.current.set(item.videoId, item); else readMetadata(item.videoId); });
    if (panel !== 'queue') setNewItems(true);
    setAnnouncement(`Đã thêm ${items.length} bài vào hàng đợi.`); setError(''); return true;
  }
  function appendLink(value: string) {
    const parsed = parseYouTubeUrl(value);
    if (!parsed) return 'Link YouTube chưa hợp lệ. Hãy kiểm tra lại đường dẫn video.';
    if (state.queue.length >= 200) return 'Hàng đợi tối đa 200 bài.';
    append([{ ...mediaFromId(parsed.videoId), ...parsed }]); return undefined;
  }
  function importPlaylist(value: string) {
    const id = parseYouTubePlaylistUrl(value);
    if (!id) return 'Link playlist YouTube chưa hợp lệ.';
    const limit = 200 - stateRef.current.queue.length;
    if (limit <= 0) return 'Hàng đợi tối đa 200 bài. Xóa bớt bài rồi thêm nhé.';
    openPanel('queue');
    void discovery.playlist(id, limit).then(data => {
      if (!data || !append(data.tracks)) return;
      const note = `Đã thêm ${data.tracks.length} bài${data.skipped ? ` · Bỏ qua ${data.skipped} video không khả dụng` : ''}${data.truncated ? ' · Playlist còn bài chưa nhập (giới hạn 200 bài mỗi lượt/hàng đợi)' : ''}.`;
      discovery.setPlaylistNote(note); setNewItems(false); setAnnouncement(note);
    });
    return undefined;
  }
  function openInput(value: string) {
    const input = parsePlayerInput(value);
    if (input.kind === 'error') return input.message;
    if (input.kind === 'video') return openLink(value);
    if (input.kind === 'playlist') return importPlaylist(value);
    openPanel('search'); void discovery.search(input.query); return undefined;
  }
  async function toggleFavorite(item = track ?? undefined) {
    if (!item || pendingFavorite.current || loadingFavorites) return;
    const save = !favorites.some(value => value.videoId === item.videoId);
    const controller = new AbortController(); requests.current.add(controller);
    pendingFavorite.current = true; setFavoritesBusy(true); setError('');
    try {
      const items = await saveFavorite(item.videoId, save, controller.signal);
      if (!controller.signal.aborted) { setFavorites(items); setAnnouncement(save ? 'Đã lưu yêu thích.' : 'Đã bỏ yêu thích.'); }
    } catch (reason) { if (!controller.signal.aborted) setError(message(reason)); }
    finally {
      requests.current.delete(controller); pendingFavorite.current = false;
      if (!controller.signal.aborted) setFavoritesBusy(false);
    }
  }
  function openPanel(value: LibraryPanelKind) { discovery.cancel(); setPanel(value); if (value === 'queue') setNewItems(false); }
  function closePanel() { discovery.cancel(); setPanel(null); queueButton.current?.focus({ preventScroll: true }); }
  function drop(event: DragEvent, key: string) {
    event.preventDefault(); const from = state.queue.findIndex(item => item.key === event.dataTransfer.getData('text/plain'));
    const to = state.queue.findIndex(item => item.key === key);
    if (from >= 0 && to >= 0) dispatch({ type: 'move', key: state.queue[from].key, offset: to - from });
  }
  return {
    track, source, queue: state.queue, favorites, favorite: !!track && favorites.some(item => item.videoId === track.videoId),
    repeat: state.repeat, shuffle: state.shuffle, panel, newItems, announcement, sourceRequest, queueButton,
    loadingFavorites, favoritesBusy, error, select, openLink, appendLink, append, toggleFavorite, openPanel, closePanel, drop,
    discovery, openInput, importPlaylist, cancelDiscovery: discovery.cancel,
    next: () => dispatch({ type: 'next', seed: seed() }), restart: () => dispatch({ type: 'restart' }),
    setRepeat: (repeat: 'off' | 'all' | 'one') => dispatch({ type: 'set-repeat', repeat, seed: seed() }),
    ended, updateDuration,
    move: (key, offset) => dispatch({ type: 'move', key, offset }), remove: key => dispatch({ type: 'remove', key }),
    playEntry: entry => dispatch({ type: 'play-entry', key: entry.key }),
    toggleShuffle: () => dispatch({ type: 'shuffle', seed: seed() }), cycleRepeat: () => dispatch({ type: 'repeat', seed: seed() }),
    toggleQueue: () => panel === 'queue' ? closePanel() : openPanel('queue'), requestSource: () => setSourceRequest(value => value + 1),
    reloadFavorites: () => { if (!pendingFavorite.current) setLoadAttempt(value => value + 1); },
  };
}
