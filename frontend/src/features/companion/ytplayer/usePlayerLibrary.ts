import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type DragEvent } from 'react';
import { getVideoInfo, listFavorites, mediaFromId, saveFavorite } from './playerApi';
import { emptyQueue, nextPlayerTracks, playerQueueReducer, type QueueAction, type UndoOperation } from './playerQueue';
import { parseYouTubePlaylistUrl, parseYouTubeUrl, type YouTubePlaybackSource } from './youtubeUrl';
import { parsePlayerInput } from './playerInput';
import { usePlayerDiscovery } from './usePlayerDiscovery';
import type { LibraryPanelKind, MediaTrack, PlayerLibrary } from './playerLibraryTypes';
import { PlayerSessionStore } from './playerSession';
import { PlayerHistoryStore, previousChoice, type ListeningEntry } from './playerHistory';

const seed = () => Math.floor(Math.random() * 0x100000000);
const message = (error: unknown) => error instanceof TypeError ? 'Không kết nối được thư viện Player. Bạn thử lại nhé.'
  : error instanceof Error && error.message ? error.message : 'Chưa tải hoặc lưu được yêu thích. Bạn thử lại nhé.';

export interface SessionEdit { revision: number; removed: number; restored: number; undoAction?: UndoOperation }

/** Favorites use the account API; the listening session stays in this account's browser storage. */
export function usePlayerLibrary(ownerId?: string): PlayerLibrary & {
  source: YouTubePlaybackSource | null;
  openLink: (value: string) => string | undefined;
  ended: (request: number, serial: number) => void;
  restart: () => void;
  setRepeat: (repeat: 'off' | 'all' | 'one') => void;
  updateDuration: (videoId: string, duration: number) => void;
  queueRevision: number;
  resetRevision: number;
  canUndo: boolean;
  clearQueue: () => SessionEdit;
  clearAll: () => SessionEdit;
  undo: () => SessionEdit | null;
  currentEntryKey: string | null;
  nextPlaybackId: string;
  history: ListeningEntry[];
  historyRevision: number;
  historySaved: boolean;
  previousTrack: MediaTrack | null;
  previous: () => boolean;
  clearHistory: () => number;
  recordPlaying: (request: number, videoId: string) => void;
  playedRequest: number | null;
  initialVolume: number;
  rememberPlayback: (key: string | null, position: number | undefined, volume: number, immediate?: boolean) => void;
  nextTracks: ReturnType<typeof nextPlayerTracks>;
  controlEntry: (operation: 'remove' | 'move' | 'play', key: string, revision: number, position?: number) => boolean;
  readFavorites: (signal: AbortSignal) => Promise<MediaTrack[]>;
  setFavorite: (item: MediaTrack, save: boolean, signal?: AbortSignal) => Promise<MediaTrack[]>;
  appendFavorites: (items: MediaTrack[]) => { added: number; skipped_duplicates: number; not_added_capacity: number; keys: string[] };
  appendControlled: (items: MediaTrack[]) => { added: number; not_added_capacity: number; keys: string[] };
} {
  const [session] = useState(() => new PlayerSessionStore(ownerId));
  const [historyStore] = useState(() => new PlayerHistoryStore(ownerId));
  const [historyError, setHistoryError] = useState(() => historyStore.failed ? 'Trình duyệt chưa đọc được lịch sử nghe.' : '');
  const [sessionError, setSessionError] = useState('');
  const persisted = useCallback((ok: boolean) => setSessionError(ok ? '' : 'Trình duyệt chưa lưu được phiên Player. Tải lại trang có thể mất thay đổi vừa rồi.'), []);
  const [state, dispatch] = useReducer(playerQueueReducer, { ...(session.initial?.queue ?? emptyQueue()), ...historyStore.initial });
  const stateRef = useRef(state); stateRef.current = state;
  const commit = useCallback((action: QueueAction) => {
    if (action.type !== 'hydrate-history') {
      const value = historyStore.refresh();
      if (value) { const update: QueueAction = { type: 'hydrate-history', value }; stateRef.current = playerQueueReducer(stateRef.current, update); dispatch(update); setHistoryError(''); }
      else if (historyStore.failed) setHistoryError('Trình duyệt chưa đọc hoặc lưu được lịch sử nghe.');
    }
    const before = stateRef.current, after = playerQueueReducer(before, action);
    if (after !== before) {
      stateRef.current = after; dispatch(action);
      if (!['played', 'hydrate-history', 'clear-history'].includes(action.type)) persisted(session.saveQueue(after, action.type !== 'metadata' && action.type !== 'ended'));
      if (action.type !== 'hydrate-history' && (after.history !== before.history || after.trail !== before.trail || after.trailIndex !== before.trailIndex)) {
        const saved = historyStore.save(after, action.type === 'clear-history');
        setHistoryError(saved ? '' : 'Trình duyệt chưa lưu được lịch sử nghe.');
      }
    }
    return after;
  }, [session, persisted, historyStore]);
  useEffect(() => {
    const refresh = (event: StorageEvent) => { if (event.storageArea === localStorage && (event.key === historyStore.key || event.key === null)) commit({ type: 'sync-history' }); };
    window.addEventListener('storage', refresh); return () => window.removeEventListener('storage', refresh);
  }, [historyStore, commit]);
  const recordPlaying = useCallback((request: number, videoId: string) => {
    if (stateRef.current.recordedRequest !== request) commit({ type: 'played', request, videoId, key: crypto.randomUUID(), playedAt: Date.now() });
  }, [commit]);
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
  const favoriteEpoch = useRef(0);
  const requests = useRef(new Set<AbortController>());
  const alive = useRef(true);
  const metadata = useRef(new Map<string, { title: string; artist: string }>());
  const track = state.current?.track ?? null;
  const source = useMemo<YouTubePlaybackSource | null>(() => track ? {
    videoId: track.videoId, startSeconds: state.request === 0 && session.initial && session.initial.queue.current?.key === state.current?.key ? session.initial.position : track.startSeconds,
    url: track.url, playbackId: String(state.request), autoplay: state.autoplay,
  } : null, [track?.videoId, track?.startSeconds, track?.url, state.request, state.autoplay]);

  useEffect(() => { alive.current = true; return () => { alive.current = false; requests.current.forEach(controller => controller.abort()); requests.current.clear(); }; }, []);
  const request = useCallback((signal?: AbortSignal) => {
    signal?.throwIfAborted();
    const controller = new AbortController();
    const abort = () => controller.abort(); signal?.addEventListener('abort', abort, { once: true });
    requests.current.add(controller);
    return { controller, finish: () => { requests.current.delete(controller); signal?.removeEventListener('abort', abort); } };
  }, []);
  const readFavorites = useCallback(async (signal: AbortSignal) => {
    if (pendingFavorite.current) throw new Error('Đang lưu yêu thích; hãy đọc lại sau khi hoàn tất.');
    const { controller, finish } = request(signal), epoch = ++favoriteEpoch.current;
    setLoadingFavorites(true);
    try {
      const items = await listFavorites(controller.signal);
      controller.signal.throwIfAborted();
      if (epoch !== favoriteEpoch.current) throw new Error('Yêu thích vừa thay đổi; hãy đọc lại danh sách.');
      setFavorites(items); setError('');
      if (metadata.current.size + items.length > 500) metadata.current.clear();
      items.forEach(item => { if (item.title) metadata.current.set(item.videoId, item); });
      return items;
    } catch (reason) {
      if (!controller.signal.aborted && epoch === favoriteEpoch.current) setError(message(reason));
      throw reason;
    } finally {
      finish(); if (alive.current && epoch === favoriteEpoch.current) setLoadingFavorites(false);
    }
  }, [request]);
  useEffect(() => {
    const controller = new AbortController();
    void readFavorites(controller.signal).catch(() => { /* Error is exposed by readFavorites; never turn failure into an empty account. */ });
    return () => controller.abort();
  }, [loadAttempt, readFavorites]);

  const readMetadata = useCallback((videoId: string) => {
    const saved = metadata.current.get(videoId);
    if (saved) { commit({ type: 'metadata', videoId, ...saved }); return; }
    const controller = new AbortController(); requests.current.add(controller);
    void getVideoInfo(videoId, controller.signal).then(info => {
      if (controller.signal.aborted) return;
      if (metadata.current.size >= 500) metadata.current.clear();
      metadata.current.set(videoId, info);
      commit({ type: 'metadata', videoId, title: info.title, artist: info.artist });
    }).catch(() => { /* Metadata is optional; playback and saving remain available. */ })
      .finally(() => requests.current.delete(controller));
  }, [commit]);
  useEffect(() => { if (track) readMetadata(track.videoId); }, [track?.videoId, readMetadata]);

  const select = useCallback((item: MediaTrack, autoplay = true) => {
    discovery.cancel();
    if (metadata.current.size >= 500) metadata.current.clear();
    if (item.title) metadata.current.set(item.videoId, item);
    commit({ type: 'select', entry: { key: `selected-${++sequence.current}`, track: item }, autoplay }); setError('');
  }, [discovery.cancel, commit]);
  const ended = useCallback((request: number, serial: number) => commit({ type: 'ended', request, serial, seed: seed() }), [commit]);
  const updateDuration = useCallback((videoId: string, duration: number) => commit({ type: 'metadata', videoId, duration }), [commit]);
  function openLink(value: string) {
    const parsed = parseYouTubeUrl(value);
    if (!parsed) return 'Link YouTube chưa hợp lệ. Hãy kiểm tra lại đường dẫn video.';
    select({ ...mediaFromId(parsed.videoId), ...parsed }, false); return undefined;
  }
  function append(items: MediaTrack[], resolveMetadata = true) {
    if (stateRef.current.queue.length + items.length > 200) { setError('Hàng đợi tối đa 200 bài. Xóa bớt bài rồi thêm nhé.'); return false; }
    const action = { type: 'append' as const, entries: items.map(item => ({ key: `queued-${++sequence.current}`, track: item })) };
    commit(action);
    if (metadata.current.size + items.length > 500) metadata.current.clear();
    items.forEach(item => { if (item.title) metadata.current.set(item.videoId, item); else if (resolveMetadata) readMetadata(item.videoId); });
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
    const epoch = stateRef.current.resetRevision;
    void discovery.playlist(id, limit).then(data => {
      if (!alive.current || epoch !== stateRef.current.resetRevision || !data || !append(data.tracks)) return;
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
  async function setFavorite(item: MediaTrack, save: boolean, signal?: AbortSignal) {
    if (pendingFavorite.current) throw new Error('Đang lưu một thay đổi yêu thích; hãy đợi hoàn tất.');
    const { controller, finish } = request(signal); ++favoriteEpoch.current;
    pendingFavorite.current = true; setFavoritesBusy(true); setError('');
    try {
      const items = await saveFavorite(item.videoId, save, controller.signal);
      controller.signal.throwIfAborted();
      setFavorites(items); setAnnouncement(save ? 'Đã lưu yêu thích.' : 'Đã bỏ yêu thích.'); return items;
    } catch (reason) { if (!controller.signal.aborted) setError(message(reason)); throw reason; }
    finally {
      finish(); pendingFavorite.current = false;
      if (alive.current) { setFavoritesBusy(false); setLoadingFavorites(false); }
    }
  }
  async function toggleFavorite(item = track ?? undefined) {
    if (!item || pendingFavorite.current || loadingFavorites) return;
    try { await setFavorite(item, !favorites.some(value => value.videoId === item.videoId)); } catch { /* UI uses error state. */ }
  }
  function appendFavorites(items: MediaTrack[]) {
    const value = stateRef.current;
    const seen = new Set([...(value.current ? [value.current.track.videoId] : []), ...value.queue.map(entry => entry.track.videoId)]);
    const unique = items.filter(item => { if (seen.has(item.videoId)) return false; seen.add(item.videoId); return true; });
    const selected = unique.slice(0, Math.max(0, 200 - value.queue.length));
    const previous = new Set(value.queue.map(entry => entry.key));
    if (selected.length) append(selected, false);
    return { added: selected.length, skipped_duplicates: items.length - unique.length, not_added_capacity: unique.length - selected.length,
      keys: stateRef.current.queue.filter(entry => !previous.has(entry.key)).map(entry => entry.key) };
  }
  function appendControlled(items: MediaTrack[]) {
    const value = stateRef.current, previous = new Set(value.queue.map(entry => entry.key));
    const selected = items.slice(0, Math.max(0, 200 - value.queue.length));
    if (selected.length) append(selected, false);
    return { added: selected.length, not_added_capacity: items.length - selected.length,
      keys: stateRef.current.queue.filter(entry => !previous.has(entry.key)).map(entry => entry.key) };
  }
  function controlEntry(operation: 'remove' | 'move' | 'play', key: string, revision: number, position?: number) {
    const action = { type: 'control-entry' as const, operation, key, revision, position, seed: seed() };
    const before = stateRef.current, after = playerQueueReducer(before, action);
    if (after === before) return false;
    commit(action); return true;
  }
  function editSession(type: 'clear_queue' | 'clear_all' | 'undo'): SessionEdit | null {
    const before = stateRef.current;
    if (type === 'undo' && !before.undo) return null;
    discovery.cancel();
    const undoAction = type === 'undo' ? before.undo!.operation : undefined;
    const removed = type === 'clear_all' ? before.queue.length + Number(!!before.current) : type === 'clear_queue' ? before.queue.length : 0;
    const after = commit({ type });
    setNewItems(false); setError(''); discovery.setPlaylistNote('');
    setAnnouncement(type === 'clear_all' ? 'Đã dọn Player.' : type === 'clear_queue' ? 'Đã xóa hàng đợi.' : 'Đã hoàn tác.');
    return { revision: after.revision, removed,
      restored: type === 'undo' ? Math.max(0, after.queue.length - before.queue.length) + Number(!before.current && !!after.current) : 0, undoAction };
  }
  function openPanel(value: LibraryPanelKind) { discovery.cancel(); setPanel(value); if (value === 'queue') setNewItems(false); }
  function closePanel() { discovery.cancel(); setPanel(null); queueButton.current?.focus({ preventScroll: true }); }
  function drop(event: DragEvent, key: string) {
    event.preventDefault(); const from = state.queue.findIndex(item => item.key === event.dataTransfer.getData('text/plain'));
    const to = state.queue.findIndex(item => item.key === key);
    if (from >= 0 && to >= 0) commit({ type: 'move', key: state.queue[from].key, offset: to - from });
  }
  return {
    track, source, queue: state.queue, favorites, favorite: !!track && favorites.some(item => item.videoId === track.videoId),
    repeat: state.repeat, shuffle: state.shuffle, panel, newItems, announcement, sourceRequest, queueButton,
    loadingFavorites, favoritesBusy, error: sessionError || historyError || error, select, openLink, appendLink, append, toggleFavorite, openPanel, closePanel, drop,
    discovery, openInput, importPlaylist, cancelDiscovery: discovery.cancel,
    next: () => commit({ type: 'next', seed: seed() }), restart: () => commit({ type: 'restart' }),
    setRepeat: (repeat: 'off' | 'all' | 'one') => commit({ type: 'set-repeat', repeat, seed: seed() }),
    ended, updateDuration,
    resetRevision: state.resetRevision, canUndo: !!state.undo,
    history: state.history, historyRevision: state.historyRevision, historySaved: !historyStore.failed, previousTrack: previousChoice(state)?.track ?? null, canPrevious: !!previousChoice(state), recordPlaying, playedRequest: state.recordedRequest,
    previous: () => {
      const before = stateRef.current, after = commit({ type: 'previous', key: `previous-${++sequence.current}` });
      if (after.request === before.request) { setError(previousChoice(after) ? 'Hàng đợi đã đủ 200 bài. Xóa bớt một bài để giữ chỗ cho bài hiện tại khi quay lại.' : 'Chưa có bài trước trong lịch sử nghe.'); return false; }
      setError(''); return true;
    },
    clearHistory: () => { commit({ type: 'sync-history' }); const removed = stateRef.current.history.length; commit({ type: 'clear-history' }); setAnnouncement('Đã xóa lịch sử nghe.'); return removed; },
    initialVolume: session.initial?.volume ?? 60,
    rememberPlayback: (key, position, volume, immediate = false) => persisted(session.remember(key, position, volume, immediate)),
    clearQueue: () => editSession('clear_queue')!, clearAll: () => editSession('clear_all')!, undo: () => editSession('undo'),
    queueRevision: state.revision, currentEntryKey: state.current?.key ?? null, nextPlaybackId: String(state.request + 1), nextTracks: nextPlayerTracks(state), readFavorites, setFavorite, appendFavorites, appendControlled, controlEntry,
    move: (key, offset) => commit({ type: 'move', key, offset }), remove: key => commit({ type: 'remove', key }),
    playEntry: entry => commit({ type: 'play-entry', key: entry.key }),
    toggleShuffle: () => commit({ type: 'shuffle', seed: seed() }), cycleRepeat: () => commit({ type: 'repeat', seed: seed() }),
    toggleQueue: () => panel === 'queue' ? closePanel() : openPanel('queue'), requestSource: () => setSourceRequest(value => value + 1),
    reloadFavorites: () => { if (!pendingFavorite.current) setLoadAttempt(value => value + 1); },
  };
}
