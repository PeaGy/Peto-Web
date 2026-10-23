import { StrictMode, useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { createRoot } from 'react-dom/client';
import { usePlayerLayout } from '../../features/companion/ytplayer/playerLayout';
import '../youtube-tv/preview.css';
import { LibraryPlayerShell } from './LibraryPlayerShell';
import { LibraryIcon } from './LibraryIcon';
import { useLibraryDemo } from './library';
import { DEMO_PLAYLIST, TRACKS } from './data';

function Preview() {
  const bounds = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(true);
  const [hidden, setHidden] = useState(false);
  const library = useLibraryDemo(open);
  const { track, playing, position, volume } = library;
  const mobile = usePlayerLayout();
  const modal = mobile && open && !hidden;
  const ownsKey = useRef(true);
  const [holding, setHolding] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<string[]>([]);
  const updateFocus = useCallback((active: boolean) => {
    ownsKey.current = active;
    if (active) setHolding(false);
  }, []);
  const toggle = () => {
    setMenuOpen(false);
    if (!open) { setOpen(true); setHidden(false); }
    else setHidden(value => !value);
  };
  const close = () => {
    library.setPlaying(false);
    library.closePanel();
    setOpen(false); setHidden(false); updateFocus(false);
  };
  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.code !== 'Space' || event.defaultPrevented || ownsKey.current || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return;
      if ((event.target as Element)?.closest?.('input, textarea, select, button, summary, a[href], [contenteditable="true"]')) return;
      event.preventDefault(); if (!event.repeat) setHolding(true);
    };
    const up = (event: KeyboardEvent) => { if (event.code === 'Space') setHolding(false); };
    const blur = () => setHolding(false);
    window.addEventListener('keydown', down); window.addEventListener('keyup', up); window.addEventListener('blur', blur);
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); window.removeEventListener('blur', blur); };
  }, []);

  return <main className="yp-preview yl-preview">
    <aside className="yp-rail" aria-label="Bối cảnh xem thử" inert={modal}>
      <img src="/docs-assets/logo.webp" alt="Peto" /><span className="yp-rail-mark">P</span><span>COMPANION</span><small>01</small>
    </aside>
    <div className="yp-workspace">
      <header className="yp-preview-head" inert={modal}>
        <button type="button" className="yp-menu-trigger" aria-label="Mở menu Companion" aria-expanded={menuOpen} onClick={() => setMenuOpen(value => !value)}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
        <div><span className="yp-breadcrumb">COMPANION <span>/</span> GÓC NHẠC</span><span className="yp-mobile-brand">Peto Companion</span></div>
        <span className="yp-preview-tag">Giao diện mẫu <b>01</b></span>
      </header>
      {menuOpen && <nav className="yp-mobile-menu" aria-label="Menu Companion"><span>COMPANION</span><button type="button" aria-expanded={open && !hidden} aria-controls="library-player" onClick={toggle}><LibraryIcon name="play" />Player</button><button type="button" onClick={() => setMenuOpen(false)}>Đóng menu</button></nav>}
      <div className="yp-room">
        <div className={`yp-stage${open && !hidden ? ' yp-stage-player-open' : ''}`} data-testid="preview-stage">
          <div className="yp-room-caption" inert={modal}><span>MỘT CHÚT NHẠC, MỘT CHÚT CHUYỆN.</span><p>Ở đây cùng Peto.</p></div>
          <img className="yp-stage-character" src="/docs-assets/peto-hero.webp" alt="Nhân vật Peto minh họa" draggable={false} />
          <div className="yp-stage-bottom" inert={modal}>
            <div className={`yp-space-hint${holding ? ' is-holding' : ''}`} role="status"><span className="yp-space-key">SPACE</span><span>{holding ? 'Đang giữ để nói · mô phỏng' : 'Giữ để nói · mô phỏng'}</span></div>
            <button type="button" className="yp-open-player" aria-label="Player" title="Player" aria-expanded={open && !hidden} aria-controls="library-player" onClick={toggle}><LibraryIcon name="play" /></button>
          </div>
          <div ref={bounds} className="yp-player-area" data-testid="player-bounds">
            {open && <LibraryPlayerShell id="library-player" library={library} bounds={bounds} bottomGap={0} hidden={hidden} onHide={() => setHidden(true)}
              track={track} playing={playing} position={position} volume={volume}
              onPlayingChange={library.setPlaying} onSeek={library.setPosition} onVolumeChange={library.setVolume}
              onOpenLink={library.openInput} onClose={close} onFocusChange={updateFocus}
              sourceChoices={choose => <div className="yl-source-choices"><button type="button" onClick={() => choose('Tetris')}>Tìm “Tetris”</button><button type="button" onClick={() => choose(DEMO_PLAYLIST)}>Playlist mẫu</button><button type="button" onClick={() => choose(TRACKS[1].url)}>Link video mẫu</button></div>}>
              <div className="yp-video-art" data-playing={playing} data-tone={track.tone}>
                <span className="yp-art-top">PETO / GÓC NHẠC <b>{String(TRACKS.findIndex(item => item.id === track.id) + 1 || 1).padStart(2, '0')}</b></span>
                <div className="yp-art-type"><small>{track.artist}</small><strong>{track.cover}</strong><span>Ở LẠI THÊM MỘT CHÚT.</span></div>
                <img src="/docs-assets/peto-hero.webp" alt="" draggable={false} />
                <span className="yp-art-note">Ảnh minh họa</span>
                <div className="yp-art-bars" aria-hidden="true">{Array.from({ length: 7 }, (_, index) => <i key={index} style={{ '--bar': `${index}` } as CSSProperties} />)}</div>
              </div>
            </LibraryPlayerShell>}
          </div>
        </div>
        <section className="yp-chat" aria-label="Trò chuyện mẫu" inert={modal}>
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
