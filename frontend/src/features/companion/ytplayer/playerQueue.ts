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
  revision: number;
  cyclePrepared: boolean;
}
export const emptyQueue = (): PlayerQueue => ({ current: null, queue: [], order: [], cyclePlayed: [], repeat: 'off', shuffle: false, request: 0, autoplay: false, endedSerial: 0, revision: 0, cyclePrepared: false });
export type QueueAction =
  | { type: 'select'; entry: QueueEntry; autoplay: boolean }
  | { type: 'next' | 'shuffle' | 'repeat'; seed: number }
  | { type: 'ended'; seed: number; request: number; serial: number }
  | { type: 'restart' }
  | { type: 'set-repeat'; repeat: RepeatMode; seed: number }
  | { type: 'append'; entries: QueueEntry[] }
  | { type: 'remove' | 'play-entry'; key: string }
  | { type: 'move'; key: string; offset: number }
  | { type: 'control-entry'; operation: 'remove' | 'move' | 'play'; key: string; revision: number; position?: number; seed: number }
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
// Plan a shuffle boundary while the last song of the old cycle is still playing, so queue[0] is always the real next.
function prepareCycle(state: PlayerQueue, seed: number): PlayerQueue {
  if (!state.shuffle || state.repeat !== 'all' || !state.current || state.cyclePrepared
    || !state.order.every(entry => entry.key === state.current!.key || state.cyclePlayed.includes(entry.key))) return state;
  return { ...state, queue: shuffled(state.queue, seed), cyclePrepared: true };
}
export function nextPlayerTracks(state: PlayerQueue) {
  const onSkip = state.current ? state.queue[0]?.track ?? null : null;
  const automatic = state.current && (state.repeat === 'one' || (state.repeat === 'all' && !state.queue.length)) ? state.current.track : onSkip;
  return { automatic, onSkip, reason: !automatic ? 'empty' as const : state.repeat === 'one' ? 'loop_one' as const
    : state.queue.length ? 'queue' as const : 'loop_all' as const };
}
function advance(state: PlayerQueue, ended: boolean, seed: number): PlayerQueue {
  if (!state.current) return state;
  if (ended && state.repeat === 'one') return { ...state, request: state.request + 1, autoplay: true };
  if (!state.queue.length) return state.repeat === 'all' ? { ...state, request: state.request + 1, autoplay: true } : state;
  const queue = state.queue;
  const cyclePlayed = state.cyclePrepared ? [] : [...new Set([...state.cyclePlayed, state.current.key])];
  return prepareCycle({ ...state, current: queue[0], queue: [...queue.slice(1), ...(state.repeat === 'all' ? [state.current] : [])], cyclePlayed, cyclePrepared: false,
    request: state.request + 1, autoplay: true }, seed);
}

