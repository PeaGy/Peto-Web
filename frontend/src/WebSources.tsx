import type { WebSource } from './api';

export function safeSources(sources: WebSource[] | undefined): WebSource[] {
  const seen = new Set<string>();
  return (Array.isArray(sources) ? sources : []).filter((source) => {
    if (!source || typeof source.url !== 'string' || /[\s\x00-\x1f]/.test(source.url)) return false;
    try {
      const url = new URL(source.url);
      if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || seen.has(source.url)) return false;
      seen.add(source.url);
      return true;
    } catch { return false; }
  }).slice(0, 30).map((source) => ({ ...source, title: typeof source.title === 'string' && source.title.trim() ? source.title : new URL(source.url).hostname }));
}

export function GlobeIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" /><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z" stroke="currentColor" strokeWidth="1.6" /></svg>;
}

export default function WebSources({ sources }: { sources?: WebSource[] }) {
  const items = safeSources(sources);
  if (!items.length) return null;
  return <details className="web-sources">
    <summary><GlobeIcon /><span>{items.length} nguồn tham khảo</span></summary>
    <p>Các trang được công cụ tìm kiếm trả về cho câu trả lời này.</p>
    <div className="web-source-list">{items.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer" className="web-source-card" title={source.url}>
      <span><strong>{source.title}</strong><small>{new URL(source.url).hostname.replace(/^www\./, '')}{new URL(source.url).pathname}</small></span><span aria-hidden="true">↗</span>
    </a>)}</div>
  </details>;
}
