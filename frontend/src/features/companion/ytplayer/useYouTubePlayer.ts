import { useCallback, useEffect, useRef, useState } from 'react';
import { loadYouTubeApi, type YouTubePlayer } from './youtubeApi';
import type { YouTubeSource } from './youtubeUrl';

export type PlayerStatus = 'loading' | 'ready' | 'playing' | 'paused' | 'buffering' | 'ended' | 'blocked' | 'suspended' | 'error';
interface Snapshot { status: PlayerStatus; ready: boolean; playing: boolean; position: number; duration: number; volume: number; error: string }
interface Session {
  active: boolean;
  ready: boolean;
  player: YouTubePlayer | null;
  key: string;
  dispose: () => void;
  cue: () => void;
}
const sourceKey = (source: YouTubeSource) => `${source.videoId}:${source.startSeconds}`;
const finite = (value: number) => Number.isFinite(value) ? Math.max(0, value) : 0;
const ERROR_MESSAGES: Record<number, string> = {
  2: 'YouTube không nhận được mã video hợp lệ.',
  5: 'Trình duyệt không phát được video này. Bạn có thể thử lại hoặc mở trên YouTube.',
  100: 'Video đã bị xóa, đặt riêng tư hoặc không còn khả dụng.',
  101: 'Chủ video không cho phép phát nhúng. Hãy mở video trên YouTube.',
  150: 'Chủ video không cho phép phát nhúng. Hãy mở video trên YouTube.',
  153: 'YouTube không xác nhận được nguồn nhúng. Hãy thử lại từ trang web hoặc mở trên YouTube.',
};

