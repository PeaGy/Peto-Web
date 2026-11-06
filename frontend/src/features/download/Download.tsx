import { useEffect, useRef, useState } from 'react';
import { Icon, Switch, readLight, saveLight, useCopied, useMotion, useScrolled } from '../docs/docsShared';
import { AppPreview, FeatureCards, SmartScreen } from './Showcase';
import {
  formatDate, formatSize, installerLabel, osName, primaryInstaller, useRelease, type Installer, type Release, type ReleaseState,
} from './release';
import { useScrollMotion } from './scrollMotion';
import '../docs/docs.css';
import './download.css';

/**
 * Trang tải Peto Agent tại /download/ (từ 6/11/2026), hướng "Trưng bày" chủ dự án chọn từ ba mockup: học bố cục và
 * chuyển động của trang DeepSeek Harness (hero canh giữa, nút tải có menu, cửa sổ ứng dụng dựng bằng HTML, thẻ tính năng có
 * minh họa, khối kêu gọi tải ở cuối), dùng hệ thiết kế của Peto Docs (màu, font, header, hai công tắc dùng chung).
 * Bộ cài nằm ở GitHub Releases; máy chủ đọc bản mới nhất (release.ts). Chưa có bản phát hành thì trang chỉ còn CLI.
 */
const TITLE = 'Tải Peto Agent · Peto';
const UPSTREAM = 'https://github.com/deepseek-ai/deepseek-harness';

function Windows() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
    <path d="M3 5.5 10.5 4.5v7H3zm0 13 7.5 1v-7H3zm8.5 1.1L21 21v-8.5h-9.5zm0-15.2v7.1H21V3z" /></svg>;
}

function Apple() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
    <path d="M16.4 12.6c0-2.3 1.9-3.4 2-3.5-1.1-1.6-2.8-1.8-3.4-1.8-1.4-.1-2.8.9-3.5.9-.7 0-1.8-.9-3-.8-1.5 0-3 .9-3.8 2.3-1.6 2.8-.4 7 1.2 9.3.8 1.1 1.7 2.4 2.9 2.3 1.2 0 1.6-.7 3-.7s1.8.7 3 .7c1.2 0 2-1.1 2.8-2.3.9-1.3 1.2-2.6 1.3-2.6-.1 0-2.5-1-2.5-3.8zM14.1 5.8c.6-.8 1.1-1.8 1-2.8-.9 0-2 .6-2.6 1.4-.6.7-1.1 1.7-1 2.7 1 .1 2-.5 2.6-1.3z" /></svg>;
}

const osIcon = (item: Installer) => (item.os === 'macos' ? <Apple /> : <Windows />);

