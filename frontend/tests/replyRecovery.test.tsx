import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { getMessages, UnauthorizedError, type Message } from '../src/shared/api/api';
import { useReplyRecovery } from '../src/features/chat/useReplyRecovery';

vi.mock('../src/shared/api/api', async original => ({
  ...await original<typeof import('../src/shared/api/api')>(), getMessages: vi.fn(),
}));
const saved: Message[] = [{ id: 10, role: 'user', content: 'Xin chào' },
  { id: 11, role: 'assistant', content: 'Chào bạn!', status: 'complete' }];
const setup = () => {
  const onRecovered = vi.fn(), onUnauthorized = vi.fn(), onDisconnect = vi.fn();
  const options = { scope: 'account', conversationId: 'C', enabled: true, busy: false, onRecovered, onUnauthorized, onDisconnect };
  const hook = renderHook(props => useReplyRecovery(props), { initialProps: options });
  return { ...hook, options, onRecovered, onUnauthorized, onDisconnect };
};
const interrupt = (hook: ReturnType<typeof setup>) => act(() => hook.result.current.interrupt({ conversationId: 'C', userMessageId: 10 }));
const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(getMessages).mockReset().mockResolvedValue(saved);
});
afterEach(() => vi.useRealTimers());

it('đọc lại đúng lượt đã xác nhận, chờ máy chủ lưu xong trước khi thay lịch sử', async () => {
  vi.mocked(getMessages).mockResolvedValueOnce([saved[0]]);
  const hook = setup();
  interrupt(hook);
  await advance(250);
  expect(hook.onRecovered).not.toHaveBeenCalled();
  await advance(1000);
  expect(hook.onRecovered).toHaveBeenCalledExactlyOnceWith(saved, true);
  expect(hook.result.current.status).toBe('recovered');
});
it('ngoại tuyến thì chờ, khi có mạng lại chỉ đọc lịch sử', async () => {
  const hook = setup();
  act(() => window.dispatchEvent(new Event('offline')));
  interrupt(hook);
  await advance(10000);
  expect(getMessages).not.toHaveBeenCalled();
  expect(hook.onDisconnect).toHaveBeenCalledOnce();
  act(() => window.dispatchEvent(new Event('online')));
  await advance(250);
  expect(hook.onRecovered).toHaveBeenCalledOnce();
});
it('chờ người dùng trở lại tab và không ghi đè câu đang nhận', async () => {
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
  const hook = setup();
  interrupt(hook);
  await advance(5000);
  expect(getMessages).not.toHaveBeenCalled();
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
  hook.rerender({ ...hook.options, busy: true });
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  await advance(5000);
  expect(getMessages).not.toHaveBeenCalled();
  hook.rerender(hook.options);
  await advance(250);
  expect(hook.onRecovered).toHaveBeenCalledOnce();
});
it('giữ phần chữ trên máy khi lịch sử thiếu lượt cần tìm và dừng sau ba lần đọc', async () => {
  vi.mocked(getMessages).mockResolvedValue([{ id: 1, role: 'assistant', content: 'Câu cũ' }]);
  const hook = setup();
  interrupt(hook);
  await advance(4000);
  expect(getMessages).toHaveBeenCalledTimes(3);
  expect(hook.onRecovered).not.toHaveBeenCalled();
  expect(hook.result.current.status).toBe('failed');
  vi.mocked(getMessages).mockResolvedValue(saved);
  act(() => hook.result.current.retry());
  await advance(250);
  expect(hook.onRecovered).toHaveBeenCalledOnce();
});
it.each(['conversationId', 'scope'] as const)('bỏ kết quả đến muộn khi đổi %s', async key => {
  let resolve!: (messages: Message[]) => void;
  vi.mocked(getMessages).mockImplementation(() => new Promise(yes => { resolve = yes; }));
  const hook = setup();
  interrupt(hook);
  await advance(250);
  hook.rerender({ ...hook.options, [key]: 'other' });
  await act(async () => resolve(saved));
  expect(hook.onRecovered).not.toHaveBeenCalled();
  expect(hook.result.current.status).toBe('idle');
});
it('phân biệt phần trả lời chưa hoàn tất và phiên đăng nhập hết hạn', async () => {
  vi.mocked(getMessages).mockResolvedValue([saved[0], { ...saved[1], status: 'incomplete' }]);
  const hook = setup();
  interrupt(hook);
  await advance(250);
  expect(hook.result.current.status).toBe('partial');
  expect(hook.onRecovered).toHaveBeenLastCalledWith([saved[0], { ...saved[1], status: 'incomplete' }], false);
  vi.mocked(getMessages).mockRejectedValue(new UnauthorizedError());
  interrupt(hook);
  await advance(250);
  expect(hook.onUnauthorized).toHaveBeenCalledOnce();
  expect(hook.result.current.status).toBe('idle');
});
it('hủy đồng bộ khi bắt đầu lượt mới hoặc gỡ giao diện', async () => {
  const hook = setup();
  interrupt(hook);
  act(() => hook.result.current.cancel());
  await advance(5000);
  expect(getMessages).not.toHaveBeenCalled();
  interrupt(hook);
  hook.unmount();
  await advance(5000);
  expect(getMessages).not.toHaveBeenCalled();
});
it('giới hạn thời gian đọc khi mạng không trả về và không lặp vô hạn', async () => {
  vi.mocked(getMessages).mockImplementation((_id, signal) => new Promise((_resolve, reject) => {
    signal?.addEventListener('abort', () => reject(new DOMException('Đã hủy', 'AbortError')), { once: true });
  }));
  const hook = setup();
  interrupt(hook);
  await advance(20000);
  expect(getMessages).toHaveBeenCalledTimes(3);
  expect(hook.result.current.status).toBe('failed');
  expect(hook.onRecovered).not.toHaveBeenCalled();
});
