import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { ChatAttachment } from '../../shared/api/api';
import { boundImageView, fitImageScale, INITIAL_IMAGE_VIEW, transformImageView, type ImagePoint, type ImageSize, type ImageView } from './imageView';
import ImageZoomMenu from './ImageZoomMenu';
import './chatImageViewer.css';

const EMPTY_SIZE: ImageSize = { width: 0, height: 0 };
const midpoint = (a: ImagePoint, b: ImagePoint): ImagePoint => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
const distance = (a: ImagePoint, b: ImagePoint) => Math.hypot(a.x - b.x, a.y - b.y);

function ViewerIcon({ name }: { name: 'image' | 'download' | 'close' | 'previous' | 'next' }) {
  return <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === 'image' ? <><rect x="3" y="3" width="18" height="18" rx="3" /><circle cx="8" cy="8" r="1.5" /><path d="m3 17 5-5 4 4 4-6 5 7" /></>
      : name === 'download' ? <><path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4" /></>
      : name === 'close' ? <path d="m6 6 12 12M18 6 6 18" />
      : <path d={name === 'previous' ? 'm14 5-7 7 7 7' : 'm10 5 7 7-7 7'} />}
  </svg>;
}

export default function ChatImageViewer({ images, index, onIndexChange, onClose }: {
  images: ChatAttachment[]; index: number; onIndexChange: (index: number) => void; onClose: () => void;
}) {
  const file = images[index];
  const dialogRef = useRef<HTMLDialogElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const imageSize = useRef(EMPTY_SIZE);
  const viewportSize = useRef(EMPTY_SIZE);
  const viewRef = useRef(INITIAL_IMAGE_VIEW);
  const pointers = useRef(new Map<number, ImagePoint>());
  const press = useRef<{ point: ImagePoint; background: boolean; moved: boolean } | null>(null);
  const [view, setView] = useState(INITIAL_IMAGE_VIEW);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);

  function applyView(next: ImageView) {
    viewRef.current = next;
    setView(next);
  }
  function fit() {
    applyView(boundImageView(INITIAL_IMAGE_VIEW, imageSize.current, viewportSize.current));
  }
  function zoom(scale: number, point: ImagePoint = { x: 0, y: 0 }) {
    applyView(transformImageView(viewRef.current, scale, point, point, imageSize.current, viewportSize.current));
  }
  function pointAt(clientX: number, clientY: number): ImagePoint {
    const rect = stageRef.current!.getBoundingClientRect();
    return { x: clientX - rect.left - rect.width / 2, y: clientY - rect.top - rect.height / 2 };
  }

  useEffect(() => {
    const trigger = document.activeElement;
    const dialog = dialogRef.current!;
    dialog.showModal();
    dialog.querySelector<HTMLButtonElement>('[aria-label="Đóng ảnh"]')?.focus({ preventScroll: true });
    return () => {
      dialog.close();
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus({ preventScroll: true });
    };
  }, []);

  useLayoutEffect(() => {
    imageSize.current = EMPTY_SIZE;
    pointers.current.clear(); press.current = null;
    setReady(false); setFailed(false);
    applyView(INITIAL_IMAGE_VIEW);
  }, [index, retry]);

  useEffect(() => {
    const stage = stageRef.current!;
    const measure = () => {
      viewportSize.current = { width: stage.clientWidth, height: stage.clientHeight };
      applyView(boundImageView(viewRef.current, imageSize.current, viewportSize.current));
    };
    measure();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(stage);
    window.addEventListener('resize', measure);
    return () => { observer?.disconnect(); window.removeEventListener('resize', measure); };
  }, []);

  useEffect(() => {
    const stage = stageRef.current!;
    const wheel = (event: WheelEvent) => {
      if (!imageSize.current.width || event.ctrlKey || event.metaKey || !event.deltaY) return;
      event.preventDefault();
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? stage.clientHeight : 1;
      const delta = Math.max(-240, Math.min(240, event.deltaY * unit));
      zoom(viewRef.current.scale * Math.exp(-delta * 0.002), pointAt(event.clientX, event.clientY));
    };
    // Chỉ bề mặt xem ảnh bắt cuộn để zoom; phím zoom trình duyệt vẫn hoạt động.
    stage.addEventListener('wheel', wheel, { passive: false });
    return () => stage.removeEventListener('wheel', wheel);
  }, []);

  function pointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    // Lần chạm ngoài menu chỉ đóng menu, không đồng thời đóng hoặc kéo ảnh.
    if (dialogRef.current?.querySelector('[role="menu"]')) { press.current = null; return; }
    if (!ready || (event.pointerType !== 'touch' && event.button !== 0)) return;
    event.preventDefault();
    const point = pointAt(event.clientX, event.clientY);
    if (!pointers.current.size) press.current = { point, background: event.target === event.currentTarget, moved: false };
    pointers.current.set(event.pointerId, point);
    if (pointers.current.size > 1 && press.current) press.current.moved = true;
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function pointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!pointers.current.has(event.pointerId)) return;
    const before = [...pointers.current.values()];
    const previous = pointers.current.get(event.pointerId)!;
    const next = pointAt(event.clientX, event.clientY);
    pointers.current.set(event.pointerId, next);
    if (press.current && distance(press.current.point, next) > 4) press.current.moved = true;
    const after = [...pointers.current.values()];
    if (before.length >= 2) {
      const from = midpoint(before[0], before[1]), to = midpoint(after[0], after[1]);
      const factor = distance(after[0], after[1]) / Math.max(1, distance(before[0], before[1]));
      applyView(transformImageView(viewRef.current, viewRef.current.scale * factor, from, to, imageSize.current, viewportSize.current));
    } else {
      applyView(boundImageView({ ...viewRef.current, x: viewRef.current.x + next.x - previous.x,
        y: viewRef.current.y + next.y - previous.y, fit: false }, imageSize.current, viewportSize.current));
    }
  }
  function pointerEnd(event: ReactPointerEvent<HTMLDivElement>) {
    pointers.current.delete(event.pointerId);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }
  function select(next: number) {
    if (next >= 0 && next < images.length) onIndexChange(next);
  }
  return <dialog ref={dialogRef} className="chat-image-viewer" aria-label="Xem ảnh đính kèm" onCancel={event => { event.preventDefault(); onClose(); }}
    onKeyDown={event => {
      if (event.key === 'Tab') {
        const controls = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled):not([tabindex="-1"]), a[href]')];
        const first = controls[0], last = controls[controls.length - 1];
        // Chromium có thể chuyển Tab từ nút cuối sang thanh trình duyệt; giữ vòng focus trong modal.
        if (first && last && ((event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last))) {
          event.preventDefault(); (event.shiftKey ? last : first).focus({ preventScroll: true });
        }
        return;
      }
      if (event.key === 'ArrowLeft') { event.preventDefault(); select(index - 1); }
      if (event.key === 'ArrowRight') { event.preventDefault(); select(index + 1); }
    }}>
    <header className="chat-image-toolbar">
      <div className="chat-image-title"><ViewerIcon name="image" /><span title={file.name}>{file.name}</span>
        {images.length > 1 && <small>{index + 1}/{images.length}</small>}
      </div>
      <div className="chat-image-controls">
        <ImageZoomMenu scale={view.scale} fit={view.fit} disabled={!ready} onZoom={zoom} onFit={fit} />
        <a className="chat-image-control" href={file.url} download={file.name} title="Tải ảnh xuống" aria-label="Tải ảnh xuống"><ViewerIcon name="download" /></a>
        <button type="button" className="chat-image-control" title="Đóng ảnh" aria-label="Đóng ảnh" onClick={onClose}><ViewerIcon name="close" /></button>
      </div>
    </header>
    <div ref={stageRef} className={`chat-image-stage${ready ? ' ready' : ''}`} onPointerDown={pointerDown} onPointerMove={pointerMove}
      onPointerUp={pointerEnd} onPointerCancel={pointerEnd} onLostPointerCapture={event => { pointers.current.delete(event.pointerId); }}
      onClick={event => { if (event.target === event.currentTarget && press.current?.background && !press.current.moved) onClose(); }}
      onDoubleClick={event => { event.preventDefault(); if (ready) view.scale > fitImageScale(imageSize.current, viewportSize.current) + 0.01 ? fit() : zoom(1, pointAt(event.clientX, event.clientY)); }}>
      <img key={`${index}-${retry}`} src={file.url} alt={file.name} draggable={false} className="chat-image-original"
        style={{ visibility: ready ? 'visible' : 'hidden', width: imageSize.current.width || undefined, height: imageSize.current.height || undefined,
          transform: `translate3d(calc(-50% + ${view.x}px), calc(-50% + ${view.y}px), 0) scale(${view.scale})` }}
        onLoad={event => {
          const image = event.currentTarget;
          imageSize.current = { width: image.naturalWidth, height: image.naturalHeight };
          setReady(true); setFailed(false);
          applyView(boundImageView(viewRef.current, imageSize.current, viewportSize.current));
        }} onError={() => { imageSize.current = EMPTY_SIZE; setReady(false); setFailed(true); }} />
      {!ready && <div className="chat-image-status" role="status">{failed ? <>Không tải được ảnh.<button type="button" onClick={() => setRetry(value => value + 1)}>Thử lại</button></> : 'Đang tải ảnh…'}</div>}
    </div>
    {images.length > 1 && <>
      <button type="button" className="chat-image-control chat-image-previous" aria-label="Ảnh trước" disabled={index === 0} onClick={() => select(index - 1)}><ViewerIcon name="previous" /></button>
      <button type="button" className="chat-image-control chat-image-next" aria-label="Ảnh tiếp theo" disabled={index === images.length - 1} onClick={() => select(index + 1)}><ViewerIcon name="next" /></button>
    </>}
  </dialog>;
}
