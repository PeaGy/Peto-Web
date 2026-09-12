import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import * as api from '../src/api';

vi.mock('../src/api', async (original) => ({
  ...await original<typeof import('../src/api')>(),
  getAuthState: vi.fn(), listConversations: vi.fn(), getMessages: vi.fn(),
  sendMessage: vi.fn(), deleteConversation: vi.fn(), logout: vi.fn(),
  listImagineJobs: vi.fn(), createImagineJob: vi.fn(), guestLogin: vi.fn(),
  getProfile: vi.fn(), saveProfile: vi.fn(),
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
    providers: { discord: true, google: true, guest: true },
    user: { id: 'acc-111', provider: 'discord', username: 'demo', display_name: 'Demo', avatar_url: '' } });
  vi.mocked(api.listConversations).mockResolvedValue({ conversations: [conversation('A'), conversation('B')], has_more: false });
  vi.mocked(api.getMessages).mockResolvedValue([]);
  vi.mocked(api.deleteConversation).mockResolvedValue();
  vi.mocked(api.listImagineJobs).mockResolvedValue([]);
  // vi.fn() trả undefined: không cài sẵn thì mọi test mở Cài đặt vỡ ở .then().
  vi.mocked(api.getProfile).mockResolvedValue({ profile: { full_name: '', nickname: '', occupation: '', instructions: '' },
    occupations: [], limits: { full_name: 80, nickname: 40, instructions: 1500 } });
  Element.prototype.scrollTo = vi.fn();
  URL.createObjectURL = vi.fn(() => 'blob:review');
  URL.revokeObjectURL = vi.fn();
});

async function openApp() {
  render(<App />);
  await screen.findByRole('button', { name: 'A', exact: true });
}

