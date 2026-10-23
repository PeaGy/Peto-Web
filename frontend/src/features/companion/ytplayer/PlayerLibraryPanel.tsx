import { useEffect, useRef } from 'react';
import { LibraryIcon } from './LibraryIcon';
import { RepeatButton, ShuffleButton } from './PlaybackModeButtons';
import { trackTitle, type MediaTrack, type PlayerLibrary, type QueueEntry } from './playerLibraryTypes';

function Cover({ track }: { track: MediaTrack }) {
  return <span className="yl-cover" aria-hidden="true"><LibraryIcon name="play" size={16} />
    <img src={`https://i.ytimg.com/vi/${track.videoId}/mqdefault.jpg`} alt="" loading="lazy" draggable={false} onError={event => { event.currentTarget.hidden = true; }} />
    {track.duration > 0 && <small>{Math.floor(track.duration / 60)}:{String(Math.floor(track.duration % 60)).padStart(2, '0')}</small>}
  </span>;
}
function TrackChoice({ track, onPlay }: { track: MediaTrack; onPlay: () => void }) {
  return <button type="button" className="yl-track-choice" aria-label={`Phát ${trackTitle(track)}`} onClick={onPlay}>
    <Cover track={track} /><span className="yl-track-copy"><strong title={trackTitle(track)}>{trackTitle(track)}</strong><span>{track.artist || track.videoId}</span></span>
  </button>;
}
function RowMenu({ entry, index, library }: { entry: QueueEntry; index: number; library: PlayerLibrary }) {
  return <details className="yl-row-menu"><summary aria-label={`Tùy chọn ${trackTitle(entry.track)}`}><LibraryIcon name="more" size={18} /></summary>
    <div className="yl-row-menu-items" onClick={event => event.currentTarget.parentElement?.removeAttribute('open')}>
      <button type="button" disabled={index === 0} onClick={() => library.move(entry.key, -1)}><LibraryIcon name="up" size={15} />Đưa lên</button>
      <button type="button" disabled={index === library.queue.length - 1} onClick={() => library.move(entry.key, 1)}><LibraryIcon name="down" size={15} />Đưa xuống</button>
      <button type="button" onClick={() => library.remove(entry.key)}><LibraryIcon name="close" size={15} />Xóa khỏi hàng đợi</button>
    </div>
  </details>;
}
export function LibraryPanel({ library }: { library: PlayerLibrary }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (library.panel) heading.current?.focus({ preventScroll: true }); }, [library.panel]);
  if (!library.panel) return null;
  const { panel, queue, favorites, track } = library;
  return <aside className="yl-panel" aria-label={panel === 'queue' ? 'Hàng đợi' : 'Yêu thích'}>
    <header className="yl-panel-head"><div><h2 ref={heading} tabIndex={-1}>{panel === 'queue' ? 'Hàng đợi' : 'Yêu thích'}</h2>
      <span>{panel === 'favorites' && library.loadingFavorites ? 'Đang tải…' : `${panel === 'queue' ? queue.length : favorites.length} bài`}</span></div>
      <button type="button" className="yl-small-button" aria-label="Đóng danh sách" onClick={library.closePanel}><LibraryIcon name="close" size={18} /></button>
    </header>
    <div className="yl-panel-scroll yl-scroll">
      {panel === 'queue' && <>
        {track && <div className="yl-now-playing"><span>ĐANG PHÁT</span><div><Cover track={track} /><span className="yl-track-copy"><strong>{trackTitle(track)}</strong><span>{track.artist || track.videoId}</span></span><LibraryIcon name="play" size={14} /></div></div>}
        <div className="yl-section-label"><span>Tiếp theo</span><div className="yl-queue-modes" role="group" aria-label="Chế độ hàng đợi">
          <ShuffleButton active={library.shuffle} onClick={library.toggleShuffle} className="yl-small-button" size={18} />
          <RepeatButton mode={library.repeat} onClick={library.cycleRepeat} className="yl-small-button" size={18} />
          <button type="button" className="yl-small-button" aria-label="Thêm bài" onClick={library.requestSource}><LibraryIcon name="plus" size={18} /></button>
        </div></div>
        {queue.length ? <ol className="yl-track-list" aria-label="Các bài tiếp theo">{queue.map((entry, index) => <li key={entry.key} className="yl-queue-row"
          onDragOver={event => event.preventDefault()} onDrop={event => library.drop(event, entry.key)}>
          <button type="button" className="yl-drag-handle" draggable aria-label={`Di chuyển ${trackTitle(entry.track)}`}
            onDragStart={event => { event.dataTransfer.setData('text/plain', entry.key); event.dataTransfer.effectAllowed = 'move'; }}
            onKeyDown={event => { if (event.key === 'ArrowUp' || event.key === 'ArrowDown') { event.preventDefault(); library.move(entry.key, event.key === 'ArrowUp' ? -1 : 1); } }}><LibraryIcon name="grip" size={15} /></button>
          <TrackChoice track={entry.track} onPlay={() => library.playEntry(entry)} /><RowMenu entry={entry} index={index} library={library} />
        </li>)}</ol> : <div className="yl-empty"><LibraryIcon name="queue" size={28} /><p>Hàng đợi đang trống.</p><button type="button" onClick={library.requestSource}>Thêm bài</button></div>}
      </>}
      {panel === 'favorites' && (library.loadingFavorites ? <div className="yl-empty" role="status">Đang tải…</div> : favorites.length ? <ul className="yl-track-list" aria-label="Các bài yêu thích">{favorites.map(item => <li key={item.videoId}>
        <TrackChoice track={item} onPlay={() => library.select(item)} /><div className="yl-row-actions">
          <button type="button" className="yl-small-button" aria-label={`Thêm ${trackTitle(item)} vào hàng đợi`} onClick={() => library.append([item])}><LibraryIcon name="plus" size={18} /></button>
          <button type="button" className="yl-small-button yl-favorite" disabled={library.favoritesBusy} aria-label={`Bỏ yêu thích ${trackTitle(item)}`} onClick={() => library.toggleFavorite(item)}><LibraryIcon name="heart" filled size={17} /></button>
        </div>
      </li>)}</ul> : <div className="yl-empty"><LibraryIcon name="heart" size={28} /><p>{library.error ? 'Chưa tải được yêu thích.' : 'Chưa có bài yêu thích.'}</p>
        {library.error && <button type="button" onClick={library.reloadFavorites}>Thử lại</button>}</div>)}
    </div>
  </aside>;
}
