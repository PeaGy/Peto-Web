import type { ReactNode } from 'react';

export type StudioIconName = 'back' | 'grid' | 'search' | 'check' | 'download' | 'trash' | 'brush' | 'palette' | 'crop' | 'info' | 'plus' | 'minus' | 'undo' | 'redo' | 'share' | 'close' | 'eraser' | 'panel' | 'heart' | 'arrowUp';
const paths: Record<StudioIconName, ReactNode> = {
  back: <path d="m12 5-7 7 7 7M5 12h14" />,
  grid: <><rect x="4" y="4" width="6" height="6" rx="1.5" /><rect x="14" y="4" width="6" height="6" rx="1.5" /><rect x="4" y="14" width="6" height="6" rx="1.5" /><rect x="14" y="14" width="6" height="6" rx="1.5" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  download: <path d="M12 3v12m-5-5 5 5 5-5M5 17v4h14v-4" />,
  trash: <path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6m4-6v6" />,
  brush: <><path d="m9 14 9-10a2 2 0 0 1 3 3L11 16M9 14l2 2" /><path d="M9 14c-4-1-5 2-5 6 4 0 7-1 7-4" /></>,
  palette: <><circle cx="12" cy="12" r="9" /><path d="M12 3v9l8 4M12 12l-8 4m8-4v9M5 6l7 6 7-6" /></>,
  crop: <path d="M6 3v15h15M3 6h15v15" />,
  info: <><rect x="4" y="4" width="7" height="7" rx="2" /><rect x="14" y="7" width="6" height="6" rx="2" /><rect x="7" y="14" width="6" height="6" rx="2" /></>,
  plus: <path d="M12 5v14M5 12h14" />, minus: <path d="M5 12h14" />,
  undo: <path d="m8 4-5 5 5 5M3 9h11a6 6 0 0 1 0 12" />, redo: <path d="m16 4 5 5-5 5M21 9H10a6 6 0 0 0 0 12" />,
  share: <path d="M12 16V3m-5 5 5-5 5 5M5 13v8h14v-8" />,
  heart: <path d="M20.8 4.6a5.4 5.4 0 0 0-7.6 0L12 5.8l-1.2-1.2a5.4 5.4 0 0 0-7.6 7.6L12 21l8.8-8.8a5.4 5.4 0 0 0 0-7.6Z" />,
  arrowUp: <path d="M12 20V4m-6 6 6-6 6 6" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  eraser: <><path d="m4 14 9-10 8 7-9 10H9l-5-4v-3Zm4-5 8 7M12 21h9" /></>,
  panel: <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M15 4v16" /></>,
};
export default function StudioIcon({ name }: { name: StudioIconName }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
