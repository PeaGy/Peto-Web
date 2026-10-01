import { useEffect, useRef, useState, type ReactNode } from 'react';

/** Dữ liệu, tiện ích và biểu tượng dùng chung cho Peto Docs (Docs.tsx, DocsHome.tsx, DocsReader.tsx). */
export type Page = { slug: string; title: string; group: string; description: string; body: string; keywords: string[] };
export type DocsData = { version: string; pages: Page[] };

export const GROUPS = ['Bắt đầu', 'Peto Web', 'Companion', 'Agent CLI', 'Trợ giúp'];
export const GROUP_ICONS: Record<string, string> = {
  'Bắt đầu': 'spark', 'Peto Web': 'chat', Companion: 'heart', 'Agent CLI': 'terminal', 'Trợ giúp': 'help',
};
export const DISCORD = 'https://discord.gg/776G5z2pm9';
export const GITHUB = 'https://github.com/PeaGy';
/** Bài hiện sẵn khi ô tìm kiếm còn trống. */
export const SUGGESTED = ['bat-dau', 'cai-agent', 'giong-noi', 'khac-phuc'];

export const fold = (text: string) => text.toLowerCase().replaceAll('đ', 'd').normalize('NFD').replace(/[̀-ͯ]/g, '');
export const anchor = (text: string) => fold(text).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
export const headings = (body: string) => [...body.matchAll(/^## (.+)$/gm)]
  .map(match => ({ title: match[1].replace(/[`*_]/g, '').trim(), id: anchor(match[1]) }));
export const ordered = (pages: Page[]) => GROUPS.flatMap(group => pages.filter(page => page.group === group));
export const pageHref = (page: Page) => `/docs/${page.slug}/`;
export const minutes = (body: string) => Math.max(1, Math.round(body.split(/\s+/).length / 180));

export type Hit = { page: Page; section?: { title: string; id: string } };

/** Tìm không dấu: bài phải chứa mọi từ; khớp ở tiêu đề hoặc từ khóa xếp trước, kèm mục "## …" có chứa từ đó. */
export function searchPages(pages: Page[], query: string): Hit[] {
  const words = fold(query).trim().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  return pages.flatMap(page => {
    const haystack = fold(`${page.title} ${page.description} ${page.keywords.join(' ')} ${page.body}`);
    if (!words.every(word => haystack.includes(word))) return [];
    const section = headings(page.body).find(heading => words.some(word => fold(heading.title).includes(word)));
    const score = words.filter(word => fold(`${page.title} ${page.keywords.join(' ')}`).includes(word)).length;
    return [{ page, section, score }];
  }).sort((a, b) => b.score - a.score).slice(0, 8).map(({ page, section }) => ({ page, section }));
}

/** Chép vào bộ nhớ tạm và báo "đã chép" trong 1,6 giây. Trình duyệt từ chối thì trả false để nút báo lỗi. */
export function useCopied() {
  const [state, setState] = useState<'idle' | 'done' | 'failed'>('idle');
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  async function copy(text: string) {
    let ok = true;
    try { await navigator.clipboard.writeText(text); } catch { ok = false; }
    setState(ok ? 'done' : 'failed');
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState('idle'), 1600);
  }
  return [state, copy] as const;
}

const PATHS: Record<string, ReactNode> = {
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.8-3.8" /></>,
  arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
  external: <path d="M8 16 16 8m-7 0h7v7" />,
  back: <path d="M19 12H5m6 6-6-6 6-6" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5" /></>,
  moon: <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />,
  motion: <><path d="M4 12h9M4 7h5m-5 10h5" /><path d="m17 6 1.2 3.3L21.5 10.5l-3.3 1.2L17 15l-1.2-3.3-3.3-1.2 3.3-1.2Z" /></>,
  still: <><path d="M4 12h9M4 7h5m-5 10h5" /><circle cx="17.5" cy="10.5" r="3.5" /></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2.5" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></>,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  spark: <path d="m12 3 2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2Z" />,
  chat: <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-5 4v-4.2A2.5 2.5 0 0 1 4 13.5Z" />,
  heart: <path d="M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.4 4.3 4.3 0 0 1 19.5 10c0 5.4-7.5 10-7.5 10Z" />,
  terminal: <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="m7 9.5 2.5 2.5L7 14.5m5 0h5" /></>,
  help: <><circle cx="12" cy="12" r="9" /><path d="M9.6 9.3a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.4m0 3v.01" /></>,
  file: <><path d="M6 3h8l4 4v14H6Z" /><path d="M14 3v4h4" /></>,
  code: <path d="m8 8-4 4 4 4m8-8 4 4-4 4m-6 3 4-14" />,
};

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{PATHS[name] ?? PATHS.file}</svg>;
}
