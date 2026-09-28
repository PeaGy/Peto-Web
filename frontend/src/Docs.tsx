import { useEffect, useRef, useState, type ReactNode } from 'react';
import Markdown from 'react-markdown';
import './docs.css';

type Page = { slug: string; title: string; group: string; description: string; body: string; keywords: string[] };
type Data = { version: string; pages: Page[] };
const groups = ['Bắt đầu', 'Peto Web', 'Companion', 'Agent CLI', 'Trợ giúp'];
const discord = 'https://discord.gg/776G5z2pm9';
const github = 'https://github.com/PeaGy';
export const fold = (text: string) => text.toLowerCase().replaceAll('đ', 'd').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
export const anchor = (text: string) => fold(text).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const headings = (body: string) => [...body.matchAll(/^## (.+)$/gm)].map(m => ({ title: m[1], id: anchor(m[1]) }));
const href = (page: Page) => `/docs/${page.slug}/`;

function Icon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/></>,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6"/>,
    book: <><path d="M12 5v15M3 4c4-1 6 0 9 2 3-2 5-3 9-2v15c-4-1-6 0-9 2-3-2-5-3-9-2Z"/></>,
    terminal: <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="m7 9 3 3-3 3m6 0h4"/></>,
    spark: <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/>,
    menu: <path d="M4 7h16M4 12h16M4 17h16"/>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1"/></>,
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.book}</svg>;
}

function Code({ children }: { children?: ReactNode }) {
  const ref = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState('Sao chép');
  return <div className="docs-code"><button onClick={async () => {
    try { await navigator.clipboard.writeText(ref.current?.textContent || ''); setCopied('Đã sao chép'); }
    catch { setCopied('Hãy chọn và sao chép'); }
  }}>{copied}</button><pre ref={ref}>{children}</pre></div>;
}

