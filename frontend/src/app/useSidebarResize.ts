import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';

export const SIDEBAR_WIDTH_KEY = 'peto-sidebar-width';
export const DEFAULT_SIDEBAR_WIDTH = 260;
export const MIN_SIDEBAR_WIDTH = 220;
export const COLLAPSED_SIDEBAR_WIDTH = 64;
const COLLAPSE_THRESHOLD = 128;
const MAX_SIDEBAR_WIDTH = 420;

/** Luôn chừa ít nhất 360px cho nội dung trên desktop hẹp. */
export function sidebarMaxWidth(viewport: number) {
  return Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, viewport - 360));
}

function boundWidth(value: number, viewport: number) {
  return Math.round(Math.max(MIN_SIDEBAR_WIDTH, Math.min(sidebarMaxWidth(viewport), value)));
}

function readWidth() {
  try {
    const value = localStorage.getItem(SIDEBAR_WIDTH_KEY);
    const number = Number(value);
    if (value && Number.isFinite(number) && number > 0) return boundWidth(number, Infinity);
  } catch {}
  return DEFAULT_SIDEBAR_WIDTH;
}

/** Kéo mép thanh bên; chỉ lưu lựa chọn khi thả chuột, không ghi storage mỗi khung hình. */
export function useSidebarResize(collapsed: boolean, onCollapsedChange: (collapsed: boolean) => void) {
  const [preferredWidth, setPreferredWidth] = useState(readWidth);
  const preferred = useRef(preferredWidth);
  const [viewport, setViewport] = useState(() => window.innerWidth);
  const [resizing, setResizing] = useState(false);
  const [dragWidth, setDragWidth] = useState<number | null>(null);
  const collapseChange = useRef(onCollapsedChange);
  collapseChange.current = onCollapsedChange;
  const handle = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: number; x: number; width: number; current: number } | null>(null);
  const maxWidth = sidebarMaxWidth(viewport);
  const expandedWidth = boundWidth(dragWidth ?? preferredWidth, viewport);
  const width = dragWidth ?? (collapsed ? COLLAPSED_SIDEBAR_WIDTH : expandedWidth);
  const visualCollapsed = dragWidth === null ? collapsed : dragWidth <= COLLAPSE_THRESHOLD;
  const contentOpacity = dragWidth === null ? undefined : Math.max(0, Math.min(1, (dragWidth - COLLAPSE_THRESHOLD) / (MIN_SIDEBAR_WIDTH - COLLAPSE_THRESHOLD)));

  function change(next: number) {
    preferred.current = boundWidth(next, window.innerWidth);
    setPreferredWidth(preferred.current);
  }
  function save() {
    try { localStorage.setItem(SIDEBAR_WIDTH_KEY, String(preferred.current)); } catch {}
  }
  function end(commit: boolean) {
    const active = drag.current;
    if (!active) return;
    drag.current = null;
    document.documentElement.classList.remove('sidebar-resizing');
    setResizing(false);
    setDragWidth(null);
    if (handle.current?.hasPointerCapture?.(active.id)) handle.current.releasePointerCapture(active.id);
    if (commit) {
      const nextCollapsed = active.current <= COLLAPSE_THRESHOLD;
      // Kéo vào rail giữ nguyên độ rộng đã chọn; mở bằng nút vẫn khôi phục được.
      if (!nextCollapsed) change(active.current);
      collapseChange.current(nextCollapsed);
      save();
    }
  }
  function finish() { end(true); }
  function cancel() { end(false); }

  useEffect(() => {
    const resize = () => { setViewport(window.innerWidth); if (window.innerWidth <= 720) cancel(); };
    window.addEventListener('resize', resize);
    window.addEventListener('blur', finish);
    return () => {
      window.removeEventListener('resize', resize);
      window.removeEventListener('blur', finish);
      document.documentElement.classList.remove('sidebar-resizing');
    };
  }, []);
  useEffect(() => { cancel(); }, [collapsed]);

  function start(event: PointerEvent<HTMLDivElement>) {
    if (drag.current || window.innerWidth <= 720 || event.button !== 0) return;
    event.preventDefault();
    drag.current = { id: event.pointerId, x: event.clientX, width, current: width };
    document.documentElement.classList.add('sidebar-resizing');
    setResizing(true);
    setDragWidth(width);
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current || drag.current.id !== event.pointerId) return;
    const next = Math.round(Math.max(COLLAPSED_SIDEBAR_WIDTH, Math.min(sidebarMaxWidth(window.innerWidth), drag.current.width + event.clientX - drag.current.x)));
    drag.current.current = next;
    setDragWidth(next);
  }
  function keyboard(event: KeyboardEvent<HTMLDivElement>) {
    if (window.innerWidth <= 720 || drag.current) return;
    const step = event.shiftKey ? 20 : 10;
    let next: number;
    if (event.key === 'ArrowLeft') next = collapsed ? COLLAPSED_SIDEBAR_WIDTH : width - step;
    else if (event.key === 'ArrowRight') next = collapsed ? boundWidth(preferred.current, window.innerWidth) : width + step;
    else if (event.key === 'Home') next = COLLAPSED_SIDEBAR_WIDTH;
    else if (event.key === 'End') next = maxWidth;
    else return;
    event.preventDefault();
    const nextCollapsed = next < MIN_SIDEBAR_WIDTH;
    if (!nextCollapsed) change(next);
    collapseChange.current(nextCollapsed);
    save();
  }

  return { width, expandedWidth, maxWidth, resizing, visualCollapsed, contentOpacity, handleProps: {
    ref: handle, onPointerDown: start, onPointerMove: move, onPointerUp: finish,
    onPointerCancel: cancel, onLostPointerCapture: finish, onKeyDown: keyboard,
    onDoubleClick: () => { if (window.innerWidth > 720) { change(DEFAULT_SIDEBAR_WIDTH); collapseChange.current(false); save(); } },
  } };
}
