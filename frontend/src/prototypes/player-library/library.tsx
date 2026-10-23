import { useCallback, useEffect, useReducer, useRef, useState, type DragEvent } from 'react';
import { parseYouTubeUrl } from '../../features/companion/ytplayer/youtubeUrl';
import { LibraryIcon } from './LibraryIcon';
import { TRACKS, SEARCH_TRACKS, type DemoTrack } from './data';
import { createPlayback, playbackReducer, type QueueEntry } from './queuePlayback';
import { RepeatButton, ShuffleButton } from './PlaybackModeButtons';

type Panel = 'queue' | 'favorites' | 'search';
type Entry = QueueEntry;
const randomSeed = () => Math.floor(Math.random() * 0x100000000);
const time = (value: number) => `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
const fold = (text: string) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

/** Toàn bộ dữ liệu chỉ nằm trong phiên xem thử: không storage, backend hay media thật. */
export function useLibraryDemo(enabled: boolean) {
  const [playback, dispatch] = useReducer(playbackReducer, undefined, () => createPlayback(TRACKS[0], TRACKS.slice(1)));
  const { current: { track }, queue, playing, position, repeat, shuffle } = playback;
  const [volume, setVolume] = useState(60);
  const [favorites, setFavorites] = useState<DemoTrack[]>([TRACKS[1], TRACKS[2]]);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [newItems, setNewItems] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<DemoTrack[]>([]);
  const [announcement, setAnnouncement] = useState('');
  const [sourceRequest, setSourceRequest] = useState(0);
  const sequence = useRef(0);
  const queueButton = useRef<HTMLButtonElement>(null);
  const favorite = favorites.some(item => item.id === track.id);

  const select = useCallback((item: DemoTrack, start = true) => {
    dispatch({ type: 'select', entry: { key: `selected-${++sequence.current}`, track: item }, playing: start });
  }, []);
  const next = useCallback(() => dispatch({ type: 'next', seed: randomSeed() }), []);
  const setPlaying = useCallback((value: boolean) => dispatch({ type: 'play', playing: value, seed: randomSeed() }), []);
  const setPosition = useCallback((value: number) => dispatch({ type: 'seek', position: value }), []);
  useEffect(() => {
    if (!enabled || !playing) return;
    const timer = window.setInterval(() => dispatch({ type: 'tick', seed: randomSeed() }), 1000);
    return () => window.clearInterval(timer);
  }, [enabled, playing, playback.current.key]);

  function append(items: DemoTrack[]) {
    dispatch({ type: 'append', entries: items.map(item => ({ key: `added-${++sequence.current}`, track: item })) });
    if (panel !== 'queue') setNewItems(true);
    setAnnouncement(`Đã thêm ${items.length} bài vào hàng đợi.`);
  }
  function openPanel(value: Panel) { setPanel(value); if (value === 'queue') setNewItems(false); }
  function closePanel() { setPanel(null); queueButton.current?.focus({ preventScroll: true }); }
  function toggleFavorite(item = track) {
    const exists = favorites.some(value => value.id === item.id);
    setFavorites(current => exists ? current.filter(value => value.id !== item.id) : [...current, item]);
    setAnnouncement(`${exists ? 'Đã bỏ yêu thích' : 'Đã yêu thích'} ${item.title}.`);
  }
  function move(key: string, offset: number) {
    dispatch({ type: 'move', key, offset });
  }
  function drop(event: DragEvent, target: string) {
    event.preventDefault(); const key = event.dataTransfer.getData('text/plain');
    const from = queue.findIndex(item => item.key === key), to = queue.findIndex(item => item.key === target);
    if (from >= 0 && to >= 0) move(key, to - from);
  }
  function playEntry(entry: Entry) {
    dispatch({ type: 'play-entry', key: entry.key });
  }
  function openInput(value: string) {
    const input = value.trim();
    if (!input) return 'Nhập link hoặc tên video.';
    if (/^[a-z][a-z\d+.-]*:/i.test(input)) {
      let url: URL; try { url = new URL(input); } catch { return 'Link chưa hợp lệ.'; }
      const source = parseYouTubeUrl(input);
      const found = source && TRACKS.find(item => parseYouTubeUrl(item.url)?.videoId === source.videoId);
      if (found) { select(found, false); return undefined; }
      if (['https:', 'http:'].includes(url.protocol) && ['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'].includes(url.hostname)
        && !url.username && !url.password && !url.port && url.pathname === '/playlist' && /^PL[\w-]{8,148}$/.test(url.searchParams.get('list') ?? '')) {
        append([TRACKS[2], TRACKS[1], TRACKS[0]]); openPanel('queue');
        setAnnouncement('Đã thêm playlist mẫu, 3 bài.'); return undefined;
      }
      return 'Bản xem thử dùng video và playlist mẫu. Bạn có thể thử tìm Tetris.';
    }
    setQuery(input);
    const key = fold(input);
    setResults(key.includes('tetris') || key.includes('tetoris') || key.includes('テトリス') ? SEARCH_TRACKS
      : [...TRACKS, ...SEARCH_TRACKS.slice(1)].filter(item => fold(`${item.title} ${item.artist}`).includes(key)).slice(0, 5));
    openPanel('search'); return undefined;
  }
  return { track, playing, position, volume, setPlaying, setPosition, setVolume, favorite, favorites, queue, panel, newItems, repeat, shuffle,
    query, results, announcement, sourceRequest, queueButton, select, next, append, openPanel, closePanel, toggleFavorite,
    move, drop, playEntry, openInput, requestSource: () => setSourceRequest(value => value + 1),
    toggleQueue: () => panel === 'queue' ? closePanel() : openPanel('queue'),
    remove: (key: string) => dispatch({ type: 'remove', key }),
    toggleShuffle: () => dispatch({ type: 'shuffle', seed: randomSeed() }),
    cycleRepeat: () => dispatch({ type: 'repeat', seed: randomSeed() }),
  };
}
export type LibraryDemo = ReturnType<typeof useLibraryDemo>;

function Cover({ track }: { track: DemoTrack }) {
  return <span className="yl-cover" data-tone={track.tone} aria-hidden="true"><b>{track.cover}</b><img src="/docs-assets/peto-hero.webp" alt="" draggable={false} /><small>{time(track.duration)}</small></span>;
}
function TrackChoice({ track, onPlay }: { track: DemoTrack; onPlay: () => void }) {
  return <button type="button" className="yl-track-choice" aria-label={`Phát ${track.title}`} onClick={onPlay}>
    <Cover track={track} /><span className="yl-track-copy"><strong title={track.title}>{track.title}</strong><span>{track.artist}</span></span>
  </button>;
}
function RowMenu({ entry, index, library }: { entry: Entry; index: number; library: LibraryDemo }) {
  return <details className="yl-row-menu"><summary aria-label={`Tùy chọn ${entry.track.title}`}><LibraryIcon name="more" size={18} /></summary>
    <div className="yl-row-menu-items" onClick={event => { event.currentTarget.parentElement?.removeAttribute('open'); }}>
      <button type="button" disabled={index === 0} onClick={() => library.move(entry.key, -1)}><LibraryIcon name="up" size={15} />Đưa lên</button>
      <button type="button" disabled={index === library.queue.length - 1} onClick={() => library.move(entry.key, 1)}><LibraryIcon name="down" size={15} />Đưa xuống</button>
      <button type="button" onClick={() => library.remove(entry.key)}><LibraryIcon name="close" size={15} />Xóa khỏi hàng đợi</button>
    </div>
  </details>;
}

export function LibraryPanel({ library }: { library: LibraryDemo }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (library.panel) heading.current?.focus({ preventScroll: true }); }, [library.panel, library.query]);
  if (!library.panel) return null;
  const { panel, queue, favorites, results, track } = library;
  const count = panel === 'queue' ? queue.length : panel === 'favorites' ? favorites.length : results.length;
  return <aside className="yl-panel" aria-label={panel === 'queue' ? 'Hàng đợi' : panel === 'favorites' ? 'Yêu thích' : 'Kết quả tìm kiếm'}>
    <header className="yl-panel-head"><div><h2 ref={heading} tabIndex={-1}>{panel === 'queue' ? 'Hàng đợi' : panel === 'favorites' ? 'Yêu thích' : 'Kết quả tìm kiếm'}</h2><span>{panel === 'search' ? `${count} kết quả mẫu · ${library.query}` : `${count} bài`}</span></div>
      <button type="button" className="yl-small-button" aria-label="Đóng danh sách" onClick={library.closePanel}><LibraryIcon name="close" size={18} /></button>
    </header>
    <div className="yl-panel-scroll yl-scroll">
      {panel === 'queue' && <>
        <div className="yl-now-playing"><span>ĐANG PHÁT</span><div><Cover track={track} /><span className="yl-track-copy"><strong>{track.title}</strong><span>{track.artist}</span></span><LibraryIcon name="play" size={14} /></div></div>
        <div className="yl-section-label"><span>Tiếp theo</span><div className="yl-queue-modes" role="group" aria-label="Chế độ hàng đợi">
          <ShuffleButton active={library.shuffle} onClick={library.toggleShuffle} className="yl-small-button" size={18} />
          <RepeatButton mode={library.repeat} onClick={library.cycleRepeat} className="yl-small-button" size={18} />
          <button type="button" className="yl-small-button" aria-label="Thêm bài" onClick={library.requestSource}><LibraryIcon name="plus" size={18} /></button>
        </div></div>
        {queue.length ? <ol className="yl-track-list" aria-label="Các bài tiếp theo">{queue.map((entry, index) => <li key={entry.key} className="yl-queue-row"
          onDragOver={event => event.preventDefault()} onDrop={event => library.drop(event, entry.key)}>
          <button type="button" className="yl-drag-handle" draggable aria-label={`Di chuyển ${entry.track.title}`}
            onDragStart={event => { event.dataTransfer.setData('text/plain', entry.key); event.dataTransfer.effectAllowed = 'move'; }}
            onKeyDown={event => { if (event.key === 'ArrowUp' || event.key === 'ArrowDown') { event.preventDefault(); library.move(entry.key, event.key === 'ArrowUp' ? -1 : 1); } }}><LibraryIcon name="grip" size={15} /></button>
          <TrackChoice track={entry.track} onPlay={() => library.playEntry(entry)} /><RowMenu entry={entry} index={index} library={library} />
        </li>)}</ol> : <div className="yl-empty"><LibraryIcon name="queue" size={28} /><p>Hàng đợi đang trống.</p><button type="button" onClick={library.requestSource}>Thêm bài</button></div>}
      </>}
      {panel === 'favorites' && (favorites.length ? <ul className="yl-track-list" aria-label="Các bài yêu thích">{favorites.map(item => <li key={item.id}>
        <TrackChoice track={item} onPlay={() => library.select(item)} /><div className="yl-row-actions"><button type="button" className="yl-small-button" aria-label={`Thêm ${item.title} vào hàng đợi`} onClick={() => library.append([item])}><LibraryIcon name="plus" size={18} /></button>
          <button type="button" className="yl-small-button yl-favorite" aria-label={`Bỏ yêu thích ${item.title}`} onClick={() => library.toggleFavorite(item)}><LibraryIcon name="heart" filled size={17} /></button></div>
      </li>)}</ul> : <div className="yl-empty"><LibraryIcon name="heart" size={28} /><p>Chưa có bài yêu thích.</p></div>)}
      {panel === 'search' && (results.length ? <ul className="yl-track-list" aria-label="Các kết quả mẫu">{results.map(item => <li key={item.id}>
        <TrackChoice track={item} onPlay={() => library.select(item)} /><button type="button" className="yl-small-button" aria-label={`Thêm ${item.title} vào hàng đợi`} onClick={() => library.append([item])}><LibraryIcon name="plus" size={19} /></button>
      </li>)}</ul> : <div className="yl-empty"><LibraryIcon name="search" size={28} /><p>Không có kết quả mẫu.</p><button type="button" onClick={library.requestSource}>Tìm lại</button></div>)}
    </div>
  </aside>;
}
