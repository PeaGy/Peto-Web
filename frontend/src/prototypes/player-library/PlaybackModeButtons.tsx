import { LibraryIcon } from './LibraryIcon';
import type { RepeatMode } from './queuePlayback';

export function ShuffleButton({ active, onClick, className, size = 21 }: {
  active: boolean; onClick: () => void; className: string; size?: number;
}) {
  return <button type="button" className={`${className} yl-mode-button yl-shuffle`} aria-label="Phát ngẫu nhiên"
    aria-pressed={active} title={active ? 'Phát ngẫu nhiên: bật' : 'Phát ngẫu nhiên: tắt'} onClick={onClick}>
    <LibraryIcon name="shuffle" size={size} />
  </button>;
}

export function RepeatButton({ mode, onClick, className, size = 21 }: {
  mode: RepeatMode; onClick: () => void; className: string; size?: number;
}) {
  return <button type="button" className={`${className} yl-mode-button yl-repeat`}
    aria-label={`Chế độ lặp: ${mode === 'off' ? 'tắt' : mode === 'all' ? 'hàng đợi' : 'một bài'}`}
    aria-pressed={mode !== 'off'} data-repeat={mode} title={mode === 'off' ? 'Tắt lặp' : mode === 'all' ? 'Lặp hàng đợi' : 'Lặp một bài'} onClick={onClick}>
    <LibraryIcon name={mode === 'one' ? 'repeat-one' : 'repeat'} size={size} />
  </button>;
}
