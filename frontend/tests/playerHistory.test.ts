import { beforeEach, expect, it, vi } from 'vitest';
import { emptyQueue, playerQueueReducer as reduce, type PlayerQueue } from '../src/features/companion/ytplayer/playerQueue';
import { decodeHistory, emptyHistory, PlayerHistoryStore, previousChoice } from '../src/features/companion/ytplayer/playerHistory';
import { mediaFromId } from '../src/features/companion/ytplayer/playerApi';

const songs = ['Soy4jGPHr3g', 'e1xCOsgWG0M', 'aircAruvnKk'].map(id => mediaFromId(id));
const select = (s: PlayerQueue, i: number, key = `selected-${s.request + 1}`) => reduce(s, { type: 'select', entry: { key, track: songs[i] }, autoplay: true });
const played = (s: PlayerQueue) => reduce(s, { type: 'played', request: s.request, videoId: s.current!.track.videoId, key: `heard-${s.request}`, playedAt: s.request * 1000 });
const listen = (s: PlayerQueue, i: number) => played(select(s, i));
const ids = (s: PlayerQueue) => s.history.map(item => item.track.videoId);
beforeEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

it('records only a matching native playing confirmation, once per request, not a selection or stale/foreign event', () => {
  const s = select(emptyQueue(), 0); expect(s.history).toEqual([]);
  expect(reduce(s, { type: 'played', request: 0, videoId: songs[0].videoId, key: 'late', playedAt: 1 })).toBe(s);
  expect(reduce(s, { type: 'played', request: s.request, videoId: songs[1].videoId, key: 'wrong', playedAt: 1 })).toBe(s);
  const heard = played(s); expect(ids(heard)).toEqual([songs[0].videoId]); expect(played(heard)).toBe(heard);
  expect(heard.revision).toBe(s.revision);
});

it('Previous follows real listening order and Next returns the departing song without consuming the pending tail', () => {
  let s = listen(listen(listen(emptyQueue(), 0), 1), 2);
  s = reduce(s, { type: 'append', entries: [{ key: 'extra', track: songs[2] }] });
  s = played(reduce(s, { type: 'previous', key: 'prev-B' }));
  expect(s.current!.track).toEqual(songs[1]); expect(s.queue.map(e => e.key)).toEqual(['selected-3', 'extra']);
  s = played(reduce(s, { type: 'previous', key: 'prev-A' }));
  expect(s.current!.track).toEqual(songs[0]); expect(previousChoice(s)).toBeNull();
  expect(s.queue.map(e => e.track.videoId)).toEqual([songs[1].videoId, songs[2].videoId, songs[2].videoId]);
  s = played(reduce(s, { type: 'next', seed: 1 })); expect(previousChoice(s)!.track).toEqual(songs[0]);
  s = played(reduce(s, { type: 'next', seed: 1 })); expect(previousChoice(s)!.track).toEqual(songs[1]);
});

it('an unplayed/failed selection is absent from history and Previous returns to the last confirmed song', () => {
  let s = select(listen(emptyQueue(), 0), 1);
  expect(previousChoice(s)!.track).toEqual(songs[0]);
  s = played(reduce(s, { type: 'previous', key: 'back' }));
  expect(ids(s)).toEqual([songs[0].videoId]); expect(previousChoice(s)).toBeNull();
});

it('loop one, pause/resume and restart do not flood history with consecutive copies; separated replays do appear', () => {
  let s = listen(emptyQueue(), 0); s = reduce(s, { type: 'set-repeat', repeat: 'one', seed: 0 });
  s = played(reduce(s, { type: 'ended', request: s.request, serial: 1, seed: 0 }));
  s = played(reduce(s, { type: 'restart' })); expect(s.history).toHaveLength(1);
  expect(s.history[0].playedAt).toBe(s.request * 1000);
  s = listen(listen(s, 1), 0); expect(ids(s)).toEqual([songs[0].videoId, songs[1].videoId, songs[0].videoId]);
});

it('Previous preserves loop/shuffle and removes only one matching pending occurrence', () => {
  let s = listen(listen(emptyQueue(), 0), 1);
  s = reduce(s, { type: 'append', entries: [{ key: 'a1', track: songs[0] }, { key: 'a2', track: songs[0] }] });
  s = reduce(s, { type: 'set-repeat', repeat: 'all', seed: 1 }); s = reduce(s, { type: 'shuffle', seed: 1 });
  const previousCount = s.queue.length;
  s = played(reduce(s, { type: 'previous', key: 'back' }));
  expect(s.repeat).toBe('all'); expect(s.shuffle).toBe(true); expect(s.queue).toHaveLength(previousCount);
  expect(s.queue[0].track).toEqual(songs[1]);
});

it('a full queue is never silently truncated by Previous', () => {
  let s = listen(listen(emptyQueue(), 0), 1);
  s = reduce(s, { type: 'append', entries: Array.from({ length: 200 }, (_, i) => ({ key: `q-${i}`, track: songs[2] })) });
  expect(reduce(s, { type: 'previous', key: 'back' })).toBe(s);
});

it('Clear All/queue Undo preserve history, while clear history preserves the live source/queue and does not immediately re-add it', () => {
  let s = listen(listen(emptyQueue(), 0), 1);
  const cleared = reduce(s, { type: 'clear_all' }); expect(ids(cleared)).toEqual(ids(s)); expect(previousChoice(cleared)).toBeNull();
  s = reduce(s, { type: 'append', entries: [{ key: 'extra', track: songs[0] }] });
  const historyCleared = reduce(s, { type: 'clear-history' });
  expect(historyCleared.current).toBe(s.current); expect(historyCleared.queue).toBe(s.queue); expect(historyCleared.undo).toBe(s.undo);
  expect(played(historyCleared)).toBe(historyCleared); expect(historyCleared.trail).toEqual([]);
  expect(listen(historyCleared, 2).history).toHaveLength(1);
});

it('keeps both recent history and Previous navigation bounded at 100 actual plays', () => {
  let s = emptyQueue(); for (let i = 0; i < 130; i++) s = listen(s, i % 3);
  expect(s.history).toHaveLength(100); expect(s.trail).toHaveLength(100); expect(s.trailIndex).toBe(99);
});

it('history has separate account storage, restores navigation, and cannot resurrect a clear from another tab', () => {
  const a = new PlayerHistoryStore('A'), b = new PlayerHistoryStore('B');
  const data = listen(listen(emptyQueue(), 0), 1); expect(a.save(data)).toBe(true);
  expect(b.refresh()).toBeNull(); const other = new PlayerHistoryStore('A'); expect(other.initial.history).toHaveLength(2);
  other.save(emptyHistory(), true); expect(a.save(data)).toBe(false); expect(a.refresh()).toEqual(emptyHistory());
  expect(new PlayerHistoryStore('A').initial.history).toEqual([]);
});

it('rejects corrupt history, unsafe IDs/keys/timestamps and reconstructs URLs from IDs only', () => {
  const store = new PlayerHistoryStore('A'); store.save(listen(emptyQueue(), 0));
  const raw = localStorage.getItem(store.key!)!, data = JSON.parse(raw);
  data.history[0].track.url = 'javascript:bad'; expect(decodeHistory(JSON.stringify(data))!.history[0].track.url).toBe(songs[0].url);
  expect(decodeHistory('x'.repeat(400001))).toBeNull(); expect(decodeHistory('{}')).toBeNull();
  data.history[0].playedAt = -1; expect(decodeHistory(JSON.stringify(data))).toBeNull();
  localStorage.setItem(store.key!, '{'); expect(new PlayerHistoryStore('A').initial).toEqual(emptyHistory());
});
