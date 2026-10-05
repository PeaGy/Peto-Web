import { afterEach, expect, it, vi } from 'vitest';
import { createImagineJob, sendMessage } from '../src/shared/api/api';

afterEach(() => vi.unstubAllGlobals());
const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;

it('giữ vị trí và thứ tự nhiều cảm xúc khi đọc SSE', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(
    event({ type: 'emotion', emotion: 'surprised', offset: 0 }) + event({ type: 'delta', text: 'Oh!' })
    + event({ type: 'emotion', emotion: 'happy', offset: 3 }) + event({ type: 'delta', text: ' Great!' }) + event({ type: 'done' }))));
  const onEmotion = vi.fn();
  await sendMessage({ message: 'Tin vui', conversationId: null, effort: 'low', mode: 'companion' }, { onEmotion });
  expect(onEmotion.mock.calls).toEqual([['surprised', 0], ['happy', 3]]);
});

it('thẻ tài liệu và tiến trình tạo tệp tách khỏi lời trả lời', async () => {
  const artifact = { id: 'D1', filename: 'Bài văn.docx', title: 'Bài văn', version: 1, pages: 2, format: 'docx', style: 'essay' };
  vi.stubGlobal('fetch', vi.fn(async () => new Response(event({ type: 'document_status', text: 'Đang tạo tệp' }) + event({ type: 'artifact', artifact }) + event({ type: 'delta', text: 'Đã tạo.' }) + event({ type: 'done' }))));
  const onArtifact = vi.fn(), onDocumentStatus = vi.fn(), onDelta = vi.fn();
  await sendMessage({ message: 'Tạo Word', conversationId: null, effort: 'auto' }, { onArtifact, onDocumentStatus, onDelta });
  expect(onArtifact).toHaveBeenCalledExactlyOnceWith(artifact);
  expect(onDocumentStatus).toHaveBeenCalledWith('Đang tạo tệp');
  expect(onDelta).toHaveBeenCalledExactlyOnceWith('Đã tạo.');
});

it('tìm và đọc thêm trong tệp đi riêng, không trộn vào câu trả lời', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(
    event({ type: 'file_lookup', text: 'Đang tìm “ERROR” trong app.log…', live: true })
    + event({ type: 'file_lookup', text: 'Đã tìm “ERROR” trong app.log: 2 dòng khớp', live: false })
    + event({ type: 'delta', text: 'Có hai lỗi.' }) + event({ type: 'done' }))));
  const onFileLookup = vi.fn(), onDelta = vi.fn();
  await sendMessage({ message: 'Lỗi gì?', conversationId: 'C', effort: 'auto' }, { onFileLookup, onDelta });
  expect(onFileLookup.mock.calls).toEqual([
    ['Đang tìm “ERROR” trong app.log…', true],
    ['Đã tìm “ERROR” trong app.log: 2 dòng khớp', false],
  ]);
  expect(onDelta).toHaveBeenCalledExactlyOnceWith('Có hai lỗi.');
});

it('cảm xúc Peto chọn đi riêng, tới trước chữ và không trộn vào câu trả lời', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(event({ type: 'emotion', emotion: 'curious' }) + event({ type: 'delta', text: 'Oh?' }) + event({ type: 'done' }))));
  const order: string[] = [];
  await sendMessage({ message: 'Đoán xem', conversationId: null, effort: 'low', mode: 'companion' }, {
    onEmotion: (emotion) => order.push(`emotion:${emotion}`), onDelta: (text) => order.push(`delta:${text}`),
  });
  expect(order).toEqual(['emotion:curious', 'delta:Oh?']);
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

it('đọc các bước của nhật ký "Đang làm", tóm tắt suy nghĩ theo bước và bản chốt', async () => {
  const step = { id: 'think-1', kind: 'think', label: 'Đang suy nghĩ…', state: 'live', start: 0 };
  const work = { ms: 4200, steps: [{ ...step, state: 'done', label: 'Đã suy nghĩ', end: 4200 }], complete: true };
  vi.stubGlobal('fetch', vi.fn(async () => new Response(
    event({ type: 'step', step }) + event({ type: 'thinking', step: 'think-1', text: '**Plan**' })
    + event({ type: 'delta', text: 'Câu dẫn.' }) + event({ type: 'replace', text: '' }) + event({ type: 'replace' })
    + event({ type: 'work', work }) + event({ type: 'done' }))));
  const onStep = vi.fn(), onThinking = vi.fn(), onReplace = vi.fn(), onWork = vi.fn();
  await sendMessage({ message: 'Sửa bảng', conversationId: null, effort: 'auto' }, { onStep, onThinking, onReplace, onWork });
  expect(onStep).toHaveBeenCalledExactlyOnceWith(step);
  expect(onThinking).toHaveBeenCalledExactlyOnceWith('**Plan**', 'think-1');
  // Máy chủ cũ gửi "replace" không kèm chữ: coi như xóa hết.
  expect(onReplace.mock.calls).toEqual([[''], ['']]);
  expect(onWork).toHaveBeenCalledExactlyOnceWith(work);
});

it('bỏ qua nhịp ": ping" máy chủ gửi để giữ kết nối khi Peto làm lâu', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(
    ': ping\n\n' + event({ type: 'delta', text: 'Xong' }) + ': ping\n\n' + event({ type: 'done' }))));
  const onDelta = vi.fn();
  const onDone = vi.fn();
  await sendMessage({ message: 'Sửa bảng', conversationId: null, effort: 'auto' }, { onDelta, onDone });
  expect(onDelta).toHaveBeenCalledExactlyOnceWith('Xong');
  expect(onDone).toHaveBeenCalledOnce();
});

it('reports a truncated stream instead of treating it as complete', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(event({type:'delta',text:'Nửa câu'}))));
  const onDone = vi.fn();
  await expect(sendMessage({message:'hi',conversationId:null,effort:'auto'}, {onDone})).rejects.toThrow('Kết nối bị ngắt');
  expect(onDone).not.toHaveBeenCalled();
});

it('chỉ cho đọc sớm khi máy chủ gửi xác nhận rõ ràng; máy chủ cũ giữ cách chờ cả tin', async () => {
  const onMeta = vi.fn();
  for (const voice_stream of [undefined, false, true]) {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(event({ type: 'meta', conversation_id: 'C', effort: 'low', voice_stream }) + event({ type: 'done' }))));
    await sendMessage({ message: 'Hi', conversationId: null, effort: 'low', mode: 'companion' }, { onMeta });
    expect(onMeta).toHaveBeenLastCalledWith('C', 'low', undefined, voice_stream === true);
  }
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

it('chuyển tiến trình đọc kết nối tới giao diện chat', async () => {
  const onConnectorLookup = vi.fn();
  vi.stubGlobal('fetch', vi.fn(async () => new Response(
    event({type: 'connector_lookup', text: 'Đang đọc GitHub…', live: true})
    + event({type: 'connector_lookup', text: 'Đã đọc GitHub', live: false}) + event({type: 'done'}))));
  await sendMessage({message: 'Kiểm tra repo', conversationId: null, effort: 'low'}, {onConnectorLookup});
  expect(onConnectorLookup.mock.calls).toEqual([['Đang đọc GitHub…', true], ['Đã đọc GitHub', false]]);
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