it('gửi Word qua dấu cộng, giữ bản nháp khi đọc và hiện trạng thái sau khi nhận', async () => {
  const result = deferred<void>();
  vi.mocked(api.sendMessage).mockImplementation(async (payload, handlers) => {
    expect(payload.attachments?.[0].name).toBe('ke-hoach.docx');
    handlers.onReading?.('Peto đang đọc 1 tài liệu…');
    await result.promise;
    handlers.onMeta?.('C', 'low', { role: 'user', content: 'Tóm tắt', attachments: [{
      id: 'word-1', name: 'ke-hoach.docx', mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', kind: 'file', size: 1200,
      url: '/api/attachments/word-1', document: { status: 'ready', notice: 'Đã đọc phần thân văn bản và bảng biểu trong Word.', characters: 500 },
    }] });
    handlers.onDelta?.('Đây là tóm tắt giả để kiểm tra giao diện.');
    handlers.onDone?.();
  });
  await openApp();
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  expect(input.accept).toContain('.docx');
  await userEvent.upload(input, new File(['tai lieu gia'], 'ke-hoach.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }));
  fireEvent.change(screen.getByLabelText('Nhắn cho Peto'), { target: { value: 'Tóm tắt' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  await screen.findByText('Peto đang đọc 1 tài liệu…');
  expect((screen.getByLabelText('Nhắn cho Peto') as HTMLTextAreaElement).value).toBe('Tóm tắt');
  await act(async () => result.resolve());
  await screen.findByText('Đã đọc chữ');
  expect(screen.queryByText('Peto đang đọc 1 tài liệu…')).toBeNull();
  expect((screen.getByLabelText('Nhắn cho Peto') as HTMLTextAreaElement).value).toBe('');
  expect(screen.getByRole('link', { name: /ke-hoach.docx/ }).getAttribute('href')).toBe('/api/attachments/word-1');
});

it('lịch sử PDF báo rõ phần không đọc được và vẫn tải lại được', async () => {
  vi.mocked(api.getMessages).mockResolvedValue([{ role: 'user', content: 'Xem PDF', attachments: [{
    id: 'pdf-1', name: 'ban-scan.pdf', mime: 'application/pdf', kind: 'file', size: 1200, url: '/api/attachments/pdf-1',
    document: { status: 'partial', notice: 'Có trang không có lớp chữ đọc được. Chưa hỗ trợ OCR.', characters: 100, pages: 3 },
  }] }]);
  await openApp();
  fireEvent.click(screen.getByRole('button', { name: 'A', exact: true }));
  fireEvent.click(await screen.findByText('Đọc được một phần · 3 trang'));
  expect(screen.getByText('Có trang không có lớp chữ đọc được. Chưa hỗ trợ OCR.')).toBeTruthy();
  expect(screen.getByRole('link', { name: /ban-scan.pdf/ }).getAttribute('download')).toBe('ban-scan.pdf');
});

it('dừng khi đang đọc tệp giữ bản nháp và bỏ trạng thái đang đọc', async () => {
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers, signal) => {
    handlers.onReading?.('Peto đang đọc 1 tài liệu…');
    await new Promise<void>((_resolve, reject) => signal?.addEventListener('abort', () => {
      handlers.onReading?.('Trạng thái đến muộn');
      reject(new DOMException('Đã dừng', 'AbortError'));
    }));
  });
  await openApp();
  fireEvent.change(screen.getByLabelText('Nhắn cho Peto'), { target: { value: 'Đọc tài liệu' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  await screen.findByText('Peto đang đọc 1 tài liệu…');
  fireEvent.click(screen.getByRole('button', { name: 'Dừng', exact: true }));
  await screen.findByText('Đã dừng gửi. Bản nháp vẫn được giữ lại.');
  expect((screen.getByLabelText('Nhắn cho Peto') as HTMLTextAreaElement).value).toBe('Đọc tài liệu');
  expect(screen.queryByText('Peto đang đọc 1 tài liệu…')).toBeNull();
  expect(screen.queryByText('Trạng thái đến muộn')).toBeNull();
});

it('tự động tìm web, hiển thị tiến trình và nguồn cùng câu trả lời', async () => {
  const result = deferred<void>();
  vi.mocked(api.sendMessage).mockImplementation(async (payload, handlers) => {
    expect(payload.webSearch).toBe('auto');
    handlers.onMeta?.('C', 'low', row('Tìm Python'));
    handlers.onSearch?.('searching');
    await result.promise;
    handlers.onSources?.([{ url: 'https://docs.python.org/3/', title: 'Tài liệu Python' }]);
    handlers.onDelta?.('Có tài liệu chính thức.');
    handlers.onDone?.();
  });
  await openApp();
  expect(screen.queryByLabelText('Tìm kiếm web')).toBeNull();
  fireEvent.change(screen.getByLabelText('Nhắn cho Peto'), { target: { value: 'Tìm Python' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  await screen.findByText('Peto đang tìm trên web…');
  expect((screen.getByRole('button', { name: 'Thêm ảnh và tùy chọn' }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => result.resolve());
  await screen.findByText('Có tài liệu chính thức.');
  expect(screen.queryByText('Peto đang tìm trên web…')).toBeNull();
  fireEvent.click(screen.getByText('1 nguồn tham khảo'));
  expect(screen.getByRole('link', { name: /Tài liệu Python/ }).getAttribute('href')).toBe('https://docs.python.org/3/');
});

it('nguồn xuất hiện khi mở lịch sử và loại bỏ liên kết không an toàn', async () => {
  vi.mocked(api.getMessages).mockResolvedValue([{ role: 'assistant', content: 'Câu trả lời cũ', sources: [
    { url: 'https://docs.python.org/3/', title: 'Tài liệu Python' },
    { url: 'https://docs.python.org/3/', title: 'Trùng' },
    { url: 'javascript:alert(1)', title: 'Nguồn nguy hiểm' },
  ] }]);
  await openApp();
  fireEvent.click(screen.getByRole('button', { name: 'A', exact: true }));
  fireEvent.click(await screen.findByText('1 nguồn tham khảo'));
  expect(screen.getByRole('link', { name: /Tài liệu Python/ }).getAttribute('rel')).toContain('noreferrer');
  expect(screen.queryByText('Nguồn nguy hiểm')).toBeNull();
});

it('dừng lúc đang tìm web không để tiến trình treo hoặc nhận nguồn đến muộn', async () => {
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers, signal) => {
    handlers.onMeta?.('C', 'low', row('Tìm Python'));
    handlers.onSearch?.('searching');
    await new Promise<void>((_resolve, reject) => signal?.addEventListener('abort', () => {
      handlers.onSources?.([{ url: 'https://example.com', title: 'Nguồn đến muộn' }]);
      reject(new DOMException('Đã dừng', 'AbortError'));
    }));
  });
  await openApp();
  fireEvent.change(screen.getByLabelText('Nhắn cho Peto'), { target: { value: 'Tìm Python' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  await screen.findByText('Peto đang tìm trên web…');
  fireEvent.click(screen.getByRole('button', { name: 'Dừng', exact: true }));
  await screen.findByText('Đã dừng. Phần đã trả lời được giữ lại.');
  expect(screen.queryByText('Peto đang tìm trên web…')).toBeNull();
  expect(screen.queryByText('1 nguồn tham khảo')).toBeNull();
});

it('giữ chế độ tìm và bản nháp khi máy chủ từ chối, gửi đúng chế độ tắt', async () => {
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => handlers.onError?.('Đang bận'));
  await openApp();
  fireEvent.click(screen.getByRole('button', { name: 'Thêm ảnh và tùy chọn' }));
  fireEvent.click(screen.getByRole('button', { name: /Tắt tìm kiếm web/ }));
  fireEvent.change(screen.getByLabelText('Nhắn cho Peto'), { target: { value: 'Giải thích Python' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  await screen.findByText('Đang bận');
  fireEvent.click(screen.getByRole('button', { name: 'Thêm ảnh và tùy chọn' }));
  expect(screen.getByRole('button', { name: /Bật tìm kiếm web/ })).toBeTruthy();
  expect((screen.getByLabelText('Nhắn cho Peto') as HTMLTextAreaElement).value).toBe('Giải thích Python');
  expect(vi.mocked(api.sendMessage).mock.calls[0][0].webSearch).toBe('off');
});

it('menu dấu cộng chọn được tệp, đóng bằng Escape và bật lại tìm web tự động', async () => {
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => handlers.onError?.('Giữ bản nháp'));
  await openApp();
  const trigger = screen.getByRole('button', { name: 'Thêm ảnh và tùy chọn' });
  fireEvent.click(trigger);
  expect(document.activeElement).toBe(screen.getByRole('button', { name: /Thêm ảnh hoặc tệp/ }));
  fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
  expect(screen.queryByRole('group', { name: 'Tùy chọn tin nhắn' })).toBeNull();
  expect(document.activeElement).toBe(trigger);
  fireEvent.click(trigger);
  fireEvent.pointerDown(screen.getByLabelText('Nhắn cho Peto'));
  expect(screen.queryByRole('group', { name: 'Tùy chọn tin nhắn' })).toBeNull();
  fireEvent.click(trigger);
  const input = document.querySelector('input[type=file]') as HTMLInputElement;
  const picker = vi.spyOn(input, 'click');
  fireEvent.click(screen.getByRole('button', { name: /Thêm ảnh hoặc tệp/ }));
  expect(picker).toHaveBeenCalledOnce();
  picker.mockRestore();
  await userEvent.upload(input, new File(['ghi chú'], 'note.txt', { type: 'text/plain' }));
  expect(screen.getByRole('button', { name: 'Gỡ note.txt' })).toBeTruthy();
  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole('button', { name: /Tắt tìm kiếm web/ }));
  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole('button', { name: /Bật tìm kiếm web/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  await screen.findByText('Giữ bản nháp');
  expect(vi.mocked(api.sendMessage).mock.calls[0][0].webSearch).toBe('auto');
});

it('allows many code files but keeps the image, PDF and Word cap', async () => {
  await openApp();
  const input = document.querySelector('input[type=file]') as HTMLInputElement;
  const code = Array.from({ length: 5 }, (_, i) => new File(['x'], `mod${i}.py`, { type: 'text/x-python' }));
  await userEvent.upload(input, code);
  expect(screen.getByRole('button', { name: 'Gỡ mod4.py' })).toBeTruthy();
  expect(screen.queryByText(/tối đa 4 ảnh, PDF hoặc Word/)).toBeNull();
  const images = Array.from({ length: 5 }, (_, i) => new File(['x'], `anh${i}.png`, { type: 'image/png' }));
  await userEvent.upload(input, images);
  expect(screen.getByText(/Mỗi tin chỉ gửi tối đa 4 ảnh, PDF hoặc Word/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Gỡ anh3.png' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Gỡ anh4.png' })).toBeNull();
});

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
    fireEvent.click(screen.getByRole('button', { name: 'Trò chuyện', exact: true }));
    await act(async () => a.resolve([row('Nội dung cũ')]));
    expect(screen.queryByText('Nội dung cũ')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: /Demo/ })).toBeTruthy();
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

describe('Khối code trong chat', () => {
  const withCode = (fence: string) => {
    vi.mocked(api.getMessages).mockResolvedValue([{ role: 'assistant', content: fence }]);
  };
  const openChat = async () => {
    await openApp();
    fireEvent.click(screen.getByRole('button', { name: 'A', exact: true }));
  };
  const PY_CODE = '```python\ndef chao():\n    return "xin chào"\n```';

  it('gắn nhãn ngôn ngữ và tô màu cú pháp', async () => {
    withCode(PY_CODE);
    await openChat();
    expect(await screen.findByText('Python')).toBeTruthy();
    // `def` phải thành thẻ riêng mang lớp của highlight.js, không còn chữ trơn.
    expect(document.querySelector('.hljs-keyword')?.textContent).toBe('def');
    expect(document.querySelector('.hljs-string')?.textContent).toBe('"xin chào"');
  });

  it('tô màu C# và các ngôn ngữ ngoài web, kèm nhãn gọn', async () => {
    withCode('```cs\npublic class Xin { public string Ten = "An"; }\n```');
    await openChat();
    expect(await screen.findByText('C#')).toBeTruthy();
    expect(document.querySelector('.hljs-keyword')?.textContent).toBe('public');
    expect(document.querySelector('.hljs-string')?.textContent).toBe('"An"');
  });

  it('nhận alias viết sau dấu ba nháy', async () => {
    withCode('```ts\nconst x: number = 1;\n```');
    await openChat();
    expect(await screen.findByText('TypeScript')).toBeTruthy();
  });

  it('vẫn dựng khối cho code không ghi ngôn ngữ', async () => {
    withCode('```\nkhong ro ngon ngu\n```');
    await openChat();
    expect(await screen.findByText('Mã')).toBeTruthy();
  });

  it('nút sao chép chép đúng nguyên văn code', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    withCode(PY_CODE);
    await openChat();
    fireEvent.click(await screen.findByRole('button', { name: /Sao chép/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('def chao():\n    return "xin chào"\n'));
    await screen.findByRole('button', { name: /Đã chép/ });
  });

  it('báo khi trình duyệt chặn clipboard', async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('bi chan')) } });
    withCode('```python\nx = 1\n```');
    await openChat();
    fireEvent.click(await screen.findByRole('button', { name: /Sao chép/ }));
    await screen.findByRole('button', { name: /Chưa chép được/ });
  });
});

describe('Màn hình đăng nhập', () => {
  const chuaDangNhap = (providers: Record<string, boolean>) => {
    vi.mocked(api.getAuthState).mockResolvedValue({ authenticated: false,
      login_configured: true, providers: providers as never });
  };

  it('bày đủ ba cách đăng nhập', async () => {
    chuaDangNhap({ discord: true, google: true, guest: true });
    render(<App />);
    expect(await screen.findByRole('link', { name: /Đăng nhập bằng Discord/ })).toBeTruthy();
    expect(screen.getByText('Đăng nhập bằng cách khác')).toBeTruthy();
    expect(screen.getByRole('link', { name: /Google/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Khách/ })).toBeTruthy();
  });

  it('ẩn nút Google khi chưa khai credential', async () => {
    chuaDangNhap({ discord: true, google: false, guest: true });
    render(<App />);
    await screen.findByRole('link', { name: /Đăng nhập bằng Discord/ });
    expect(screen.queryByRole('link', { name: /Google/ })).toBeNull();
    // Khách không cần cấu hình gì nên luôn còn.
    expect(screen.getByRole('button', { name: /Khách/ })).toBeTruthy();
  });

  it('đăng xuất xong vẫn còn đủ các cách đăng nhập', async () => {
    // handleUnauthorized từng dựng AuthState mới toanh, làm mất `providers`,
    // nên nút Google biến mất tới khi F5. Đăng xuất không đổi gì ở máy chủ.
    vi.mocked(api.logout).mockResolvedValue(undefined);
    await openApp();
    fireEvent.click(screen.getByRole('button', { name: /Cài đặt/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Đăng xuất' }));

    expect(await screen.findByRole('link', { name: /Đăng nhập bằng Discord/ })).toBeTruthy();
    expect(screen.getByRole('link', { name: /Google/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Khách/ })).toBeTruthy();
    // Không gọi lại /api/auth/me: thông tin đã biết thì giữ lấy.
    expect(api.getAuthState).toHaveBeenCalledTimes(1);
  });

  it('báo lỗi thay vì bày nút chết khi không gọi được /api/auth/me', async () => {
    // getAuthState hỏng -> login_configured false. Trước đây màn hình vẫn bày
    // nút Discord bấm không ăn thua và giấu Google, làm người dùng tưởng thiếu
    // cấu hình Google trong khi thật ra backend không chạy.
    vi.mocked(api.getAuthState).mockRejectedValue(new Error('mat mang'));
    render(<App />);
    expect(await screen.findByText(/Chưa kết nối được dịch vụ đăng nhập/)).toBeTruthy();
    expect(screen.queryByRole('link', { name: /Đăng nhập bằng Discord/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Khách/ })).toBeNull();
  });

  it('vào được với tư cách khách', async () => {
    // Lần hỏi đầu là lúc mở trang (chưa đăng nhập); lần sau là ngay sau khi
    // bấm Khách, nên phải trả trạng thái đã vào được.
    vi.mocked(api.getAuthState)
      .mockResolvedValueOnce({ authenticated: false, login_configured: true,
        providers: { discord: true, google: true, guest: true } })
      .mockResolvedValue({ authenticated: true, login_configured: true,
        providers: { discord: true, google: true, guest: true },
        user: { id: 'acc-khach', provider: 'guest', username: 'khach', display_name: 'Khách', avatar_url: '' } });
    vi.mocked(api.guestLogin).mockResolvedValue(undefined);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Khách/ }));
    await waitFor(() => expect(api.guestLogin).toHaveBeenCalled());
    await screen.findByRole('button', { name: 'A', exact: true });
    // Không có ảnh đại diện thì rơi về chữ cái đầu, không phải <img src="">.
    // Hiện ở cả khối tài khoản lẫn hộp cài đặt.
    expect(screen.getAllByText('K')).toHaveLength(2);
    expect(document.querySelector('img.account-avatar')).toBeNull();
  });

  it('vào bằng khách rồi đăng xuất thì nút Khách dùng lại được', async () => {
    // guestBusy từng chỉ được dọn trong nhánh catch. Vào được thì cờ ở nguyên
    // true, và vì App không unmount, đăng xuất là nút kẹt "Đang vào…" mãi mãi.
    vi.mocked(api.getAuthState)
      .mockResolvedValueOnce({ authenticated: false, login_configured: true,
        providers: { discord: true, google: true, guest: true } })
      .mockResolvedValue({ authenticated: true, login_configured: true,
        providers: { discord: true, google: true, guest: true },
        user: { id: 'acc-khach', provider: 'guest', username: 'khach', display_name: 'Khách', avatar_url: '' } });
    vi.mocked(api.guestLogin).mockResolvedValue(undefined);
    vi.mocked(api.logout).mockResolvedValue(undefined);

    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Khách/ }));
    await screen.findByRole('button', { name: 'A', exact: true });

    fireEvent.click(screen.getByRole('button', { name: /Cài đặt/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Đăng xuất' }));
    await screen.findByRole('link', { name: /Đăng nhập bằng Discord/ });

    const nut = document.querySelector('.login-alts button') as HTMLButtonElement;
    expect(nut.disabled).toBe(false);
    expect(nut.textContent).toContain('Khách');
    expect(screen.queryByText(/Đang vào/)).toBeNull();
  });

  it('báo lỗi khi không vào được bằng khách', async () => {
    chuaDangNhap({ discord: true, google: true, guest: true });
    vi.mocked(api.guestLogin).mockRejectedValue(new Error('Máy chủ đang bận'));
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Khách/ }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Máy chủ đang bận');
  });
});

describe('Thanh bên', () => {
  beforeEach(() => localStorage.removeItem('peto-sidebar-collapsed'));

  it('thu gọn, mở lại và nhớ lựa chọn', async () => {
    await openApp();
    const sidebar = document.querySelector('.sidebar')!;
    fireEvent.click(screen.getByRole('button', { name: 'Thu gọn thanh bên' }));
    expect(sidebar.classList.contains('collapsed')).toBe(true);
    expect(localStorage.getItem('peto-sidebar-collapsed')).toBe('1');

    const expand = screen.getByRole('button', { name: 'Mở rộng thanh bên' });
    expect(expand.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(expand);
    expect(sidebar.classList.contains('collapsed')).toBe(false);
    expect(localStorage.getItem('peto-sidebar-collapsed')).toBe('0');
  });

  it('mở app vẫn thu gọn nếu lần trước đã thu gọn', async () => {
    localStorage.setItem('peto-sidebar-collapsed', '1');
    await openApp();
    expect(document.querySelector('.sidebar')!.classList.contains('collapsed')).toBe(true);
    // Thu gọn chỉ là chuyện hiển thị: tên mục vẫn còn cho trình đọc màn hình.
    expect(screen.getByRole('button', { name: 'Tạo ảnh', exact: true })).toBeTruthy();
  });

  it('có nhãn Gần đây ngay trên lịch sử trò chuyện', async () => {
    await openApp();
    expect(screen.getByRole('heading', { name: 'Gần đây' })).toBeTruthy();
    expect(screen.getByRole('navigation', { name: 'Gần đây' })).toBeTruthy();
  });

  it('từ Tạo ảnh quay về thì giữ cuộc đang mở, bấm lại mới mở cuộc mới', async () => {
    vi.mocked(api.getMessages).mockResolvedValue([row('Nội dung A')]);
    await openApp();
    fireEvent.click(screen.getByRole('button', { name: 'A', exact: true }));
    await screen.findByText('Nội dung A');

    fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: 'Trò chuyện', exact: true }));
    expect(screen.getByText('Nội dung A')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Trò chuyện', exact: true }));
    expect(screen.queryByText('Nội dung A')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: /Demo/ })).toBeTruthy();
  });
});

describe('Chọn mức suy nghĩ', () => {
  beforeEach(() => localStorage.removeItem('peto-effort'));

  it('mở menu, đánh dấu mức đang chọn và đổi được mức', async () => {
    await openApp();
    const trigger = screen.getByRole('button', { name: 'Mức suy nghĩ: Tự động' });
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getAllByRole('menuitemradio').map((item) => item.textContent))
      .toEqual(['Tự động', 'Thấp', 'Trung bình', 'Cao']);
    expect(screen.getByRole('menuitemradio', { name: 'Tự động' }).getAttribute('aria-checked')).toBe('true');

    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Cao' }));
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.getByRole('button', { name: 'Mức suy nghĩ: Cao' })).toBeTruthy();
    expect(localStorage.getItem('peto-effort')).toBe('high');
  });

  it('dùng được bằng bàn phím, Escape trả con trỏ về nút', async () => {
    await openApp();
    const trigger = screen.getByRole('button', { name: /Mức suy nghĩ/ });
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    const auto = await screen.findByRole('menuitemradio', { name: 'Tự động' });
    await waitFor(() => expect(document.activeElement).toBe(auto));
    fireEvent.keyDown(auto, { key: 'ArrowDown' });
    expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: 'Thấp' }));
    fireEvent.keyDown(auto, { key: 'End' });
    expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: 'Cao' }));
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('gửi đúng mức đã chọn lên máy chủ', async () => {
    vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => { handlers.onDone?.(); });
    await openApp();
    fireEvent.click(screen.getByRole('button', { name: /Mức suy nghĩ/ }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Trung bình' }));
    fireEvent.change(screen.getByPlaceholderText('Nhắn cho Peto…'), { target: { value: 'Giải giúp' } });
    fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
    await waitFor(() => expect(api.sendMessage).toHaveBeenCalled());
    expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({ effort: 'medium' });
  });
});

