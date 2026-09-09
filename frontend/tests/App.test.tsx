import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import * as api from '../src/api';

vi.mock('../src/api', async (original) => ({
  ...await original<typeof import('../src/api')>(),
  getAuthState: vi.fn(), listConversations: vi.fn(), getMessages: vi.fn(),
  sendMessage: vi.fn(), deleteConversation: vi.fn(), logout: vi.fn(),
}));

const conversation = (id: string): api.Conversation => ({ id, title: id, created_at: 0, updated_at: 0, message_count: 2 });
const row = (content: string): api.Message => ({ role: 'user', content });
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(api.getAuthState).mockResolvedValue({ authenticated: true, login_configured: true,
    user: { discord_id: '111', username: 'demo', display_name: 'Demo', avatar_url: '' } });
  vi.mocked(api.listConversations).mockResolvedValue({ conversations: [conversation('A'), conversation('B')], has_more: false });
  vi.mocked(api.getMessages).mockResolvedValue([]);
  vi.mocked(api.deleteConversation).mockResolvedValue();
  URL.createObjectURL = vi.fn(() => 'blob:review');
  URL.revokeObjectURL = vi.fn();
});

async function openApp() {
  render(<App />);
  await screen.findByRole('button', { name: 'A', exact: true });
}

describe('Conversation navigation', () => {
  it('ignores late A results after choosing B', async () => {
    const a = deferred<api.Message[]>();
    vi.mocked(api.getMessages).mockImplementation((id) => id === 'A' ? a.promise : Promise.resolve([row('Nội dung B')]));
    await openApp();
    fireEvent.click(screen.getByRole('button', { name: 'A', exact: true }));
    expect(screen.getByText('Đang mở hội thoại…')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'B', exact: true }));
    await screen.findByText('Nội dung B');
    await act(async () => a.resolve([row('Nội dung A')]));
    expect(screen.queryByText('Nội dung A')).toBeNull();
    expect(screen.getByRole('button', { name: 'B', exact: true }).getAttribute('aria-current')).toBe('page');
  });

  it('ignores old results after starting a new conversation', async () => {
    const a = deferred<api.Message[]>();
    vi.mocked(api.getMessages).mockReturnValue(a.promise);
    await openApp();
    fireEvent.click(screen.getByRole('button', { name: 'A', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: '+ Trò chuyện mới' }));
    await act(async () => a.resolve([row('Nội dung cũ')]));
    expect(screen.queryByText('Nội dung cũ')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Chào Demo' })).toBeTruthy();
  });

  it('blocks send while history failed and offers to reload it', async () => {
    vi.mocked(api.getMessages).mockRejectedValueOnce(new Error('Mạng lỗi')).mockResolvedValue([row('Đã tải lại')]);
    await openApp();
    fireEvent.click(screen.getByRole('button', { name: 'A', exact: true }));
    await screen.findByText('Chưa tải được nội dung hội thoại.');
    fireEvent.change(screen.getByPlaceholderText('Nhắn cho Peto…'), {target: {value: 'Nháp'}});
    expect((screen.getByRole('button', { name: 'Gửi', exact: true }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Thử mở lại' }));
    await screen.findByText('Đã tải lại');
    expect((screen.getByRole('button', { name: 'Gửi', exact: true }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('Sending and stopping', () => {
  it('keeps the draft and selected file on rejection, then sends it once successfully', async () => {
    vi.mocked(api.sendMessage).mockImplementationOnce(async (_payload, handlers) => handlers.onError?.('Tạm thời bận'))
      .mockImplementationOnce(async (_payload, handlers) => {
        handlers.onMeta?.('C', 'low', { role: 'user', content: 'Bản nháp', attachments: [] });
        handlers.onDelta?.('Đã nhận'); handlers.onDone?.();
      });
    await openApp();
    fireEvent.change(screen.getByPlaceholderText('Nhắn cho Peto…'), {target: {value: 'Bản nháp'}});
    const file = new File(['Ghi chú'], 'note.txt', {type: 'text/plain'});
    await userEvent.upload(document.querySelector('input[type=file]') as HTMLInputElement, file);
    fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
    await screen.findByText('Tạm thời bận');
    expect((screen.getByPlaceholderText('Nhắn cho Peto…') as HTMLTextAreaElement).value).toBe('Bản nháp');
    expect(screen.getByRole('button', {name: 'Gỡ note.txt'})).toBeTruthy();
    expect(document.querySelectorAll('.bubble').length).toBe(0);
    fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
    await screen.findByText('Đã nhận');
    await waitFor(() => expect((screen.getByPlaceholderText('Nhắn cho Peto…') as HTMLTextAreaElement).disabled).toBe(false));
    expect(document.querySelectorAll('.bubble.user').length).toBe(1);
    expect((screen.getByPlaceholderText('Nhắn cho Peto…') as HTMLTextAreaElement).value).toBe('');
    expect(api.sendMessage).toHaveBeenCalledTimes(2);
  });

  it('stops an empty reply without leaving a typing indicator', async () => {
    vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers, signal) => {
      handlers.onMeta?.('C', 'low', row('Xin chào'));
      await new Promise<void>((_resolve, reject) => signal?.addEventListener('abort', () => reject(new DOMException('Stopped', 'AbortError'))));
    });
    await openApp();
    fireEvent.change(screen.getByPlaceholderText('Nhắn cho Peto…'), {target: {value: 'Xin chào'}});
    fireEvent.click(screen.getByRole('button', {name:'Gửi', exact:true}));
    await screen.findByRole('button', {name:'Dừng', exact:true});
    fireEvent.click(screen.getByRole('button', {name:'Dừng', exact:true}));
    await screen.findByText('Đã dừng. Phần đã trả lời được giữ lại.');
    expect(document.querySelector('.typing')).toBeNull();
    expect(document.querySelectorAll('.bubble.assistant').length).toBe(0);
  });

  it('marks visible partial text incomplete after a stream error', async () => {
    vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
      handlers.onMeta?.('C', 'low', row('Xin chào'));
      handlers.onDelta?.('Phần đầu'); handlers.onError?.('AI lỗi');
    });
    await openApp();
    fireEvent.change(screen.getByPlaceholderText('Nhắn cho Peto…'), {target: {value: 'Xin chào'}});
    fireEvent.click(screen.getByRole('button', {name:'Gửi', exact:true}));
    await screen.findByText('Câu trả lời chưa hoàn tất');
    expect(screen.getByText('Phần đầu')).toBeTruthy();
    expect(document.querySelectorAll('.bubble.user').length).toBe(1);
  });
});

it('asks before deleting and keeps the conversation when cancelled', async () => {
  await openApp();
  fireEvent.click(screen.getAllByRole('button', {name:'Xóa hội thoại'})[0]);
  const dialog = screen.getByRole('dialog');
  expect(api.deleteConversation).not.toHaveBeenCalled();
  fireEvent.click(within(dialog).getByRole('button', {name:'Giữ lại'}));
  expect(api.deleteConversation).not.toHaveBeenCalled();
  expect(screen.queryByRole('dialog')).toBeNull();
});

it('opens settings from the account box and switches to the light theme', async () => {
  await openApp();
  expect(document.documentElement.dataset.theme).toBe('dark');
  fireEvent.click(screen.getByRole('button', {name: /Cài đặt · Demo/}));
  const dialog = screen.getByRole('dialog');
  fireEvent.click(within(dialog).getByRole('radio', {name: /Sáng/}));
  expect(document.documentElement.dataset.theme).toBe('light');
  expect(localStorage.getItem('peto-theme')).toBe('light');
  fireEvent.click(within(dialog).getByRole('button', {name: 'Đóng cài đặt'}));
  expect(screen.queryByRole('dialog')).toBeNull();
});

it('renders Markdown tables as a scrollable table', async () => {
  vi.mocked(api.getMessages).mockResolvedValue([{ role:'assistant', content:'| A | B |\n| --- | --- |\n| Một | Hai |'}]);
  await openApp();
  fireEvent.click(screen.getByRole('button', {name:'A', exact:true}));
  expect(await screen.findByRole('table')).toBeTruthy();
  expect(screen.getByRole('region', {name:'Bảng nội dung'})).toBeTruthy();
});

it('loads conversations beyond the first 50', async () => {
  const first = Array.from({length:50}, (_, i) => conversation(i === 0 ? 'A' : `Chat ${i}`));
  vi.mocked(api.listConversations).mockImplementation(async (offset = 0) => offset === 0
    ? {conversations:first, has_more:true} : {conversations:[conversation('Hội thoại cũ')], has_more:false});
  await openApp();
  fireEvent.click(screen.getByRole('button', {name:'Xem hội thoại cũ hơn'}));
  await screen.findByRole('button', {name:'Hội thoại cũ', exact:true});
  expect(api.listConversations).toHaveBeenCalledWith(50);
});