export default function Docs() {
  const [data, setData] = useState<Data>();
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [path, setPath] = useState(location.pathname);
  const [menu, setMenu] = useState(false);
  const [light, setLight] = useState(() => { try { return localStorage.getItem('peto-docs-theme') === 'light'; } catch { return false; } });
  const [query, setQuery] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const searchTrigger = useRef<HTMLButtonElement>(null);
  const slug = path.replace(/^\/docs\/?/, '').replace(/\/$/, '');
  const page = data?.pages.find(p => p.slug === slug);
  const outline = page ? headings(page.body) : [];
  const ordered = groups.flatMap(group => data?.pages.filter(p => p.group === group) || []);
  const index = page ? ordered.indexOf(page) : -1;

  useEffect(() => {
    const abort = new AbortController(); setError(false);
    fetch('/api/docs', { signal: abort.signal }).then(r => { if (!r.ok) throw Error(); return r.json(); })
      .then(setData).catch(e => { if (e.name !== 'AbortError') setError(true); });
    return () => abort.abort();
  }, [attempt]);
  useEffect(() => {
    const pop = () => { setPath(location.pathname); setMenu(false); };
    const key = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openSearch(); } };
    window.addEventListener('popstate', pop); window.addEventListener('keydown', key);
    return () => { window.removeEventListener('popstate', pop); window.removeEventListener('keydown', key); };
  }, []);
  useEffect(() => {
    document.title = page ? `${page.title} · Peto Docs` : 'Peto Docs · Cùng Peto, bắt đầu điều mới';
    if (location.hash) requestAnimationFrame(() => document.getElementById(location.hash.slice(1))?.scrollIntoView());
  }, [page]);

  function openSearch() { setQuery(''); dialog.current?.showModal(); searchInput.current?.focus(); }
  function go(url: string) {
    history.pushState({}, '', url); setPath(location.pathname); setMenu(false); dialog.current?.close();
    window.scrollTo(0, 0);
    requestAnimationFrame(() => { if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView(); });
  }
  const words = fold(query).trim().split(/\s+/).filter(Boolean);
  const results = data?.pages.flatMap(p => {
    const haystack = fold(`${p.title} ${p.description} ${p.keywords.join(' ')} ${p.body}`);
    if (!words.length || !words.every(word => haystack.includes(word))) return [];
    const section = headings(p.body).find(h => words.some(word => fold(h.title).includes(word)));
    return [{ p, section, score: words.filter(word => fold(p.title + ' ' + p.keywords.join(' ')).includes(word)).length }];
  }).sort((a, b) => b.score - a.score).slice(0, 8) || [];

  const nav = <>{groups.map(group => <div className="docs-nav-group" key={group}><h3>{group}</h3>
    {data?.pages.filter(p => p.group === group).map(p => <a key={p.slug} href={href(p)} aria-current={p === page ? 'page' : undefined}>{p.title}</a>)}
  </div>)}</>;

  return <div className={`docs-shell${light ? ' docs-light' : ''}`} onClick={e => {
    const a = (e.target as Element).closest('a');
    if (a && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey && a.getAttribute('href')?.startsWith('/docs/')) {
      e.preventDefault(); go(a.getAttribute('href')!);
    }
  }}>
    <a href="#docs-main" className="docs-skip">Đến nội dung chính</a>
    <header className="docs-header">
      <a href="/docs/" className="docs-brand"><img src="/docs-assets/logo.png" alt=""/><span>Peto<span className="docs-brand-sub"> / docs</span></span></a>
      <button className="docs-search-trigger" aria-label="Tìm trong hướng dẫn" ref={searchTrigger} onClick={openSearch}><Icon name="search"/><span>Tìm trong hướng dẫn…</span><kbd>Ctrl K</kbd></button>
      <nav aria-label="Liên kết chính" className="docs-top-links"><a href="/docs/bat-dau/">Hướng dẫn</a><a href={discord} target="_blank" rel="noreferrer">Discord ↗</a><a href={github} target="_blank" rel="noreferrer">GitHub ↗</a></nav>
      <button className="docs-icon-button" aria-label={light ? 'Bật giao diện tối' : 'Bật giao diện sáng'} onClick={() => { setLight(!light); try { localStorage.setItem('peto-docs-theme', light ? 'dark' : 'light'); } catch { /* optional preference */ } }}><Icon name="sun"/></button>
      <a className="docs-open-app" href="/">Mở Peto <Icon name="arrow"/></a>
    </header>

    {!slug ? <main id="docs-main">
      <section className="docs-hero">
        <div className="docs-hero-grid" aria-hidden="true"/>
        <div className="docs-hero-copy"><div className="docs-eyebrow"><span/> KHÁM PHÁ KHÔNG GIAN CỦA BẠN</div>
          <h1>Một chút tò mò.<br/>Cả một thế giới<br/><em>cùng Peto.</em></h1>
          <p>Trò chuyện, sáng tạo, hay bắt tay vào một ý tưởng mới.<br className="docs-desktop-break"/> Mọi hành trình đều có một điểm bắt đầu.</p>
          <div className="docs-hero-actions"><a className="docs-primary" href="/docs/bat-dau/">Bắt đầu khám phá <Icon name="arrow"/></a><a className="docs-secondary" href="/docs/cai-agent/"><Icon name="terminal"/> Cài Agent CLI</a></div>
          <div className="docs-hero-note"><span>TIẾNG VIỆT</span><i/> Web · Companion · Agent</div>
        </div>
        <div className="docs-hero-art"><div className="docs-orbit"/><img src="/docs-assets/background.png" alt="Nhân vật minh họa rực rỡ của Peto" fetchPriority="high"/><div className="docs-art-label"><span>✦</span> Ý tưởng nhỏ. Khả năng lớn.</div></div>
        <div className="docs-hero-bottom"><span>HƯỚNG DẪN CHÍNH THỨC</span><a href="#kham-pha">Tìm không gian của bạn ↓</a></div>
      </section>
      <section className="docs-discover" id="kham-pha"><div className="docs-section-title"><div><div className="docs-eyebrow">BẠN MUỐN BẮT ĐẦU TỪ ĐÂU?</div><h2>Có một Peto dành cho việc đó.</h2></div><p>Từ lời chào đầu tiên đến dòng code tiếp theo.</p></div>
        <div className="docs-cards">{[
          ['01', 'book', 'Trò chuyện & sáng tạo', 'Hỏi điều bạn tò mò. Viết, học và biến ý tưởng thành hình ảnh.', 'tro-chuyen'],
          ['02', 'spark', 'Một người bạn đồng hành', 'Gặp nhân vật của bạn. Chọn bối cảnh, chuyển động và giọng nói.', 'companion'],
          ['03', 'terminal', 'Cùng bạn làm việc', 'Đưa Peto vào dự án với Agent CLI, skills và các công cụ MCP.', 'cai-agent'],
        ].map(([n, icon, title, desc, target]) => <a className="docs-card" key={n} href={`/docs/${target}/`}><div className="docs-card-top"><Icon name={icon}/><span>{n}</span></div><h3>{title}</h3><p>{desc}</p><span className="docs-card-link">Khám phá <Icon name="arrow"/></span></a>)}</div>
      </section>
      <section className="docs-community"><div><span className="docs-eyebrow">KHÔNG CẦN TỰ MÒ MỘT MÌNH</span><h2>Có câu hỏi? Cùng nói chuyện nhé.</h2><p>Chia sẻ ý tưởng, góp ý hoặc nhờ cộng đồng giúp một tay.</p></div><a className="docs-secondary" href={discord} target="_blank" rel="noreferrer">Tham gia Discord ↗</a></section>
    </main> : <>
      <div className="docs-mobile-bar"><button onClick={() => setMenu(!menu)} aria-expanded={menu} aria-controls="docs-sidebar"><Icon name="menu"/> Danh mục</button><span>{page?.group || 'Hướng dẫn'}</span></div>
      <div className="docs-reader">
        <aside id="docs-sidebar" className={`docs-sidebar${menu ? ' is-open' : ''}`} aria-label="Danh mục tài liệu">{nav}<a href={discord} className="docs-sidebar-help" target="_blank" rel="noreferrer">Cần trợ giúp? ↗</a></aside>
        <main id="docs-main" className="docs-article">
          {!data && !error ? <p role="status">Đang tải hướng dẫn…</p> : page ? <>
            <div className="docs-breadcrumb"><a href="/docs/">Tài liệu</a><span>/</span>{page.group}</div>
            <h1>{page.title}</h1><p className="docs-lead">{page.description}</p>
            <div className="docs-article-meta"><span>Hướng dẫn tiếng Việt</span>{page.group === 'Agent CLI' && <span>CLI {data?.version || '—'}</span>}</div>
            <details className="docs-mobile-outline"><summary>Trong bài này</summary>{outline.map(h => <a key={h.id} href={`#${h.id}`}>{h.title}</a>)}</details>
            <div className="docs-prose"><Markdown components={{
              h2: ({ children }) => <h2 id={anchor(String(children))}>{children}<a className="docs-heading-anchor" href={`#${anchor(String(children))}`} aria-label={`Liên kết đến ${children}`}>#</a></h2>,
              pre: ({ children }) => <Code>{children}</Code>,
              a: ({ href: url, children }) => <a href={url} {...(url?.startsWith('https://') ? { target: '_blank', rel: 'noreferrer' } : {})}>{children}</a>,
            }}>{page.body}</Markdown></div>
            <div className="docs-article-feedback"><span>Vướng ở bước nào đó?</span><a href={discord} target="_blank" rel="noreferrer">Hỏi cộng đồng trên Discord ↗</a><a href={`/api/docs/${page.slug}.md`}>Đọc bản Markdown ↗</a></div>
            <nav className="docs-pager" aria-label="Bài trước và tiếp theo">{index > 0 ? <a href={href(ordered[index - 1])}><small>← Bài trước</small>{ordered[index - 1].title}</a> : <span/>}{index < ordered.length - 1 && <a href={href(ordered[index + 1])}><small>Tiếp theo →</small>{ordered[index + 1].title}</a>}</nav>
          </> : !error && <><h1>Không tìm thấy bài viết</h1><p>Bài có thể đã được chuyển hoặc đường dẫn chưa đúng.</p><a href="/docs/">Về Peto Docs →</a></>}
        </main>
        <aside className="docs-outline" aria-label="Trong bài này"><h3>TRONG BÀI NÀY</h3>{outline.map(h => <a key={h.id} href={`#${h.id}`}>{h.title}</a>)}<div><span>Cùng xây dựng Peto</span><a href={github} target="_blank" rel="noreferrer">GitHub của PeaGy ↗</a><a href={discord} target="_blank" rel="noreferrer">Góp ý trên Discord ↗</a></div></aside>
      </div>
    </>}
    {error && <div className="docs-error" role="alert">Chưa tải được tài liệu. <button onClick={() => setAttempt(attempt + 1)}>Thử lại</button></div>}
    <footer className="docs-footer"><a href="/docs/" className="docs-brand"><img src="/docs-assets/logo.png" alt=""/>Peto <span className="docs-brand-sub">/ docs</span></a><span>Một nơi để bắt đầu, cùng nhau.</span><a href={github} target="_blank" rel="noreferrer">PeaGy ↗</a></footer>
    <dialog ref={dialog} className="docs-search-dialog" onClose={() => searchTrigger.current?.focus()} onClick={e => { if (e.target === dialog.current) dialog.current.close(); }} aria-labelledby="docs-search-title">
      <div className="docs-search-panel"><h2 id="docs-search-title">Tìm trong Peto Docs</h2><div className="docs-search-input"><Icon name="search"/><input ref={searchInput} value={query} onChange={e => setQuery(e.target.value)} placeholder="Thử “MCP”, “giọng nói”, “cài Agent”…" aria-label="Từ khóa tìm kiếm"/><button className="docs-icon-button" onClick={() => dialog.current?.close()} aria-label="Đóng tìm kiếm"><Icon name="close"/></button></div>
        <div className="docs-search-results" aria-live="polite">{!data ? <p>{error ? 'Chưa tải được tài liệu. Đóng tìm kiếm và thử tải lại.' : 'Đang tải tài liệu…'}</p> : !words.length ? <><p>Đi đến hướng dẫn thường dùng</p>{data.pages.filter(p => ['bat-dau', 'cai-agent', 'mcp', 'skills'].includes(p.slug)).map(p => <a key={p.slug} href={href(p)}><span>{p.title}</span><Icon name="arrow"/></a>)}</> : results.length ? results.map(({ p, section }) => <a key={p.slug} href={href(p) + (section ? '#' + section.id : '')}><div><small>{p.group}{section ? ' / ' + section.title : ''}</small><strong>{p.title}</strong><p>{p.description}</p></div><Icon name="arrow"/></a>) : <p>Không tìm thấy kết quả. Thử từ khóa ngắn hơn hoặc không dấu.</p>}</div><div className="docs-search-foot">Tab để chọn · Enter để mở · Esc để đóng</div></div>
    </dialog>
  </div>;
}
