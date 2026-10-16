import { useEffect, useRef, useState, type PointerEvent, type RefObject } from 'react';
import { drawStrokes, type Stroke } from './imageTools';

type Selection = { strokes: Stroke[]; inverse: boolean };
type History = { source: string; current: Selection; past: Selection[]; future: Selection[] };
const EMPTY: Selection = { strokes: [], inverse: false };
const MAX_PIXELS = 16_000_000;
const MAX_POINTS = 100_000;
const clamp = (value: number) => Math.max(0, Math.min(1, value));

/** Mask là lớp độc lập, không ghép nét tô vào ảnh và không gửi ngầm tới AI. */
function drawSelection(context: CanvasRenderingContext2D, selection: Selection, width: number, height: number) {
  drawStrokes(context, selection.strokes, width, height);
  if (selection.inverse) {
    context.globalCompositeOperation = 'xor'; context.fillStyle = '#fff'; context.fillRect(0, 0, width, height);
    context.globalCompositeOperation = 'source-over';
  }
}

function bounds(context: CanvasRenderingContext2D, width: number, height: number) {
  const pixels = context.getImageData(0, 0, width, height).data;
  let left = width, top = height, right = 0, bottom = 0;
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    if (!pixels[(y * width + x) * 4 + 3]) continue;
    left = Math.min(left, x); top = Math.min(top, y); right = Math.max(right, x + 1); bottom = Math.max(bottom, y + 1);
  }
  return right > left ? { left, top, width: right - left, height: bottom - top } : null;
}

