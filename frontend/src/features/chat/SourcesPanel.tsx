import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { WebSource } from '../../shared/api/api';
import { GlobeIcon, SourceIcon, sourceHost } from './SourceIcon';
import { mergeDisplaySources, normalizeWeb, type DisplaySource, type WebActivity, type WebCall } from './sourceActivity';
import './sources.css';

function evidence(source: DisplaySource, groupAccess?: DisplaySource['access']) {
  if (source.access === groupAccess && !source.partial) return '';
  return source.access === 'page' ? 'Đã mở trang' : source.access === 'tool'
    ? source.partial ? 'Công cụ · một phần' : 'Kết quả công cụ' : source.access === 'search' ? 'Kết quả tìm kiếm' : '';
}

function SourceCards({ items, showEvidence = false, groupAccess }: { items: DisplaySource[]; showEvidence?: boolean; groupAccess?: DisplaySource['access'] }) {
  return <div className="web-source-list">{items.map(source => <a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer"
    className="web-source-card" title={source.url}>
    <span className="web-source-text"><strong>{source.title}</strong>{source.snippet && <span className="web-source-snippet">{source.snippet}</span>}</span>
    <span className="web-source-site"><span className="web-source-icon" aria-hidden="true"><SourceIcon url={source.url} /></span><span>{sourceHost(source.url)}</span></span>
    {showEvidence && evidence(source, groupAccess) && <small className="web-source-evidence">{evidence(source, groupAccess)}</small>}
  </a>)}</div>;
}

function callLabel(call: WebCall) {
  if (call.state === 'failed') return call.kind === 'page' ? 'Mở trang bị lỗi' : 'Tìm kiếm bị lỗi';
  if (call.state === 'stopped') return call.kind === 'page' ? 'Đã dừng mở trang' : 'Đã dừng tìm kiếm';
  if (call.operation === 'find_in_page') return call.state === 'live' ? 'Đang tìm trong trang' : 'Đã tìm trong trang';
  return call.kind === 'page' ? call.state === 'live' ? 'Đang mở trang' : 'Đã mở trang'
    : call.state === 'live' ? 'Đang tìm trên web' : 'Đã tìm trên web';
}

function PageIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M13 5H5a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h13a1 1 0 0 0 1-1v-8M14 4h6v6M20 4 10 14" /></svg>;
}

function SourceGroup({ call, items }: { call: WebCall; items: DisplaySource[] }) {
  const [open, setOpen] = useState(false);
  const regionId = useId();
  const label = callLabel(call);
  const title = call.queries.length ? call.queries.join('\n') : call.url ? sourceHost(call.url) : call.kind === 'page' ? 'Trang tham khảo' : 'Lượt tra cứu';
  return <section className={`source-query-group ${call.state}`}>
    <h3><button type="button" className="source-query-toggle" aria-label={`${label}: ${title} · ${items.length} nguồn`} aria-expanded={open} aria-controls={regionId} onClick={() => setOpen(value => !value)}>
      <span className="source-query-glyph" aria-hidden="true">{open ? <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg> : call.kind === 'page' ? <PageIcon /> : <GlobeIcon />}</span>
      <span className="source-query-copy"><span className="source-query-label">{label}</span><strong title={title}>{title}</strong></span>
      <span className="source-query-count" aria-label={`${items.length} nguồn`}>{items.length}</span>
    </button></h3>
    <div id={regionId} role="region" aria-label={title} hidden={!open}>
      {open && (items.length ? <SourceCards items={items} /> : <p className="source-query-empty">{call.state === 'live' ? 'Đang nhận kết quả…' : call.state === 'failed' ? 'Lượt này chưa có nguồn dùng được.' : 'Không có nguồn để hiển thị.'}</p>)}
    </div>
  </section>;
}

export default function SourcesPanel({ sources, web, onClose }: { sources?: WebSource[]; web?: WebActivity; onClose: () => void }) {
  const activity = useMemo(() => normalizeWeb(web), [web]);
  const items = useMemo(() => mergeDisplaySources(sources, activity), [sources, activity]);
  const panel = useRef<HTMLDialogElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [sheet, setSheet] = useState(() => window.matchMedia?.('(max-width: 1100px)')?.matches ?? false);
  useEffect(() => {
    const element = panel.current;
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    return () => { element?.close(); if (opener.current?.isConnected) opener.current.focus({ preventScroll: true }); };
  }, []);
  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 1100px)');
    if (!media) return;
    const update = () => setSheet(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    const element = panel.current;
    if (!element) return;
    if (sheet) element.showModal(); else element.show();
    close.current?.focus({ preventScroll: true });
    return () => element.close();
  }, [sheet]);
  const byUrl = new Map(items.map(source => [source.url, source]));
  const assigned = new Set(activity?.calls.flatMap(call => call.source_urls) ?? []);
  const unassigned = items.filter(source => !assigned.has(source.url));
  const groups: { title: string; items: DisplaySource[]; access?: DisplaySource['access'] }[] = activity?.calls.length ? [{ title: 'Nguồn tham khảo khác', items: unassigned }] : [
    { title: 'Nguồn trích dẫn', items: unassigned.filter(source => source.kind === 'citation') },
    { title: 'Trang đã mở', access: 'page', items: unassigned.filter(source => source.kind !== 'citation' && source.access === 'page') },
    { title: 'Kết quả công cụ', access: 'tool', items: unassigned.filter(source => source.kind !== 'citation' && source.access === 'tool') },
    { title: 'Kết quả tìm kiếm', access: 'search', items: unassigned.filter(source => source.kind !== 'citation' && (!source.access || source.access === 'search') && (source.kind === 'result' || source.access === 'search')) },
    { title: 'Nguồn tham khảo', items: unassigned.filter(source => !source.kind && !source.access) },
  ];
  return <dialog ref={panel} id="chat-sources-panel" className="sources-panel" role={sheet ? 'dialog' : 'complementary'} aria-modal={sheet ? true : undefined}
    aria-label="Nguồn tham khảo" onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { if (sheet && event.target === event.currentTarget && event.clientY < event.currentTarget.getBoundingClientRect().top) onClose(); }}
    onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onClose(); }
      if (sheet && event.key === 'Tab') {
        const targets = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button, a[href], [tabindex="0"]')).filter(target => !target.closest('[hidden]') && !(target instanceof HTMLButtonElement && target.disabled));
        const first = targets[0], last = targets.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }}>
    <header className="sources-panel-head"><h2>Nguồn</h2><button ref={close} type="button" className="sources-panel-close" aria-label="Đóng bảng nguồn" onClick={onClose}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
    </button></header>
    <div className="sources-panel-scroll" tabIndex={0} role="region" aria-label="Danh sách nguồn">
      {activity?.calls.map(call => <SourceGroup key={call.id} call={call} items={call.source_urls.flatMap(url => byUrl.has(url) ? [byUrl.get(url)!] : [])} />)}
      {groups.filter(group => group.items.length).map(group => <section key={group.title} className="source-ungrouped"><h3>{group.title}<span>{group.items.length}</span></h3><SourceCards items={group.items} showEvidence groupAccess={group.access} /></section>)}
      {activity?.truncated && <p className="source-limit-note">Đang hiển thị phần nguồn đã được lưu trong giới hạn của lượt này.</p>}
      {!items.length && !activity?.calls.length && <p className="source-query-empty">Chưa có nguồn để hiển thị.</p>}
    </div>
  </dialog>;
}
