import { isValidElement, useEffect, useRef, useState, type ReactNode } from 'react';
import Markdown, { type Components } from 'react-markdown';
import {
  DISCORD, GITHUB, GROUPS, GROUP_ICONS, Icon, anchor, headings, minutes, ordered, pageHref, useCopied, type DocsData, type Page,
} from './docsShared';

/** Trang bài của Peto Docs: tab nhóm, danh sách bài bên trái, bài ở giữa, mục lục và cộng đồng bên phải. */
const LANGS: Record<string, string> = {
  bash: 'Bash', sh: 'Shell', powershell: 'PowerShell', ps1: 'PowerShell', json: 'JSON', markdown: 'Markdown', md: 'Markdown',
  python: 'Python', text: 'Văn bản',
};

function textOf(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return '';
}

function CodeBlock({ children }: { children?: ReactNode }) {
  const pre = useRef<HTMLPreElement>(null);
  const [copied, copy] = useCopied();
  const className = isValidElement<{ className?: string }>(children) ? children.props.className ?? '' : '';
  const lang = /language-([\w-]+)/.exec(className)?.[1] ?? 'text';
  return <div className="docs-code">
    <div className="docs-code-bar">
      <span>{LANGS[lang] ?? lang}</span>
      <button type="button" aria-label={copied === 'done' ? 'Đã sao chép' : 'Sao chép khối này'}
        onClick={() => copy(pre.current?.textContent ?? '')}>
        <Icon name={copied === 'done' ? 'check' : 'copy'} size={15} />
      </button>
    </div>
    <pre ref={pre}>{children}</pre>
  </div>;
}

const MARKDOWN: Components = {
  h2: ({ children }) => {
    const id = anchor(textOf(children));
    return <h2 id={id}>{children}<a className="docs-anchor" href={`#${id}`} aria-label={`Liên kết tới mục ${textOf(children)}`}>#</a></h2>;
  },
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  a: ({ href, children }) => <a href={href} {...(href?.startsWith('http') ? { target: '_blank', rel: 'noreferrer' } : {})}>{children}</a>,
};

