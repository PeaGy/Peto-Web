import { expect, it } from 'vitest';
import { mergeDisplaySources, normalizeWeb } from '../src/features/chat/sourceActivity';
import { safeSources } from '../src/features/chat/sourceData';

const a = { url: 'https://example.com/a', title: 'Trang A' };
const b = { url: 'https://example.org/b', title: 'Trang B' };
const call = { id: 'xai:1:web-1', kind: 'search', operation: 'search', queries: ['Một truy vấn thật'], state: 'done', source_urls: [a.url] };

it('chỉ nhận envelope có version và mảng nguồn/call hỗ trợ', () => {
  for (const value of [null, [], {}, { version: 2, sources: [], calls: [] }, { version: 1, sources: {}, calls: [] }]) expect(normalizeWeb(value)).toBeUndefined();
  expect(normalizeWeb({ version: 1, sources: [], calls: [] })).toEqual({ version: 1, sources: [], calls: [] });
});

it('hiển thị 105 nguồn mà không nới ngưỡng 30 nguồn ngữ cảnh/citation cũ', () => {
  const sources = Array.from({ length: 105 }, (_, n) => ({ url: `https://example.com/${n}`, title: `Trang ${n}` }));
  const web = normalizeWeb({ version: 1, sources, calls: [{ ...call, source_urls: sources.map(source => source.url) }] })!;
  expect(web.sources).toHaveLength(105);
  expect(web.calls[0].source_urls).toHaveLength(105);
  expect(mergeDisplaySources([], web)).toHaveLength(105);
  expect(safeSources(sources)).toHaveLength(30);
});

it('dedup URL giữ alias, bằng chứng page và snippet thật; không đọc encrypted_content', () => {
  const web = normalizeWeb({ version: 1, sources: [
    { ...a, title: 'example.com', access: 'search', citation_ids: ['web:1'], encrypted_content: 'secret' },
    { ...a, kind: 'citation', access: 'page', citation_ids: ['web:2'], snippet: '  Đoạn\n trích  thật ' },
    { ...b, encrypted_content: 'ciphertext', snippet: 5 },
  ], calls: [] })!;
  expect(web.sources).toHaveLength(2);
  expect(web.sources[0]).toEqual({ ...a, kind: 'citation', access: 'page', citation_ids: ['web:1', 'web:2'], snippet: 'Đoạn trích thật' });
  expect(web.sources[1]).not.toHaveProperty('snippet');
  expect(JSON.stringify(web)).not.toContain('secret');
  expect(JSON.stringify(web)).not.toContain('ciphertext');
});

it('nguồn có thể thuộc nhiều call, không tự ghép URL không có trong registry hoặc chia query', () => {
  const web = normalizeWeb({ version: 1, sources: [a, b], calls: [
    { ...call, queries: ['Truy vấn một', 'Truy vấn hai'], source_urls: [a.url, a.url, 'https://unknown.example/'] },
    { ...call, id: 'xai:1:web-2', queries: ['Truy vấn một'], source_urls: [a.url, b.url] },
  ] })!;
  expect(web.calls).toHaveLength(2);
  expect(web.calls[0].queries).toEqual(['Truy vấn một', 'Truy vấn hai']);
  expect(web.calls[0].source_urls).toEqual([a.url]);
  expect(web.calls[1].source_urls).toEqual([a.url, b.url]);
  expect(mergeDisplaySources([a], web)).toHaveLength(2);
});

it('không dựng query từ tiêu đề/prompt và loại call có ID/state/kind sai', () => {
  const web = normalizeWeb({ version: 1, sources: [a], calls: [
    { ...call, queries: [] },
    { ...call, id: '', queries: ['Không được nhận'] },
    { ...call, id: 'bad id' },
    { ...call, id: 'invalid-state', state: 'complete' },
    { ...call, id: 'invalid-kind', kind: 'thinking' },
  ] })!;
  expect(web.calls).toHaveLength(1);
  expect(web.calls[0].queries).toEqual([]);
});

it('lượt lặp ID không làm state kết thúc quay lại live', () => {
  const web = normalizeWeb({ version: 1, sources: [a], calls: [call, { ...call, state: 'live' }] })!;
  expect(web.calls).toHaveLength(1);
  expect(web.calls[0].state).toBe('done');
});

it('lọc URL không an toàn ở cả registry và membership, chỉ giữ HTTP(S) không credentials', () => {
  const bad = ['javascript:alert(1)', 'https://u:p@example.com/x', 'https://example.com/\\evil', 'data:text/html,x'];
  const web = normalizeWeb({ version: 1, sources: [a, ...bad.map(url => ({ url, title: 'Unsafe' }))], calls: [{ ...call, source_urls: [a.url, ...bad], url: 'javascript:alert(1)' }] })!;
  expect(web.sources).toEqual([a]);
  expect(web.calls[0].source_urls).toEqual([a.url]);
  expect(web.calls[0]).not.toHaveProperty('url');
});

it('giới hạn nguồn/call/snippet/query và đánh dấu truncated khi cắt danh mục', () => {
  const web = normalizeWeb({ version: 1,
    sources: Array.from({ length: 210 }, (_, n) => ({ url: `https://example.com/${n}`, title: `Trang ${n}`, snippet: 'x'.repeat(600) })),
    calls: Array.from({ length: 45 }, (_, n) => ({ ...call, id: `web-${n}`, queries: ['q'.repeat(700)] })),
  })!;
  expect(web.sources).toHaveLength(200);
  expect(web.calls).toHaveLength(40);
  expect(web.sources[0].snippet).toHaveLength(320);
  expect(web.calls[0].queries[0]).toHaveLength(500);
  expect(web.truncated).toBe(true);
});

it('envelope vượt ngân sách quay về nguồn phẳng an toàn', () => {
  const web = normalizeWeb({ version: 1, sources: Array.from({ length: 200 }, (_, n) => ({ url: `https://example.com/${n}/${'x'.repeat(1800)}`, title: `Trang ${n}` })), calls: [] });
  expect(web).toBeUndefined();
  expect(mergeDisplaySources([a], web)).toEqual([a]);
});

it('bổ sung metadata nguồn phẳng không làm mất snippet hay alias của danh mục', () => {
  const web = normalizeWeb({ version: 1, sources: [{ ...a, snippet: 'Đoạn trích', citation_ids: ['web:21'] }], calls: [] })!;
  expect(mergeDisplaySources([{ ...a, kind: 'citation', citation_ids: ['web:26'] }], web)).toEqual([
    { ...a, kind: 'citation', citation_ids: ['web:26', 'web:21'], snippet: 'Đoạn trích' },
  ]);
});