/** Nút tải chính kèm menu các bản khác (như DeepSeek): mọi bộ cài của bản phát hành, macOS "sắp có" nếu chưa có, và CLI. */
function DownloadMenu({ release, primary }: { release: Extract<Release, { available: true }>; primary: Installer }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const hasMac = release.installers.some(item => item.os === 'macos');

  useEffect(() => {
    if (!open) return;
    box.current?.querySelector<HTMLElement>('[role="menuitem"]:not([aria-disabled])')?.focus();
    const outside = (event: PointerEvent) => { if (!box.current?.contains(event.target as Node)) setOpen(false); };
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); toggle.current?.focus(); return; }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      event.preventDefault();
      const items = [...(box.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([aria-disabled])') ?? [])];
      const at = items.indexOf(document.activeElement as HTMLElement);
      items[(at + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', key); };
  }, [open]);

  return <div className="dl-cta" ref={box}>
    <div className="dl-split">
      <a href={primary.url} className="dl-split-main">{osIcon(primary)}Tải cho {osName(primary)}</a>
      <button ref={toggle} type="button" aria-haspopup="menu" aria-expanded={open} aria-label="Các bản tải khác"
        onClick={() => setOpen(value => !value)}><Icon name="chevron" size={16} /></button>
    </div>
    {open && <div className="dl-menu" role="menu" aria-label="Các bản tải">
      {release.installers.map(item => <a key={item.url} role="menuitem" href={item.url} onClick={() => setOpen(false)}>
        {osIcon(item)}<span>{installerLabel(item)}<small>{item.name} · {formatSize(item.size)}</small></span>
      </a>)}
      {!hasMac && <span role="menuitem" aria-disabled="true"><Apple /><span>macOS<small>Sắp có</small></span></span>}
      <a role="menuitem" href="#cli" onClick={() => setOpen(false)}><Icon name="terminal" size={18} />
        <span>Dòng lệnh (CLI)<small>Cài bằng một lệnh PowerShell</small></span></a>
    </div>}
  </div>;
}

/** Nút tải và dòng thông tin dưới nó, theo trạng thái đọc bản phát hành. */
function Hero({ state }: { state: ReleaseState }) {
  const release = state.kind === 'ready' ? state.release : undefined;
  const primary = release?.available ? primaryInstaller(release.installers) : undefined;
  if (release?.available && primary) {
    const date = formatDate(release.published_at);
    return <>
      <DownloadMenu release={release} primary={primary} />
      <p className="dl-meta">
        Bản <b>{release.version}</b>{date && <> · {date}</>} · {installerLabel(primary)} · {formatSize(primary.size)}
        {' · '}<a href={release.notes_url} target="_blank" rel="noreferrer">Có gì mới</a>
      </p>
    </>;
  }
  if (!release) {
    return <>
      <div className="dl-cta"><span className="dl-split dl-split-wait"><Windows />Tải cho Windows</span></div>
      <p className="dl-meta" role="status">Đang tìm bản mới nhất…</p>
    </>;
  }
  return <>
    <div className="dl-cta"><a className="dl-split dl-split-solo" href="#cli"><Icon name="terminal" size={18} />Cài bản dòng lệnh</a></div>
    <p className="dl-meta">Bộ cài cho Windows đang được chuẩn bị. Trong lúc chờ, bạn dùng được Peto Agent CLI ngay.</p>
  </>;
}

function InstallCommand() {
  const command = `irm ${location.origin}/install.ps1 | iex`;
  const [copied, copy] = useCopied();
  return <div className="dl-cmd">
    <code>{command}</code>
    <button type="button" onClick={() => void copy(command)} aria-live="polite">
      <Icon name={copied === 'done' ? 'check' : 'copy'} size={15} />
      {copied === 'done' ? 'Đã chép' : copied === 'failed' ? 'Chép không được' : 'Sao chép'}
    </button>
  </div>;
}

export default function Download() {
  const [light, setLight] = useState(readLight);
  const [motion, toggleMotion] = useMotion();
  const scrolled = useScrolled();
  const state = useRelease();
  const page = useRef<HTMLDivElement>(null);
  useScrollMotion(page, motion);
  useEffect(() => { document.title = TITLE; }, []);

  const release = state.kind === 'ready' && state.release.available ? state.release : undefined;
  const primary = release ? primaryInstaller(release.installers) : undefined;
  const releases = state.kind === 'ready' ? state.release.releases_url : null;

  function toggleTheme() {
    setLight(!light);
    saveLight(!light);
  }

  return <div ref={page} className={`docs dl${light ? ' docs-light' : ''}${motion ? ' docs-motion' : ''}`}>
    <a href="#dl-main" className="docs-skip">Đến nội dung chính</a>
    <header className="docs-top" data-glass={scrolled ? '' : undefined}>
      <div className="docs-top-inner">
        <a className="docs-brand" href="/download/">
          <img src="/docs-assets/logo.webp" alt="" width="144" height="100" />
          <span>Peto</span><em>Agent</em>
        </a>
        <nav className="docs-top-links" aria-label="Liên kết chính">
          <a href="/docs/">Hướng dẫn</a>
          <a href="/">Peto Web</a>
          {release && <a href={release.notes_url} target="_blank" rel="noreferrer">Có gì mới<Icon name="external" size={14} /></a>}
        </nav>
        <div className="docs-top-tools dl-tools">
          <Switch label="Hiệu ứng chuyển động" on={motion} icon={motion ? 'motion' : 'still'} onToggle={toggleMotion}
            className="docs-motion-switch" />
          <Switch label="Nền tối" on={!light} icon={light ? 'sun' : 'moon'} onToggle={toggleTheme} />
          <a className="docs-open" href={primary?.url ?? '#cli'}><Icon name="download" size={15} />Tải xuống</a>
        </div>
      </div>
    </header>

    <main id="dl-main">
      <section className="dl-hero">
        <div className="dl-glow" aria-hidden="true" />
        <div className="dl-wrap">
          <p className="dl-eyebrow dl-rise"><Icon name="spark" size={14} />Bản xem trước</p>
          <h1 className="dl-rise" data-step="1">Peto Agent<br /><span>làm việc ngay trên máy bạn.</span></h1>
          <p className="dl-lead dl-rise" data-step="2">Giao việc bằng lời: Peto đọc và sửa tệp, chạy lệnh, kiểm tra kết quả ngay trong
            thư mục dự án của bạn. Đăng nhập bằng tài khoản Peto, không cần khóa API.</p>
          <div className="dl-rise" data-step="3"><Hero state={state} /></div>
          <div className="dl-rise" data-step="4"><AppPreview /></div>
        </div>
      </section>

      <section className="dl-block">
        <div className="dl-wrap">
          <h2 data-reveal="20">Một trợ lý,<br />đủ việc cho dự án của bạn.</h2>
          <p className="dl-sub" data-reveal="20" data-delay="90">Peto làm ngay trên máy bạn, trong đúng thư mục bạn chọn, và chỉ
            làm tới mức quyền bạn cho.</p>
          <FeatureCards />
        </div>
      </section>

      <section className="dl-block" id="cai-dat">
        <div className="dl-wrap">
          <h2 data-reveal="20">Cài trong ba bước</h2>
          <ol className="dl-steps">
            <li data-reveal="30"><span className="dl-step-n">1</span><h3>Tải bộ cài</h3>
              <p>Bấm “Tải cho Windows” rồi mở tệp <code>.exe</code> vừa tải.</p></li>
            <li data-reveal="30"><span className="dl-step-n">2</span><h3>Nếu Windows cảnh báo</h3>
              <p>Bản xem trước chưa có chữ ký số, nên Windows có thể hiện hộp màu xanh. Chọn “More info” rồi “Run anyway”.</p>
              <SmartScreen /></li>
            <li data-reveal="30"><span className="dl-step-n">3</span><h3>Đăng nhập Peto</h3>
              <p>Mở Peto Agent, bấm “Sign in”, rồi bấm “Cho phép” trên Peto Web. Từ đó bạn giao việc được ngay.</p></li>
          </ol>
        </div>
      </section>

      <section className="dl-block" id="cli">
        <div className="dl-wrap">
          <h2 data-reveal="20">Thích dòng lệnh?</h2>
          <div className="dl-dev">
            <article className="dl-card dl-card-flat" data-reveal="30">
              <h3>Peto Agent CLI</h3>
              <p>Bản dòng lệnh <code>peto</code> chạy trong terminal Windows, dùng chung tài khoản Peto. Mở PowerShell rồi dán:</p>
              <InstallCommand />
            </article>
            <article className="dl-card dl-card-flat" data-reveal="30">
              <h3>Có bản mới thì sao?</h3>
              <p>Tải bộ cài mới ở trang này rồi cài như lần đầu. Các phiên làm việc và cài đặt của bạn vẫn giữ nguyên.</p>
              {releases && <a className="dl-link" href={releases} target="_blank" rel="noreferrer">
                Xem mọi bản phát hành<Icon name="external" size={14} /></a>}
            </article>
          </div>
        </div>
      </section>

      <section className="dl-end" data-glow="">
        <div className="dl-wrap" data-reveal="40" data-blur="10">
          <h2>Sẵn sàng thử Peto Agent?</h2>
          <div className="dl-end-row">
            {primary
              ? <a className="dl-solid" href={primary.url}><Icon name="download" size={18} />Tải cho {osName(primary)}</a>
              : <a className="dl-solid" href="#cli"><Icon name="terminal" size={18} />Cài bản dòng lệnh</a>}
            <a className="dl-ghost" href="/docs/">Đọc hướng dẫn</a>
          </div>
        </div>
      </section>
    </main>

    <footer className="dl-foot">
      <div className="dl-wrap">
        <a className="docs-brand" href="/"><img src="/docs-assets/logo.webp" alt="" width="144" height="100" /><span>Peto</span></a>
        <a href="/docs/">Hướng dẫn</a>
        <a href="/">Peto Web</a>
        <span className="dl-foot-credit">Dựng trên <a href={UPSTREAM} target="_blank" rel="noreferrer">DeepSeek Harness</a> · MIT</span>
      </div>
    </footer>
  </div>;
}
