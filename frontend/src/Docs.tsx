import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react';
import { motionEnabled, readCharacterMotion } from './characterView';
import DocsHome from './DocsHome';
import DocsReader from './DocsReader';
import { DISCORD, GITHUB, GROUP_ICONS, Icon, SUGGESTED, pageHref, searchPages, type DocsData, type Hit, type Page } from './docsShared';
import './docs.css';

/**
 * Peto Docs tại /docs/: trang đầu (nhân vật và họa tiết theo chuột) và trang bài ba cột, theo hướng "Bàn làm việc" mà
 * chủ dự án chọn, pha giao diện docs của AIRI. Đây là khung chung: tải dữ liệu, đường dẫn, header, tìm kiếm và hai công tắc.
 */
const THEME_KEY = 'peto-docs-theme';
const MOTION_KEY = 'peto-docs-motion';
const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';
const HOME_TITLE = 'Peto Docs · Cùng Peto, bắt đầu điều mới';

function readLight() {
  try { return localStorage.getItem(THEME_KEY) === 'light'; } catch { return false; }
}

function readMotionChoice(): 'on' | 'off' | null {
  try {
    const value = localStorage.getItem(MOTION_KEY);
    return value === 'on' || value === 'off' ? value : null;
  } catch {
    return null;
  }
}

function systemReducesMotion() {
  return typeof matchMedia === 'function' && matchMedia(REDUCED_MOTION).matches;
}

/**
 * Hiệu ứng động (nhân vật theo chuột, họa tiết trôi). Đã bấm công tắc trên header thì theo công tắc. Chưa bấm thì theo
 * "Nhân vật cử động" của Peto (cùng localStorage vì cùng tên miền): mặc định nhường cài đặt giảm chuyển động của máy.
 */
function useMotion() {
  const [choice, setChoice] = useState(readMotionChoice);
  const [systemReduces, setSystemReduces] = useState(systemReducesMotion);
  useEffect(() => {
    if (typeof matchMedia !== 'function') return;
    const query = matchMedia(REDUCED_MOTION);
    const change = () => setSystemReduces(query.matches);
    query.addEventListener('change', change);
    return () => query.removeEventListener('change', change);
  }, []);
  const enabled = choice ? choice === 'on' : motionEnabled(readCharacterMotion(), systemReduces);
  const toggle = () => {
    const next = enabled ? 'off' : 'on';
    setChoice(next);
    try { localStorage.setItem(MOTION_KEY, next); } catch { /* chỉ là lựa chọn hiển thị */ }
  };
  return [enabled, toggle] as const;
}

/** Như header của AIRI: ở đầu trang thì trong suốt để thấy nền, cuộn xuống thì phủ nền mờ. */
function useScrolled() {
  const [scrolled, setScrolled] = useState(() => window.scrollY > 0);
  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 0);
    update();
    window.addEventListener('scroll', update, { passive: true });
    return () => window.removeEventListener('scroll', update);
  }, []);
  return scrolled;
}

function scrollToHash(hash: string) {
  if (!hash) return;
  requestAnimationFrame(() => document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView());
}

function Switch({ label, on, icon, onToggle, className = '' }: {
  label: string; on: boolean; icon: string; onToggle: () => void; className?: string;
}) {
  return <button type="button" role="switch" aria-checked={on} aria-label={label} title={label}
    className={`docs-switch ${className}`} onClick={onToggle}>
    <span className="docs-switch-knob"><Icon name={icon} size={13} /></span>
  </button>;
}

/** Ô tìm ngay trên header (combobox): gõ không dấu cũng được, ↑↓ để chọn, Enter để mở, Esc để thoát, Ctrl K để tới ô. */
function Search({ pages, onOpen }: { pages?: Page[]; onOpen: (url: string) => void }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const text = query.trim();
  const hits: Hit[] = !pages ? [] : text ? searchPages(pages, text)
    : SUGGESTED.flatMap(slug => pages.filter(page => page.slug === slug)).map(page => ({ page }));
  const url = (hit: Hit) => pageHref(hit.page) + (hit.section ? `#${hit.section.id}` : '');

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        input.current?.focus();
        input.current?.select();
      }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, []);

  function choose(hit: Hit) {
    setQuery('');
    setOpen(false);
    input.current?.blur();
    onOpen(url(hit));
  }

  return <div className="docs-search">
    <Icon name="search" size={16} />
    <input ref={input} value={query} placeholder="Tìm hướng dẫn, lệnh, lỗi…" aria-label="Tìm trong Peto Docs"
      role="combobox" aria-expanded={open} aria-controls="docs-search-list" aria-autocomplete="list"
      aria-activedescendant={open && hits[active] ? `docs-search-${active}` : undefined}
      onChange={event => { setQuery(event.target.value); setActive(0); setOpen(true); }}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault();
          setOpen(true);
          const step = event.key === 'ArrowDown' ? 1 : -1;
          setActive(index => hits.length ? (index + step + hits.length) % hits.length : 0);
        } else if (event.key === 'Enter' && open && hits[active]) {
          event.preventDefault();
          choose(hits[active]);
        } else if (event.key === 'Escape') {
          if (query) setQuery('');
          else { setOpen(false); input.current?.blur(); }
        }
      }} />
    <kbd aria-hidden="true">Ctrl K</kbd>
    {open && <div className="docs-search-panel" onMouseDown={event => event.preventDefault()}>
      <p id="docs-search-caption" className="docs-search-caption">
        {!pages ? 'Đang tải hướng dẫn…' : text ? (hits.length ? 'Kết quả' : `Không có kết quả cho “${text}”`) : 'Bài hay đọc'}
      </p>
      <div id="docs-search-list" role="listbox" aria-labelledby="docs-search-caption">
        {hits.map((hit, index) => (
          <a key={url(hit)} id={`docs-search-${index}`} role="option" tabIndex={-1} aria-selected={index === active}
            href={url(hit)} onMouseMove={() => setActive(index)} onClick={() => { setQuery(''); setOpen(false); input.current?.blur(); }}>
            <Icon name={GROUP_ICONS[hit.page.group]} size={16} />
            <span><strong>{hit.page.title}</strong><small>{hit.page.group}{hit.section ? ` › ${hit.section.title}` : ` · ${hit.page.description}`}</small></span>
            <Icon name="arrow" size={15} />
          </a>
        ))}
      </div>
      {text && !hits.length && pages && <p className="docs-search-empty">Thử từ ngắn hơn, không dấu cũng được.</p>}
    </div>}
  </div>;
}

