import { beforeEach, expect, it, vi } from 'vitest';
import { decodePlayerSession, hasPlayerSession, PlayerSessionStore } from '../src/features/companion/ytplayer/playerSession';
import { emptyQueue, playerQueueReducer as reduce } from '../src/features/companion/ytplayer/playerQueue';
import { mediaFromId } from '../src/features/companion/ytplayer/playerApi';

const song = { key: 'selected-1', track: { ...mediaFromId('Soy4jGPHr3g', 'Tetris', 'Teto'), duration: 240 } };
const pending = [1, 2].map(i => ({ key: `queued-${i}`, track: mediaFromId('e1xCOsgWG0M', 'Vampire') }));
const initial = () => reduce(reduce(emptyQueue(), { type: 'select', entry: song, autoplay: true }), { type: 'append', entries: pending });
const saved = () => { const store = new PlayerSessionStore('A'); store.saveQueue(initial(), true); return store; };
beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

it('restores exact duplicate queue entries, order and modes with fresh keys and no intents, revisions or Undo', () => {
  const store = new PlayerSessionStore('A');
  const state = reduce(reduce(initial(), { type: 'set-repeat', repeat: 'all', seed: 8 }), { type: 'shuffle', seed: 10 });
  store.saveQueue(state, true); store.remember(song.key, 43.5, 23, true);
  const restored = new PlayerSessionStore('A').initial!;
  expect(restored.position).toBe(43.5); expect(restored.volume).toBe(23);
  expect(restored.queue).toMatchObject({ autoplay: false, request: 0, revision: 0, endedSerial: 0, undo: null, repeat: 'all', shuffle: true });
  expect(restored.queue.queue.map(e => e.track.videoId)).toEqual(state.queue.map(e => e.track.videoId));
  expect(new Set(restored.queue.order.map(e => e.key)).size).toBe(3);
  expect(restored.queue.order.some(e => e.key === song.key)).toBe(false);
  expect(restored.queue.queue.map(e => e.key)).not.toContain(restored.queue.current!.key);
});

it('Clear All removes saved current/queue synchronously; Undo saves the restored stopped session', () => {
  const store = saved(), before = initial();
  store.saveQueue(reduce(before, { type: 'clear_queue' }), true);
  expect(new PlayerSessionStore('A').initial?.queue.current?.track.videoId).toBe(song.track.videoId);
  expect(new PlayerSessionStore('A').initial?.queue.queue).toHaveLength(0);
  const cleared = reduce(before, { type: 'clear_all' }); store.saveQueue(cleared, true);
  expect(hasPlayerSession('A')).toBe(false);
  store.flush(); expect(new PlayerSessionStore('A').initial).toBeNull();
  store.saveQueue(reduce(cleared, { type: 'undo' }), true);
  expect(new PlayerSessionStore('A').initial?.queue).toMatchObject({ autoplay: false, undo: null });
});

it('isolates accounts and disables persistence when no authenticated account ID is supplied', () => {
  saved(); expect(new PlayerSessionStore('B').initial).toBeNull(); expect(hasPlayerSession('B')).toBe(false);
  const other = new PlayerSessionStore(); other.saveQueue(initial(), true);
  expect(localStorage.length).toBe(1); expect(new PlayerSessionStore().initial).toBeNull();
});

it('throttles progress, flushes on lifecycle events and ignores a late checkpoint for the previous source', () => {
  const store = saved(); const writes = vi.spyOn(Storage.prototype, 'setItem');
  store.remember(song.key, 12, 40); store.remember(song.key, 15, 40);
  expect(writes).not.toHaveBeenCalled(); store.flush(); expect(writes).toHaveBeenCalledTimes(1);
  const next = reduce(initial(), { type: 'next', seed: 0 }); store.saveQueue(next, true);
  store.remember(song.key, 100, 80, true);
  const restored = new PlayerSessionStore('A').initial!;
  expect(restored.position).toBe(0); expect(restored.volume).toBe(40);
});

it('a stale tab cannot resurrect another tab’s cleared snapshot on timer/unmount, but a new explicit edit can save', () => {
  const first = saved(), second = new PlayerSessionStore('A');
  second.saveQueue(reduce(second.initial!.queue, { type: 'clear_all' }), true);
  first.remember(song.key, 50, 60, true); first.flush();
  expect(hasPlayerSession('A')).toBe(false);
  first.saveQueue(reduce(initial(), { type: 'remove', key: pending[0].key }), true);
  expect(new PlayerSessionStore('A').initial?.queue.queue).toHaveLength(1);
});

