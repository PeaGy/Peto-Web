import type { usePlayerLibrary } from './usePlayerLibrary';
import type { MediaTrack } from './playerLibraryTypes';
import { mediaFromId } from './playerApi';
import { controlTrack } from './playerLibraryControl';
import { waitForPlayer, type PlayerCommand, type PlayerResult, type PlayerSnapshot } from './playerControl';

interface Context {
  library: () => ReturnType<typeof usePlayerLibrary>;
  snapshot: () => PlayerSnapshot;
  available: () => boolean;
  windowRevision: () => number;
  play: (track: MediaTrack) => Promise<void>;
}

/** The native tool supplies IDs/metadata resolved on the server, never an arbitrary iframe URL. */
export async function controlDiscovery(command: PlayerCommand, signal: AbortSignal, context: Context): Promise<PlayerResult | null> {
  if (!['play_video', 'enqueue_video', 'enqueue_playlist'].includes(command.action)) return null;
  const { library, snapshot, available } = context;
  const ensure = () => {
    signal.throwIfAborted();
    if (!available() || command.window_revision !== context.windowRevision()) throw new Error('Player đã đóng hoặc lệnh đã hết hiệu lực; chưa thực hiện.');
  };
  ensure();
  const items = command.tracks;
  if (!items?.length || items.length > 200 || (command.action !== 'enqueue_playlist' && items.length !== 1)
    || items.some(item => !/^[A-Za-z0-9_-]{11}$/.test(item.video_id) || typeof item.title !== 'string' || Array.from(item.title).length > 300
      || typeof item.artist !== 'string' || Array.from(item.artist).length > 200
      || !Number.isInteger(item.start_seconds) || item.start_seconds < 0 || item.start_seconds > 604800
      || !Number.isInteger(item.duration) || item.duration < 0 || item.duration > 604800)) throw new Error('Thông tin video chưa hợp lệ; chưa thực hiện.');
  const tracks = items.map(item => ({ ...mediaFromId(item.video_id, item.title, item.artist), startSeconds: item.start_seconds, duration: item.duration }));
  if (command.action === 'play_video') {
    await context.play(tracks[0]); ensure();
    return { ok: true, state: snapshot(), data: { kind: 'mutation', target: controlTrack(tracks[0]) } };
  }
  const { keys, ...counts } = library().appendControlled(tracks);
  if (keys.length) await waitForPlayer(() => {
    ensure();
    const value = library(), present = new Set([value.currentEntryKey, ...value.queue.map(entry => entry.key)]);
    return keys.every(key => present.has(key)) ? true : undefined;
  }, signal, available);
  ensure();
  return { ok: true, state: snapshot(), data: { kind: 'mutation', ...counts, queue_revision: library().queueRevision,
    ...(tracks.length === 1 ? { target: controlTrack(tracks[0]) } : {}) } };
}
