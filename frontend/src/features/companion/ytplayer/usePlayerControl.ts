import { useEffect, useRef } from 'react';
import type { SessionEdit, usePlayerLibrary } from './usePlayerLibrary';
import type { useYouTubePlayer } from './useYouTubePlayer';
import { youtubeSourceKey } from './youtubeUrl';
import { waitForPlayer, type PlayerControlBridge, type PlayerSnapshot } from './playerControl';
import { controlLibrary, controlTrack } from './playerLibraryControl';
import { controlDiscovery } from './playerDiscoveryControl';
import type { MediaTrack } from './playerLibraryTypes';

interface ControlProps {
  library: ReturnType<typeof usePlayerLibrary>; youtube: ReturnType<typeof useYouTubePlayer>;
  open: boolean; hidden: boolean; active: boolean; onShow: () => void; onHide: () => void; onClose: () => void;
  bridge?: PlayerControlBridge;
  clearQueue: (signal: AbortSignal) => SessionEdit;
  clearAll: (signal: AbortSignal) => SessionEdit;
  undo: (signal: AbortSignal) => SessionEdit | null;
}

/** Reads committed React state and native API observations; mutation acknowledgement never means only "button called". */
export function usePlayerControl(props: ControlProps) {
  const latest = useRef(props); latest.current = props;
  const windowLife = useRef({ open: props.open, closed: 0 });
  if (windowLife.current.open && !props.open) windowLife.current.closed++;
  windowLife.current.open = props.open;
  const lastVolume = useRef(60);
  if (props.youtube.volume > 0) lastVolume.current = props.youtube.volume;
  useEffect(() => props.bridge?.register(async (command, signal) => {
    const closed = windowLife.current.closed;
    const media = ['play_video', 'play_queue_entry', 'play_history_entry', 'previous', 'play', 'pause', 'next', 'restart', 'seek', 'set_volume', 'mute', 'unmute'].includes(command.action);
    const available = () => latest.current.active && !document.hidden && command.expires_at > Date.now() && (!media || windowLife.current.closed === closed);
    const snapshot = (): PlayerSnapshot => {
      const { library: l, youtube: y, open, hidden } = latest.current;
      const native = y.observe();
      return { window: !open ? 'closed' : hidden ? 'hidden' : 'visible', status: !l.track ? 'empty' : !open ? 'suspended' : y.status,
        track: l.track ? controlTrack(l.track) : null,
        position: !l.track ? 0 : native?.position ?? y.position, duration: !l.track ? 0 : native?.duration ?? y.duration,
        volume: y.readVolume(), ...(native ? { effective_volume: native.volume, ducked: y.ducked } : {}),
        shuffle: l.shuffle, repeat: l.repeat, queue_count: l.queue.length,
        window_revision: windowLife.current.closed + l.resetRevision, native_video_id: native?.videoId ?? null, native_state: native?.state ?? null,
        can_undo: l.canUndo, history_count: l.historySaved ? l.history.length : undefined, can_previous: !!l.previousTrack,
        previous_track: l.previousTrack ? controlTrack(l.previousTrack) : null };
    };
    const done = () => ({ ok: true, state: snapshot() });
    const wait = (condition: () => boolean) => waitForPlayer(() => {
      const s = snapshot();
      if (s.window === 'closed') throw new Error('Player đã đóng; thao tác chưa được xác nhận.');
      if (s.status === 'error' || s.status === 'blocked') throw new Error(latest.current.youtube.error || 'YouTube chưa phát được video.');
      return condition() ? true : undefined;
    }, signal, available);
    signal.throwIfAborted();
    if (!available()) throw new Error('Hãy quay lại Companion để điều khiển Player.');
    const p = latest.current;
    if (['clear_queue', 'clear_all', 'undo_queue'].includes(command.action)) {
      if (command.action === 'undo_queue' && (command.queue_revision !== p.library.queueRevision || !p.library.canUndo))
        return { ok: false, state: snapshot(), error: 'Không còn bản hoàn tác phù hợp hoặc hàng đợi vừa đổi. Đọc lại list_queue.' };
      const edit = command.action === 'clear_all' ? p.clearAll(signal) : command.action === 'clear_queue' ? p.clearQueue(signal) : p.undo(signal);
      if (!edit) return { ok: false, state: snapshot(), error: 'Không có thay đổi hàng đợi để hoàn tác.' };
      await waitForPlayer(() => {
        const value = latest.current;
        if (value.library.queueRevision < edit.revision) return undefined;
        if (value.library.queueRevision !== edit.revision) throw new Error('Hàng đợi đã đổi tiếp; chưa xác nhận thao tác cũ.');
        if (command.action === 'clear_all' && (value.library.track || value.library.queue.length || value.youtube.observe())) return undefined;
        if (command.action === 'clear_queue' && value.library.queue.length) return undefined;
        return true;
      }, signal, available);
      return { ...done(), data: { kind: 'mutation', queue_revision: edit.revision, removed: edit.removed, restored: edit.restored,
        ...(edit.undoAction ? { undo_action: edit.undoAction } : {}) } };
    }
    const playSelected = async (track: MediaTrack, select: () => void, selected?: () => boolean) => {
      if (!latest.current.open) latest.current.onShow();
      await waitForPlayer(() => latest.current.open && latest.current.youtube.container.current ? true : undefined, signal, available);
      const expected = youtubeSourceKey({ ...track, playbackId: latest.current.library.nextPlaybackId });
      signal.throwIfAborted();
      select();
      await waitForPlayer(() => {
        const value = latest.current;
        if (!value.open) return undefined;
        if (!value.library.source || youtubeSourceKey(value.library.source) !== expected || value.youtube.sourceKey !== expected) return undefined;
        if (selected && !selected()) throw new Error('Bài đang nghe đã thay đổi; chưa xác nhận lệnh cũ.');
        if (value.youtube.status === 'blocked' || value.youtube.status === 'error') throw new Error(value.youtube.error);
        const native = value.youtube.observe();
        return value.youtube.playing && native?.videoId === track.videoId && native.state === 1 && value.library.playedRequest === Number(value.library.source.playbackId) ? true : undefined;
      }, signal, available);
    };
    if (command.action === 'list_history') {
      const offset = command.offset ?? 0, limit = command.limit ?? 20, l = latest.current.library;
      if (!l.historySaved) throw new Error('Trình duyệt chưa đọc hoặc lưu được lịch sử nghe. Chưa xác nhận danh sách đã lưu.');
      if (!Number.isInteger(offset) || offset < 0 || offset > 500 || !Number.isInteger(limit) || limit < 0 || limit > 50) throw new Error('Trang lịch sử không hợp lệ.');
      return { ...done(), data: { kind: 'history', total: l.history.length, offset,
        items: l.history.slice(offset, offset + limit).map((item, i) => ({ ...controlTrack(item.track), index: offset + i + 1, entry_id: item.key, played_at: item.playedAt })),
        next_offset: limit > 0 && offset + limit < l.history.length ? offset + limit : null, history_revision: l.historyRevision } };
    }
    if (command.action === 'clear_history') {
      const before = latest.current.library.historyRevision, removed = latest.current.library.clearHistory();
      await waitForPlayer(() => {
        if (latest.current.library.historyRevision <= before) return undefined;
        if (!latest.current.library.historySaved) throw new Error('Chưa xóa được lịch sử đã lưu trong trình duyệt.');
        return latest.current.library.history.length === 0 ? true : undefined;
      }, signal, available);
      return { ...done(), data: { kind: 'mutation', removed, total: 0, history_revision: latest.current.library.historyRevision } };
    }
    if (command.action === 'previous' || command.action === 'play_history_entry') {
      const l = latest.current.library, item = l.history.find(entry => entry.key === command.entry_id);
      if (command.action === 'play_history_entry' && (!item || command.history_revision !== l.historyRevision)) throw new Error('Lịch sử vừa thay đổi. Đọc lại list_history trước khi chọn bài.');
      const target = command.action === 'previous' ? l.previousTrack : item!.track;
      if (!target) throw new Error('Chưa có bài trước trong lịch sử nghe.');
      await playSelected(target, () => {
        const current = latest.current.library;
        if (command.action === 'previous') {
          if (!current.previousTrack || current.previousTrack.videoId !== target.videoId || current.previousTrack.startSeconds !== target.startSeconds) throw new Error('Bài trước vừa thay đổi; hãy đọc lại trạng thái.');
          if (!current.previous()) throw new Error('Chưa quay được bài trước; hàng đợi có thể đã đủ 200 bài hoặc lịch sử vừa đổi.');
        }
        else {
          const fresh = current.history.find(entry => entry.key === command.entry_id);
          if (!fresh || current.historyRevision !== command.history_revision) throw new Error('Lịch sử vừa thay đổi; chưa phát mục cũ.');
          current.select(fresh.track);
        }
      });
      return { ...done(), data: { kind: 'mutation', target: controlTrack(target), history_revision: latest.current.library.historyRevision } };
    }
    const discoveryResult = await controlDiscovery(command, signal, {
      library: () => latest.current.library, snapshot, available, windowRevision: () => windowLife.current.closed + latest.current.library.resetRevision,
      play: track => playSelected(track, () => latest.current.library.select(track)),
    });
    if (discoveryResult) return discoveryResult;
    const libraryResult = await controlLibrary(command, signal, {
      library: () => latest.current.library, snapshot, available,
      play: async (key, revision) => {
        const before = latest.current, entry = before.library.queue.find(item => item.key === key);
        if (!entry || before.library.queueRevision !== revision) throw new Error('Hàng đợi đã thay đổi; đọc lại trước khi phát.');
        // Mount the window/host before creating a new autoplay intent. A pre-mount stop would consume that intent.
        // Old sources remain stopped after X; the iframe constructor itself always uses autoplay: 0.
        await playSelected(entry.track, () => {
          if (!latest.current.library.controlEntry('play', key, revision)) throw new Error('Không chọn được mục đã yêu cầu hoặc hàng đợi vừa đổi.');
        }, () => latest.current.library.currentEntryKey === key);
      },
    });
    if (libraryResult) return libraryResult;
    signal.throwIfAborted();
    if (!available()) throw new Error('Lệnh Player đã hết hiệu lực.');
    switch (command.action) {
      case 'status': return done();
      case 'open': p.onShow(); await waitForPlayer(() => latest.current.open && !latest.current.hidden ? true : undefined, signal, available); return done();
      case 'hide': p.onHide(); await waitForPlayer(() => !latest.current.open || latest.current.hidden ? true : undefined, signal, available); return done();
      case 'close': p.onClose(); await waitForPlayer(() => !latest.current.open ? true : undefined, signal, available); return done();
      case 'set_shuffle':
        if (typeof command.enabled !== 'boolean') throw new Error('Thiếu chế độ shuffle.');
        if (p.library.shuffle !== command.enabled) p.library.toggleShuffle();
        await waitForPlayer(() => latest.current.library.shuffle === command.enabled ? true : undefined, signal, available); return done();
      case 'set_repeat':
        if (!['off', 'all', 'one'].includes(command.repeat ?? '')) throw new Error('Chế độ lặp không hợp lệ.');
        p.library.setRepeat(command.repeat!);
        await waitForPlayer(() => latest.current.library.repeat === command.repeat ? true : undefined, signal, available); return done();
    }
    if (!p.library.source) return { ok: false, state: snapshot(), error: 'Player chưa có video. Chọn một bài trước nhé.' };
    if (command.action === 'pause' && !p.open) return done(); // Already stopped by X/suspend.
    if (command.action === 'next' && !p.library.queue.length) return { ok: false, state: snapshot(), error: 'Không còn bài tiếp theo trong hàng đợi.' };
    // Reopen a stopped session only for a requested playback operation. Hidden sessions stay hidden.
    if (!p.open && !['play', 'next', 'restart'].includes(command.action)) return { ok: false, state: snapshot(), error: 'Player đã dừng và đóng. Yêu cầu phát lại trước khi điều chỉnh video.' };
    if (!p.open) p.onShow();
    await waitForPlayer(() => latest.current.open ? true : undefined, signal, available);
    const oldKey = youtubeSourceKey(p.library.source);
    const same = () => {
      const source = latest.current.library.source;
      if (!source || youtubeSourceKey(source) !== oldKey) throw new Error('Bài đang nghe đã thay đổi; chưa xác nhận thao tác cho bài cũ.');
    };
    if (command.action === 'next' || command.action === 'restart' || (command.action === 'play' && p.youtube.status === 'ended')) {
      const target = command.action === 'next' ? p.library.queue[0].track : p.library.track!;
      const expectedKey = youtubeSourceKey({ ...target, playbackId: String(Number(p.library.source.playbackId) + 1) });
      if (command.action === 'next') latest.current.library.next(); else latest.current.library.restart();
      await waitForPlayer(() => {
        const q = latest.current, source = q.library.source;
        if (!q.open) throw new Error('Player đã đóng; thao tác chưa được xác nhận.');
        if (!source || youtubeSourceKey(source) === oldKey || q.youtube.sourceKey !== youtubeSourceKey(source)) return undefined;
        if (youtubeSourceKey(source) !== expectedKey) throw new Error('Bài đang nghe đã thay đổi trong lúc thực hiện; chưa xác nhận lệnh cũ.');
        if (q.youtube.status === 'error' || q.youtube.status === 'blocked') throw new Error(q.youtube.error);
        const native = q.youtube.observe();
        return q.youtube.playing && native?.videoId === target.videoId && native.state === 1 && q.library.playedRequest === Number(source.playbackId) ? true : undefined;
      }, signal, available);
      return done();
    }
    await wait(() => latest.current.youtube.ready && latest.current.youtube.sourceKey === oldKey);
    signal.throwIfAborted(); same();
    const y = latest.current.youtube;
    switch (command.action) {
      case 'play':
        y.setPlaying(true);
        await wait(() => { same(); const q = latest.current, native = q.youtube.observe(); return q.youtube.playing && native?.videoId === p.library.source!.videoId && native.state === 1 && q.library.playedRequest === Number(q.library.source!.playbackId); }); break;
      case 'pause': y.setPlaying(false); await wait(() => { same(); return latest.current.youtube.status === 'paused' || latest.current.youtube.status === 'ready'; }); break;
      case 'seek': {
        if (!Number.isFinite(command.seconds) || command.seconds! < 0) throw new Error('Thời điểm tua không hợp lệ.');
        const position = Math.min(command.seconds!, y.duration || command.seconds!);
        y.seek(position);
        await wait(() => { same(); return Math.abs((latest.current.youtube.observe()?.position ?? -100) - position) < 2; }); break;
      }
      case 'set_volume':
      case 'mute':
      case 'unmute': {
        const volume = command.action === 'mute' ? 0 : command.action === 'unmute' ? lastVolume.current : command.volume;
        if (!Number.isInteger(volume) || volume! < 0 || volume! > 100) throw new Error('Âm lượng phải từ 0 đến 100.');
        y.setVolume(volume!);
        await wait(() => { same(); const player = latest.current.youtube;
          return player.readVolume() === volume && player.observe()?.volume === player.readEffectiveVolume(); }); break;
      }
      default: throw new Error('Thao tác Player chưa được hỗ trợ.');
    }
    return done();
  }), [props.bridge]);
}
