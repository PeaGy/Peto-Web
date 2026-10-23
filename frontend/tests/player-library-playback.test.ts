import { describe, expect, it } from 'vitest';
import { TRACKS } from '../src/prototypes/player-library/data';
import { createPlayback, playbackReducer as reduce, type QueuePlayback } from '../src/prototypes/player-library/queuePlayback';

const initial = () => createPlayback(TRACKS[0], TRACKS.slice(1));
const keys = (state: QueuePlayback) => state.queue.map(entry => entry.key);
const next = (state: QueuePlayback, seed = 42) => reduce(state, { type: 'next', seed });
const loop = (state: QueuePlayback) => reduce(state, { type: 'repeat', seed: 42 });
const shuffle = (state: QueuePlayback) => reduce(state, { type: 'shuffle', seed: 42 });
function end(state: QueuePlayback) {
  return reduce({ ...state, playing: true, position: state.current.track.duration - 1 }, { type: 'tick', seed: 42 });
}

describe('queue preview playback', () => {
  it('cycles off → all → one → off without restarting the current song', () => {
    let state = initial();
    const current = state.current;
    for (const repeat of ['all', 'one', 'off']) {
      state = loop(state);
      expect(state.repeat).toBe(repeat); expect(state.current).toBe(current); expect(state.position).toBe(13);
    }
  });

  it('repeat all rotates the complete queue without dropping or duplicating entries', () => {
    let state = loop(initial());
    const original = state.order.map(entry => entry.key);
    for (let round = 0; round < 3; round++) {
      const visited: string[] = [];
      for (let step = 0; step < original.length; step++) {
        visited.push(state.current.key); state = end(state);
        expect(new Set([state.current.key, ...keys(state)]).size).toBe(original.length);
      }
      expect(visited).toEqual(original);
      expect(state.current.key).toBe(original[0]); expect(state.playing).toBe(true);
    }
  });

  it('repeat one restarts on end, while an explicit next still skips the song', () => {
    const state = shuffle(loop(loop(initial())));
    const repeated = end(state);
    expect(repeated.current).toBe(state.current); expect(repeated.queue).toEqual(state.queue);
    expect(repeated.position).toBe(0); expect(repeated.playing).toBe(true);
    const skipped = next(repeated);
    expect(skipped.current).toEqual(state.queue[0]); expect(skipped.queue).toHaveLength(state.queue.length - 1);
  });

  it('off stops at the end; all and one can repeat a single remaining song', () => {
    let state = initial();
    for (const entry of state.queue) state = reduce(state, { type: 'remove', key: entry.key });
    const stopped = end(state);
    expect(stopped.playing).toBe(false); expect(stopped.position).toBe(state.current.track.duration);
    for (const repeated of [end(loop(state)), end(loop(loop(state)))]) {
      expect(repeated.current).toBe(state.current); expect(repeated.queue).toEqual([]);
      expect(repeated.position).toBe(0); expect(repeated.playing).toBe(true);
    }
  });

  it('enabling repeat later includes played songs but never restores explicitly removed entries', () => {
    let state = initial();
    const removed = state.queue[1].key;
    state = reduce(state, { type: 'remove', key: removed });
    state = next(state);
    state = loop(state);
    expect(keys(state)).toEqual(['initial-2', 'current-0']);
    for (let count = 0; count < 8; count++) {
      state = next(state);
      expect([state.current.key, ...keys(state)]).not.toContain(removed);
    }
  });

  it('shuffle keeps the current song and plays each pending entry once, without mutating the original state', () => {
    const original = initial();
    let state = shuffle(original);
    expect(state.current).toBe(original.current); expect(state.position).toBe(13);
    expect(keys(state)).not.toEqual(keys(original)); expect([...keys(state)].sort()).toEqual([...keys(original)].sort());
    const visited: string[] = [];
    while (state.queue.length) { state = next(state); visited.push(state.current.key); }
    expect(new Set(visited).size).toBe(3); expect([...visited].sort()).toEqual([...keys(original)].sort());
    expect(end(state).playing).toBe(false);
    expect(keys(original)).toEqual(['initial-0', 'initial-1', 'initial-2']);
    expect(shuffle(original)).toEqual(shuffle(original)); // Strict Mode may replay the same action.
  });

  it('turning shuffle off restores the remaining canonical order after skipping and adding duplicate videos', () => {
    let state = shuffle(initial());
    state = next(state);
    state = reduce(state, { type: 'append', entries: [{ key: 'duplicate-tetris', track: TRACKS[0] }] });
    const pending = new Set(keys(state));
    const index = state.order.findIndex(entry => entry.key === state.current.key);
    const expected = [...state.order.slice(index + 1), ...state.order.slice(0, index)].filter(entry => pending.has(entry.key));
    state = shuffle(state);
    expect(state.shuffle).toBe(false); expect(state.queue).toEqual(expected);
    expect(keys(state)).toContain('duplicate-tetris');
  });

  it('shuffle + all completes each round and avoids immediately repeating the last entry across rounds', () => {
    let state = shuffle(loop(initial()));
    const all = state.order.map(entry => entry.key).sort();
    let last: string | undefined;
    for (let round = 0; round < 4; round++) {
      const visited: string[] = [];
      for (let step = 0; step < all.length; step++) {
        expect(state.current.key).not.toBe(last);
        last = state.current.key; visited.push(last);
        state = next(state, 77 + round);
      }
      expect(visited.sort()).toEqual(all);
    }
  });

  it('manual ordering disables shuffle and removed items stay removed when modes change', () => {
    let state = shuffle(initial());
    const moved = state.queue[1].key, removed = state.queue[2].key;
    state = reduce(state, { type: 'move', key: moved, offset: -1 });
    expect(state.shuffle).toBe(false); expect(state.queue[0].key).toBe(moved);
    state = reduce(state, { type: 'remove', key: removed });
    state = loop(shuffle(state));
    expect([state.current.key, ...keys(state)]).not.toContain(removed);
  });

  it('a new source preserves pending entries, and duplicate track IDs remain separate queue entries', () => {
    let state = loop(initial());
    state = reduce(state, { type: 'append', entries: [{ key: 'duplicate', track: TRACKS[0] }] });
    state = reduce(state, { type: 'play-entry', key: 'duplicate' });
    expect(state.current.key).toBe('duplicate'); expect(keys(state)).toContain('current-0');
    const pending = keys(state);
    state = reduce(state, { type: 'select', entry: { key: 'external', track: TRACKS[2] }, playing: false });
    expect(keys(state)).toEqual(pending); expect(state.playing).toBe(false);
    expect(state.order).toHaveLength(pending.length + 1);
  });
});