export function useImageSelection({ src, width, height, imageRef, active, disabled, onError }: {
  src: string; width: number; height: number; imageRef: RefObject<HTMLImageElement | null>;
  active: boolean; disabled: boolean; onError: (message: string) => void;
}) {
  const [history, setHistory] = useState<History>({ source: src, current: EMPTY, past: [], future: [] });
  const current = history.source === src ? history.current : EMPTY;
  const [size, setSize] = useState(28);
  const [erasing, setErasing] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [preview, setPreview] = useState<{ source: string; selection: Selection; url: string; selected: boolean } | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drag = useRef<{ pointer: number; stroke: Stroke; base: Selection } | null>(null);
  const frame = useRef<number | null>(null);
  const available = width > 0 && height > 0 && width * height <= MAX_PIXELS;
  const scale = Math.min(1, 1024 / Math.max(width, height, 1));
  const previewWidth = Math.max(1, Math.round(width * scale)), previewHeight = Math.max(1, Math.round(height * scale));
  const validPreview = preview?.source === src && preview.selection === current;
  const selected = !!(validPreview && preview.selected);
  const locked = disabled || !available || drawing;

  function commit(next: Selection) {
    setHistory(previous => {
      const sameSource = previous.source === src;
      return { source: src, current: next, past: [...(sameSource ? previous.past : []), sameSource ? previous.current : EMPTY].slice(-20), future: [] };
    });
  }
  function repaint(selection = current) {
    const canvas = canvasRef.current, context = canvas?.getContext('2d');
    if (canvas && context) drawSelection(context, selection, canvas.width, canvas.height);
  }
  function cancel() {
    drag.current = null; setDrawing(false);
    if (frame.current !== null) { cancelAnimationFrame(frame.current); frame.current = null; }
    repaint();
  }
  useEffect(() => {
    drag.current = null; setDrawing(false);
    if (frame.current !== null) { cancelAnimationFrame(frame.current); frame.current = null; }
    repaint();
    return () => { if (frame.current !== null) cancelAnimationFrame(frame.current); };
  }, [src, active, disabled]);
  useEffect(() => {
    if (!active || !available) return;
    const canvas = canvasRef.current, context = canvas?.getContext('2d', { willReadFrequently: true });
    if (!canvas || !context) return;
    try {
      drawSelection(context, current, previewWidth, previewHeight);
      const box = bounds(context, previewWidth, previewHeight);
      let url = '';
      const image = imageRef.current;
      if (box && image?.complete && image.naturalWidth === width && image.naturalHeight === height) {
        const thumbnail = document.createElement('canvas');
        const factor = Math.min(1, 160 / Math.max(box.width, box.height));
        thumbnail.width = Math.max(1, Math.round(box.width * factor)); thumbnail.height = Math.max(1, Math.round(box.height * factor));
        const target = thumbnail.getContext('2d');
        if (target) {
          target.drawImage(image, box.left / scale, box.top / scale, box.width / scale, box.height / scale, 0, 0, thumbnail.width, thumbnail.height);
          target.globalCompositeOperation = 'destination-in';
          target.drawImage(canvas, box.left, box.top, box.width, box.height, 0, 0, thumbnail.width, thumbnail.height);
          url = thumbnail.toDataURL('image/png');
        }
      }
      setPreview({ source: src, selection: current, selected: !!box, url });
    } catch { onError('Trình duyệt chưa đọc được vùng chọn của ảnh này.'); }
  }, [current, src, active, available, previewWidth, previewHeight, width, height, imageRef]);

  function point(event: PointerEvent<HTMLCanvasElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) };
  }
  function begin(event: PointerEvent<HTMLCanvasElement>) {
    if (locked || !active || event.isPrimary === false || event.button !== 0 || drag.current) return;
    if (current.strokes.length >= 200 || current.strokes.reduce((sum, stroke) => sum + stroke.points.length, 0) >= MAX_POINTS) {
      onError('Vùng chọn đã có nhiều nét. Bạn tải xuống hoặc đặt lại trước khi tô tiếp nhé.'); return;
    }
    if (event.pointerType !== 'touch') { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); }
    const rect = event.currentTarget.getBoundingClientRect();
    drag.current = { pointer: event.pointerId, base: current, stroke: { points: [point(event)], color: '#fff', size: size / rect.width, erasing: current.inverse ? !erasing : erasing } };
    setDrawing(true);
    repaint({ ...current, strokes: [...current.strokes, drag.current.stroke] });
  }
  function move(event: PointerEvent<HTMLCanvasElement>) {
    const held = drag.current;
    if (!held || held.pointer !== event.pointerId || disabled || held.stroke.points.length >= 4096) return;
    held.stroke.points.push(point(event));
    if (frame.current !== null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      if (drag.current) repaint({ ...held.base, strokes: [...held.base.strokes, held.stroke] });
    });
  }
  function end(event: PointerEvent<HTMLCanvasElement>) {
    const held = drag.current;
    if (!held || held.pointer !== event.pointerId) return;
    drag.current = null; setDrawing(false);
    if (frame.current !== null) { cancelAnimationFrame(frame.current); frame.current = null; }
    commit({ ...held.base, strokes: [...held.base.strokes, held.stroke] });
  }
  function snapshot(maskOnly = false) {
    const image = imageRef.current;
    if (locked || !active || !selected || !image?.complete || image.naturalWidth !== width || image.naturalHeight !== height) throw new Error('Bạn chọn vùng trên ảnh trước nhé.');
    const mask = document.createElement('canvas'); mask.width = width; mask.height = height;
    const context = mask.getContext('2d', { willReadFrequently: true });
    if (!context) throw new Error('Trình duyệt chưa mở được công cụ chọn vùng.');
    drawSelection(context, current, width, height);
    const box = bounds(context, width, height);
    if (!box) throw new Error('Vùng chọn đang trống. Bạn tô lại vùng cần dùng nhé.');
    let output = mask;
    if (!maskOnly) {
      output = document.createElement('canvas'); output.width = box.width; output.height = box.height;
      const target = output.getContext('2d');
      if (!target) throw new Error('Trình duyệt chưa xuất được vùng chọn.');
      target.drawImage(image, box.left, box.top, box.width, box.height, 0, 0, box.width, box.height);
      target.globalCompositeOperation = 'destination-in';
      target.drawImage(mask, box.left, box.top, box.width, box.height, 0, 0, box.width, box.height);
    }
    const data = output.toDataURL('image/png');
    if (data.length * .75 > 8 * 1024 * 1024) throw new Error('PNG vùng chọn vượt quá 8 MB. Bạn thu nhỏ vùng chọn trước nhé.');
    return data;
  }
  function undo() {
    if (locked || !history.past.length || history.source !== src) return;
    setHistory(previous => ({ ...previous, current: previous.past.at(-1)!, past: previous.past.slice(0, -1), future: [...previous.future, previous.current] }));
  }
  function redo() {
    if (locked || !history.future.length || history.source !== src) return;
    setHistory(previous => ({ ...previous, current: previous.future.at(-1)!, past: [...previous.past, previous.current], future: previous.future.slice(0, -1) }));
  }
  return {
    canvasRef, selected, size, setSize, erasing, setErasing, locked, drawing, snapshot,
    preview: validPreview ? preview.url : '', inverse: current.inverse, available,
    limited: width * height > MAX_PIXELS,
    canUndo: history.source === src && history.past.length > 0,
    canRedo: history.source === src && history.future.length > 0,
    dirty: current.inverse || current.strokes.length > 0,
    undo, redo, invert: () => { if (!locked) commit({ ...current, inverse: !current.inverse }); },
    reset: () => { if (!locked) commit(EMPTY); },
    overlay: active && available ? <canvas ref={canvasRef} className="workspace-selection-overlay" width={previewWidth} height={previewHeight} aria-label="Tô vùng chọn trên ảnh"
      onPointerDown={begin} onPointerMove={move} onPointerUp={end} onPointerCancel={cancel} onLostPointerCapture={() => { if (drag.current) cancel(); }} /> : null,
  };
}
