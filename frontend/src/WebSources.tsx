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

function SourceList({ items }: { items: WebSource[] }) {
  return <div className="web-source-list">{items.map(source => <a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer" className="web-source-card" title={source.url}>
    <span><strong>{source.title}</strong><small>{new URL(source.url).hostname.replace(/^www\./, '')}{new URL(source.url).pathname}</small></span><span aria-hidden="true">↗</span>
  </a>)}</div>;
}

export default function WebSources({ sources }: { sources?: WebSource[] }) {
  const items = safeSources(sources);
  if (!items.length) return null;
  const cited = items.filter(item => item.kind === 'citation');
  const results = items.filter(item => item.kind === 'result');
  const legacy = items.filter(item => !item.kind);
  const label = cited.length ? `Nguồn · ${cited.length}`
    : results.length ? `Kết quả tìm kiếm · ${results.length}` : `Nguồn tham khảo · ${legacy.length}`;
  return <details className="web-sources">
    <summary><GlobeIcon /><span>{label}</span></summary>
    <div className="web-sources-panel">
      {cited.length > 0 && <section><h3>Nguồn trích dẫn</h3><SourceList items={cited} /></section>}
      {results.length > 0 && (cited.length > 0
        ? <details className="web-source-results"><summary>Kết quả tìm kiếm khác · {results.length}</summary>
            <p>Các trang tìm thấy, chưa được đánh dấu trích dẫn trong câu trả lời.</p><SourceList items={results} />
          </details>
        : <section><h3>Kết quả tìm kiếm</h3><p>Các trang tìm thấy, chưa được đánh dấu trích dẫn trong câu trả lời.</p><SourceList items={results} /></section>)}
      {legacy.length > 0 && <section><h3>Nguồn tham khảo</h3><p>Hội thoại cũ chưa phân biệt nguồn trích dẫn và kết quả tìm kiếm.</p><SourceList items={legacy} /></section>}
    </div>
  </details>;
}
