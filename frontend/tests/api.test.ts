import { afterEach, expect, it, vi } from 'vitest';
import { sendMessage } from '../src/api';

afterEach(() => vi.unstubAllGlobals());
const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;

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

it('sends only the browser timezone, never the browser clock', async () => {
  const fetchMock = vi.fn(async () => new Response(event({type:'done'})));
  vi.stubGlobal('fetch', fetchMock);
  await sendMessage({message:'Mấy giờ?',conversationId:null,effort:'auto'}, {});
  const body = JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string);
  expect(body.timezone).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
  expect(body).not.toHaveProperty('timestamp');
  expect(body).not.toHaveProperty('current_time');
});
