import type { WebSource } from '../../shared/api/api';

export const CITATION_ID = /^(?:(?:web|x):[0-9]{1,9}|src:[a-f0-9]{16}|turn[0-9]{1,6}(?:search|view|fetch)[0-9]{1,6})$/;

export function safeSourceUrl(value: unknown): string | undefined {
  if (typeof value !== 'string' || !/^https?:\/\//i.test(value) || value.length > 2048 || /[\s\x00-\x1f\x7f\\]/.test(value)) return;
  try {
    const url = new URL(value);
    if (['https:', 'http:'].includes(url.protocol) && !url.username && !url.password) return value;
  } catch { /* Untrusted source metadata must not break the answer. */ }
}

export function safeSources(sources: WebSource[] | undefined): WebSource[] {
  const seen = new Map<string, WebSource>();
  const rank = { search: 1, tool: 2, page: 3 };
  for (const source of (Array.isArray(sources) ? sources : []).slice(0, 300)) {
    const safeUrl = safeSourceUrl(source?.url);
    if (!safeUrl) continue;
    const url = new URL(safeUrl);
    const item: WebSource = { url: safeUrl, title: typeof source.title === 'string' && source.title.trim()
      ? source.title.trim().slice(0, 200) : url.hostname };
    if (source.kind === 'citation' || source.kind === 'result') item.kind = source.kind;
    if (source.access === 'search' || source.access === 'page' || source.access === 'tool') item.access = source.access;
    if (source.partial === true) item.partial = true;
    const aliases = Array.isArray(source.citation_ids) ? source.citation_ids.slice(0, 24)
      .filter((id): id is string => typeof id === 'string' && CITATION_ID.test(id)) : [];
    if (aliases.length) item.citation_ids = [...new Set(aliases)];
    const old = seen.get(item.url);
    if (!old) seen.set(item.url, item);
    else {
      if (old.title === url.hostname || old.title === item.url) old.title = item.title;
      if (item.kind === 'citation') old.kind = 'citation';
      if (item.access && rank[item.access] > (old.access ? rank[old.access] : 0)) old.access = item.access;
      if (item.partial) old.partial = true;
      if (item.citation_ids?.length) old.citation_ids = [...new Set([...(old.citation_ids ?? []), ...item.citation_ids])].slice(0, 24);
    }
  }
  return [...seen.values()].sort((a, b) => Number(b.kind === 'citation') - Number(a.kind === 'citation')).slice(0, 30);
}

export function citationIndex(sources: WebSource[]) {
  const index = new Map<string, WebSource | null>();
  for (const source of sources) for (const id of source.citation_ids ?? []) {
    const old = index.get(id);
    index.set(id, old === undefined || old?.url === source.url ? source : null);
  }
  return index;
}
