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
  const groups = [
    { kind: 'citation', label: 'nguồn được trích dẫn', note: 'Các nguồn được nhà cung cấp đánh dấu trích dẫn trong câu trả lời.' },
    { kind: 'result', label: 'kết quả tìm kiếm', note: 'Các trang công cụ tìm thấy, không đồng nghĩa đều được dùng trong câu trả lời.' },
    { kind: undefined, label: 'nguồn tham khảo', note: 'Nguồn của hội thoại cũ chưa có thông tin phân biệt trích dẫn và kết quả tìm kiếm.' },
  ] as const;
  return <>{groups.map(group => {
    const entries = items.filter(item => item.kind === group.kind);
    if (!entries.length) return null;
    return <details className="web-sources" key={group.label}>
    <summary><GlobeIcon /><span>{entries.length} {group.label}</span></summary>
    <p>{group.note}</p>
    <div className="web-source-list">{entries.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer" className="web-source-card" title={source.url}>
      <span><strong>{source.title}</strong><small>{new URL(source.url).hostname.replace(/^www\./, '')}{new URL(source.url).pathname}</small></span><span aria-hidden="true">↗</span>
    </a>)}</div>
  </details>;
  })}</>;
}
