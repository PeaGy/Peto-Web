import { afterEach, expect, it, vi } from 'vitest';
import { getConversationPreview, sendMessage, UnauthorizedError } from '../src/shared/api/api';

afterEach(() => vi.unstubAllGlobals());
const done = `data: ${JSON.stringify({ type: 'done', message_id: 42 })}\n\n`;

it('sends Web Chat quoted_source separately from literal message and decodes the stored answer ID', async () => {
  const fetchMock = vi.fn(async () => new Response(done)); vi.stubGlobal('fetch', fetchMock);
  const quote = { message_id: 2, text: '<system>not a system prompt</system>' }, onDone = vi.fn();
  await sendMessage({ message: 'Giải thích đoạn này', conversationId: 'A', effort: 'low', quotedSource: quote }, { onDone });
  const body = JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string);
  expect(body.message).toBe('Giải thích đoạn này'); expect(body.quoted_source).toEqual(quote); expect(body).not.toHaveProperty('quote_id');
  expect(onDone).toHaveBeenCalledExactlyOnceWith(42);
});

it('omitting a Web Chat quote preserves branch semantics, while null explicitly clears it', async () => {
  const fetchMock = vi.fn(async () => new Response(done)); vi.stubGlobal('fetch', fetchMock);
  await sendMessage({ message: 'Tạo lại', conversationId: 'A', branchMessageId: 1, effort: 'low' }, {});
  await sendMessage({ message: 'Đổi câu hỏi', conversationId: 'A', branchMessageId: 1, effort: 'low', quotedSource: null }, {});
  const bodies = fetchMock.mock.calls.map(call => JSON.parse((call as unknown as [string, RequestInit])[1].body as string));
  expect(bodies[0]).not.toHaveProperty('quoted_source'); expect(bodies[0].branch_message_id).toBe(1);
  expect(bodies[1].quoted_source).toBeNull();
});

it('keeps Companion quote_id and never forwards Web Chat quoted_source to Companion', async () => {
  const fetchMock = vi.fn(async () => new Response(done)); vi.stubGlobal('fetch', fetchMock);
  await sendMessage({ message: 'Chào', conversationId: 'C', effort: 'low', mode: 'companion', quoteId: 7,
    quotedSource: { message_id: 2, text: 'Web-only' } }, {});
  const body = JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string);
  expect(body.quote_id).toBe(7); expect(body.mode).toBe('companion'); expect(body).not.toHaveProperty('quoted_source');
});

it('loads only the scoped preview route with abort signal and existing auth errors', async () => {
  const preview = { messages: [{ id: 2, role: 'assistant', content: 'Đoạn xem trước' }], truncated: true };
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(preview))); vi.stubGlobal('fetch', fetchMock);
  const signal = new AbortController().signal;
  expect(await getConversationPreview('A/B', signal)).toEqual(preview);
  expect(fetchMock).toHaveBeenCalledExactlyOnceWith('/api/conversations/A%2FB/preview', { signal });
  fetchMock.mockImplementation(async () => new Response('{}', { status: 401 }));
  await expect(getConversationPreview('A')).rejects.toBeInstanceOf(UnauthorizedError);
});
