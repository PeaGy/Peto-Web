import type { QueueEntry, RepeatMode } from './playerLibraryTypes';

export interface PlayerQueue {
  current: QueueEntry | null;
  queue: QueueEntry[];
  order: QueueEntry[];
  cyclePlayed: string[];
  repeat: RepeatMode;
  shuffle: boolean;
  request: number;
  autoplay: boolean;
  endedSerial: number;
}
export const emptyQueue = (): PlayerQueue => ({ current: null, queue: [], order: [], cyclePlayed: [], repeat: 'off', shuffle: false, request: 0, autoplay: false, endedSerial: 0 });
export type QueueAction =
  | { type: 'select'; entry: QueueEntry; autoplay: boolean }
  | { type: 'next' | 'shuffle' | 'repeat'; seed: number }
  | { type: 'ended'; seed: number; request: number; serial: number }
  | { type: 'restart' }
  | { type: 'append'; entries: QueueEntry[] }
  | { type: 'remove' | 'play-entry'; key: string }
  | { type: 'move'; key: string; offset: number }
  | { type: 'metadata'; videoId: string; title?: string; artist?: string; duration?: number };

function shuffled(entries: QueueEntry[], seed: number) {
  const result = [...entries]; let value = seed >>> 0;
  for (let index = result.length - 1; index > 0; index--) {
    value = (Math.imul(value, 1664525) + 1013904223) >>> 0;
    const other = Math.floor(value / 0x100000000 * (index + 1));
    [result[index], result[other]] = [result[other], result[index]];
  }
  return result;
}
function following(state: PlayerQueue) {
  if (!state.current) return state.order;
  const index = state.order.findIndex(entry => entry.key === state.current!.key);
  return [...state.order.slice(index + 1), ...state.order.slice(0, index)];
}
function restorePending(state: PlayerQueue) {
  const pending = new Set(state.queue.map(entry => entry.key));
  return following(state).filter(entry => pending.has(entry.key));
}
function advance(state: PlayerQueue, ended: boolean, seed: number): PlayerQueue {
  if (!state.current) return state;
  if (ended && state.repeat === 'one') return { ...state, request: state.request + 1, autoplay: true };
  if (!state.queue.length) return state.repeat === 'all' ? { ...state, request: state.request + 1, autoplay: true } : state;
  let queue = state.queue;
  let cyclePlayed = [...new Set([...state.cyclePlayed, state.current.key])];
  if (state.repeat === 'all' && state.shuffle && state.order.every(entry => cyclePlayed.includes(entry.key))) {
    queue = shuffled(queue, seed); cyclePlayed = [];
  }
  return { ...state, current: queue[0], queue: [...queue.slice(1), ...(state.repeat === 'all' ? [state.current] : [])], cyclePlayed,
    request: state.request + 1, autoplay: true };
}

/** Queue order is independent of the iframe; only actual ENDED events advance it. */
export function playerQueueReducer(state: PlayerQueue, action: QueueAction): PlayerQueue {
  switch (action.type) {
    case 'select': return { ...state, current: action.entry, order: [action.entry, ...restorePending(state)], cyclePlayed: [], request: state.request + 1, autoplay: action.autoplay };
    case 'next': return advance(state, false, action.seed);
    case 'restart': return state.current ? { ...state, request: state.request + 1, autoplay: true } : state;
    case 'ended': return action.request !== state.request || action.serial <= state.endedSerial ? state
      : advance({ ...state, endedSerial: action.serial }, true, action.seed);
    case 'append': return { ...state, queue: [...state.queue, ...action.entries], order: [...state.order, ...action.entries] };
    case 'play-entry': {
      const current = state.queue.find(entry => entry.key === action.key);
      if (!current) return state;
      const queue = [...state.queue.filter(entry => entry.key !== current.key), ...(state.repeat === 'all' && state.current ? [state.current] : [])];
      return { ...state, current, queue, cyclePlayed: [...new Set([...state.cyclePlayed, ...(state.current ? [state.current.key] : [])])], request: state.request + 1, autoplay: true };
    }
    case 'remove': return { ...state, queue: state.queue.filter(entry => entry.key !== action.key), order: state.order.filter(entry => entry.key !== action.key), cyclePlayed: state.cyclePlayed.filter(key => key !== action.key) };
    case 'move': {
      const from = state.queue.findIndex(entry => entry.key === action.key), to = from + action.offset;
      if (from < 0 || to < 0 || to >= state.queue.length) return state;
      const queue = [...state.queue]; const [entry] = queue.splice(from, 1); queue.splice(to, 0, entry);
      const active = new Set([...(state.current ? [state.current.key] : []), ...queue.map(item => item.key)]);
      return { ...state, queue, shuffle: false, order: [...(state.current ? [state.current] : []), ...queue, ...state.order.filter(item => !active.has(item.key))] };
    }
    case 'shuffle': return { ...state, shuffle: !state.shuffle, queue: state.shuffle ? restorePending(state) : shuffled(state.queue, action.seed), cyclePlayed: [] };
    case 'repeat': {
      const repeat: RepeatMode = state.repeat === 'off' ? 'all' : state.repeat === 'all' ? 'one' : 'off';
      if (repeat !== 'all') return { ...state, repeat };
      const pending = new Set(state.queue.map(entry => entry.key));
      const played = following(state).filter(entry => !pending.has(entry.key));
      return { ...state, repeat, cyclePlayed: [], queue: [...state.queue, ...(state.shuffle ? shuffled(played, action.seed) : played)] };
    }
    case 'metadata': {
      const update = (entry: QueueEntry): QueueEntry => entry.track.videoId !== action.videoId ? entry : { ...entry, track: { ...entry.track,
        ...(action.title ? { title: action.title } : {}), ...(action.artist ? { artist: action.artist } : {}), ...(action.duration && action.duration > 0 ? { duration: action.duration } : {}) } };
      return { ...state, current: state.current ? update(state.current) : null, queue: state.queue.map(update), order: state.order.map(update) };
    }
  }
}
