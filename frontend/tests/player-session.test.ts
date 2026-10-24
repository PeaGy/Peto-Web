import { expect, it } from 'vitest';
import { emptyQueue, playerQueueReducer as reduce, type PlayerQueue } from '../src/features/companion/ytplayer/playerQueue';
import { mediaFromId } from '../src/features/companion/ytplayer/playerApi';

const entries = ['Soy4jGPHr3g', 'Soy4jGPHr3g', 'aircAruvnKk'].map((id, i) => ({ key: `q-${i}`, track: mediaFromId(id) }));
const initial = () => reduce(reduce(emptyQueue(), { type: 'select', entry: entries[0], autoplay: true }), { type: 'append', entries: entries.slice(1) });
const keys = (s: PlayerQueue) => s.queue.map(item => item.key);

it('bulk clear keeps current source; undo restores exact duplicate entries and playback without reloading', () => {
  const before = initial();
  const cleared = reduce(before, { type: 'clear_queue' });
  expect(cleared.current).toBe(before.current); expect(cleared.queue).toEqual([]);
  expect(cleared.request).toBe(before.request); expect(cleared.autoplay).toBe(true);
  const restored = reduce(cleared, { type: 'undo' });
  expect(keys(restored)).toEqual(keys(before)); expect(restored.request).toBe(before.request);
  expect(restored.undo).toBeNull(); expect(restored.revision).toBeGreaterThan(cleared.revision);
});

it('clear all and its undo invalidate old media events and restore stopped with a fresh source token', () => {
  const before = initial(), cleared = reduce(before, { type: 'clear_all' });
  expect(cleared.current).toBeNull(); expect(cleared.queue).toEqual([]); expect(cleared.order).toEqual([]);
  const idempotent = reduce(cleared, { type: 'clear_all' });
  const restored = reduce(idempotent, { type: 'undo' });
  expect(restored.current).toEqual(before.current); expect(keys(restored)).toEqual(keys(before));
  expect(restored.autoplay).toBe(false); expect(restored.request).toBeGreaterThan(cleared.request);
  expect(reduce(restored, { type: 'ended', request: before.request, serial: 55, seed: 1 })).toBe(restored);
  expect(reduce(restored, { type: 'undo' })).toBe(restored);
});

it('clear queue prunes old repeat cycles so enabling All cannot resurrect cleared entries', () => {
  let s = reduce(initial(), { type: 'next', seed: 42 });
  s = reduce(s, { type: 'clear_queue' });
  s = reduce(s, { type: 'set-repeat', repeat: 'all', seed: 42 });
  expect(s.queue).toEqual([]); expect(s.order).toEqual([s.current]);
});

it('undo is one level; no-op removals and metadata updates preserve it, playback/mode changes invalidate it', () => {
  const before = initial(), removed = reduce(before, { type: 'remove', key: entries[1].key });
  expect(reduce(removed, { type: 'remove', key: 'missing' })).toBe(removed);
  const metadata = reduce(removed, { type: 'metadata', videoId: entries[0].track.videoId, title: 'Resolved title' });
  expect(metadata.undo).not.toBeNull(); expect(keys(reduce(metadata, { type: 'undo' }))).toEqual(keys(before));
  expect(reduce(removed, { type: 'next', seed: 1 }).undo).toBeNull();
  expect(reduce(removed, { type: 'set-repeat', repeat: 'one', seed: 1 }).undo).toBeNull();
  const moved = reduce(before, { type: 'move', key: entries[2].key, offset: -1 });
  expect(keys(reduce(moved, { type: 'undo' }))).toEqual(keys(before));
});

it('undo after append restores the previous queue without touching the current playback request', () => {
  const s = initial(), added = reduce(s, { type: 'append', entries: [{ ...entries[1], key: 'extra' }] });
  const undo = reduce(added, { type: 'undo' });
  expect(keys(undo)).toEqual(keys(s)); expect(undo.current).toBe(s.current); expect(undo.request).toBe(s.request);
});