it('storage denial or quota exhaustion does not throw and never reports that a write succeeded', () => {
  const store = saved(); vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError'); });
  expect(store.remember(song.key, 30, 20, true)).toBe(false);
  expect(store.remember(song.key, 31, 20)).toBe(false);
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
  expect(() => new PlayerSessionStore('A')).not.toThrow(); expect(store.flush()).toBe(false);
});

it('rejects a serialized snapshot beyond the read limit without overwriting the previous valid session', () => {
  const store = saved(), track = { ...song.track, title: '\u0000'.repeat(500), artist: '\u0000'.repeat(200) };
  const huge = reduce(reduce(emptyQueue(), { type: 'select', entry: { ...song, track }, autoplay: true }),
    { type: 'append', entries: Array.from({ length: 200 }, (_, i) => ({ key: `large-${i}`, track })) });
  expect(store.saveQueue(huge, true)).toBe(false);
  expect(new PlayerSessionStore('A').initial!.queue.current!.track.title).toBe('Tetris');
});

it('drops corrupt/unknown/oversized/unsafe snapshots and rebuilds URLs only from a valid video ID', () => {
  saved(); const raw = localStorage.getItem(localStorage.key(0)!)!;
  const snapshot = JSON.parse(raw);
  for (const bad of ['{', 'x'.repeat(400001), JSON.stringify({ ...snapshot, version: 99 }),
    JSON.stringify({ ...snapshot, queue: ['missing'] }), JSON.stringify({ ...snapshot, queue: Array(201).fill('queued-1') }),
    JSON.stringify({ ...snapshot, volume: -1 }), JSON.stringify({ ...snapshot, position: '30' }), JSON.stringify({ ...snapshot, repeat: ['all'] }),
    JSON.stringify({ ...snapshot, order: [snapshot.order[0], snapshot.order[0]] })]) expect(decodePlayerSession(bad)).toBeNull();
  snapshot.order[0].track.url = 'javascript:alert(1)'; snapshot.autoplay = true;
  expect(decodePlayerSession(JSON.stringify(snapshot))!.queue.current!.track.url).toBe(song.track.url);
  snapshot.order[0].track.videoId = '<invalid>';
  expect(decodePlayerSession(JSON.stringify(snapshot))).toBeNull();
  const key = localStorage.key(0)!; localStorage.setItem(key, '{}');
  expect(new PlayerSessionStore('A').initial).toBeNull(); expect(localStorage.getItem(key)).toBeNull();
});

it('bounds long Unicode metadata without splitting characters or dropping an otherwise valid session', () => {
  const store = new PlayerSessionStore('A'), title = '🎵'.repeat(501), artist = '🎤'.repeat(201);
  store.saveQueue(reduce(emptyQueue(), { type: 'select', entry: { ...song, track: { ...song.track, title, artist } }, autoplay: true }), true);
  const restored = new PlayerSessionStore('A').initial!.queue.current!.track;
  expect(restored.title).toBe('🎵'.repeat(500)); expect(restored.artist).toBe('🎤'.repeat(200));
});

it('retains the internal repeat cycle so restored next-track order matches the saved shuffle cycle', () => {
  const store = new PlayerSessionStore('A');
  let s = reduce(initial(), { type: 'set-repeat', repeat: 'all', seed: 2 });
  s = reduce(s, { type: 'shuffle', seed: 2 }); s = reduce(s, { type: 'next', seed: 8 });
  s = { ...s, cyclePlayed: [...s.cyclePlayed, 'pruned-old-history'] };
  store.saveQueue(s, true); const restored = new PlayerSessionStore('A').initial!.queue;
  expect(restored.queue.map(e => e.track.videoId)).toEqual(s.queue.map(e => e.track.videoId));
  const oldNext = reduce(s, { type: 'next', seed: 4 }), newNext = reduce(restored, { type: 'next', seed: 4 });
  expect(newNext.queue.map(e => e.track.videoId)).toEqual(oldNext.queue.map(e => e.track.videoId));
});
