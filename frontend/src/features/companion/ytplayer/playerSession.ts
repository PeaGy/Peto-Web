import { emptyQueue, type PlayerQueue } from './playerQueue';
import type { QueueEntry } from './playerLibraryTypes';

const PREFIX = 'peto-player-session-v1:';
const MAX_LENGTH = 400_000;
const MAX_SECONDS = 604800;
const seconds = (value: number) => Number.isFinite(value) ? Math.min(MAX_SECONDS, Math.max(0, value)) : 0;
const volumeOf = (value: number) => Number.isFinite(value) ? Math.round(Math.min(100, Math.max(0, value))) : 60;
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= MAX_SECONDS;
const keyOf = (owner?: string) => owner && owner.length <= 256 ? PREFIX + encodeURIComponent(owner) : null;
const bounded = (value: string, length: number) => Array.from(value).slice(0, length).join('');

export interface RestoredPlayerSession { queue: PlayerQueue; position: number; volume: number }

/** Stored URLs, playback intents, revisions and Undo are never trusted or restored. */
export function decodePlayerSession(raw: string): RestoredPlayerSession | null {
  if (raw.length > MAX_LENGTH) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!record(value) || value.version !== 1 || !Array.isArray(value.order) || value.order.length > 201
      || !Array.isArray(value.queue) || value.queue.length > 200 || !Array.isArray(value.cyclePlayed)
      || value.cyclePlayed.length > 201 || typeof value.repeat !== 'string' || !['off', 'all', 'one'].includes(value.repeat)
      || typeof value.shuffle !== 'boolean' || typeof value.cyclePrepared !== 'boolean'
      || !number(value.position) || !number(value.volume) || value.volume > 100) return null;
    const entries = new Map<string, QueueEntry>();
    for (const [index, item] of value.order.entries()) {
      if (!record(item) || typeof item.key !== 'string' || !/^[A-Za-z0-9_-]{1,100}$/.test(item.key) || entries.has(item.key)
        || !record(item.track)) return null;
      const t = item.track;
      if (typeof t.videoId !== 'string' || !/^[A-Za-z0-9_-]{11}$/.test(t.videoId)
        || typeof t.title !== 'string' || Array.from(t.title).length > 500 || typeof t.artist !== 'string' || Array.from(t.artist).length > 200
        || !number(t.startSeconds) || !number(t.duration)) return null;
      entries.set(item.key, { key: `restored-${index}`, track: { videoId: t.videoId, title: t.title, artist: t.artist,
        startSeconds: t.startSeconds, duration: t.duration,
        url: `https://www.youtube.com/watch?v=${t.videoId}${t.startSeconds ? `&t=${t.startSeconds}s` : ''}` } });
    }
    const keys = (items: unknown[]) => items.every(key => typeof key === 'string' && entries.has(key)) && new Set(items).size === items.length;
    if (!keys(value.queue) || !keys(value.cyclePlayed) || (value.current !== null && (typeof value.current !== 'string' || !entries.has(value.current)))
      || value.queue.includes(value.current)) return null;
    const current = typeof value.current === 'string' ? entries.get(value.current)! : null;
    if (!current && !value.queue.length) return null;
    const position = current && current.track.duration > 0 && value.position >= current.track.duration ? current.track.startSeconds : value.position;
    return { queue: { ...emptyQueue(), current, queue: value.queue.map(key => entries.get(key as string)!), order: [...entries.values()],
      cyclePlayed: value.cyclePlayed.map(key => entries.get(key as string)!.key), repeat: value.repeat as PlayerQueue['repeat'],
      shuffle: value.shuffle, cyclePrepared: value.cyclePrepared }, position: current ? position : 0, volume: volumeOf(value.volume) };
  } catch { return null; }
}

export function hasPlayerSession(owner?: string) {
  const key = keyOf(owner);
  try { return !!key && localStorage.getItem(key) !== null; } catch { return false; }
}

/** One browser-local, account-scoped snapshot. Progress is throttled; explicit edits/clear flush synchronously. */
export class PlayerSessionStore {
  readonly initial: RestoredPlayerSession | null;
  private key: string | null;
  private lastRaw: string | null = null;
  private lastFlush = 0;
  private state: PlayerQueue;
  private position: number;
  private volume: number;
  private failed = false;
  constructor(owner?: string) {
    this.key = keyOf(owner);
    let restored: RestoredPlayerSession | null = null;
    try {
      this.lastRaw = this.key ? localStorage.getItem(this.key) : null;
      if (this.lastRaw !== null) {
        restored = decodePlayerSession(this.lastRaw);
        if (!restored && this.key) { localStorage.removeItem(this.key); this.lastRaw = null; }
      }
    } catch { /* A blocked store never prevents using Player in memory. */ }
    this.initial = restored;
    this.state = restored?.queue ?? emptyQueue();
    this.position = restored?.position ?? 0;
    this.volume = restored?.volume ?? 60;
  }
  saveQueue(state: PlayerQueue, explicit: boolean) {
    if (this.state.current?.key !== state.current?.key) this.position = state.current?.track.startSeconds ?? 0;
    this.state = state;
    return this.flush(true, explicit);
  }
  remember(key: string | null, position: number | undefined, volume: number, immediate = false) {
    if (key !== (this.state.current?.key ?? null)) return !this.failed;
    if (position !== undefined) this.position = seconds(position);
    this.volume = volumeOf(volume);
    return this.flush(immediate);
  }
  flush(immediate = true, explicit = false) {
    if (!this.key) return true;
    if (!immediate && Date.now() - this.lastFlush < 5000) return !this.failed;
    try {
      const existing = localStorage.getItem(this.key);
      // A stale tab's timer/pagehide must not overwrite another tab's newer edit or Clear All.
      if (!explicit && existing !== this.lastRaw) return !this.failed;
      const s = this.state;
      const keys = new Set(s.order.map(entry => entry.key));
      const raw = !s.current && !s.queue.length ? null : JSON.stringify({ version: 1,
        current: s.current?.key ?? null, queue: s.queue.map(entry => entry.key),
        order: s.order.map(entry => ({ key: entry.key, track: { videoId: entry.track.videoId,
          title: bounded(entry.track.title, 500), artist: bounded(entry.track.artist, 200),
          startSeconds: seconds(entry.track.startSeconds), duration: seconds(entry.track.duration) } })),
        cyclePlayed: s.cyclePlayed.filter(key => keys.has(key)), cyclePrepared: s.cyclePrepared, repeat: s.repeat, shuffle: s.shuffle,
        position: seconds(this.position), volume: this.volume });
      if (raw && raw.length > MAX_LENGTH) { this.failed = true; return false; }
      if (raw !== existing) { if (raw === null) localStorage.removeItem(this.key); else localStorage.setItem(this.key, raw); }
      this.lastRaw = raw; this.lastFlush = Date.now(); this.failed = false;
      return true;
    } catch { this.failed = true; return false; }
  }
}
