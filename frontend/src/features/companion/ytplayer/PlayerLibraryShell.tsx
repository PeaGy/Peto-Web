import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { RESIZE_EDGES, usePlayerWindow } from './usePlayerWindow';
import { usePlayerLayout } from './playerLayout';
import './playerShell.css';
import './playerLibrary.css';
import { LibraryIcon } from './LibraryIcon';
import { LibraryPanel } from './PlayerLibraryPanel';
import type { PlayerLibrary } from './playerLibraryTypes';
import { RepeatButton, ShuffleButton } from './PlaybackModeButtons';

export interface PlayerTrack {
  title: string;
  artist: string;
  url: string;
  duration: number;
}

type Menu = 'File' | 'View' | 'Play' | 'Tools' | 'Help';
const MENUS: Menu[] = ['File', 'View', 'Play', 'Tools', 'Help'];
const KEY_CONTROLS = 'input, textarea, select, button, summary, a[href], iframe, [contenteditable="true"], [role="slider"]';
export const playerTime = (value: number) => `${Math.floor(value / 60)}:${Math.floor(value % 60).toString().padStart(2, '0')}`;

function Icon({ name, size = 22 }: { name: 'play' | 'pause' | 'back' | 'volume' | 'muted' | 'down' | 'more' | 'close'; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === 'play' && <path fill="currentColor" stroke="none" d="M7 4.5v15l12-7.5z" />}
    {name === 'pause' && <path fill="currentColor" stroke="none" d="M6 4h4v16H6zm8 0h4v16h-4z" />}
    {name === 'back' && <><path d="M5 5v14" /><path fill="currentColor" stroke="none" d="M19 5v14L7 12z" /></>}
    {(name === 'volume' || name === 'muted') && <><path d="m11 4-5 4H3v8h3l5 4z" />{name === 'volume' ? <><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14" /></> : <path d="m16 9 6 6m0-6-6 6" />}</>}
    {name === 'down' && <path d="m5 9 7 7 7-7" />}
    {name === 'more' && <><circle cx="12" cy="5" r="1" fill="currentColor" /><circle cx="12" cy="12" r="1" fill="currentColor" /><circle cx="12" cy="19" r="1" fill="currentColor" /></>}
    {name === 'close' && <path d="m5 5 14 14M19 5 5 19" />}
  </svg>;
}

interface Props {
  library: PlayerLibrary;
  id?: string;
  mode?: 'mock' | 'youtube';
  mobileLayout?: boolean;
  bottomGap?: number;
  controlsReady?: boolean;
  status?: string;
  details?: ReactNode;
  hidden?: boolean;
  onHide?: () => void;
  bounds: RefObject<HTMLElement | null>;
  track: PlayerTrack;
  playing: boolean;
  position: number;
  volume: number;
  onPlayingChange: (playing: boolean) => void;
  onSeek: (position: number) => void;
  onVolumeChange: (volume: number) => void;
  onOpenLink: (url: string) => string | undefined;
  onClose: (reason: 'close' | 'minimize') => void;
  onFocusChange: (active: boolean) => void;
  sourceChoices?: (choose: (url: string) => void) => ReactNode;
  notice?: string;
  children: ReactNode;
}

/** Giao diện Player đã duyệt, nhận trạng thái từ phiên YouTube và thư viện tài khoản. */
export function PlayerLibraryShell({ library, id, mode = 'youtube', mobileLayout, bottomGap, controlsReady = true, status, details, hidden = false, onHide, bounds, track, playing, position, volume, onPlayingChange, onSeek, onVolumeChange,
  onOpenLink, onClose, onFocusChange, sourceChoices, notice, children }: Props) {
  const root = useRef<HTMLElement>(null);
  const initialized = useRef(false);
  const sourceInput = useRef<HTMLInputElement>(null);
  const menuButton = useRef<HTMLButtonElement | null>(null);
  const menuPanel = useRef<HTMLElement>(null);
  const volumeControl = useRef<HTMLDivElement>(null);
  const volumeButton = useRef<HTMLButtonElement>(null);
  const lastVolume = useRef(60);
  const controls = usePlayerWindow(bounds, root, bottomGap);
  const [active, setActive] = useState(true);
  const activeRef = useRef(true);
  const hiddenRef = useRef(hidden);
  hiddenRef.current = hidden;
  const defaultMobile = usePlayerLayout();
  const mobile = mobileLayout ?? defaultMobile;
  const [menu, setMenu] = useState<Menu | null>(null);
  const [panelStyle, setPanelStyle] = useState({ left: 8, top: 84, width: 440, maxHeight: 400 });
  const [volumeOpen, setVolumeOpen] = useState(false);
  const [draft, setDraft] = useState(track.url);
  const [error, setError] = useState('');
  const panelId = useId();
  const volumeId = useId();
  const closeVolume = useCallback(() => setVolumeOpen(false), []);
  const chooseOwner = useCallback((next: boolean) => {
    // Quyền phím đổi ngay trong sự kiện, không đợi một Effect sau khi vẽ lại.
    const ownsKey = next && !hiddenRef.current;
    activeRef.current = ownsKey;
    setActive(ownsKey);
    onFocusChange(ownsKey);
  }, [onFocusChange]);

  useLayoutEffect(() => {
    if (!initialized.current) { initialized.current = true; controls.resize(800); }
  }, [controls]);
  useEffect(() => {
    if (!library.sourceRequest) return;
    menuButton.current = root.current?.querySelector<HTMLButtonElement>(mobile ? '.yt-mobile-head [data-player-menu-trigger]' : '.yt-menu-bar button') ?? null;
    setMenu('File');
    const timer = window.setTimeout(() => { sourceInput.current?.focus(); sourceInput.current?.select(); }, 0);
    return () => window.clearTimeout(timer);
  }, [library.sourceRequest, mobile]);
  useEffect(() => { setDraft(track.url); setError(''); setMenu(null); }, [track.url]);
  useEffect(() => { if (volume > 0) lastVolume.current = volume; }, [volume]);
  // Bảng nổi neo dưới nút menu, không tham gia bố cục của video.
  useLayoutEffect(() => {
    const node = root.current;
    const button = menuButton.current;
    if (!menu || !node || !button) return;
    const place = () => {
      const frame = node.getBoundingClientRect();
      const anchor = button.getBoundingClientRect();
      const width = Math.min(mobile ? frame.width - 24 : menu === 'File' ? 440 : 320, frame.width - 16);
      const top = anchor.bottom - frame.top + 2;
      setPanelStyle({ left: mobile ? 12 : Math.max(8, Math.min(anchor.left - frame.left, frame.width - width - 8)),
        top, width, maxHeight: Math.max(100, frame.height - top - 12) });
    };
    place();
    const observer = new ResizeObserver(place);
    observer.observe(node);
    observer.observe(button);
    return () => observer.disconnect();
  }, [menu, mobile]);
  useLayoutEffect(() => {
    const pointer = (event: PointerEvent) => {
      const inside = root.current?.contains(event.target as Node) ?? false;
      chooseOwner(inside);
      const target = event.target as Element;
      if (!menuPanel.current?.contains(target) && !target.closest('[data-player-menu-trigger]')) setMenu(null);
      if (!volumeControl.current?.contains(target)) closeVolume();
      root.current?.querySelectorAll<HTMLDetailsElement>('.yl-row-menu[open]').forEach(details => {
        if (!details.contains(target)) details.open = false;
      });
      if (!inside) {
        setMenu(null);
        // Bấm nền không tự chuyển focus: bỏ focus cũ để Space trở về vùng Companion.
        if (root.current?.contains(document.activeElement)) (document.activeElement as HTMLElement)?.blur();
      }
    };
    const focus = (event: FocusEvent) => {
      const inside = root.current?.contains(event.target as Node) ?? false;
      chooseOwner(inside);
      if (!inside) setMenu(null);
      if (!volumeControl.current?.contains(event.target as Node)) closeVolume();
    };
    const blur = () => {
      // Sự kiện phím trong iframe khác nguồn không nổi lên trang cha; YouTube tự nhận Space ở đó.
      const iframeFocused = document.activeElement instanceof HTMLIFrameElement && !!root.current?.contains(document.activeElement);
      chooseOwner(iframeFocused);
      if (iframeFocused) { setMenu(null); closeVolume(); }
    };
    document.addEventListener('pointerdown', pointer, true);
    document.addEventListener('focusin', focus);
    window.addEventListener('blur', blur);
    return () => {
      document.removeEventListener('pointerdown', pointer, true);
      document.removeEventListener('focusin', focus);
      window.removeEventListener('blur', blur);
      onFocusChange(false);
    };
  }, [chooseOwner, onFocusChange, closeVolume]);

  useLayoutEffect(() => {
    setMenu(null);
    closeVolume();
    chooseOwner(!hidden);
    if (hidden) {
      if (root.current?.contains(document.activeElement)) (document.activeElement as HTMLElement)?.blur();
    } else root.current?.focus({ preventScroll: true });
  }, [hidden, chooseOwner, closeVolume]);

  useLayoutEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (hiddenRef.current || !activeRef.current || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      if (mobile && event.key === 'Tab') {
        const items = Array.from(root.current?.querySelectorAll<HTMLElement>('button, summary, input, a[href], iframe, select, textarea') ?? [])
          .filter(item => !item.hasAttribute('disabled') && item.getClientRects().length > 0);
        const first = items[0], last = items.at(-1);
        if (event.shiftKey && (document.activeElement === first || document.activeElement === root.current)) {
          event.preventDefault(); last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault(); first?.focus();
        }
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        const rowMenu = root.current?.querySelector<HTMLDetailsElement>('.yl-row-menu[open]');
        if (rowMenu) { rowMenu.open = false; rowMenu.querySelector('summary')?.focus(); }
        else if (volumeOpen) { closeVolume(); volumeButton.current?.focus(); }
        else if (menu) { setMenu(null); menuButton.current?.focus(); }
        else if (library.panel) library.closePanel();
        else onClose('close');
      }
      if (event.code !== 'Space' || event.shiftKey || (event.target as Element)?.closest?.(KEY_CONTROLS)) return;
      event.preventDefault();
      if (!event.repeat && controlsReady) onPlayingChange(!playing);
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [mobile, playing, menu, volumeOpen, closeVolume, onPlayingChange, onClose, controlsReady, library]);

  function toggleMenu(next: Menu, button: HTMLButtonElement) {
    menuButton.current = button;
    setMenu(current => current === next ? null : next);
    closeVolume();
    setError('');
  }
  function toggleMute() {
    if (volume > 0) { lastVolume.current = volume; onVolumeChange(0); }
    else onVolumeChange(lastVolume.current);
  }
  function openSource(value: string) {
    const message = onOpenLink(value);
    setError(message ?? '');
    if (!message) { setMenu(null); root.current?.focus({ preventScroll: true }); }
  }
  function hidePlayer() {
    chooseOwner(false);
    if (root.current?.contains(document.activeElement)) (document.activeElement as HTMLElement)?.blur();
    onHide?.();
  }
  const favoriteButton = <button type="button" className="yt-icon-button yl-heart" aria-label="Yêu thích bài đang phát" aria-pressed={library.favorite} disabled={!library.track || library.favoritesBusy || library.loadingFavorites} onClick={() => library.toggleFavorite()}><LibraryIcon name="heart" filled={library.favorite} /></button>;

  return <section id={id} ref={root} tabIndex={-1} hidden={hidden} inert={hidden} aria-hidden={hidden || undefined}
    role={mobile ? 'dialog' : 'region'} aria-modal={mobile && !hidden || undefined} aria-label="Peto Media Player"
    className={`yt-player yl-shell${mobile ? ' is-mobile' : ''}${controls.maximized ? ' is-maximized' : ''}${controls.sized ? ' is-sized' : ''}${controls.dragging ? ' is-dragging' : ''}${controls.resizing ? ' is-resizing' : ''}`}
    data-panel={library.panel ?? undefined} data-active={active} data-playing={playing} data-mode={mode} data-status={status} style={controls.style}
    onPointerDown={event => {
      if (!(event.target as Element).closest(KEY_CONTROLS)) root.current?.focus({ preventScroll: true });
    }}>
    <header className="yt-window-head" {...controls.dragProps}
      onDoubleClick={event => { if (!(event.target as Element).closest('button')) controls.toggleMaximized(); }}>
      <img src="/docs-assets/logo.webp" alt="" width="24" height="20" draggable={false} />
      <strong>Peto Media Player</strong>
      <div className="yt-window-actions">
        <button type="button" aria-label="Thu nhỏ Player" onClick={() => onHide ? hidePlayer() : onClose('minimize')}><span className="yt-minimize-icon" /></button>
        <button type="button" aria-label={controls.maximized ? 'Khôi phục kích thước Player' : 'Phóng lớn Player'} onClick={controls.toggleMaximized}><span className={controls.maximized ? 'yt-restore-icon' : 'yt-maximize-icon'} /></button>
        <button type="button" aria-label="Đóng Player" onClick={() => onClose('close')}><Icon name="close" size={20} /></button>
      </div>
    </header>
    <header className="yt-mobile-head">
      <button type="button" aria-label={onHide ? 'Ẩn Player' : 'Về Companion'} onClick={() => {
        if (!onHide) { onClose('close'); return; }
        hidePlayer();
      }}><Icon name="down" size={29} /></button>
      <div><span>ĐANG PHÁT</span><strong>Peto Player</strong></div>
      <div className="yt-mobile-actions">
        <button type="button" data-player-menu-trigger aria-label="Tùy chọn Player" aria-expanded={menu !== null} aria-controls={panelId}
          onClick={event => toggleMenu('File', event.currentTarget)}><Icon name="more" /></button>
        {onHide && <button type="button" aria-label="Dừng và đóng Player" onClick={() => onClose('close')}><Icon name="close" /></button>}
      </div>
    </header>
    <nav className="yt-menu-bar" aria-label="Menu Player">
      {MENUS.map(item => <button key={item} type="button" data-player-menu-trigger aria-expanded={menu === item} aria-controls={panelId}
        onClick={event => toggleMenu(item, event.currentTarget)}
        onKeyDown={event => {
          if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
          event.preventDefault();
          const next = (MENUS.indexOf(item) + (event.key === 'ArrowRight' ? 1 : MENUS.length - 1)) % MENUS.length;
          const button = event.currentTarget.parentElement?.children[next] as HTMLButtonElement;
          button?.focus();
          if (menu) { menuButton.current = button; setMenu(MENUS[next]); }
        }}>{item}</button>)}
      <span className="yt-menu-light" aria-label={active ? 'Player đang nhận phím' : 'Companion đang nhận phím'} />
    </nav>

      {menu && <section ref={menuPanel} id={panelId} className="yt-command-panel" style={panelStyle} aria-label={`Bảng ${menu}`}>
        <button type="button" className="yt-command-close" aria-label="Đóng bảng tùy chọn" onClick={() => { setMenu(null); menuButton.current?.focus(); }}><Icon name="close" size={17} /></button>
        {menu === 'File' && <>
          <form className="yt-source-form" onSubmit={event => {
            event.preventDefault();
            openSource(draft.trim());
          }}>
            <label htmlFor={`${panelId}-source`}>Link YouTube</label>
            <div><input ref={sourceInput} id={`${panelId}-source`} type="text" autoComplete="off" spellCheck={false} value={draft}
              onChange={event => { setDraft(event.target.value); setError(''); }} required placeholder="https://www.youtube.com/watch?v=…" />
              <button type="submit" aria-label="Mở video"><LibraryIcon name="search" size={19} /></button></div>
          </form>
          {error && <p className="yt-source-error" role="alert">{error}</p>}
          {sourceChoices?.(openSource)}
          <button type="button" className="yl-add-link" onClick={() => { const message = library.appendLink(draft.trim()); setError(message ?? ''); if (!message) setMenu(null); }}><LibraryIcon name="plus" size={18} />Thêm vào hàng đợi</button>
          <button type="button" className="yl-favorites-menu" onClick={() => { library.openPanel('favorites'); setMenu(null); }}>
            <LibraryIcon name="heart" size={18} /><span>Yêu thích</span><small>{library.loadingFavorites ? '…' : library.favorites.length}</small>
          </button>
        </>}
        {menu === 'View' && <><strong>Kích thước cửa sổ</strong><div className="yt-command-row">
          <button type="button" onClick={() => { controls.resize(480); setMenu(null); }}>Nhỏ</button>
          <button type="button" onClick={() => { controls.resize(640); setMenu(null); }}>Vừa</button>
          <button type="button" onClick={() => { controls.resize(800); setMenu(null); }}>Lớn</button>
          <button type="button" onClick={() => { controls.toggleMaximized(); setMenu(null); }}>Vừa sân khấu</button>
        </div></>}
        {menu === 'Play' && <><strong>Điều khiển phát</strong><div className="yt-command-row">
          <button type="button" disabled={!controlsReady} onClick={() => onPlayingChange(!playing)}>{playing ? 'Tạm dừng' : 'Phát'}</button>
          <button type="button" disabled={!controlsReady || track.duration <= 0} onClick={() => onSeek(0)}>Phát lại từ đầu</button>
          <button type="button" onClick={toggleMute}>{volume === 0 ? 'Bật tiếng' : 'Tắt tiếng'}</button>
        </div></>}
        {menu === 'Tools' && <><strong>Đặt lại cửa sổ</strong><p>Đưa cửa sổ về vị trí ban đầu, kích thước vừa và âm lượng 60%.</p>
          <div className="yt-command-row"><button type="button" onClick={() => { controls.reset(); onVolumeChange(60); setMenu(null); }}>Đặt lại</button></div></>}
        {menu === 'Help' && <><strong>Một góc nhạc trong Companion</strong><p>Chọn Player rồi nhấn Space để phát hoặc tạm dừng. Bấm ra ngoài để trả phím cho Companion. Ô nhập vẫn gõ khoảng trắng bình thường.</p>
          <p>Kéo thanh tiêu đề để di chuyển, kéo mép hoặc góc để đổi kích thước. Esc đóng bảng đang mở; nhấn Esc lần nữa để đóng Player.</p></>}
      </section>}

    <div className="yt-player-body yl-player-body"><div className="yl-layout"><div className="yl-main">
      <div className="yt-video" aria-label="Vùng xem video">{children}</div>
      {(track.title || track.artist) && <div className="yt-track-info"><div>{track.title && <h1>{track.title}</h1>}{track.artist && <p>{track.artist}</p>}</div>{favoriteButton}</div>}
      <div className="yt-transport">
        <div className="yt-timeline">
          <input type="range" min="0" max={track.duration} step="1" value={Math.min(position, track.duration)}
            disabled={!controlsReady || track.duration <= 0} aria-label="Vị trí phát" aria-valuetext={`${playerTime(position)} trên ${playerTime(track.duration)}`} onChange={event => onSeek(Number(event.target.value))} />
          <div><span>{playerTime(position)}</span><span>{playerTime(track.duration)}</span></div>
        </div>
        <div className="yt-playback-buttons">
          <div className="yl-primary-controls" role="group" aria-label="Điều khiển phát">
          <ShuffleButton active={library.shuffle} onClick={library.toggleShuffle} className="yt-icon-button" />
          <button type="button" className="yt-icon-button yl-back" aria-label="Phát lại từ đầu" disabled={!controlsReady || track.duration <= 0} onClick={() => onSeek(0)}><Icon name="back" size={27} /></button>
          <button type="button" className="yt-play-button yl-play" disabled={!controlsReady} aria-label={mode === 'mock' ? playing ? 'Tạm dừng bản mẫu' : 'Phát bản mẫu' : playing ? 'Tạm dừng video' : 'Phát video'} onClick={() => onPlayingChange(!playing)}><Icon name={playing ? 'pause' : 'play'} size={31} /></button>
          <button type="button" className="yt-icon-button yl-next" aria-label="Bài tiếp theo" disabled={!library.track || (!library.queue.length && library.repeat !== 'all')} onClick={library.next}><LibraryIcon name="next" size={26} /></button>
          <RepeatButton mode={library.repeat} onClick={library.cycleRepeat} className="yt-icon-button" />
          </div>
          <div className="yl-secondary-controls">
          <div ref={volumeControl} className="yt-volume-control"
            onPointerEnter={event => { if (event.pointerType === 'mouse' && window.matchMedia('(hover: hover) and (pointer: fine)').matches) setVolumeOpen(true); }}
            onPointerLeave={() => { if (!volumeControl.current?.contains(document.activeElement)) setVolumeOpen(false); }}
            onFocus={event => { if (!event.currentTarget.contains(event.relatedTarget)) setVolumeOpen(true); }}
            onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) closeVolume(); }}>
            <button ref={volumeButton} type="button" className="yt-icon-button" aria-label={volume === 0 ? 'Bật tiếng' : 'Tắt tiếng'} aria-expanded={volumeOpen} aria-controls={volumeId}
              onClick={() => { setVolumeOpen(true); toggleMute(); }}><Icon name={volume === 0 ? 'muted' : 'volume'} /></button>
            {volumeOpen && <input id={volumeId} className="yt-volume-slider" type="range" min="0" max="100" value={volume}
              aria-label="Âm lượng Player" aria-valuetext={`${volume}%`} onChange={event => onVolumeChange(Number(event.target.value))} />}
          </div>
          <button ref={library.queueButton} type="button" className="yt-icon-button yl-queue-toggle" aria-label="Hàng đợi" aria-expanded={library.panel === 'queue'} onClick={library.toggleQueue}>
            <LibraryIcon name="queue" /><i className="yl-new-dot" hidden={!library.newItems} />
          </button>
          </div>
        </div>
      </div>
      {details && <div className="yt-player-details">{details}</div>}
      {notice && <p className="yt-player-notice">{notice}</p>}
    </div><LibraryPanel library={library} /></div></div>
    <span className="yl-sr-only" role="status" aria-live="polite">{library.announcement}</span>
    {!controls.maximized && RESIZE_EDGES.map(edge => <div key={edge} className={`yt-resize-handle yt-resize-${edge}`} data-resize={edge} aria-hidden="true" {...controls.resizeProps(edge)} />)}
  </section>;
}