describe('Hồ sơ trong Cài đặt', () => {
  const PROFILE = { full_name: 'Nguyễn An', nickname: 'An', occupation: 'student', instructions: 'Trả lời ngắn.' };
  const data = () => ({ profile: PROFILE, limits: { full_name: 80, nickname: 40, instructions: 1500 },
    occupations: [{ value: 'student', label: 'Học sinh, sinh viên' }, { value: 'other', label: 'Khác' }] });
  const openSettings = async () => {
    await openApp();
    fireEvent.click(screen.getByRole('button', { name: /Cài đặt/ }));
  };

  it('tải hồ sơ vào các ô và chỉ cho lưu khi có thay đổi', async () => {
    vi.mocked(api.getProfile).mockResolvedValue(data());
    await openSettings();
    expect((await screen.findByLabelText('Họ và tên') as HTMLInputElement).value).toBe('Nguyễn An');
    expect((screen.getByLabelText('Peto nên gọi bạn là gì?') as HTMLInputElement).value).toBe('An');
    expect((screen.getByLabelText('Công việc của bạn') as HTMLSelectElement).value).toBe('student');
    expect((screen.getByLabelText('Hướng dẫn cho Peto') as HTMLTextAreaElement).value).toBe('Trả lời ngắn.');
    const save = screen.getByRole('button', { name: 'Lưu thay đổi' });
    expect(save).toHaveProperty('disabled', true);
    fireEvent.change(screen.getByLabelText('Peto nên gọi bạn là gì?'), { target: { value: 'Bé An' } });
    expect(save).toHaveProperty('disabled', false);
  });

  it('lưu đúng giá trị rồi hiện bản máy chủ đã chuẩn hóa', async () => {
    vi.mocked(api.getProfile).mockResolvedValue(data());
    vi.mocked(api.saveProfile).mockResolvedValue({ ...PROFILE, nickname: 'Bé An', occupation: 'other' });
    await openSettings();
    fireEvent.change(await screen.findByLabelText('Peto nên gọi bạn là gì?'), { target: { value: '  Bé   An ' } });
    fireEvent.change(screen.getByLabelText('Công việc của bạn'), { target: { value: 'other' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }));
    await screen.findByText('Đã lưu');
    expect(api.saveProfile).toHaveBeenCalledWith({ ...PROFILE, nickname: '  Bé   An ', occupation: 'other' });
    expect((screen.getByLabelText('Peto nên gọi bạn là gì?') as HTMLInputElement).value).toBe('Bé An');
    expect(screen.getByRole('button', { name: 'Lưu thay đổi' })).toHaveProperty('disabled', true);
  });

  it('lưu hỏng thì báo lỗi và giữ nguyên chữ đang gõ', async () => {
    vi.mocked(api.getProfile).mockResolvedValue(data());
    vi.mocked(api.saveProfile).mockRejectedValue(new Error('Tên để Peto gọi dài quá, tối đa 40 ký tự nhé.'));
    await openSettings();
    fireEvent.change(await screen.findByLabelText('Peto nên gọi bạn là gì?'), { target: { value: 'Tên mới' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Tên để Peto gọi dài quá, tối đa 40 ký tự nhé.');
    expect((screen.getByLabelText('Peto nên gọi bạn là gì?') as HTMLInputElement).value).toBe('Tên mới');
  });

  it('không tải được hồ sơ thì cho thử lại', async () => {
    vi.mocked(api.getProfile).mockRejectedValueOnce(new Error('mat mang')).mockResolvedValue(data());
    await openSettings();
    fireEvent.click(await screen.findByRole('button', { name: 'Thử lại' }));
    expect((await screen.findByLabelText('Họ và tên') as HTMLInputElement).value).toBe('Nguyễn An');
  });
});

describe('Lời chào theo giờ', () => {
  // Chỉ giả lập Date; timer vẫn chạy thật để findBy/waitFor không bị treo.
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2026, 8, 11, 20, 30)); // tối thứ Sáu
    vi.spyOn(Math, 'random').mockReturnValue(0);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('chào theo buổi trên máy thay cho "Chào tên"', async () => {
    await openApp();
    expect(screen.getByRole('heading', { level: 1, name: 'Chào buổi tối, Demo' })).toBeTruthy();
  });

  it('gọi bằng tên đặt trong Hồ sơ nếu có', async () => {
    vi.mocked(api.getAuthState).mockResolvedValue({ authenticated: true, login_configured: true,
      providers: { discord: true, google: true, guest: true },
      user: { id: 'acc-111', provider: 'discord', username: 'demo', display_name: 'Demo', avatar_url: '', nickname: 'Bé Na' } });
    await openApp();
    expect(screen.getByRole('heading', { level: 1, name: 'Chào buổi tối, Bé Na' })).toBeTruthy();
  });

  it('lưu tên mới trong Hồ sơ là lời chào đổi theo ngay', async () => {
    vi.mocked(api.saveProfile).mockResolvedValue({ full_name: '', nickname: 'Bé An', occupation: '', instructions: '' });
    await openApp();
    fireEvent.click(screen.getByRole('button', { name: /Cài đặt/ }));
    fireEvent.change(await screen.findByLabelText('Peto nên gọi bạn là gì?'), { target: { value: 'Bé An' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }));
    await screen.findByText('Đã lưu');
    expect(screen.getByRole('heading', { level: 1, name: 'Chào buổi tối, Bé An' })).toBeTruthy();
  });

  it('quay lại tab khi đã sang buổi khác thì chọn câu hợp giờ', async () => {
    await openApp();
    vi.mocked(Math.random).mockReturnValue(0.99);
    const comeBack = () => act(() => { document.dispatchEvent(new Event('visibilitychange')); });

    vi.setSystemTime(new Date(2026, 8, 11, 21, 45)); // vẫn buổi tối: giữ câu cũ
    comeBack();
    expect(screen.getByRole('heading', { level: 1, name: 'Chào buổi tối, Demo' })).toBeTruthy();

    vi.setSystemTime(new Date(2026, 8, 12, 7, 0)); // sáng thứ Bảy
    comeBack();
    expect(screen.getByRole('heading', { level: 1, name: 'Cuối tuần vui chứ, Demo?' })).toBeTruthy();
  });
});

describe('Bố cục màn hình trống', () => {
  const originalMatchMedia = window.matchMedia;
  let animate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    animate = vi.fn();
    // jsdom không có Web Animations API và không tính bố cục, nên giả cả hai: ô
    // nhắn "ở giữa" (top 400) khi còn trống, "ở đáy" (top 700) khi đã có tin.
    Object.defineProperty(HTMLElement.prototype, 'animate', { value: animate, configurable: true, writable: true });
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(() => {
      const top = document.querySelector('main.chat')?.classList.contains('empty-state') ? 400 : 700;
      return { top, bottom: top, left: 0, right: 0, width: 0, height: 0, x: 0, y: top, toJSON() {} } as DOMRect;
    });
    // Như máy chủ thật: meta xác nhận đã lưu tin, thiếu nó App trả lại danh sách cũ.
    vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
      handlers.onMeta?.('C', 'low', row('Chào Peto'));
      handlers.onDone?.();
    });
  });
  afterEach(() => {
    delete (HTMLElement.prototype as { animate?: unknown }).animate;
    window.matchMedia = originalMatchMedia;
  });

  const send = (text: string) => {
    fireEvent.change(screen.getByPlaceholderText('Nhắn cho Peto…'), { target: { value: text } });
    fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  };

  it('còn trống thì gợi ý nằm cùng ô nhắn, gửi tin đầu là về bố cục thường', async () => {
    await openApp();
    const main = document.querySelector('main.chat')!;
    expect(main.classList.contains('empty-state')).toBe(true);
    const hint = screen.getByRole('button', { name: 'Hôm nay cậu thế nào?' });
    expect(hint.closest('form')).toBe(screen.getByPlaceholderText('Nhắn cho Peto…').closest('form'));
    send('Chào Peto');
    await waitFor(() => expect(api.sendMessage).toHaveBeenCalled());
    expect(main.classList.contains('empty-state')).toBe(false);
    expect(screen.queryByRole('button', { name: 'Hôm nay cậu thế nào?' })).toBeNull();
  });

  it('gửi tin đầu thì ô nhắn trượt từ giữa xuống đáy', async () => {
    await openApp();
    send('Chào Peto');
    await waitFor(() => expect(animate).toHaveBeenCalledTimes(1));
    expect(animate.mock.calls[0][0]).toEqual([{ transform: 'translateY(-300px)' }, { transform: 'none' }]);
    expect(animate.mock.calls[0][1]).toMatchObject({ duration: 300 });
  });

  it('bật giảm chuyển động thì chỉ hiện dần, không trượt', async () => {
    window.matchMedia = vi.fn((query: string) => ({ matches: query.includes('reduce'), media: query,
      addEventListener: vi.fn(), removeEventListener: vi.fn() })) as unknown as typeof window.matchMedia;
    await openApp();
    send('Chào Peto');
    await waitFor(() => expect(animate).toHaveBeenCalledTimes(1));
    expect(animate.mock.calls[0][0]).toEqual([{ opacity: 0 }, { opacity: 1 }]);
  });

  it('mở hội thoại từ màn hình trống thì đổi ngay, không hiệu ứng', async () => {
    vi.mocked(api.getMessages).mockResolvedValue([row('Nội dung A')]);
    await openApp();
    fireEvent.click(screen.getByRole('button', { name: 'A', exact: true }));
    await screen.findByText('Nội dung A');
    expect(document.querySelector('main.chat')!.classList.contains('empty-state')).toBe(false);
    expect(animate).not.toHaveBeenCalled();
  });
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
