import { useEffect, useRef } from 'react';
import type { usePlayerLibrary } from './usePlayerLibrary';
import type { useYouTubePlayer } from './useYouTubePlayer';
import { youtubeSourceKey } from './youtubeUrl';
import { waitForPlayer, type PlayerControlBridge, type PlayerSnapshot } from './playerControl';

interface ControlProps {
  library: ReturnType<typeof usePlayerLibrary>; youtube: ReturnType<typeof useYouTubePlayer>;
  open: boolean; hidden: boolean; active: boolean; onShow: () => void; onHide: () => void; onClose: () => void;
  bridge?: PlayerControlBridge;
}

/** Reads committed React state and native API observations; mutation acknowledgement never means only "button called". */
export function usePlayerControl(props: ControlProps) {
  const latest = useRef(props); latest.current = props;
  const lastVolume = useRef(60);
  if (props.youtube.volume > 0) lastVolume.current = props.youtube.volume;
  useEffect(() => props.bridge?.register(async (command, signal) => {
    const available = () => latest.current.active && !document.hidden && command.expires_at > Date.now();
    const snapshot = (): PlayerSnapshot => {
      const { library: l, youtube: y, open, hidden } = latest.current;
      const native = y.observe();
      return { window: !open ? 'closed' : hidden ? 'hidden' : 'visible', status: !l.track ? 'empty' : !open ? 'suspended' : y.status,
        track: l.track ? { video_id: l.track.videoId, title: l.track.title.slice(0, 300), artist: l.track.artist.slice(0, 200) } : null,
        position: native?.position ?? y.position, duration: native?.duration ?? y.duration,
        volume: native?.volume ?? y.volume, shuffle: l.shuffle, repeat: l.repeat, queue_count: l.queue.length };
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
      const target = command.action === 'next' ? p.library.queue[0].track : p.library.source;
      const expectedKey = youtubeSourceKey({ ...target, playbackId: String(Number(p.library.source.playbackId) + 1) });
      if (command.action === 'next') latest.current.library.next(); else latest.current.library.restart();
      await waitForPlayer(() => {
        const q = latest.current, source = q.library.source;
        if (!q.open) throw new Error('Player đã đóng; thao tác chưa được xác nhận.');
        if (!source || youtubeSourceKey(source) === oldKey || q.youtube.sourceKey !== youtubeSourceKey(source)) return undefined;
        if (youtubeSourceKey(source) !== expectedKey) throw new Error('Bài đang nghe đã thay đổi trong lúc thực hiện; chưa xác nhận lệnh cũ.');
        if (q.youtube.status === 'error' || q.youtube.status === 'blocked') throw new Error(q.youtube.error);
        return q.youtube.playing ? true : undefined;
      }, signal, available);
      return done();
    }
    await wait(() => latest.current.youtube.ready && latest.current.youtube.sourceKey === oldKey);
    signal.throwIfAborted(); same();
    const y = latest.current.youtube;
    switch (command.action) {
      case 'play':
        y.setPlaying(true);
        await wait(() => { same(); return latest.current.youtube.playing; }); break;
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
        await wait(() => { same(); return latest.current.youtube.observe()?.volume === volume; }); break;
      }
      default: throw new Error('Thao tác Player chưa được hỗ trợ.');
    }
    return done();
  }), [props.bridge]);
}
