import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { applyLiveEvent, useLiveChat } from '../src/features/chat/useLiveChat';
import * as api from '../src/shared/api/api';
import type { LiveEnvelope, Message } from '../src/shared/api/api';

// Đồng bộ trực tiếp tab Trò chuyện: lượt của tab/thiết bị khác hiện ở đây như lượt tự gửi.

vi.mock('../src/shared/api/api', async (original) => ({
  ...await original<typeof import('../src/shared/api/api')>(),
  watchChatLive: vi.fn(), getMessages: vi.fn(), stopChat: vi.fn(),
}));

let feed: ((envelope: LiveEnvelope) => void) | null = null;
let ready: (() => void) | null = null;
const history: Message[] = [{ id: 1, role: 'user', content: 'Câu cũ' }, { id: 2, role: 'assistant', content: 'Trả lời cũ' }];
const asked: Message = { id: 3, role: 'user', content: 'Câu mới từ máy kia' };

beforeEach(() => {
  vi.clearAllMocks();
  feed = null;
  vi.mocked(api.watchChatLive).mockImplementation((handlers, signal) => new Promise((resolve) => {
    feed = handlers.onLive;
    ready = handlers.onReady;
    handlers.onReady();
    signal.addEventListener('abort', () => resolve());
  }));
  // Máy chủ lưu dần câu trả lời dở: lịch sử lúc đang chạy có cả tin trả lời chưa xong, phải bị cắt đi.
  vi.mocked(api.getMessages).mockResolvedValue([...history, asked, { id: 4, role: 'assistant', content: 'Dở', status: 'incomplete' }]);
  vi.mocked(api.stopChat).mockResolvedValue({ stopped: true, state: 'stopped', conversation_id: 'c1', message: null });
});

const envelope = (event: LiveEnvelope['event'], request = 'r-other', conversation = 'c1'): LiveEnvelope =>
  ({ request_id: request, conversation_id: conversation, event });

function setup(overrides: Partial<Parameters<typeof useLiveChat>[0]> = {}) {
  let messages: Message[] = [...history];
  const setMessages = vi.fn((next: Message[] | ((prev: Message[]) => Message[])) => {
    messages = typeof next === 'function' ? next(messages) : next;
  });
  const refreshConversations = vi.fn(async () => {});
  const onDocument = vi.fn();
  const own = { current: new Set<string>(['r-mine']) };
  const hook = renderHook((props: Parameters<typeof useLiveChat>[0]) => useLiveChat(props), {
    initialProps: { enabled: true, conversationId: 'c1', loadingConversation: false, localBusy: false, ownRequests: own,
      setMessages, refreshConversations, onUnauthorized: vi.fn(), onDocument, ...overrides },
  });
  return { hook, setMessages, refreshConversations, onDocument, own, messages: () => messages };
}

it('applies events like the sending tab', () => {
  let message: Message = { role: 'assistant', content: '', work: { ms: 0, steps: [{ id: 'wait', kind: 'wait', label: 'chờ', state: 'live', start: 0 }] } };
  message = applyLiveEvent(message, { type: 'step', step: { id: 's1', kind: 'think', label: 'Nghĩ', state: 'live', start: 0 } } as never);
  expect(message.work?.steps.map((step) => step.id)).toEqual(['s1']);
  message = applyLiveEvent(message, { type: 'delta', text: 'Xin' });
  message = applyLiveEvent(message, { type: 'delta', text: ' chào' });
  expect(message.content).toBe('Xin chào');
  message = applyLiveEvent(message, { type: 'replace', text: 'Chào' });
  expect(message.content).toBe('Chào');
  expect(applyLiveEvent(message, { type: 'reading', text: 'x' } as never)).toBe(message);
});

it('shows a turn from another device while it runs, then the saved version', async () => {
  const { hook, messages, refreshConversations } = setup();
  await waitFor(() => expect(feed).not.toBeNull());
  act(() => feed!(envelope({ type: 'meta', conversation_id: 'c1', effort: 'low', message: asked } as never)));
  await waitFor(() => expect(messages()).toHaveLength(4));
  expect(messages().slice(0, 3).map((row) => row.content)).toEqual(['Câu cũ', 'Trả lời cũ', 'Câu mới từ máy kia']);
  expect(hook.result.current.remote).toEqual({ requestId: 'r-other', stopping: false });
  act(() => feed!(envelope({ type: 'delta', text: 'Đang ' })));
  act(() => feed!(envelope({ type: 'delta', text: 'viết' })));
  expect(messages().at(-1)?.content).toBe('Đang viết');
  vi.mocked(api.getMessages).mockResolvedValue([...history, asked, { id: 4, role: 'assistant', content: 'Đang viết xong.' }]);
  act(() => feed!(envelope({ type: 'done', message_id: 4 })));
  await waitFor(() => expect(messages().at(-1)?.content).toBe('Đang viết xong.'));
  expect(hook.result.current.remote).toBeNull();
  expect(refreshConversations).toHaveBeenCalled();
})

