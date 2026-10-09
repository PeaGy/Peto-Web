import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';

export const SIDEBAR_WIDTH_KEY = 'peto-sidebar-width';
export const DEFAULT_SIDEBAR_WIDTH = 260;
export const MIN_SIDEBAR_WIDTH = 220;
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
export function useSidebarResize(collapsed: boolean) {
  const [preferredWidth, setPreferredWidth] = useState(readWidth);
  const preferred = useRef(preferredWidth);
  const [viewport, setViewport] = useState(() => window.innerWidth);
  const [resizing, setResizing] = useState(false);
  const handle = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: number; x: number; width: number } | null>(null);
  const maxWidth = sidebarMaxWidth(viewport);
  const width = boundWidth(preferredWidth, viewport);

  function change(next: number) {
    preferred.current = boundWidth(next, window.innerWidth);
    setPreferredWidth(preferred.current);
  }
  function save() {
    try { localStorage.setItem(SIDEBAR_WIDTH_KEY, String(preferred.current)); } catch {}
  }
  function finish() {
    const active = drag.current;
    if (!active) return;
    drag.current = null;
    document.documentElement.classList.remove('sidebar-resizing');
    setResizing(false);
    if (handle.current?.hasPointerCapture?.(active.id)) handle.current.releasePointerCapture(active.id);
    save();
  }

  useEffect(() => {
    const resize = () => { setViewport(window.innerWidth); if (window.innerWidth <= 720) finish(); };
    window.addEventListener('resize', resize);
    window.addEventListener('blur', finish);
    return () => {
      window.removeEventListener('resize', resize);
      window.removeEventListener('blur', finish);
      document.documentElement.classList.remove('sidebar-resizing');
    };
  }, []);
  useEffect(() => { if (collapsed) finish(); }, [collapsed]);

  function start(event: PointerEvent<HTMLDivElement>) {
    if (collapsed || window.innerWidth <= 720 || event.button !== 0) return;
    event.preventDefault();
    drag.current = { id: event.pointerId, x: event.clientX, width };
    document.documentElement.classList.add('sidebar-resizing');
    setResizing(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current || drag.current.id !== event.pointerId) return;
    change(drag.current.width + event.clientX - drag.current.x);
  }
  function keyboard(event: KeyboardEvent<HTMLDivElement>) {
    if (collapsed || window.innerWidth <= 720) return;
    const step = event.shiftKey ? 20 : 10;
    let next: number;
    if (event.key === 'ArrowLeft') next = width - step;
    else if (event.key === 'ArrowRight') next = width + step;
    else if (event.key === 'Home') next = MIN_SIDEBAR_WIDTH;
    else if (event.key === 'End') next = maxWidth;
    else return;
    event.preventDefault(); change(next); save();
  }

  return { width, maxWidth, resizing, handleProps: {
    ref: handle, onPointerDown: start, onPointerMove: move, onPointerUp: finish,
    onPointerCancel: finish, onLostPointerCapture: finish, onKeyDown: keyboard,
    onDoubleClick: () => { if (!collapsed && window.innerWidth > 720) { change(DEFAULT_SIDEBAR_WIDTH); save(); } },
  } };
}
