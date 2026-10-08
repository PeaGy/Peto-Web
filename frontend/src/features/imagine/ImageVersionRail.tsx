import { useEffect, useRef, useState } from 'react';
import type { ImagineImage, ImagineJob } from '../../shared/api/api';
import StudioIcon from './studioIcons';

export type ImageVersion = { job: ImagineJob; image: ImagineImage };

export default function ImageVersionRail({ versions, selectedId, disabled, onSelect, onClose, compact = false, pending = false }: {
  versions: ImageVersion[]; selectedId: string; disabled: boolean;
  onSelect: (version: ImageVersion) => void; onClose: () => void;
  compact?: boolean; pending?: boolean;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const [arrows, setArrows] = useState({ before: false, after: false });
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const measure = () => {
      const horizontal = getComputedStyle(list).flexDirection === 'row';
      const position = horizontal ? list.scrollLeft : list.scrollTop;
      const total = horizontal ? list.scrollWidth - list.clientWidth : list.scrollHeight - list.clientHeight;
      setArrows({ before: position > 1, after: position < total - 1 });
    };
    // Chỉ cuộn dải thumbnail, không để scrollIntoView kéo cả canvas/dialog theo.
    const selected = list.querySelector<HTMLElement>(compact && pending ? '.history-pending' : '[aria-current="true"]');
    if (selected) {
      const horizontal = getComputedStyle(list).flexDirection === 'row';
      const row = list.getBoundingClientRect(), item = selected.getBoundingClientRect();
      const start = horizontal ? item.left - row.left : item.top - row.top;
      const end = horizontal ? item.right - row.right : item.bottom - row.bottom;
      const delta = start < 0 ? start : end > 0 ? end : 0;
      if (horizontal) list.scrollLeft += delta; else list.scrollTop += delta;
    }
    measure(); list.addEventListener('scroll', measure);
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure); observer?.observe(list);
    return () => { list.removeEventListener('scroll', measure); observer?.disconnect(); };
  }, [selectedId, versions.length, compact, pending]);
  function scroll(direction: number) {
    const list = listRef.current;
    if (!list) return;
    const horizontal = getComputedStyle(list).flexDirection === 'row';
    list.scrollBy(horizontal ? { left: direction * list.clientWidth * .8, behavior: 'instant' } : { top: direction * list.clientHeight * .8, behavior: 'instant' });
  }
  return <nav className="workspace-history" aria-label="Lịch sử chỉnh sửa ảnh">
    {!compact && <button type="button" className="workspace-round history-back" aria-label="Quay lại" onClick={onClose}><StudioIcon name="back" /></button>}
    {!compact && arrows.before && <button type="button" className="history-scroll history-scroll-up" aria-label="Cuộn lịch sử lên" onClick={() => scroll(-1)}><StudioIcon name="arrowUp" /></button>}
    <div className="history-list" ref={listRef}>
      {versions.map((entry, index) => <button type="button" className="history-thumb" key={entry.image.id}
        aria-label={index === 0 ? 'Ảnh chính' : `Phiên bản ${index}`} title={index === 0 ? 'Ảnh chính' : `Phiên bản ${index}`}
        aria-current={entry.image.id === selectedId ? 'true' : undefined} disabled={disabled} onClick={() => onSelect(entry)}>
        <img src={entry.image.url} alt="" loading="lazy" decoding="async" />
      </button>)}
      {compact && pending && <span className="history-pending" role="status" aria-label="Phiên bản đang tạo"><span /></span>}
    </div>
    {!compact && arrows.after && <button type="button" className="history-scroll history-scroll-down" aria-label="Cuộn lịch sử xuống" onClick={() => scroll(1)}><StudioIcon name="arrowUp" /></button>}
  </nav>;
}
