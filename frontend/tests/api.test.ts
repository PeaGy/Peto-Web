import { afterEach, expect, it, vi } from 'vitest';
import { createImagineJob, sendMessage } from '../src/api';

afterEach(() => vi.unstubAllGlobals());
const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;

it('thẻ tài liệu và tiến trình tạo tệp tách khỏi lời trả lời', async () => {
  const artifact = { id: 'D1', filename: 'Bài văn.docx', title: 'Bài văn', version: 1, pages: 2, format: 'docx', style: 'essay' };
  vi.stubGlobal('fetch', vi.fn(async () => new Response(event({ type: 'document_status', text: 'Đang tạo tệp' }) + event({ type: 'artifact', artifact }) + event({ type: 'delta', text: 'Đã tạo.' }) + event({ type: 'done' }))));
  const onArtifact = vi.fn(), onDocumentStatus = vi.fn(), onDelta = vi.fn();
  await sendMessage({ message: 'Tạo Word', conversationId: null, effort: 'auto' }, { onArtifact, onDocumentStatus, onDelta });
  expect(onArtifact).toHaveBeenCalledExactlyOnceWith(artifact);
  expect(onDocumentStatus).toHaveBeenCalledWith('Đang tạo tệp');
  expect(onDelta).toHaveBeenCalledExactlyOnceWith('Đã tạo.');
});

it('tiến trình đọc tệp không trộn vào câu trả lời', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(event({ type: 'reading', text: 'Peto đang đọc 1 tài liệu…' }) + event({ type: 'delta', text: 'Nội dung' }) + event({ type: 'done' }))));
  const onReading = vi.fn(), onDelta = vi.fn();
  await sendMessage({ message: 'Tóm tắt', conversationId: null, effort: 'auto' }, { onReading, onDelta });
  expect(onReading).toHaveBeenCalledExactlyOnceWith('Peto đang đọc 1 tài liệu…');
  expect(onDelta).toHaveBeenCalledExactlyOnceWith('Nội dung');
});

it('gửi chế độ tìm web và đọc nguồn qua SSE mà không trộn vào văn bản', async () => {
  const sources = [{ url: 'https://docs.python.org/3/', title: 'Tài liệu Python' }];
  const fetchMock = vi.fn(async () => new Response(event({ type: 'search', status: 'searching' }) + event({ type: 'sources', sources }) + event({ type: 'delta', text: 'Có nguồn' }) + event({ type: 'done' })));
  vi.stubGlobal('fetch', fetchMock);
  const onSources = vi.fn(), onSearch = vi.fn(), onDelta = vi.fn();
  await sendMessage({ message: 'Tìm Python', conversationId: null, effort: 'auto', webSearch: 'on' }, { onSources, onSearch, onDelta });
  expect(onSearch).toHaveBeenCalledWith('searching');
  expect(onSources).toHaveBeenCalledWith(sources);
  expect(onDelta).toHaveBeenCalledExactlyOnceWith('Có nguồn');
  const body = JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string);
  expect(body.web_search).toBe('on');
});

it.each([{ source_image: { data: 'anh-base64' } }, { source_image_id: 'anh-da-luu' }])('gửi ảnh gốc trong yêu cầu chỉnh sửa', async (source) => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ job: { id: 'ket-qua' } })));
  vi.stubGlobal('fetch', fetchMock);
  const payload = { prompt: 'Đổi nền', quality: 'low' as const, resolution: '1k' as const, aspect_ratio: 'auto', n: 1, ...source };
  expect(await createImagineJob(payload)).toEqual({ id: 'ket-qua' });
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe('/api/imagine');
  expect(JSON.parse(init.body as string)).toEqual(payload);
});

it('decodes UTF-8 and SSE boundaries split across network chunks', async () => {
  const encoded = new TextEncoder().encode(event({type:'delta',text:'Tiếng Việt'}) + event({type:'done'}));
  vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream({
    start(controller) { for (const byte of encoded) controller.enqueue(new Uint8Array([byte])); controller.close(); },
  }))));
  const onDelta = vi.fn();
  const onDone = vi.fn();
  await sendMessage({message:'hi',conversationId:null,effort:'auto'}, {onDelta,onDone});
  expect(onDelta).toHaveBeenCalledWith('Tiếng Việt');
  expect(onDone).toHaveBeenCalledOnce();
});

it('reports a truncated stream instead of treating it as complete', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(event({type:'delta',text:'Nửa câu'}))));
  const onDone = vi.fn();
  await expect(sendMessage({message:'hi',conversationId:null,effort:'auto'}, {onDone})).rejects.toThrow('Kết nối bị ngắt');
  expect(onDone).not.toHaveBeenCalled();
});

it('stopping discards remaining events already buffered in the same chunk', async () => {
  const controller = new AbortController();
  vi.stubGlobal('fetch', vi.fn(async () => new Response(
    event({type:'delta',text:'Giữ phần này'}) + event({type:'delta',text:'Đến muộn'}) + event({type:'done'}),
  )));
  const onDelta = vi.fn(() => controller.abort());
  const onDone = vi.fn();
  await expect(sendMessage({message:'hi',conversationId:null,effort:'auto'}, {onDelta,onDone}, controller.signal))
    .rejects.toMatchObject({name:'AbortError'});
  expect(onDelta).toHaveBeenCalledExactlyOnceWith('Giữ phần này');
  expect(onDone).not.toHaveBeenCalled();
});

it('sends only the browser timezone, never the browser clock', async () => {
  const fetchMock = vi.fn(async () => new Response(event({type:'done'})));
  vi.stubGlobal('fetch', fetchMock);
  await sendMessage({message:'Mấy giờ?',conversationId:null,effort:'auto'}, {});
  const body = JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string);
  expect(body.timezone).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
  expect(body).not.toHaveProperty('timestamp');
  expect(body).not.toHaveProperty('current_time');
});
