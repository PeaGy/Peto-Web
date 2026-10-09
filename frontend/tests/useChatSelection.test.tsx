import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useChatSelection } from '../src/features/chat/useChatSelection';
import { getConversationSettings, updateConversation, type ModelOption } from '../src/shared/api/api';

vi.mock('../src/shared/api/api', async original => ({ ...await original<typeof import('../src/shared/api/api')>(), updateConversation: vi.fn(), getConversationSettings: vi.fn() }));
const models: ModelOption[] = [
  { key: 'peto', label: 'Peto', description: '', step_cost: 1, efforts: ['low', 'medium', 'high'] },
  { key: 'luna', label: 'Luna', description: '', step_cost: 1, efforts: ['none', 'low', 'medium', 'high', 'xhigh', 'max'] },
  { key: 'haiku', label: 'Haiku', description: '', step_cost: 1, efforts: ['low', 'medium', 'high', 'xhigh', 'max'] },
];
const deferred = () => { let resolve!: () => void; const promise = new Promise<void>(yes => { resolve = yes; }); return { promise, resolve }; };
beforeEach(() => { localStorage.clear(); vi.resetAllMocks(); vi.mocked(updateConversation).mockResolvedValue(); });

it('đọc lựa chọn riêng không ghi server hay làm đổi mặc định chat mới', () => {
  localStorage.setItem('peto-model', 'luna'); localStorage.setItem('peto-effort', 'none');
  const { result } = renderHook(() => useChatSelection('owner', models, vi.fn(), vi.fn(), vi.fn()));
  act(() => result.current.restore('A', { model: 'haiku', effort: 'max' }));
  expect(result.current).toMatchObject({ model: 'haiku', effort: 'max' });
  act(() => result.current.restore('B', { model: 'peto', effort: 'high' }));
  expect(result.current).toMatchObject({ model: 'peto', effort: 'high' });
  act(() => result.current.restore(null));
  expect(result.current).toMatchObject({ model: 'luna', effort: 'none' });
  expect(updateConversation).not.toHaveBeenCalled();
});

it('gửi tuần tự cặp lựa chọn theo chat, không đổi chat khác khi lưu xong', async () => {
  const first = deferred(); vi.mocked(updateConversation).mockImplementationOnce(() => first.promise);
  const { result } = renderHook(() => useChatSelection('owner', models, vi.fn(), vi.fn(), vi.fn()));
  act(() => result.current.restore('A', { model: 'luna', effort: 'none' }));
  act(() => result.current.setModel('haiku'));
  await act(async () => {});
  expect(updateConversation).toHaveBeenLastCalledWith('A', { model: 'haiku', effort: 'auto' });
  act(() => result.current.setEffort('max'));
  expect(updateConversation).toHaveBeenCalledTimes(1);
  act(() => result.current.restore('B', { model: 'peto', effort: 'high' }));
  await act(async () => { first.resolve(); await result.current.waitForSave('A'); });
  expect(updateConversation).toHaveBeenLastCalledWith('A', { model: 'haiku', effort: 'max' });
  expect(result.current).toMatchObject({ model: 'peto', effort: 'high' });
});

it('lưu lỗi báo rõ và giữ lựa chọn chưa đồng bộ khi mở lại; gửi thành công xóa bản chờ', async () => {
  const error = vi.fn(); vi.mocked(updateConversation).mockRejectedValue(new Error('Mạng hỏng'));
  const { result } = renderHook(() => useChatSelection('owner', models, vi.fn(), error, vi.fn()));
  act(() => result.current.restore('A'));
  await act(async () => { result.current.setEffort('high'); await result.current.waitForSave('A'); });
  expect(error).toHaveBeenCalled();
  act(() => result.current.restore('B'));
  act(() => result.current.restore('A', { model: 'peto', effort: 'auto' }));
  expect(result.current.effort).toBe('high');
  act(() => result.current.accepted('A', { model: 'peto', effort: 'high' }));
  act(() => result.current.restore('A', { model: 'luna', effort: 'none' }));
  expect(result.current.model).toBe('luna');
});

it('đổi tài khoản không gửi yêu cầu chờ và không áp dụng phản hồi cũ', async () => {
  const first = deferred(); const error = vi.fn();
  vi.mocked(updateConversation).mockImplementationOnce(() => first.promise);
  const { result, rerender } = renderHook(({ owner }) => useChatSelection(owner, models, vi.fn(), error, vi.fn()), { initialProps: { owner: 'A' } });
  act(() => result.current.restore('chatA'));
  act(() => result.current.setModel('haiku')); await act(async () => {});
  act(() => result.current.setEffort('max'));
  rerender({ owner: 'B' });
  act(() => result.current.restore('chatB', { model: 'luna', effort: 'none' }));
  await act(async () => first.resolve());
  expect(updateConversation).toHaveBeenCalledTimes(1);
  expect(result.current).toMatchObject({ model: 'luna', effort: 'none' });
  expect(error).not.toHaveBeenCalled();
});

it('trở lại tab đọc lựa chọn mới nhưng phản hồi cũ không đè thao tác vừa chọn', async () => {
  let resolve!: (saved: { model: string; effort: 'max' }) => void;
  vi.mocked(getConversationSettings).mockReturnValue(new Promise(yes => { resolve = yes; }));
  const { result } = renderHook(() => useChatSelection('owner', models, vi.fn(), vi.fn(), vi.fn()));
  act(() => result.current.restore('A', { model: 'haiku', effort: 'low' }));
  act(() => window.dispatchEvent(new Event('focus')));
  expect(getConversationSettings).toHaveBeenCalledWith('A', expect.anything());
  act(() => result.current.setEffort('high'));
  await act(async () => resolve({ model: 'haiku', effort: 'max' }));
  expect(result.current.effort).toBe('high');
});
