import type { WebSource } from '../../shared/api/api';
import { GitHubIcon } from '../../shared/ui/GitHubIcon';
import { YouTubeIcon } from '../../shared/ui/YouTubeIcon';
import { safeSources } from './sourceData';
export { safeSources } from './sourceData';

export function GlobeIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" /><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z" stroke="currentColor" strokeWidth="1.6" /></svg>;
}

function sourceSite(url: string) {
  const host = new URL(url).hostname;
  // Dựa vào hostname thật, không dựa vào tiêu đề, đường dẫn hoặc tên miền giả có chứa tên dịch vụ.
  const belongsTo = (domain: string) => host === domain || host.endsWith(`.${domain}`);
  if (belongsTo('youtube.com') || belongsTo('youtu.be') || belongsTo('youtube-nocookie.com')) return 'youtube';
  if (belongsTo('github.com')) return 'github';
  return 'web';
}

function SourceIcon({ site }: { site: ReturnType<typeof sourceSite> }) {
  if (site === 'youtube') return <YouTubeIcon />;
  if (site === 'github') return <GitHubIcon />;
  return <GlobeIcon />;
}

function SourceList({ items }: { items: WebSource[] }) {
  return <div className="web-source-list">{items.map(source => <a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer" className="web-source-card" title={source.url}>
    <span className="web-source-icon"><SourceIcon site={sourceSite(source.url)} /></span>
    <span className="web-source-text"><strong>{source.title}</strong><small>{new URL(source.url).hostname.replace(/^www\./, '')}{new URL(source.url).pathname}</small>
      {source.access && <small className="web-source-evidence">{source.access === 'page' ? 'Đã mở trang'
        : source.access === 'tool' ? source.partial ? 'Công cụ · một phần' : 'Kết quả công cụ' : 'Kết quả tìm kiếm'}</small>}
    </span><span aria-hidden="true">↗</span>
  </a>)}</div>;
}

export default function WebSources({ sources }: { sources?: WebSource[] }) {
  const items = safeSources(sources);
  if (!items.length) return null;
  const firstSite = sourceSite(items[0].url);
  const summarySite = items.every(item => sourceSite(item.url) === firstSite) ? firstSite : 'web';
  const cited = items.filter(item => item.kind === 'citation');
  const opened = items.filter(item => item.kind !== 'citation' && item.access === 'page');
  const tools = items.filter(item => item.kind !== 'citation' && item.access === 'tool');
  const results = items.filter(item => item.kind !== 'citation' && (!item.access || item.access === 'search') && (item.kind === 'result' || item.access === 'search'));
  const legacy = items.filter(item => !item.kind && !item.access);
  const label = cited.length ? `Nguồn · ${cited.length}`
    : opened.length || tools.length ? `Nguồn tham khảo · ${items.length}`
    : results.length ? `Kết quả tìm kiếm · ${results.length}` : `Nguồn tham khảo · ${legacy.length}`;
  return <details className="web-sources">
    <summary><SourceIcon site={summarySite} /><span>{label}</span></summary>
    <div className="web-sources-panel">
      {cited.length > 0 && <section><h3>Nguồn trích dẫn</h3><SourceList items={cited} /></section>}
      {opened.length > 0 && <section><h3>Trang đã mở</h3><SourceList items={opened} /></section>}
      {tools.length > 0 && <section><h3>Kết quả công cụ</h3><SourceList items={tools} /></section>}
      {results.length > 0 && (cited.length > 0
        ? <details className="web-source-results"><summary>Kết quả tìm kiếm khác · {results.length}</summary>
            <p>Các trang tìm thấy, chưa được đánh dấu trích dẫn trong câu trả lời.</p><SourceList items={results} />
          </details>
        : <section><h3>Kết quả tìm kiếm</h3><p>Các trang tìm thấy, chưa được đánh dấu trích dẫn trong câu trả lời.</p><SourceList items={results} /></section>)}
      {legacy.length > 0 && <section><h3>Nguồn tham khảo</h3><p>Hội thoại cũ chưa phân biệt nguồn trích dẫn và kết quả tìm kiếm.</p><SourceList items={legacy} /></section>}
    </div>
  </details>;
}
