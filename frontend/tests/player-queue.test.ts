import { describe, expect, it } from 'vitest';
import { emptyQueue, nextPlayerTracks, playerQueueReducer as reduce, type PlayerQueue } from '../src/features/companion/ytplayer/playerQueue';
import { mediaFromId } from '../src/features/companion/ytplayer/playerApi';

const entries = ['Soy4jGPHr3g', 'aircAruvnKk', 'e1xCOsgWG0M', 'HDz9dSuAI4s'].map((id, index) => ({ key: String(index), track: mediaFromId(id) }));
const initial = () => reduce(reduce(emptyQueue(), { type: 'select', entry: entries[0], autoplay: false }), { type: 'append', entries: entries.slice(1) });
const next = (state: PlayerQueue) => reduce(state, { type: 'next', seed: 42 });
const loop = (state: PlayerQueue) => reduce(state, { type: 'repeat', seed: 42 });
const shuffle = (state: PlayerQueue) => reduce(state, { type: 'shuffle', seed: 42 });
const end = (state: PlayerQueue, serial = state.endedSerial + 1) => reduce(state, { type: 'ended', request: state.request, serial, seed: 42 });
const keys = (state: PlayerQueue) => state.queue.map(entry => entry.key);

describe('production queue', () => {
  it('long listening sessions cannot restore an oversized queue when switching to loop all', () => {
    let state = initial();
    for (let i = 0; i < 260; i++) {
      state = reduce(state, { type: 'append', entries: [{ key: `new-${i}`, track: entries[0].track }] });
      state = next(state);
    }
    expect(state.order.length).toBeLessThanOrEqual(201);
    state = loop(state);
    expect(state.queue.length).toBeLessThanOrEqual(200);
    expect(new Set([state.current?.key, ...keys(state)]).size).toBe(state.queue.length + 1);
  });
  it('the visible first item and reported next match actual playback across every all/shuffle boundary', () => {
    let state = shuffle(loop(initial()));
    for (let index = 0; index < 100; index++) {
      const visible = state.queue[0].track.videoId;
      expect(nextPlayerTracks(state).automatic?.videoId).toBe(visible);
      state = reduce(state, { type: 'ended', request: state.request, serial: state.endedSerial + 1, seed: index * 9271 });
      expect(state.current?.track.videoId).toBe(visible);
    }
    const one = reduce(state, { type: 'set-repeat', repeat: 'one', seed: 1 });
    expect(nextPlayerTracks(one).automatic).toBe(one.current?.track);
    expect(nextPlayerTracks(one).onSkip).toBe(one.queue[0].track);
    let solo = initial(); for (const entry of solo.queue) solo = reduce(solo, { type: 'remove', key: entry.key });
    solo = loop(solo);
    expect(nextPlayerTracks(solo)).toMatchObject({ automatic: solo.current?.track, onSkip: null, reason: 'loop_all' });
  });
  it('ordinal mutations use entry identity plus queue revision, and metadata updates do not invalidate a selection', () => {
    let state = reduce(initial(), { type: 'append', entries: [{ ...entries[1], key: 'duplicate' }] });
    const revision = state.revision, key = state.queue[2].key, request = state.request;
    state = reduce(state, { type: 'metadata', videoId: entries[1].track.videoId, title: 'Updated title' });
    expect(state.revision).toBe(revision);
    state = reduce(state, { type: 'control-entry', operation: 'remove', key, revision, seed: 42 });
    expect(state.queue.some(entry => entry.key === key)).toBe(false);
    expect(state.queue.some(entry => entry.key === 'duplicate')).toBe(true);
    expect(state.request).toBe(request);
    expect(reduce(state, { type: 'control-entry', operation: 'remove', key: state.queue[0].key, revision, seed: 42 })).toBe(state);
    const moved = reduce(state, { type: 'control-entry', operation: 'move', key: 'duplicate', revision: state.revision, position: 1, seed: 42 });
    expect(moved.queue[0].key).toBe('duplicate');
    const selected = reduce(moved, { type: 'control-entry', operation: 'play', key: 'duplicate', revision: moved.revision, seed: 42 });
    expect(selected.current?.key).toBe('duplicate'); expect(selected.autoplay).toBe(true);
  });
  it('explicit repeat one/off never transiently enables repeat all or restores already-played tracks', () => {
    const state = next(initial());
    const one = reduce(state, { type: 'set-repeat', repeat: 'one', seed: 42 });
    expect(keys(one)).toEqual(keys(state));
    expect(one.repeat).toBe('one');
    expect(reduce(one, { type: 'set-repeat', repeat: 'one', seed: 42 })).toBe(one);
    const all = reduce(one, { type: 'set-repeat', repeat: 'all', seed: 42 });
    expect(keys(all)).toContain('0');
  });
  it('starts empty without a playback intent; a pasted video cues and an explicit next plays', () => {
    expect(emptyQueue().current).toBeNull();
    let state = initial(); expect(state.autoplay).toBe(false);
    state = next(state); expect(state.current?.key).toBe('1'); expect(state.autoplay).toBe(true);
    expect(keys(state)).toEqual(['2', '3']);
  });
  it('consumes an ended event once and ignores events from the previous source', () => {
    const first = initial(), second = end(first);
    expect(second.current?.key).toBe('1');
    expect(reduce(second, { type: 'ended', request: first.request, serial: 2, seed: 42 })).toBe(second);
    const last = end(end(second));
    expect(last.queue).toEqual([]); const stopped = end(last);
    expect(stopped.request).toBe(last.request);
    expect(end(stopped, stopped.endedSerial)).toBe(stopped);
  });
  it('repeat one reloads the same video with a new intent; next bypasses it', () => {
    const state = loop(loop(initial())); const repeated = end(state);
    expect(repeated.current).toEqual(state.current); expect(repeated.queue).toEqual(state.queue);
    expect(repeated.request).toBe(state.request + 1); expect(repeated.autoplay).toBe(true);
    expect(next(repeated).current?.key).toBe('1');
  });
  it('all + shuffle completes each round, avoids adjacent repeats and keeps unique queue entry identities', () => {
    let state = shuffle(loop(initial())); let last = '';
    for (let round = 0; round < 4; round++) {
      const visited: string[] = [];
      for (let index = 0; index < 4; index++) {
        expect(state.current?.key).not.toBe(last); last = state.current!.key;
        visited.push(last); state = end(state);
        expect(new Set([state.current!.key, ...keys(state)]).size).toBe(4);
      }
      expect(visited.sort()).toEqual(['0', '1', '2', '3']);
    }
  });
  it('enabling all later restores played entries but not explicitly deleted videos', () => {
    let state = next(initial()); state = reduce(state, { type: 'remove', key: '2' }); state = loop(state);
    expect(keys(state)).toEqual(['3', '0']);
    for (let i = 0; i < 8; i++) { state = end(state); expect([state.current!.key, ...keys(state)]).not.toContain('2'); }
  });
  it('turning shuffle off restores remaining order and manual ordering disables shuffle', () => {
    let state = shuffle(initial()); expect(state.current?.key).toBe('0');
    expect(keys(shuffle(state))).toEqual(['1', '2', '3']);
    const key = state.queue[1].key;
    state = reduce(state, { type: 'move', key, offset: -1 });
    expect(state.shuffle).toBe(false); expect(state.queue[0].key).toBe(key);
  });
  it('accepts duplicates as separate entries, selecting from an empty player and metadata cannot restart playback', () => {
    let state = reduce(emptyQueue(), { type: 'append', entries: [entries[0], { ...entries[0], key: 'duplicate' }] });
    state = reduce(state, { type: 'play-entry', key: 'duplicate' });
    expect(state.current?.key).toBe('duplicate'); expect(keys(state)).toEqual(['0']);
    const metadata = reduce(state, { type: 'metadata', videoId: entries[0].track.videoId, title: 'Real title', artist: 'Channel', duration: 143 });
    expect(metadata.current?.track.title).toBe('Real title'); expect(metadata.queue[0].track.duration).toBe(143);
    expect(metadata.request).toBe(state.request); expect(metadata.autoplay).toBe(state.autoplay);
  });
  it('repeat all/one with a single remaining item restarts, while off does not request another playback', () => {
    let state = initial(); for (const entry of state.queue) state = reduce(state, { type: 'remove', key: entry.key });
    expect(end(state).request).toBe(state.request);
    expect(end(loop(state)).request).toBe(state.request + 1);
    expect(end(loop(loop(state))).request).toBe(state.request + 1);
  });
});
