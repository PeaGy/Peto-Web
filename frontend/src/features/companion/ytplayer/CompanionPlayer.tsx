import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { PlayerLibraryShell } from './PlayerLibraryShell';
import { usePlayerLibrary } from './usePlayerLibrary';
import { trackTitle } from './playerLibraryTypes';
import { LibraryIcon } from './LibraryIcon';
import { youtubeSourceKey } from './youtubeUrl';
import { useYouTubePlayer } from './useYouTubePlayer';
import './companionPlayer.css';
import { usePlayerControl } from './usePlayerControl';
import type { PlayerControlBridge } from './playerControl';

interface Props {
  ownerId?: string;
  active: boolean;
  open: boolean;
  hidden: boolean;
  mobileLayout: boolean;
  allowBackground: boolean;
  ducked?: boolean;
  bounds: RefObject<HTMLElement | null>;
  onClose: () => void;
  onHide: () => void;
  onFocusChange: (active: boolean) => void;
  onShow: () => void;
  control?: PlayerControlBridge;
}

/** Favorites live on the account; the local listening session restores stopped, and the portal keeps one iframe. */
export default function CompanionPlayer({ ownerId, active, open, hidden, mobileLayout, allowBackground, ducked = false, bounds, onClose, onHide, onFocusChange, onShow, control }: Props) {
  const library = usePlayerLibrary(ownerId);
  const { source, ended, updateDuration } = library;
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [frame, setFrame] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const youtube = useYouTubePlayer(source, (active || allowBackground) && open && source !== null && frame !== null, allowBackground, library.initialVolume, ducked);
  const latest = useRef({ library, youtube }); latest.current = { library, youtube };
  const checkpoint = useCallback((immediate = false) => {
    const { library: l, youtube: y } = latest.current;
    const native = y.observe();
    const matches = l.source && y.sourceKey === youtubeSourceKey(l.source) && native?.videoId === l.source.videoId;
    l.rememberPlayback(l.currentEntryKey, matches ? (y.status === 'ended' ? l.track!.startSeconds : native.position) : undefined, y.readVolume(), immediate);
  }, []);
  useEffect(() => { checkpoint(!youtube.playing); }, [youtube.sourceKey, youtube.position, youtube.volume, youtube.playing, youtube.status, checkpoint]);
  useLayoutEffect(() => {
    const flush = () => checkpoint(true);
    // Capture before the YouTube lifecycle disposes the native player, including mobile visibility changes.
    window.addEventListener('pagehide', flush, true);
    document.addEventListener('visibilitychange', flush, true);
    return () => {
      flush(); window.removeEventListener('pagehide', flush, true); document.removeEventListener('visibilitychange', flush, true);
    };
  }, [checkpoint]);
  const openLink = library.openInput;
  useEffect(() => {
    const native = youtube.observe();
    if (source && youtube.sourceKey === youtubeSourceKey(source) && youtube.playing && native?.state === 1 && native.videoId === source.videoId)
      library.recordPlaying(Number(source.playbackId), source.videoId);
  }, [source, youtube.sourceKey, youtube.playing, youtube.position, library.recordPlaying]);
  useEffect(() => {
    if (source && youtube.sourceKey === youtubeSourceKey(source) && youtube.status === 'ended') ended(Number(source.playbackId), youtube.endedSerial);
  }, [source, youtube.sourceKey, youtube.status, youtube.endedSerial, ended]);
  useEffect(() => {
    if (source && youtube.sourceKey === youtubeSourceKey(source) && youtube.duration > 0) updateDuration(source.videoId, youtube.duration);
  }, [source, youtube.sourceKey, youtube.duration, updateDuration]);
  const close = useCallback(() => { checkpoint(true); library.cancelDiscovery(); youtube.stop(); onClose(); }, [checkpoint, library.cancelDiscovery, youtube.stop, onClose]);
  const clearQueue = (signal?: AbortSignal) => { control?.invalidate(signal); return library.clearQueue(); };
  const clearAll = (signal?: AbortSignal) => { control?.invalidate(signal); youtube.stop(); return library.clearAll(); };
  const undo = (signal?: AbortSignal) => {
    if (!library.canUndo) return null;
    control?.invalidate(signal); return library.undo();
  };
  usePlayerControl({ library, youtube, open, hidden, active, onShow, onHide, onClose: close, bridge: control, clearQueue, clearAll, undo });

  // Portal giữ cùng cây iframe khi xoay màn hình, tránh container của sân khấu giới hạn position:fixed trên mobile.
  useLayoutEffect(() => {
    const area = bounds.current;
    if (!active || !open || !area) return;
    const fit = () => {
      const rect = area.getBoundingClientRect();
      setFrame(value => value && value.left === rect.left && value.top === rect.top && value.width === rect.width && value.height === rect.height
        ? value : { left: rect.left, top: rect.top, width: rect.width, height: rect.height });
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(area);
    window.addEventListener('resize', fit);
    window.addEventListener('scroll', fit, true);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', fit);
      window.removeEventListener('scroll', fit, true);
    };
  }, [active, open, bounds]);

  if ((!active && !allowBackground) || !open || !frame) return null;
  return createPortal(<div className="companion-player-layer" data-mobile={mobileLayout} style={frame}>
    <PlayerLibraryShell library={library} id="companion-player" mode="youtube" mobileLayout={mobileLayout} bottomGap={0} bounds={bounds} hidden={hidden} onHide={onHide}
      sessionActions={{ canUndo: library.canUndo, clearQueue, clearAll, undo }}
      track={{ title: library.track ? trackTitle(library.track) : '', artist: library.track?.artist ?? '', url: source?.url ?? '', duration: youtube.duration }}
      controlsReady={source !== null && youtube.ready} status={source ? youtube.status : 'empty'}
      playing={youtube.playing} position={youtube.position} volume={youtube.volume}
      onPlayingChange={value => { if (value && youtube.status === 'ended') library.restart(); else youtube.setPlaying(value); }} onSeek={youtube.seek} onVolumeChange={youtube.setVolume}
      onOpenLink={openLink} onClose={close} onFocusChange={onFocusChange}
      details={(library.error || (source && youtube.error)) ? <>
        {library.error && <p className="yt-player-error" role="alert">{library.error}</p>}
        {source && youtube.error && <>
        <p className="yt-player-error" role="alert">{youtube.error}</p>
        {youtube.status === 'error' && <button type="button" className="yt-retry" onClick={youtube.retry}>Thử lại YouTube</button>}
        <a className="companion-player-external" href={source.url} target="_blank" rel="noopener noreferrer">Mở trên YouTube ↗</a>
      </>}
      </> : undefined}>
      <div ref={youtube.container} className="yt-youtube-container" />
      {!source && <form className="yt-source-form companion-player-empty" onSubmit={event => {
        event.preventDefault(); setError(openLink(draft.trim()) ?? '');
      }}>
        <label htmlFor="companion-player-source">Link hoặc tên video</label>
        <div><input id="companion-player-source" type="text" enterKeyHint="search" placeholder="Tìm video hoặc dán link…" autoComplete="off" maxLength={4096}
          value={draft} required onChange={event => { setDraft(event.target.value); setError(''); }} />
          <button type="submit" aria-label="Tìm hoặc mở"><LibraryIcon name="search" size={19} /></button></div>
        {error && <p className="yt-source-error" role="alert">{error}</p>}
      </form>}
    </PlayerLibraryShell>
  </div>, document.body);
}
