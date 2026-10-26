import type { ReactNode } from 'react';

function Icon({ children }: { children: ReactNode }) {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>;
}

export function CopyIcon() {
  return <Icon><rect x="9" y="9" width="11" height="11" rx="2.5" /><path d="M15 5.5A2.5 2.5 0 0 0 12.5 3h-7A2.5 2.5 0 0 0 3 5.5v7A2.5 2.5 0 0 0 5.5 15" /></Icon>;
}
export function CheckIcon() { return <Icon><path d="m5 12.5 4.5 4.5L19 7" /></Icon>; }
export function DownloadIcon() { return <Icon><path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4" /></Icon>; }
export function RetryIcon() { return <Icon><path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5" /></Icon>; }
export function MoreIcon() { return <Icon><circle cx="5" cy="12" r="1" fill="currentColor" /><circle cx="12" cy="12" r="1" fill="currentColor" /><circle cx="19" cy="12" r="1" fill="currentColor" /></Icon>; }
export function MarkdownIcon() { return <Icon><path d="M3 5h18v14H3zM6 15V9l3 3 3-3v6m3-3 2 2 2-2m-2-3v5" /></Icon>; }
export function PrintIcon() { return <Icon><path d="M7 8V3h10v5M7 17H4V9h16v8h-3M7 14h10v7H7zM17 11h.01" /></Icon>; }
export function ChevronIcon({ next = false }: { next?: boolean }) { return <Icon><path d={next ? 'm9 6 6 6-6 6' : 'm15 6-6 6 6 6'} /></Icon>; }
export function CollapseIcon({ collapsed }: { collapsed: boolean }) {
  return <Icon><path d={collapsed ? 'M9 3H3v6m0-6 7 7m5 11h6v-6m0 6-7-7' : 'M3 9h6V3M9 9 2 2m19 13h-6v6m0-6 7 7'} /></Icon>;
}
export function WrapIcon({ wrapped }: { wrapped: boolean }) {
  return <Icon>{wrapped
    ? <><path d="M3 6h18M3 12h18M3 18h14" /><path d="m14 15 3 3-3 3" /></>
    : <><path d="M3 6h18M3 12h13a4 4 0 0 1 0 8h-3M3 18h4" /><path d="m13 17-3 3 3 3" /></>}</Icon>;
}
