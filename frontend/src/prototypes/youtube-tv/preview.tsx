import { StrictMode, useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { createRoot } from 'react-dom/client';
import { PlayerShell, type PlayerTrack } from '../../features/companion/ytplayer/PlayerShell';
import { parseYouTubeUrl } from '../../features/companion/ytplayer/youtubeUrl';
import { useYouTubePlayer } from '../../features/companion/ytplayer/useYouTubePlayer';
import './preview.css';

interface Sample extends PlayerTrack { id: string; short: string; cover: string }

/** Sáu link thử từ báo cáo ngày 22/10. Chế độ mode=ui chỉ dùng ảnh, không tải YouTube. */
const SAMPLES: Sample[] = [
  { id: 'HDz9dSuAI4s', short: 'Miku concert', title: 'Magical Mirai 2023', artist: 'Hatsune Miku', duration: 3457, cover: 'MIKU LIVE', url: 'https://www.youtube.com/watch?v=HDz9dSuAI4s' },
  { id: 'e1xCOsgWG0M', short: 'Vampire', title: 'The Vampire', artist: 'DECO*27', duration: 180, cover: 'VAMPIRE', url: 'https://www.youtube.com/watch?v=e1xCOsgWG0M' },
  { id: 'Soy4jGPHr3g', short: 'Tetris', title: 'Tetris', artist: 'Kasane Teto SV', duration: 143, cover: 'TETRIS', url: 'https://www.youtube.com/watch?v=Soy4jGPHr3g' },
  { id: 'dQw4w9WgXcQ', short: 'Rick Astley', title: 'Never Gonna Give You Up', artist: 'Rick Astley', duration: 213, cover: 'NEVER GONNA', url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' },
  { id: 'JGwWNGJdvx8', short: 'Shape of You', title: 'Shape of You', artist: 'Ed Sheeran', duration: 263, cover: 'SHAPE OF YOU', url: 'https://www.youtube.com/watch?v=JGwWNGJdvx8' },
  { id: 'aircAruvnKk', short: '3Blue1Brown', title: 'But what is a neural network?', artist: '3Blue1Brown', duration: 1120, cover: 'NEURAL NETWORK', url: 'https://www.youtube.com/watch?v=aircAruvnKk' },
];
const MOCK = new URLSearchParams(window.location.search).get('mode') === 'ui';

function Preview() {
  const bounds = useRef<HTMLDivElement>(null);
  const [track, setTrack] = useState(SAMPLES[2]);
  const [open, setOpen] = useState(true);
  const [playerHidden, setPlayerHidden] = useState(false);
  const [source, setSource] = useState(() => parseYouTubeUrl(SAMPLES[2].url)!);
  const youtube = useYouTubePlayer(source, !MOCK && open);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(13);
  const [volume, setVolume] = useState(60);
  const [playerFocus, setPlayerFocus] = useState(true);
  const playerOwnsKey = useRef(true);
  const [holding, setHolding] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<string[]>([]);
  const [hint, setHint] = useState('');
  const updatePlayerFocus = useCallback((active: boolean) => {
    playerOwnsKey.current = active;
    setPlayerFocus(active);
    if (active) setHolding(false);
  }, []);

  const closePlayer = useCallback((reason: 'close' | 'minimize') => {
    youtube.stop();
    setPlaying(false);
    setOpen(false);
    setPlayerHidden(false);
    setHint(reason === 'minimize' ? 'Player đã thu nhỏ. Bấm Player để mở lại.' : 'Player đã đóng.');
  }, [youtube.stop]);
  const togglePlayer = () => {
    setMenuOpen(false);
    setHolding(false);
    if (open && playerHidden) setPlayerHidden(false);
    else if (open && !MOCK) setPlayerHidden(true);
    else if (open) closePlayer('close');
    else { setHint(''); setOpen(true); }
  };
  const openLink = useCallback((value: string) => {
    if (!MOCK) {
      const parsed = parseYouTubeUrl(value);
      if (!parsed) return 'Link YouTube chưa hợp lệ. Hãy dùng link watch, youtu.be, shorts, live hoặc embed có mã video.';
      const sample = SAMPLES.find(item => item.id === parsed.videoId);
      setTrack(sample ? { ...sample, url: parsed.url } : { id: parsed.videoId, title: 'Video YouTube', artist: parsed.videoId,
        short: 'YouTube', cover: 'YOUTUBE', duration: 0, url: parsed.url });
      setSource(parsed);
      return undefined;
    }
    const sample = SAMPLES.find(item => value === item.url || value === `https://youtu.be/${item.id}`);
    if (!sample) return 'Bản xem thử dùng sáu video mẫu bên dưới. Chọn một video để tiếp tục.';
    setTrack(sample);
    setPosition(0);
    setPlaying(false);
    return undefined;
  }, []);

  // Đồng hồ chỉ minh họa trạng thái phát; không có media hoặc micro thật trong bản giao diện.
  useEffect(() => {
    if (!MOCK || !playing || !open) return;
    const timer = window.setInterval(() => setPosition(value => Math.min(value + 1, track.duration)), 1000);
    return () => window.clearInterval(timer);
  }, [playing, open, track.duration]);
  useEffect(() => { if (position >= track.duration) setPlaying(false); }, [position, track.duration]);
  useEffect(() => {
    const suspend = () => { setPlaying(false); setHolding(false); };
    const visibility = () => { if (document.hidden) suspend(); };
    const blur = () => setHolding(false);
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', suspend);
    window.addEventListener('blur', blur);
    return () => {
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', suspend);
      window.removeEventListener('blur', blur);
    };
  }, []);
  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.code !== 'Space' || event.defaultPrevented || playerOwnsKey.current || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return;
      if ((event.target as Element)?.closest?.('input, textarea, select, button, a[href], [contenteditable="true"]')) return;
      event.preventDefault();
      if (!event.repeat) setHolding(true);
    };
    const up = (event: KeyboardEvent) => { if (event.code === 'Space') setHolding(false); };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); };
  }, []);

  return <main className="yp-preview">
    <aside className="yp-rail" aria-label="Bối cảnh xem thử"><img src="/docs-assets/logo.webp" alt="Peto" /><span className="yp-rail-mark">P</span><span>COMPANION</span><small>{MOCK ? '01' : '02'}</small></aside>
    <div className="yp-workspace">
      <header className="yp-preview-head">
        <button type="button" className="yp-menu-trigger" aria-label="Mở menu Companion" aria-expanded={menuOpen}
          onClick={() => setMenuOpen(value => !value)}><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg></button>
        <div><span className="yp-breadcrumb">COMPANION <span>/</span> GÓC NHẠC</span><span className="yp-mobile-brand">Peto Companion</span></div>
        <span className="yp-preview-tag">{MOCK ? 'Bản giao diện' : 'YouTube POC'} <b>{MOCK ? '01' : '02'}</b></span>
      </header>
      {menuOpen && <nav className="yp-mobile-menu" aria-label="Menu Companion"><span>COMPANION</span><button type="button" aria-expanded={open && !playerHidden} aria-controls="preview-player" onClick={togglePlayer}><span aria-hidden="true">▷</span> Player</button><button type="button" onClick={() => setMenuOpen(false)}>Đóng menu</button></nav>}
      <div className="yp-room">
        <div className={`yp-stage${open && !playerHidden ? ' yp-stage-player-open' : ''}`} data-testid="preview-stage">
          <div className="yp-room-caption"><span>MỘT CHÚT NHẠC, MỘT CHÚT CHUYỆN.</span><p>Ở đây cùng Peto.</p></div>
          <img className="yp-stage-character" src="/docs-assets/peto-hero.webp" alt="Nhân vật Peto minh họa" draggable={false} />
          <div className="yp-stage-bottom"><div className={`yp-space-hint${holding ? ' is-holding' : ''}`} role="status" aria-live="polite">
            <span className="yp-space-key">SPACE</span><span>{holding ? 'Đang giữ để nói · mô phỏng' : open && playerFocus ? 'Player đang nhận phím' : 'Giữ để nói · mô phỏng'}</span>
          </div><button type="button" className="yp-open-player" aria-expanded={open && !playerHidden} aria-controls="preview-player" onClick={togglePlayer}><span aria-hidden="true">▷</span> Player</button></div>
          {hint && <p className="yp-close-hint" role="status">{hint}</p>}
          <div ref={bounds} className="yp-player-area" data-testid="player-bounds">
          {open && <PlayerShell id="preview-player" mode={MOCK ? 'mock' : 'youtube'} bounds={bounds}
            hidden={playerHidden} onHide={MOCK ? undefined : () => setPlayerHidden(true)}
            track={MOCK ? track : { ...track, duration: youtube.duration }} playing={MOCK ? playing : youtube.playing}
            position={MOCK ? position : youtube.position} volume={MOCK ? volume : youtube.volume}
            controlsReady={MOCK || youtube.ready} status={MOCK ? undefined : youtube.status}
            onPlayingChange={MOCK ? value => { if (value && position >= track.duration) setPosition(0); setPlaying(value); } : youtube.setPlaying}
            onSeek={MOCK ? setPosition : youtube.seek} onVolumeChange={MOCK ? setVolume : youtube.setVolume}
            onOpenLink={openLink} onClose={closePlayer} onFocusChange={updatePlayerFocus}
            notice={MOCK ? 'Bản xem thử giao diện · Chưa phát video hoặc âm thanh.' : undefined}
            details={!MOCK && youtube.error && <>
              <p className="yt-player-error" role="alert">{youtube.error}</p>
              {youtube.status === 'error' && <button type="button" className="yt-retry" onClick={youtube.retry}>Thử lại YouTube</button>}
            </>}
            sourceChoices={choose => <div className="yp-sample-choices"><span>{MOCK ? 'VIDEO MẪU' : 'VIDEO THỬ'}</span><div>{SAMPLES.map(sample => <button key={sample.id} type="button"
              aria-pressed={track.id === sample.id} onClick={() => choose(sample.url)}>{sample.short}</button>)}</div></div>}>
            {MOCK ? <div className="yp-video-art" data-playing={playing}>
              <span className="yp-art-top">PETO / GÓC NHẠC <b>{String(SAMPLES.indexOf(track) + 1).padStart(2, '0')}</b></span>
              <div className="yp-art-type"><small>{track.artist}</small><strong>{track.cover}</strong><span>Ở LẠI THÊM MỘT CHÚT.</span></div>
              <img src="/docs-assets/peto-hero.webp" alt="" draggable={false} />
              <span className="yp-art-note">Ảnh minh họa</span>
              <div className="yp-art-bars" aria-hidden="true">{Array.from({ length: 7 }, (_, index) => <i key={index} style={{ '--bar': `${index}` } as CSSProperties} />)}</div>
            </div> : <div ref={youtube.container} className="yt-youtube-container" />}
          </PlayerShell>}
          </div>
        </div>
        <section className="yp-chat" aria-label="Trò chuyện mẫu">
          <header><img src="/docs-assets/logo.webp" alt="" /><div><strong>Peto</strong><span>Cùng bạn một lúc</span></div><i aria-label="Bố cục minh họa" /></header>
          <div className="yp-chat-messages"><span className="yp-chat-day">HÔM NAY</span><p className="yp-user-bubble">Mở một chút nhạc nhé?</p><div className="yp-peto-message"><span>PETO</span><p>Ừ, chọn một bài đi.<br />Mình ở đây mà.</p></div>{messages.map((message, index) => <p className="yp-user-bubble" key={index}>{message}</p>)}</div>
          <form className="yp-chat-compose" onSubmit={event => { event.preventDefault(); if (draft.trim()) { setMessages(value => [...value, draft.trim()]); setDraft(''); } }}>
            <label htmlFor="preview-chat" className="yp-sr-only">Nhắn thử trong Companion</label>
            <textarea id="preview-chat" placeholder="Thử gõ ở đây…" value={draft} rows={2} onChange={event => setDraft(event.target.value)} />
            <div><span>Tin nhắn mẫu · không gửi tới AI</span><button type="submit" aria-label="Gửi tin nhắn mẫu" disabled={!draft.trim()}>↑</button></div>
          </form>
        </section>
      </div>
    </div>
  </main>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><Preview /></StrictMode>);
