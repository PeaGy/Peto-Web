import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type PointerEvent, type RefObject } from 'react';

const EDGE = 16;
const DEFAULT_WIDTH = 640;
export const RESIZE_EDGES = ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw'] as const;
export type ResizeEdge = typeof RESIZE_EDGES[number];
const RESIZE_CURSORS: Record<ResizeEdge, string> = {
  n: 'ns-resize', ne: 'nesw-resize', e: 'ew-resize', se: 'nwse-resize',
  s: 'ns-resize', sw: 'nesw-resize', w: 'ew-resize', nw: 'nwse-resize',
};

interface Frame { x: number; y: number; width: number; height: number | null }
interface Gesture {
  id: number;
  kind: 'move' | ResizeEdge;
  pointerX: number;
  pointerY: number;
  x: number;
  y: number;
  width: number;
  height: number;
  minWidth: number;
  minHeight: number;
}

/** Kéo và đổi kích thước trực tiếp, giữ góc đối diện cố định và chừa vùng nút Player ở sân khấu. */
export function usePlayerWindow(bounds: RefObject<HTMLElement | null>, windowRef: RefObject<HTMLElement | null>) {
  const [frame, setFrame] = useState<Frame>({ x: 32, y: 56, width: DEFAULT_WIDTH, height: null });
  const [maximized, setMaximized] = useState(false);
  const [interaction, setInteraction] = useState<Gesture['kind'] | null>(null);
  const gesture = useRef<Gesture | null>(null);

  const constrain = useCallback((x: number, y: number) => {
    const area = bounds.current;
    const node = windowRef.current;
    if (!area || !node) return { x, y };
    return {
      x: Math.max(EDGE, Math.min(x, area.clientWidth - node.offsetWidth - EDGE)),
      y: Math.max(EDGE, Math.min(y, area.clientHeight - node.offsetHeight - EDGE)),
    };
  }, [bounds, windowRef]);

  useLayoutEffect(() => {
    const area = bounds.current;
    const node = windowRef.current;
    if (!area || !node) return;
    const fit = () => {
      if (gesture.current || maximized) return;
      setFrame(current => {
        const next = constrain(current.x, current.y);
        return next.x === current.x && next.y === current.y ? current : { ...current, ...next };
      });
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(area);
    observer.observe(node);
    return () => observer.disconnect();
  }, [bounds, windowRef, constrain, maximized]);

  const finish = useCallback((event?: PointerEvent<HTMLElement>) => {
    if (event && gesture.current && event.pointerId !== gesture.current.id) return;
    gesture.current = null;
    setInteraction(null);
  }, []);
  useEffect(() => {
    const cancel = () => finish();
    window.addEventListener('blur', cancel);
    return () => window.removeEventListener('blur', cancel);
  }, [finish]);

  function start(event: PointerEvent<HTMLElement>, kind: Gesture['kind']) {
    const node = windowRef.current;
    const area = bounds.current;
    if (maximized || event.button !== 0 || gesture.current || !node || !area) return;
    if (kind === 'move' && (event.target as Element).closest('button')) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const video = node.querySelector<HTMLElement>('.yt-video');
    gesture.current = {
      id: event.pointerId, kind, pointerX: event.clientX, pointerY: event.clientY,
      x: node.offsetLeft, y: node.offsetTop, width: node.offsetWidth, height: node.offsetHeight,
      minWidth: Math.min(360, area.clientWidth - EDGE * 2),
      minHeight: Math.min(area.clientHeight - EDGE * 2, node.offsetHeight - (video?.offsetHeight ?? 200) + 200),
    };
    setInteraction(kind);
    if (kind !== 'move') setFrame(current => ({ ...current, width: node.offsetWidth, height: node.offsetHeight }));
  }

  function move(event: PointerEvent<HTMLElement>) {
    const current = gesture.current;
    const area = bounds.current;
    if (!current || !area || event.pointerId !== current.id) return;
    const dx = event.clientX - current.pointerX;
    const dy = event.clientY - current.pointerY;
    if (current.kind === 'move') {
      setFrame(value => ({ ...value, ...constrain(current.x + dx, current.y + dy) }));
      return;
    }
    let left = current.x, top = current.y;
    let right = current.x + current.width, bottom = current.y + current.height;
    if (current.kind.includes('w')) left = Math.max(EDGE, Math.min(current.x + dx, right - current.minWidth));
    if (current.kind.includes('e')) right = Math.min(area.clientWidth - EDGE, Math.max(left + current.minWidth, right + dx));
    if (current.kind.includes('n')) top = Math.max(EDGE, Math.min(current.y + dy, bottom - current.minHeight));
    if (current.kind.includes('s')) bottom = Math.min(area.clientHeight - EDGE, Math.max(top + current.minHeight, bottom + dy));
    setFrame({ x: left, y: top, width: right - left, height: bottom - top });
  }

  const pointerProps = { onPointerMove: move, onPointerUp: finish, onPointerCancel: finish, onLostPointerCapture: finish };
  return {
    maximized, dragging: interaction === 'move', resizing: interaction !== null && interaction !== 'move',
    sized: frame.height !== null,
    style: { left: frame.x, top: frame.y, '--player-width': `${frame.width}px`,
      '--resize-cursor': interaction && interaction !== 'move' ? RESIZE_CURSORS[interaction] : 'auto',
      '--player-height': frame.height === null ? 'auto' : `${frame.height}px` } as CSSProperties,
    toggleMaximized: () => { finish(); setMaximized(value => !value); },
    resize: (width: number) => { finish(); setMaximized(false); setFrame(value => ({ ...value, width, height: null })); },
    reset: () => { finish(); setMaximized(false); setFrame({ x: 32, y: 56, width: DEFAULT_WIDTH, height: null }); },
    dragProps: { ...pointerProps, onPointerDown: (event: PointerEvent<HTMLElement>) => start(event, 'move') },
    resizeProps: (edge: ResizeEdge) => ({ ...pointerProps, onPointerDown: (event: PointerEvent<HTMLElement>) => start(event, edge) }),
  };
}
