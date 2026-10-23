import { useCallback, useEffect, useLayoutEffect, useState, type RefObject } from 'react';
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
  active: boolean;
  open: boolean;
  hidden: boolean;
  mobileLayout: boolean;
  allowBackground: boolean;
  bounds: RefObject<HTMLElement | null>;
  onClose: () => void;
  onHide: () => void;
  onFocusChange: (active: boolean) => void;
  onShow: () => void;
  control?: PlayerControlBridge;
}

/** Favorites live on the account; queue/source live in this login, and the portal keeps one iframe. */
export default function CompanionPlayer({ active, open, hidden, mobileLayout, allowBackground, bounds, onClose, onHide, onFocusChange, onShow, control }: Props) {
  const library = usePlayerLibrary();
  const { source, ended, updateDuration } = library;
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [frame, setFrame] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const youtube = useYouTubePlayer(source, (active || allowBackground) && open && source !== null, allowBackground);
  const openLink = library.openInput;
  useEffect(() => {
    if (source && youtube.sourceKey === youtubeSourceKey(source) && youtube.status === 'ended') ended(Number(source.playbackId), youtube.endedSerial);
  }, [source, youtube.sourceKey, youtube.status, youtube.endedSerial, ended]);
  useEffect(() => {
    if (source && youtube.sourceKey === youtubeSourceKey(source) && youtube.duration > 0) updateDuration(source.videoId, youtube.duration);
  }, [source, youtube.sourceKey, youtube.duration, updateDuration]);
  const close = useCallback(() => { library.cancelDiscovery(); youtube.stop(); onClose(); }, [library.cancelDiscovery, youtube.stop, onClose]);
  usePlayerControl({ library, youtube, open, hidden, active, onShow, onHide, onClose: close, bridge: control });

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
