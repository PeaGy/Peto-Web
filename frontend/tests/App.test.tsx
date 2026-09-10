import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import * as api from '../src/api';

vi.mock('../src/api', async (original) => ({
  ...await original<typeof import('../src/api')>(),
  getAuthState: vi.fn(), listConversations: vi.fn(), getMessages: vi.fn(),
  sendMessage: vi.fn(), deleteConversation: vi.fn(), logout: vi.fn(),
  listImagineJobs: vi.fn(), createImagineJob: vi.fn(),
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
  window.history.replaceState(null, '', '/');
  vi.mocked(api.getAuthState).mockResolvedValue({ authenticated: true, login_configured: true,
    user: { discord_id: '111', username: 'demo', display_name: 'Demo', avatar_url: '' } });
  vi.mocked(api.listConversations).mockResolvedValue({ conversations: [conversation('A'), conversation('B')], has_more: false });
  vi.mocked(api.getMessages).mockResolvedValue([]);
  vi.mocked(api.deleteConversation).mockResolvedValue();
  vi.mocked(api.listImagineJobs).mockResolvedValue([]);
  Element.prototype.scrollTo = vi.fn();
  URL.createObjectURL = vi.fn(() => 'blob:review');
  URL.revokeObjectURL = vi.fn();
});

async function openApp() {
  render(<App />);
  await screen.findByRole('button', { name: 'A', exact: true });
}

it('keeps image generation alive while navigating to chat and back', async () => {
  const generated = deferred<api.ImagineJob>();
  vi.mocked(api.createImagineJob).mockReturnValue(generated.promise);
  await openApp();
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  await screen.findByRole('heading', { name: /Bạn tưởng tượng/ });
  fireEvent.change(screen.getByLabelText('Bức ảnh bạn muốn tạo'), { target: { value: 'Mèo tím' } });
  fireEvent.submit(screen.getByLabelText('Bức ảnh bạn muốn tạo').closest('form')!);
  await screen.findByText('Peto đang tạo 1 ảnh…');
  fireEvent.click(screen.getByRole('button', { name: 'Trò chuyện', exact: true }));
  const chat = screen.getByLabelText('Nhắn cho Peto');
  chat.focus();
  await act(async () => generated.resolve({ id: 'image-job', prompt: 'Mèo tím', quality: 'low', resolution: '1k', aspect_ratio: 'auto', created_at: null,
    images: [{ id: 'image-1', mime: 'image/png', url: '/api/imagine/images/image-1' }] }));
  expect(document.activeElement).toBe(chat);
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  await screen.findByRole('button', { name: 'Xem ảnh 1: Mèo tím' });
  expect(api.createImagineJob).toHaveBeenCalledTimes(1);
  expect(api.listImagineJobs).toHaveBeenCalledTimes(1);
});

it('giữ ảnh gốc và yêu cầu chỉnh sửa khi chuyển sang chat rồi quay lại', async () => {
  await openApp();
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  await screen.findByRole('heading', { name: /Bạn tưởng tượng/ });
  fireEvent.change(screen.getByLabelText('Chọn ảnh để sửa'), { target: { files: [new File(['anh-gia'], 'anh-goc.png', { type: 'image/png' })] } });
  const prompt = await screen.findByLabelText('Bạn muốn sửa gì trong ảnh?');
  fireEvent.change(prompt, { target: { value: 'Đổi nền xanh' } });
  fireEvent.click(screen.getByRole('button', { name: 'Trò chuyện', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  expect((screen.getByLabelText('Bạn muốn sửa gì trong ảnh?') as HTMLTextAreaElement).value).toBe('Đổi nền xanh');
  expect(screen.getByRole('img', { name: 'Ảnh gốc để chỉnh sửa' })).toBeTruthy();
  expect(api.createImagineJob).not.toHaveBeenCalled();
});

it('liệt kê lượt tạo ảnh ở cột trái và cuộn tới lượt được chọn', async () => {
  const job = (id: string, prompt: string): api.ImagineJob => ({ id, prompt, quality: 'low', resolution: '1k',
    aspect_ratio: 'auto', created_at: null, images: [{ id: id + '-1', mime: 'image/png', url: '/api/imagine/images/' + id }] });
  vi.mocked(api.listImagineJobs).mockResolvedValue([job('j1', 'Ngôi nhà bên hồ'), job('j2', 'Mèo trên mặt trăng')]);
  await openApp();
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  const list = await screen.findByRole('navigation', { name: 'Thư viện' });
  await within(list).findByRole('button', { name: 'Ngôi nhà bên hồ' });
  expect(within(list).getAllByRole('button').map((item) => item.getAttribute('aria-label')))
    .toEqual(['Ngôi nhà bên hồ', 'Mèo trên mặt trăng']);
  expect([...list.querySelectorAll('img')].map((item) => item.getAttribute('src')))
    .toEqual(['/api/imagine/images/j1', '/api/imagine/images/j2']);

  const scrolled = vi.mocked(Element.prototype.scrollIntoView);
  scrolled.mockClear();
  fireEvent.click(within(list).getByRole('button', { name: 'Mèo trên mặt trăng' }));
  await waitFor(() => expect(scrolled).toHaveBeenCalled());
  expect(scrolled.mock.instances[0]).toBe(document.querySelector('[data-job-id="j2"]'));
});

it('báo cột trái trống khi chưa có ảnh nào', async () => {
  await openApp();
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  const list = await screen.findByRole('navigation', { name: 'Thư viện' });
  expect(within(list).getByText('Chưa có ảnh nào. Ảnh bạn tạo sẽ hiện ở đây.')).toBeTruthy();
  expect(within(list).queryAllByRole('button')).toHaveLength(0);
});

it('thêm lượt vừa tạo vào cột trái', async () => {
  vi.mocked(api.createImagineJob).mockResolvedValue({ id: 'moi', prompt: 'Mèo tím', quality: 'low', resolution: '1k',
    aspect_ratio: 'auto', created_at: null, images: [{ id: 'anh-1', mime: 'image/png', url: '/api/imagine/images/anh-1' }] });
  await openApp();
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  await screen.findByRole('heading', { name: /Bạn tưởng tượng/ });
  fireEvent.change(screen.getByLabelText('Bức ảnh bạn muốn tạo'), { target: { value: 'Mèo tím' } });
  fireEvent.submit(screen.getByLabelText('Bức ảnh bạn muốn tạo').closest('form')!);
  const list = await screen.findByRole('navigation', { name: 'Thư viện' });
  await waitFor(() => expect(within(list).getByRole('button', { name: 'Mèo tím' })).toBeTruthy());
});

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
  it('allows messages longer than the former 4,000 character limit', async () => {
    vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => handlers.onError?.('Giữ bản nháp để kiểm tra'));
    await openApp();
    const longText = 'Nội dung web đầy đủ. '.repeat(300);
    fireEvent.change(screen.getByPlaceholderText('Nhắn cho Peto…'), {target:{value:longText}});
    fireEvent.click(screen.getByRole('button', {name:'Gửi',exact:true}));
    await screen.findByText('Giữ bản nháp để kiểm tra');
    expect(vi.mocked(api.sendMessage).mock.calls[0][0].message).toBe(longText.trim());
  });
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

  it('shows Grok thinking separately from the answer', async () => {
    vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
      handlers.onMeta?.('C', 'medium', row('Giải giúp'));
      handlers.onThinking?.('Nhẩm từng bước…');
      handlers.onDelta?.('Kết quả là 4.');
      handlers.onDone?.();
    });
    await openApp();
    fireEvent.change(screen.getByPlaceholderText('Nhắn cho Peto…'), {target: {value: 'Giải giúp'}});
    fireEvent.click(screen.getByRole('button', {name:'Gửi', exact:true}));
    await screen.findByText('Kết quả là 4.');
    expect(screen.queryByText('Nhẩm từng bước…')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Đã suy nghĩ'}));
    expect(screen.getByText('Nhẩm từng bước…')).toBeTruthy();
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
    expect(document.querySelector('.thinking-panel')).toBeNull();
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