it('ignores turns this tab sent itself', async () => {
  const { setMessages } = setup();
  await waitFor(() => expect(feed).not.toBeNull());
  act(() => feed!(envelope({ type: 'meta', conversation_id: 'c1', effort: 'low', message: asked } as never, 'r-mine')));
  act(() => feed!(envelope({ type: 'delta', text: 'không vẽ' }, 'r-mine')));
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(setMessages).not.toHaveBeenCalled();
  expect(api.getMessages).not.toHaveBeenCalled();
});

it('a turn in another conversation only refreshes the list', async () => {
  const { setMessages, refreshConversations, hook } = setup();
  await waitFor(() => expect(feed).not.toBeNull());
  act(() => feed!(envelope({ type: 'meta', conversation_id: 'c2', effort: 'low', message: asked } as never, 'r-other', 'c2')));
  act(() => feed!(envelope({ type: 'delta', text: 'ở chỗ khác' }, 'r-other', 'c2')));
  act(() => feed!(envelope({ type: 'done', message_id: 9 }, 'r-other', 'c2')));
  await waitFor(() => expect(refreshConversations).toHaveBeenCalledTimes(2));
  expect(setMessages).not.toHaveBeenCalled();
  expect(hook.result.current.remote).toBeNull();
});

it('Dừng on this tab stops the other device\'s turn', async () => {
  const { hook } = setup();
  await waitFor(() => expect(feed).not.toBeNull());
  act(() => feed!(envelope({ type: 'meta', conversation_id: 'c1', effort: 'low', message: asked } as never)));
  await waitFor(() => expect(hook.result.current.remote?.requestId).toBe('r-other'));
  await act(async () => { await hook.result.current.stopRemote(); });
  expect(api.stopChat).toHaveBeenCalledWith('r-other');
  expect(hook.result.current.remote?.stopping).toBe(true);
  act(() => feed!(envelope({ type: 'stopped' })));
  await waitFor(() => expect(hook.result.current.remote).toBeNull());
});

it('a turn that ended while disconnected is read again after reconnecting', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    const { messages } = setup();
    await vi.waitFor(() => expect(feed).not.toBeNull());
    act(() => feed!(envelope({ type: 'meta', conversation_id: 'c1', effort: 'low', message: asked } as never)));
    await vi.waitFor(() => expect(messages()).toHaveLength(4));
    vi.mocked(api.getMessages).mockResolvedValue([...history, asked, { id: 4, role: 'assistant', content: 'Xong lúc mất mạng' }]);
    act(() => ready!());  // kết nối lại, không có gì được phát lại cho lượt này
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    await vi.waitFor(() => expect(messages().at(-1)?.content).toBe('Xong lúc mất mạng'));
  } finally {
    vi.useRealTimers();
  }
});

it('after this tab\'s own stream breaks, resync reconnects and shows its still-running turn from the start', async () => {
  // 23/11/2026: lượt chạy tiếp trên máy chủ khi luồng của tab đứt; tab thôi bỏ qua lượt của mình và nối lại.
  const { hook, own, messages } = setup();
  await waitFor(() => expect(feed).not.toBeNull());
  act(() => feed!(envelope({ type: 'delta', text: 'bị bỏ qua' }, 'r-mine')));
  expect(hook.result.current.remote).toBeNull();
  const calls = vi.mocked(api.watchChatLive).mock.calls.length;
  own.current.delete('r-mine');
  act(() => hook.result.current.resync());
  await waitFor(() => expect(vi.mocked(api.watchChatLive).mock.calls.length).toBe(calls + 1));
  // Máy chủ phát lại lượt từ meta: tab vẽ câu hỏi và chữ đang chạy.
  act(() => feed!(envelope({ type: 'meta', conversation_id: 'c1', effort: 'low', message: asked } as never, 'r-mine')));
  await waitFor(() => expect(api.getMessages).toHaveBeenCalled());
  act(() => feed!(envelope({ type: 'delta', text: 'Chạy tiếp' }, 'r-mine')));
  await waitFor(() => expect(messages().at(-1)?.content).toBe('Chạy tiếp'));
  expect(messages().at(-2)).toEqual(asked);
});
