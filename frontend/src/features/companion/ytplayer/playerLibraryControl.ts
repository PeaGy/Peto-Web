import type { usePlayerLibrary } from './usePlayerLibrary';
import type { MediaTrack } from './playerLibraryTypes';
import { waitForPlayer, type PlayerCommand, type PlayerResult, type PlayerSnapshot, type PlayerTrack } from './playerControl';

export const controlTrack = (track: MediaTrack): PlayerTrack => ({ video_id: track.videoId, title: Array.from(track.title).slice(0, 300).join(''), artist: Array.from(track.artist).slice(0, 200).join('') });
interface Context {
  library: () => ReturnType<typeof usePlayerLibrary>;
  snapshot: () => PlayerSnapshot;
  available: () => boolean;
  play: (entryId: string, revision: number) => Promise<void>;
}

/** Library commands can run while the Player window is closed; reading or appending never starts YouTube. */
export async function controlLibrary(command: PlayerCommand, signal: AbortSignal, context: Context): Promise<PlayerResult | null> {
  const { library, snapshot, available } = context;
  const ensure = () => {
    signal.throwIfAborted();
    if (!available()) throw new Error('Lệnh Player không còn hiệu lực; chưa xác nhận thao tác.');
  };
  const wait = (condition: () => boolean) => waitForPlayer(() => condition() ? true : undefined, signal, available);
  const done = (data: NonNullable<PlayerResult['data']>): PlayerResult => ({ ok: true, state: snapshot(), data });
  const l = library();
  ensure();
  if (command.action === 'list_queue' || command.action === 'list_favorites') {
    const offset = command.offset ?? 0, limit = command.limit ?? 20;
    if (!Number.isInteger(offset) || offset < 0 || offset > 500 || !Number.isInteger(limit) || limit < 0 || limit > 50) throw new Error('Trang danh sách không hợp lệ.');
    const items = command.action === 'list_favorites' ? await l.readFavorites(signal) : l.queue.map(entry => entry.track);
    ensure();
    return done({ kind: command.action === 'list_queue' ? 'queue' : 'favorites', total: items.length, offset,
      items: items.slice(offset, offset + limit).map((track, index) => ({ ...controlTrack(track), index: offset + index + 1,
        ...(command.action === 'list_queue' ? { entry_id: l.queue[offset + index].key } : {}) })),
      next_offset: limit > 0 && offset + limit < items.length ? offset + limit : null,
      ...(command.action === 'list_queue' ? { queue_revision: l.queueRevision } : {}) });
  }
  if (command.action === 'next_track') {
    const { automatic, onSkip, reason } = l.nextTracks;
    return done({ kind: 'next', automatic: automatic ? controlTrack(automatic) : null, on_skip: onSkip ? controlTrack(onSkip) : null, reason });
  }
  if (['remove_queue_entry', 'move_queue_entry', 'play_queue_entry'].includes(command.action)) {
    if (!command.entry_id || !Number.isInteger(command.queue_revision) || command.queue_revision !== l.queueRevision) {
      return { ok: false, state: snapshot(), error: 'Hàng đợi đã thay đổi hoặc thiếu mã phiên bản. Đọc lại list_queue trước khi thao tác; không thay bằng bài khác.' };
    }
    const entry = l.queue.find(item => item.key === command.entry_id);
    if (!entry) return { ok: false, state: snapshot(), error: 'Mục này không còn trong phần Tiếp theo. Đọc lại hàng đợi.' };
    if (command.action === 'play_queue_entry') await context.play(entry.key, command.queue_revision);
    else {
      if (command.action === 'move_queue_entry' && (!Number.isInteger(command.position) || command.position! < 1 || command.position! > l.queue.length)) throw new Error('Vị trí đích nằm ngoài hàng đợi.');
      if (!l.controlEntry(command.action === 'remove_queue_entry' ? 'remove' : 'move', entry.key, command.queue_revision, command.position)) throw new Error('Hàng đợi vừa thay đổi; đọc lại trước khi thao tác.');
      await wait(() => library().queueRevision > command.queue_revision! && (command.action === 'remove_queue_entry'
        ? !library().queue.some(item => item.key === entry.key) : library().queue[command.position! - 1]?.key === entry.key && !library().shuffle));
    }
    return done({ kind: 'mutation', target: controlTrack(entry.track), queue_revision: library().queueRevision });
  }
  if (command.action === 'enqueue_favorites' || command.action === 'enqueue_favorite') {
    const favorites = await l.readFavorites(signal);
    ensure();
    const items = command.action === 'enqueue_favorites' ? favorites : favorites.filter(item => item.videoId === command.video_id);
    if (command.action === 'enqueue_favorite' && !items.length) return { ok: false, state: snapshot(), error: 'Bài này không còn trong yêu thích. Đọc lại danh sách để chọn đúng bài.' };
    const { keys, ...counts } = library().appendFavorites(items);
    if (keys.length) await wait(() => {
      const current = library();
      const present = new Set([current.currentEntryKey, ...current.queue.map(entry => entry.key)]);
      return keys.every(key => present.has(key));
    });
    return done({ kind: 'mutation', ...counts, queue_revision: library().queueRevision });
  }
  if (command.action === 'set_favorite') {
    if (typeof command.enabled !== 'boolean') throw new Error('Thiếu trạng thái yêu thích mong muốn.');
    const current = l.track;
    let target = command.video_id ? [current, ...l.queue.map(item => item.track), ...l.favorites].find(item => item?.videoId === command.video_id) : current;
    if (!target && command.video_id) target = (await l.readFavorites(signal)).find(item => item.videoId === command.video_id);
    if (!target) return { ok: false, state: snapshot(), error: 'Chưa có bài hiện tại hoặc mã bài chưa được đọc từ Player. Không tự chọn một video khác.' };
    await wait(() => !library().favoritesBusy);
    ensure();
    if (!command.video_id && library().track?.videoId !== target.videoId) throw new Error('Bài hiện tại vừa đổi; chưa sửa yêu thích cho bài khác.');
    const items = await library().setFavorite(target, command.enabled, signal);
    ensure();
    if (items.some(item => item.videoId === target.videoId) !== command.enabled) throw new Error('Máy chủ chưa xác nhận trạng thái yêu thích mong muốn.');
    await wait(() => !library().favoritesBusy && library().favorites.some(item => item.videoId === target.videoId) === command.enabled);
    return done({ kind: 'mutation', target: controlTrack(target), favorite: command.enabled, total: items.length });
  }
  return null;
}