/** Queue order is independent of the iframe; only actual ENDED events advance it. */
export function playerQueueReducer(state: PlayerQueue, action: QueueAction): PlayerQueue {
  const result = reduceQueue(state, action);
  if (result === state) return state;
  // Pending items and current song always fit; bound old cycle history so enabling All cannot restore >200 upcoming items.
  let order = result.order;
  if (order.length > 201) {
    const keep = new Set([...(result.current ? [result.current.key] : []), ...result.queue.map(entry => entry.key)]);
    const history = order.filter(entry => !keep.has(entry.key));
    history.slice(Math.max(0, history.length - Math.max(0, 201 - keep.size))).forEach(entry => keep.add(entry.key));
    order = order.filter(entry => keep.has(entry.key));
  }
  return { ...result, order, revision: state.revision + (action.type === 'metadata' ? 0 : 1) };
}
function reduceQueue(state: PlayerQueue, action: QueueAction): PlayerQueue {
  switch (action.type) {
    case 'select': return { ...state, current: action.entry, order: [action.entry, ...restorePending(state)], cyclePlayed: [], cyclePrepared: false, request: state.request + 1, autoplay: action.autoplay };
    case 'control-entry': {
      if (action.revision !== state.revision || !state.queue.some(entry => entry.key === action.key)) return state;
      if (action.operation === 'remove') return reduceQueue(state, { type: 'remove', key: action.key });
      if (action.operation === 'play') return prepareCycle(reduceQueue(state, { type: 'play-entry', key: action.key }), action.seed);
      if (!action.position || action.position < 1 || action.position > state.queue.length) return state;
      return reduceQueue(state, { type: 'move', key: action.key, offset: action.position - 1 - state.queue.findIndex(entry => entry.key === action.key) });
    }
    case 'next': return advance(state, false, action.seed);
    case 'restart': return state.current ? { ...state, request: state.request + 1, autoplay: true } : state;
    case 'ended': return action.request !== state.request || action.serial <= state.endedSerial ? state
      : advance({ ...state, endedSerial: action.serial }, true, action.seed);
    case 'append': return state.queue.length + action.entries.length > 200 ? state
      : { ...state, queue: [...state.queue, ...action.entries], order: [...state.order, ...action.entries] };
    case 'play-entry': {
      const current = state.queue.find(entry => entry.key === action.key);
      if (!current) return state;
      const queue = [...state.queue.filter(entry => entry.key !== current.key), ...(state.repeat === 'all' && state.current ? [state.current] : [])];
      return { ...state, current, queue, cyclePrepared: false, cyclePlayed: [...new Set([...state.cyclePlayed, ...(state.current ? [state.current.key] : [])])], request: state.request + 1, autoplay: true };
    }
    case 'remove': return { ...state, queue: state.queue.filter(entry => entry.key !== action.key), order: state.order.filter(entry => entry.key !== action.key), cyclePlayed: state.cyclePlayed.filter(key => key !== action.key) };
    case 'move': {
      const from = state.queue.findIndex(entry => entry.key === action.key), to = from + action.offset;
      if (from < 0 || to < 0 || to >= state.queue.length) return state;
      const queue = [...state.queue]; const [entry] = queue.splice(from, 1); queue.splice(to, 0, entry);
      const active = new Set([...(state.current ? [state.current.key] : []), ...queue.map(item => item.key)]);
      return { ...state, queue, shuffle: false, cyclePrepared: false, order: [...(state.current ? [state.current] : []), ...queue, ...state.order.filter(item => !active.has(item.key))] };
    }
    case 'shuffle': return prepareCycle({ ...state, shuffle: !state.shuffle, queue: state.shuffle ? restorePending(state) : shuffled(state.queue, action.seed), cyclePlayed: [], cyclePrepared: false }, action.seed);
    case 'set-repeat':
    case 'repeat': {
      const repeat: RepeatMode = action.type === 'set-repeat' ? action.repeat : state.repeat === 'off' ? 'all' : state.repeat === 'all' ? 'one' : 'off';
      if (repeat === state.repeat) return state;
      if (repeat !== 'all') return { ...state, repeat, cyclePrepared: false };
      const pending = new Set(state.queue.map(entry => entry.key));
      const played = following(state).filter(entry => !pending.has(entry.key));
      return prepareCycle({ ...state, repeat, cyclePlayed: [], cyclePrepared: false, queue: [...state.queue, ...(state.shuffle ? shuffled(played, action.seed) : played)] }, action.seed);
    }
    case 'metadata': {
      const update = (entry: QueueEntry): QueueEntry => entry.track.videoId !== action.videoId ? entry : { ...entry, track: { ...entry.track,
        ...(action.title ? { title: action.title } : {}), ...(action.artist ? { artist: action.artist } : {}), ...(action.duration && action.duration > 0 ? { duration: action.duration } : {}) } };
      return { ...state, current: state.current ? update(state.current) : null, queue: state.queue.map(update), order: state.order.map(update) };
    }
  }
}