export default function Docs() {
  const [data, setData] = useState<DocsData>();
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [path, setPath] = useState(location.pathname);
  const [light, setLight] = useState(readLight);
  const [motion, toggleMotion] = useMotion();
  const scrolled = useScrolled();
  const slug = path.replace(/^\/docs\/?/, '').replace(/\/$/, '');
  const page = data?.pages.find(item => item.slug === slug);

  useEffect(() => {
    const abort = new AbortController();
    setError(false);
    fetch('/api/docs', { signal: abort.signal })
      .then(response => { if (!response.ok) throw new Error(String(response.status)); return response.json(); })
      .then(setData)
      .catch(reason => { if (reason.name !== 'AbortError') setError(true); });
    return () => abort.abort();
  }, [attempt]);

  useEffect(() => {
    const pop = () => setPath(location.pathname);
    window.addEventListener('popstate', pop);
    return () => window.removeEventListener('popstate', pop);
  }, []);

  useEffect(() => {
    if (!slug) document.title = HOME_TITLE;
    else if (data) document.title = `${page ? page.title : 'Không tìm thấy bài'} · Peto Docs`;
    scrollToHash(location.hash);
  }, [slug, page, data]);

  // Liên kết nội bộ (/docs/...) đổi bài tại chỗ, không tải lại trang. Ctrl/⌘/Shift-click vẫn mở tab mới như thường.
  const go = useCallback((url: string) => {
    const target = new URL(url, location.origin);
    const samePage = target.pathname === location.pathname;
    history.pushState({}, '', target.pathname + target.hash);
    if (samePage) { scrollToHash(target.hash); return; }
    window.scrollTo(0, 0);
    setPath(target.pathname);
  }, []);

  function follow(event: MouseEvent) {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const link = (event.target as Element).closest('a');
    const url = link?.getAttribute('href');
    if (!link || !url?.startsWith('/docs') || link.target) return;
    event.preventDefault();
    go(url);
  }

  function toggleTheme() {
    setLight(!light);
    try { localStorage.setItem(THEME_KEY, light ? 'dark' : 'light'); } catch { /* chỉ là lựa chọn hiển thị */ }
  }

  // Trang đầu luôn phủ nền cho header như AIRI; trang bài để header trong suốt khi còn ở đầu trang.
  const glass = !slug || scrolled;
  return <div className={`docs${light ? ' docs-light' : ''}${motion ? ' docs-motion' : ''}`} onClick={follow}>
    <a href="#docs-main" className="docs-skip">Đến nội dung chính</a>
    {slug && <div className="docs-glow" aria-hidden="true" />}
    <header className="docs-top" data-glass={glass ? '' : undefined}>
      <div className="docs-top-inner">
        <a className="docs-brand" href="/docs/">
          <img src="/docs-assets/logo.webp" alt="" width="144" height="100" />
          <span>Peto</span><em>Docs</em>
        </a>
        <Search pages={data?.pages} onOpen={go} />
        <nav className="docs-top-links" aria-label="Liên kết chính">
          <a href="/docs/bat-dau/" aria-current={slug ? 'page' : undefined}>Hướng dẫn</a>
          <a href={DISCORD} target="_blank" rel="noreferrer">Discord<Icon name="external" size={14} /></a>
          <a href={GITHUB} target="_blank" rel="noreferrer">GitHub<Icon name="external" size={14} /></a>
        </nav>
        <div className="docs-top-tools">
          <Switch label="Hiệu ứng chuyển động" on={motion} icon={motion ? 'motion' : 'still'} onToggle={toggleMotion}
            className="docs-motion-switch" />
          <Switch label="Nền tối" on={!light} icon={light ? 'sun' : 'moon'} onToggle={toggleTheme} />
          {slug && <a className="docs-open" href="/">Mở Peto<Icon name="arrow" size={15} /></a>}
        </div>
      </div>
    </header>

    {slug ? <DocsReader data={data} page={page} error={error} glass={glass} /> : <DocsHome motion={motion} />}

    {error && <div className="docs-error" role="alert">
      Chưa tải được tài liệu.
      <button type="button" onClick={() => setAttempt(value => value + 1)}>Thử lại</button>
    </div>}
  </div>;
}