/** Một iframe mỗi phiên. Ẩn giao diện mobile giữ phiên; rời Companion/ẩn trang/đóng hẳn thì giải phóng. */
export function useYouTubePlayer(source: YouTubeSource | null, enabled: boolean) {
  const hasSource = source !== null;
  const container = useRef<HTMLDivElement>(null);
  const latestSource = useRef(source);
  latestSource.current = source;
  const latestEnabled = useRef(enabled);
  latestEnabled.current = enabled && hasSource;
  const session = useRef<Session | null>(null);
  const volume = useRef(60);
  const [visible, setVisible] = useState(() => !document.hidden);
  const [pageActive, setPageActive] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [snapshot, setSnapshot] = useState<Snapshot>({ status: 'loading', ready: false, playing: false, position: source?.startSeconds ?? 0, duration: 0, volume: 60, error: '' });

  const stop = useCallback(() => {
    session.current?.dispose();
    setSnapshot(value => ({ ...value, status: 'suspended', ready: false, playing: false }));
  }, []);

  useEffect(() => {
    const visibility = () => { if (document.hidden) stop(); setVisible(!document.hidden); };
    const hide = () => { stop(); setPageActive(false); };
    const show = () => { setPageActive(true); setVisible(!document.hidden); };
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', hide);
    window.addEventListener('pageshow', show);
    return () => {
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', hide);
      window.removeEventListener('pageshow', show);
    };
  }, [stop]);

  useEffect(() => {
    const host = container.current;
    if (!enabled || !source || !visible || !pageActive || document.hidden || !host) { stop(); return; }
    let poll = 0, readyTimer = 0;
    const current: Session = { active: true, ready: false, player: null, key: '', dispose, cue };
    session.current = current;
    const alive = () => current.active && session.current === current && latestEnabled.current && !document.hidden;
    const publish = (patch: Partial<Snapshot>) => { if (alive()) setSnapshot(value => ({ ...value, ...patch })); };
    function dispose() {
      if (!current.active) return;
      current.active = false;
      current.ready = false;
      window.clearInterval(poll);
      window.clearTimeout(readyTimer);
      // Mỗi thao tác riêng: lỗi pause trước onReady không ngăn destroy.
      try { current.player?.pauseVideo(); } catch { /* Player chưa sẵn sàng. */ }
      try { current.player?.stopVideo(); } catch { /* Player chưa sẵn sàng. */ }
      try { current.player?.destroy(); } catch { /* Vẫn gỡ iframe bên dưới. */ }
      host?.replaceChildren();
      if (session.current === current) session.current = null;
    }
    function sync() {
      if (!alive() || !current.ready || !current.player) return;
      try {
        const nextVolume = current.player.isMuted() ? 0 : Math.min(100, finite(current.player.getVolume()));
        volume.current = nextVolume;
        const position = finite(current.player.getCurrentTime()), duration = finite(current.player.getDuration());
        setSnapshot(value => value.position === position && value.duration === duration && value.volume === nextVolume ? value
          : { ...value, position, duration, volume: nextVolume });
      } catch { /* Dữ liệu API có thể chưa có trong lúc đổi video. */ }
    }
    function cue() {
      if (!alive() || !current.ready || !current.player) return;
      const next = latestSource.current;
      if (!next) return;
      if (current.key === sourceKey(next)) return;
      current.key = sourceKey(next);
      publish({ status: 'ready', ready: true, playing: false, position: next.startSeconds, duration: 0, error: '' });
      try {
        current.player.cueVideoById({ videoId: next.videoId, startSeconds: next.startSeconds });
        window.clearInterval(poll);
        poll = window.setInterval(sync, 500);
      } catch { publish({ status: 'error', ready: false, playing: false, error: 'Không mở được video. Hãy thử lại.' }); }
    }
    setSnapshot(value => ({ ...value, status: 'loading', ready: false, playing: false, duration: 0, position: source.startSeconds, error: '' }));
    const placeholder = document.createElement('div');
    host.replaceChildren(placeholder);
    void loadYouTubeApi().then(api => {
      if (!alive()) return;
      const next = latestSource.current;
      if (!next) return;
      current.player = new api.Player(placeholder, {
        videoId: next.videoId, width: '100%', height: '100%',
        playerVars: { autoplay: 0, controls: 1, playsinline: 1, enablejsapi: 1, origin: window.location.origin, hl: 'vi', start: next.startSeconds },
        events: {
          onReady: event => {
            if (!alive()) return;
            window.clearTimeout(readyTimer);
            current.player = event.target;
            current.ready = true;
            event.target.setVolume(volume.current);
            if (volume.current === 0) event.target.mute();
            cue();
          },
          onStateChange: event => {
            if (!alive()) return;
            const status: Record<number, PlayerStatus> = { '-1': 'ready', 0: 'ended', 1: 'playing', 2: 'paused', 3: 'buffering', 5: 'ready' };
            setSnapshot(value => {
              if ((value.status === 'error' || value.status === 'blocked') && event.data !== 1) return value;
              return { ...value, status: status[event.data] ?? 'ready', playing: event.data === 1,
                ...(event.data === 1 ? { ready: current.ready, error: '' } : {}) };
            });
            if (event.data === 1) {
              window.clearInterval(poll);
              poll = window.setInterval(sync, 500);
            }
            sync();
          },
          onError: event => {
            if (!alive()) return;
            window.clearInterval(poll);
            window.clearTimeout(readyTimer);
            publish({ status: 'error', ready: false, playing: false, error: `${ERROR_MESSAGES[event.data] ?? 'YouTube không phát được video này.'} (Mã ${event.data})` });
          },
          onAutoplayBlocked: () => publish({ status: 'blocked', playing: false, error: 'Trình duyệt đã chặn phát. Hãy bấm nút Phát trực tiếp trong video YouTube.' }),
        },
      });
      const iframe = current.player.getIframe();
      iframe.title = 'Video YouTube';
      iframe.referrerPolicy = 'strict-origin-when-cross-origin';
      iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen';
      iframe.allowFullscreen = true;
      readyTimer = window.setTimeout(() => {
        if (!alive() || current.ready) return;
        publish({ status: 'error', ready: false, playing: false, error: 'YouTube phản hồi quá lâu. Hãy kiểm tra kết nối hoặc thử lại.' });
        dispose();
      }, 20000);
    }).catch(error => {
      publish({ status: 'error', ready: false, playing: false, error: error instanceof Error ? error.message : 'Không tải được YouTube.' });
      dispose();
    });
    return dispose;
    // Nguồn được cập nhật bằng cue ở Effect riêng để không tạo lại iframe.
  }, [enabled, hasSource, visible, pageActive, attempt, stop]);

  useEffect(() => { session.current?.cue(); }, [source?.videoId, source?.startSeconds]);

  function command(action: (player: YouTubePlayer) => void) {
    const current = session.current;
    if (!current?.active || !current.ready || !current.player || !latestEnabled.current || document.hidden) return;
    try { action(current.player); } catch { setSnapshot(value => ({ ...value, status: 'error', ready: false, playing: false, error: 'Player chưa phản hồi. Hãy thử lại.' })); }
  }
  return {
    container, ...snapshot, stop,
    setPlaying: (playing: boolean) => command(player => playing ? player.playVideo() : player.pauseVideo()),
    seek: (position: number) => command(player => player.seekTo(Math.min(finite(position), snapshot.duration || finite(position)), true)),
    setVolume: (next: number) => {
      volume.current = Math.round(Math.min(100, finite(next)));
      setSnapshot(value => ({ ...value, volume: volume.current }));
      command(player => { player.setVolume(volume.current); if (volume.current === 0) player.mute(); else player.unMute(); });
    },
    retry: () => { stop(); setAttempt(value => value + 1); },
  };
}
