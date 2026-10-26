import type { WebSource } from '../../shared/api/api';
import { safeSources, safeSourceUrl } from './sourceData';

export interface DisplaySource extends WebSource { snippet?: string }
export interface WebCall {
  id: string;
  kind: 'search' | 'page';
  operation?: 'search' | 'fetch' | 'open_page' | 'find_in_page';
  queries: string[];
  state: 'live' | 'done' | 'failed' | 'stopped';
  source_urls: string[];
  url?: string;
}
export interface WebActivity { version: 1; sources: DisplaySource[]; calls: WebCall[]; truncated?: true }

export const MAX_DISPLAY_SOURCES = 200;
export const MAX_SOURCE_CALLS = 40;
const MAX_WEB_BYTES = 256 * 1024;
const accessRank = { search: 1, tool: 2, page: 3 };
const record = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown, limit: number) => typeof value === 'string' ? value.replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, limit) : '';

function displaySource(value: unknown): DisplaySource | undefined {
  if (!record(value)) return;
  const source = safeSources([value as unknown as WebSource])[0];
  if (!source) return;
  const snippet = text(value.snippet, 320);
  return snippet ? { ...source, snippet } : source;
}

function addSource(items: Map<string, DisplaySource>, next: DisplaySource) {
  const old = items.get(next.url);
  if (!old) { items.set(next.url, next); return; }
  const host = new URL(next.url).hostname;
  if (old.title === host || old.title === next.url) old.title = next.title;
  if (next.kind === 'citation') old.kind = 'citation';
  if (next.access && accessRank[next.access] > (old.access ? accessRank[old.access] : 0)) old.access = next.access;
  if (next.partial) old.partial = true;
  if (!old.snippet && next.snippet) old.snippet = next.snippet;
  const aliases = [...new Set([...(old.citation_ids ?? []), ...(next.citation_ids ?? [])])].slice(0, 24);
  if (aliases.length) old.citation_ids = aliases;
}

/** Display metadata is independent of the 30 sources used in the model context. */
export function normalizeWeb(value: unknown): WebActivity | undefined {
  if (!record(value) || value.version !== 1 || !Array.isArray(value.sources) || !Array.isArray(value.calls)) return;
  const sources = new Map<string, DisplaySource>();
  for (const raw of value.sources.slice(0, 400)) {
    const source = displaySource(raw);
    if (source) addSource(sources, source);
  }
  const all = [...sources.values()].sort((a, b) => Number(b.kind === 'citation') - Number(a.kind === 'citation'));
  const selected = all.slice(0, MAX_DISPLAY_SOURCES);
  const urls = new Set(selected.map(source => source.url));
  const calls = new Map<string, WebCall>();
  for (const raw of value.calls.slice(0, 80)) {
    if (!record(raw) || typeof raw.id !== 'string' || !raw.id || raw.id.length > 128 || /[\s\u0000-\u001f\u007f]/.test(raw.id)) continue;
    if (raw.kind !== 'search' && raw.kind !== 'page') continue;
    if (!['live', 'done', 'failed', 'stopped'].includes(String(raw.state))) continue;
    if (!Array.isArray(raw.queries) || !Array.isArray(raw.source_urls)) continue;
    const operation = raw.operation;
    const validOperation = raw.kind === 'search' ? operation === 'search' : operation === 'fetch' || operation === 'open_page' || operation === 'find_in_page';
    const call: WebCall = {
      id: raw.id, kind: raw.kind, state: raw.state as WebCall['state'],
      queries: [...new Set(raw.queries.slice(0, 8).map(query => text(query, 500)).filter(Boolean))],
      source_urls: [...new Set(raw.source_urls.slice(0, MAX_DISPLAY_SOURCES).filter((url): url is string => typeof url === 'string' && urls.has(url)))],
      ...(validOperation ? { operation: operation as WebCall['operation'] } : {}),
    };
    const url = safeSourceUrl(raw.url);
    if (url) call.url = url;
    const previous = calls.get(call.id);
    if (previous && previous.state !== 'live' && call.state === 'live') call.state = previous.state;
    calls.set(call.id, call);
  }
  const result: WebActivity = { version: 1, sources: selected, calls: [...calls.values()].slice(0, MAX_SOURCE_CALLS) };
  if (value.truncated === true || value.sources.length > 400 || all.length > MAX_DISPLAY_SOURCES || value.calls.length > 80 || calls.size > MAX_SOURCE_CALLS) result.truncated = true;
  // An oversized/unsupported envelope falls back to the existing safe flat source list.
  if (new TextEncoder().encode(JSON.stringify(result)).byteLength > MAX_WEB_BYTES) return;
  return result;
}

/** A source can appear in several query groups, but only once in the footer count. */
export function mergeDisplaySources(flat?: WebSource[], web?: WebActivity): DisplaySource[] {
  const items = new Map<string, DisplaySource>();
  for (const source of safeSources(flat)) addSource(items, { ...source });
  for (const source of web?.sources ?? []) addSource(items, { ...source });
  return [...items.values()].sort((a, b) => Number(b.kind === 'citation') - Number(a.kind === 'citation')).slice(0, MAX_DISPLAY_SOURCES);
}