/** Mục đang đọc: mục cuối cùng có tiêu đề đã qua dưới header và thanh tab. */
function useReading(ids: string[]) {
  const [active, setActive] = useState(ids[0] ?? '');
  const key = ids.join('|');
  useEffect(() => {
    const update = () => {
      let current = ids[0] ?? '';
      for (const id of ids) {
        const element = document.getElementById(id);
        if (element && element.getBoundingClientRect().top < 140) current = id;
      }
      setActive(current);
    };
    update();
    window.addEventListener('scroll', update, { passive: true });
    return () => window.removeEventListener('scroll', update);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return active;
}

function Article({ page, version, previous, next }: { page: Page; version: string; previous?: Page; next?: Page }) {
  const [copied, copy] = useCopied();
  return <article className="docs-article">
    <p className="docs-eyebrow">{page.group}</p>
    <h1>{page.title}</h1>
    <p className="docs-lead">{page.description}</p>
    <div className="docs-meta">
      <span>{minutes(page.body)} phút đọc</span>
      {page.group === 'Agent CLI' && <span className="docs-badge">CLI {version}</span>}
      <span className="docs-meta-actions">
        <button type="button" onClick={() => copy(`# ${page.title}\n\n${page.body}\n`)}>
          <Icon name={copied === 'done' ? 'check' : 'copy'} size={15} />
          {copied === 'done' ? 'Đã chép' : copied === 'failed' ? 'Chưa chép được' : 'Chép Markdown'}
        </button>
        <a href={`/api/docs/${page.slug}.md`} target="_blank" rel="noreferrer"><Icon name="file" size={15} />Bản Markdown</a>
      </span>
    </div>
    <div className="docs-prose"><Markdown components={MARKDOWN}>{page.body}</Markdown></div>
    <div className="docs-help">
      <Icon name="help" size={18} />
      <p>Vẫn vướng ở một bước? Gửi ảnh chụp lỗi lên <a href={DISCORD} target="_blank" rel="noreferrer">Discord</a>
        {page.group === 'Agent CLI' ? ', kèm phiên bản CLI.' : '.'}</p>
    </div>
    <nav className="docs-pager" aria-label="Bài trước và bài tiếp theo">
      {previous ? <a href={pageHref(previous)} className="docs-pager-previous"><small>← Bài trước</small><span>{previous.title}</span></a> : <span />}
      {next && <a href={pageHref(next)} className="docs-pager-next"><small>Tiếp theo →</small><span>{next.title}</span></a>}
    </nav>
  </article>;
}

export default function DocsReader({ data, page, error, glass }: { data?: DocsData; page?: Page; error: boolean; glass: boolean }) {
  const pages = data ? ordered(data.pages) : [];
  const group = page?.group ?? '';
  const inGroup = pages.filter(item => item.group === group);
  const index = page ? pages.indexOf(page) : -1;
  const outline = page ? headings(page.body) : [];
  const reading = useReading(outline.map(heading => heading.id));
  const drawer = useRef<HTMLDialogElement>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const closeDrawer = () => { drawer.current?.close(); setDrawerOpen(false); };

  // Chọn một bài trong ngăn danh mục (điện thoại) thì đóng ngăn.
  useEffect(closeDrawer, [page?.slug]);

  return <>
    <nav className="docs-tabs" data-glass={glass ? '' : undefined} aria-label="Nhóm hướng dẫn">
      <div className="docs-tabs-inner">
        {GROUPS.map(name => {
          const first = pages.find(item => item.group === name);
          return first && <a key={name} href={pageHref(first)} aria-current={name === group ? 'true' : undefined}>
            <Icon name={GROUP_ICONS[name]} size={17} />{name}
          </a>;
        })}
      </div>
      <div className="docs-tabs-compact">
        <button type="button" aria-expanded={drawerOpen} aria-controls="docs-drawer"
          onClick={() => { drawer.current?.showModal(); setDrawerOpen(true); }}>
          <Icon name="menu" size={18} />Danh mục
        </button>
        {group && <span>{group}</span>}
      </div>
    </nav>

    <dialog id="docs-drawer" ref={drawer} className="docs-drawer" aria-label="Danh mục hướng dẫn"
      onClose={() => setDrawerOpen(false)}
      onClick={event => { if (event.target === drawer.current) closeDrawer(); }}>
      <div className="docs-drawer-head">
        <span>Danh mục</span>
        <button type="button" aria-label="Đóng danh mục" onClick={closeDrawer}><Icon name="close" /></button>
      </div>
      {GROUPS.map(name => {
        const items = pages.filter(item => item.group === name);
        return items.length > 0 && <section key={name}>
          <p><Icon name={GROUP_ICONS[name]} size={16} />{name}</p>
          {items.map(item => <a key={item.slug} href={pageHref(item)} aria-current={item === page ? 'page' : undefined}>{item.title}</a>)}
        </section>;
      })}
      <div className="docs-drawer-links">
        <a href="/">Mở Peto<Icon name="arrow" size={15} /></a>
        <a href={DISCORD} target="_blank" rel="noreferrer">Discord<Icon name="external" size={14} /></a>
        <a href={GITHUB} target="_blank" rel="noreferrer">GitHub<Icon name="external" size={14} /></a>
      </div>
    </dialog>

    <div className="docs-reader">
      <aside className="docs-side" aria-label={group ? `Bài trong nhóm ${group}` : 'Danh sách bài'}>
        {group && <p className="docs-side-title"><Icon name={GROUP_ICONS[group]} size={16} />{group}</p>}
        {inGroup.map(item => <a key={item.slug} href={pageHref(item)} aria-current={item === page ? 'page' : undefined}>{item.title}</a>)}
      </aside>

      <main id="docs-main" className="docs-main">
        {!data && !error ? <p className="docs-status" role="status">Đang tải hướng dẫn…</p>
          : page ? <Article key={page.slug} page={page} version={data?.version ?? ''} previous={pages[index - 1]} next={pages[index + 1]} />
            : !error && <div className="docs-missing">
              <h1>Không tìm thấy bài viết</h1>
              <p>Bài có thể đã được chuyển hoặc đường dẫn chưa đúng.</p>
              <a href="/docs/">Về trang đầu Peto Docs<Icon name="arrow" size={15} /></a>
            </div>}
      </main>

      <aside className="docs-aside" aria-label="Trên trang này và cộng đồng">
        {outline.length > 0 && <nav className="docs-outline" aria-label="Trên trang này">
          <p>Trên trang này</p>
          {outline.map(heading => <a key={heading.id} href={`#${heading.id}`} aria-current={reading === heading.id ? 'location' : undefined}>
            {heading.title}
          </a>)}
        </nav>}
        <div className="docs-community">
          <p>Cộng đồng</p>
          <a href={DISCORD} target="_blank" rel="noreferrer"><Icon name="chat" size={16} />Hỏi trên Discord<Icon name="external" size={13} /></a>
          <a href={GITHUB} target="_blank" rel="noreferrer"><Icon name="code" size={16} />GitHub của PeaGy<Icon name="external" size={13} /></a>
        </div>
      </aside>
    </div>
  </>;
}
