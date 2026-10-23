import type { DemoTrack } from './data';

export type RepeatMode = 'off' | 'all' | 'one';
export interface QueueEntry { key: string; track: DemoTrack }
export interface QueuePlayback {
  current: QueueEntry;
  queue: QueueEntry[];
  /** Includes played entries so enabling repeat later can restore the whole queue. */
  order: QueueEntry[];
  cyclePlayed: string[];
  repeat: RepeatMode;
  shuffle: boolean;
  playing: boolean;
  position: number;
}
export type PlaybackAction =
  | { type: 'play'; playing: boolean; seed: number }
  | { type: 'seek'; position: number }
  | { type: 'tick' | 'next' | 'shuffle' | 'repeat'; seed: number }
  | { type: 'select'; entry: QueueEntry; playing: boolean }
  | { type: 'play-entry' | 'remove'; key: string }
  | { type: 'append'; entries: QueueEntry[] }
  | { type: 'move'; key: string; offset: number };

export function createPlayback(track: DemoTrack, tracks: DemoTrack[]): QueuePlayback {
  const current = { key: 'current-0', track };
  const queue = tracks.map((item, index) => ({ key: `initial-${index}`, track: item }));
  return { current, queue, order: [current, ...queue], cyclePlayed: [], repeat: 'off', shuffle: false, playing: false, position: 13 };
}

// A seed belongs to the action: replaying a reducer in Strict Mode gives the same order.
function shuffled(entries: QueueEntry[], seed: number) {
  const result = [...entries];
  let value = seed >>> 0;
  for (let index = result.length - 1; index > 0; index--) {
    value = (Math.imul(value, 1664525) + 1013904223) >>> 0;
    const other = Math.floor(value / 0x100000000 * (index + 1));
    [result[index], result[other]] = [result[other], result[index]];
  }
  return result;
}

function following(state: QueuePlayback) {
  const index = state.order.findIndex(entry => entry.key === state.current.key);
  return [...state.order.slice(index + 1), ...state.order.slice(0, index)];
}
function restorePending(state: QueuePlayback) {
  const pending = new Set(state.queue.map(entry => entry.key));
  return following(state).filter(entry => pending.has(entry.key));
}
function advance(state: QueuePlayback, ended: boolean, seed: number): QueuePlayback {
  if (ended && state.repeat === 'one') return { ...state, position: 0, playing: true };
  if (!state.queue.length) return state.repeat === 'all'
    ? { ...state, position: 0, playing: true }
    : { ...state, position: state.current.track.duration, playing: false };

  let queue = state.queue;
  let cyclePlayed = [...new Set([...state.cyclePlayed, state.current.key])];
  if (state.repeat === 'all' && state.shuffle && state.order.every(entry => cyclePlayed.includes(entry.key))) {
    // A fresh round, without repeating the just-finished entry across the boundary.
    queue = shuffled(queue, seed);
    cyclePlayed = [];
  }
  return { ...state, current: queue[0], queue: [...queue.slice(1), ...(state.repeat === 'all' ? [state.current] : [])],
    cyclePlayed, position: 0, playing: true };
}

/** Mock playback only; no media API or persisted state. */
export function playbackReducer(state: QueuePlayback, action: PlaybackAction): QueuePlayback {
  switch (action.type) {
    case 'play':
      if (action.playing && state.position >= state.current.track.duration) {
        return state.queue.length || state.repeat !== 'off' ? advance(state, true, action.seed) : { ...state, position: 0, playing: true };
      }
      return { ...state, playing: action.playing };
    case 'seek': return { ...state, position: Math.max(0, Math.min(action.position, state.current.track.duration)) };
    case 'tick': {
      if (!state.playing) return state;
      const next = { ...state, position: Math.min(state.position + 1, state.current.track.duration) };
      return next.position >= state.current.track.duration ? advance(next, true, action.seed) : next;
    }
    case 'next': return advance(state, false, action.seed);
    case 'select': return { ...state, current: action.entry, order: [action.entry, ...restorePending(state)], cyclePlayed: [], position: 0, playing: action.playing };
    case 'play-entry': {
      const entry = state.queue.find(item => item.key === action.key);
      if (!entry) return state;
      return { ...state, current: entry, queue: [...state.queue.filter(item => item.key !== entry.key), ...(state.repeat === 'all' ? [state.current] : [])],
        cyclePlayed: [...new Set([...state.cyclePlayed, state.current.key])], position: 0, playing: true };
    }
    case 'append': return { ...state, queue: [...state.queue, ...action.entries], order: [...state.order, ...action.entries] };
    case 'remove': return { ...state, queue: state.queue.filter(entry => entry.key !== action.key), order: state.order.filter(entry => entry.key !== action.key),
      cyclePlayed: state.cyclePlayed.filter(key => key !== action.key) };
    case 'move': {
      const from = state.queue.findIndex(entry => entry.key === action.key), to = from + action.offset;
      if (from < 0 || to < 0 || to >= state.queue.length) return state;
      const queue = [...state.queue]; const [entry] = queue.splice(from, 1); queue.splice(to, 0, entry);
      const active = new Set([state.current.key, ...queue.map(item => item.key)]);
      return { ...state, queue, shuffle: false, order: [state.current, ...queue, ...state.order.filter(item => !active.has(item.key))] };
    }
    case 'shuffle': return { ...state, shuffle: !state.shuffle, queue: state.shuffle ? restorePending(state) : shuffled(state.queue, action.seed), cyclePlayed: [] };
    case 'repeat': {
      const repeat: RepeatMode = state.repeat === 'off' ? 'all' : state.repeat === 'all' ? 'one' : 'off';
      if (repeat !== 'all') return { ...state, repeat };
      const pending = new Set(state.queue.map(entry => entry.key));
      const played = following(state).filter(entry => !pending.has(entry.key));
      return { ...state, repeat, cyclePlayed: [], queue: [...state.queue, ...(state.shuffle ? shuffled(played, action.seed) : played)] };
    }
  }
}
