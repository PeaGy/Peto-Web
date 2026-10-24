import type { MediaTrack } from './playerLibraryTypes';
import type { PlayerQueue } from './playerQueue';

export interface ListeningEntry { key: string; track: MediaTrack; playedAt: number }
export interface HistorySnapshot { history: ListeningEntry[]; trail: MediaTrack[]; trailIndex: number }
export const emptyHistory = (): HistorySnapshot => ({ history: [], trail: [], trailIndex: -1 });
export const sameSong = (a: MediaTrack, b: MediaTrack) => a.videoId === b.videoId && a.startSeconds === b.startSeconds;
export function previousChoice(state: PlayerQueue) {
  if (!state.current || state.trailIndex < 0) return null;
  const index = state.trailIndex - Number(sameSong(state.current.track, state.trail[state.trailIndex]));
  return index >= 0 ? { index, track: state.trail[index] } : null;
}
export function recordPlayed(state: PlayerQueue, request: number, videoId: string, key: string, playedAt: number): PlayerQueue {
  if (!state.current || request !== state.request || videoId !== state.current.track.videoId || state.recordedRequest === request) return state;
  const track = state.current.track;
  let trail = state.trail, trailIndex = state.trailIndex;
  if (state.pendingTrailIndex !== null && trail[state.pendingTrailIndex] && sameSong(track, trail[state.pendingTrailIndex])) trailIndex = state.pendingTrailIndex;
  else if (trailIndex < 0 || !sameSong(track, trail[trailIndex])) {
    trail = [...trail.slice(0, trailIndex + 1), track].slice(-100); trailIndex = trail.length - 1;
  }
  const history = state.history[0] && sameSong(state.history[0].track, track)
    ? [{ ...state.history[0], track, playedAt }, ...state.history.slice(1)] : [{ key, track, playedAt }, ...state.history].slice(0, 100);
  return { ...state, history, trail, trailIndex, recordedRequest: request, pendingTrailIndex: null,
    historyRevision: state.historyRevision + Number(history !== state.history) };
}

const PREFIX = 'peto-player-history-v1:';
const MAX_LENGTH = 400000;
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const seconds = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 604800;
const bounded = (value: string, limit: number) => Array.from(value).slice(0, limit).join('');
const keyOf = (owner?: string) => owner && owner.length <= 256 ? PREFIX + encodeURIComponent(owner) : null;
function trackFrom(value: unknown): MediaTrack | null {
  if (!object(value) || typeof value.videoId !== 'string' || !/^[A-Za-z0-9_-]{11}$/.test(value.videoId)
    || typeof value.title !== 'string' || Array.from(value.title).length > 500 || typeof value.artist !== 'string'
    || Array.from(value.artist).length > 200 || !seconds(value.startSeconds) || !seconds(value.duration)) return null;
  return { videoId: value.videoId, title: value.title, artist: value.artist, startSeconds: value.startSeconds, duration: value.duration,
    url: `https://www.youtube.com/watch?v=${value.videoId}${value.startSeconds ? `&t=${value.startSeconds}s` : ''}` };
}
export function decodeHistory(raw: string): HistorySnapshot | null {
  if (raw.length > MAX_LENGTH) return null;
  try {
    const data: unknown = JSON.parse(raw);
    if (!object(data) || data.version !== 1 || !Array.isArray(data.history) || data.history.length > 100 || !Array.isArray(data.trail)
      || data.trail.length > 100 || !Number.isInteger(data.trailIndex) || (data.trailIndex as number) < -1
      || (data.trailIndex as number) >= data.trail.length || (data.trail.length > 0 && data.trailIndex === -1)) return null;
    const history: ListeningEntry[] = [], trail: MediaTrack[] = [], keys = new Set<string>();
    for (const item of data.history) {
      if (!object(item) || typeof item.key !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(item.key) || keys.has(item.key)
        || !Number.isSafeInteger(item.playedAt) || (item.playedAt as number) < 0 || (item.playedAt as number) > 8640000000000000) return null;
      const track = trackFrom(item.track); if (!track) return null;
      keys.add(item.key); history.push({ key: item.key, track, playedAt: item.playedAt as number });
    }
    for (const value of data.trail) { const track = trackFrom(value); if (!track) return null; trail.push(track); }
    return { history, trail, trailIndex: data.trailIndex as number };
  } catch { return null; }
}
export function hasPlayerHistory(owner?: string) {
  try { const key = keyOf(owner); return !!key && localStorage.getItem(key) !== null; } catch { return false; }
}
/** Separate from the listening session so Clear All and older bundles cannot delete listening history. */
export class PlayerHistoryStore {
  readonly key: string | null;
  readonly initial: HistorySnapshot;
  private raw: string | null = null;
  failed = false;
  constructor(owner?: string) { this.key = keyOf(owner); this.initial = this.refresh() ?? emptyHistory(); }
  refresh(): HistorySnapshot | null {
    if (!this.key) return null;
    try {
      const raw = localStorage.getItem(this.key); if (raw === this.raw) return null;
      this.raw = raw; const value = raw ? decodeHistory(raw) : emptyHistory();
      if (!value) { localStorage.removeItem(this.key); this.raw = null; }
      this.failed = false; return value ?? emptyHistory();
    } catch { this.failed = true; return null; }
  }
  save(value: HistorySnapshot, clear = false) {
    if (!this.key) return true;
    try {
      if (!clear && localStorage.getItem(this.key) !== this.raw) { this.failed = true; return false; }
      const track = (t: MediaTrack) => ({ videoId: t.videoId, title: bounded(t.title, 500), artist: bounded(t.artist, 200),
        startSeconds: Math.min(604800, Math.max(0, t.startSeconds)), duration: Math.min(604800, Math.max(0, t.duration)) });
      const raw = !value.history.length && !value.trail.length ? null : JSON.stringify({ version: 1,
        history: value.history.map(item => ({ ...item, track: track(item.track) })), trail: value.trail.map(track), trailIndex: value.trailIndex });
      if (raw && raw.length > MAX_LENGTH) { this.failed = true; return false; }
      if (raw !== this.raw || clear) { if (raw === null) localStorage.removeItem(this.key); else localStorage.setItem(this.key, raw); }
      this.raw = raw; this.failed = false; return true;
    } catch { this.failed = true; return false; }
  }
}
