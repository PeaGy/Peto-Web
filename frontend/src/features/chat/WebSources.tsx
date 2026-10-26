import { useMemo } from 'react';
import type { WebSource } from '../../shared/api/api';
import { GlobeIcon, SourceIcon } from './SourceIcon';
import { mergeDisplaySources, normalizeWeb, type WebActivity } from './sourceActivity';
import './sources.css';
export { safeSources } from './sourceData';
export { GlobeIcon } from './SourceIcon';

export default function WebSources({ sources, web, onOpen, expanded = false }: {
  sources?: WebSource[]; web?: WebActivity; onOpen?: () => void; expanded?: boolean;
}) {
  const activity = useMemo(() => normalizeWeb(web), [web]);
  const items = useMemo(() => mergeDisplaySources(sources, activity), [sources, activity]);
  if (!items.length && !activity?.calls.length) return null;
  const sites = items.slice(0, 3);
  return <div className="web-sources">
    <button type="button" className="web-sources-trigger" aria-label={items.length ? `Mở ${items.length} nguồn tham khảo` : 'Mở chi tiết tra cứu'}
      aria-expanded={expanded} aria-controls={expanded ? 'chat-sources-panel' : undefined} onClick={onOpen}>
      {sites.length ? <span className="source-favicons" aria-hidden="true">{sites.map(source => <span className="source-favicon" key={source.url}><SourceIcon url={source.url} /></span>)}</span> : <span className="source-trigger-globe"><GlobeIcon /></span>}
      <span>{items.length ? `${items.length} nguồn` : activity?.calls.some(call => call.state === 'live') ? 'Đang tra cứu' : 'Tra cứu'}</span>
    </button>
  </div>;
}
