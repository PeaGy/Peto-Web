import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from '../src/App';
import * as api from '../src/api';

vi.mock('../src/api', async (original) => ({
  ...await original<typeof import('../src/api')>(),
  getAuthState: vi.fn(), listConversations: vi.fn(), getMessages: vi.fn(), sendMessage: vi.fn(),
  listImagineJobs: vi.fn(), getProfile: vi.fn(), getAppInfo: vi.fn(), getCompanion: vi.fn(),
  deleteConversation: vi.fn(),
}));

const fetchMock = vi.fn();
const played: string[] = [];

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  played.length = 0;
  window.history.replaceState(null, '', '/');
  vi.mocked(api.getAuthState).mockResolvedValue({ authenticated: true, login_configured: true,
    providers: { discord: true, google: true, guest: true },
    user: { id: 'acc-111', provider: 'discord', username: 'demo', display_name: 'Demo', avatar_url: '' } });
  vi.mocked(api.listConversations).mockResolvedValue({ conversations: [], has_more: false });
  vi.mocked(api.getMessages).mockResolvedValue([]);
  vi.mocked(api.listImagineJobs).mockResolvedValue([]);
  vi.mocked(api.getAppInfo).mockRejectedValue(new Error('offline'));
  vi.mocked(api.getProfile).mockResolvedValue({ profile: { full_name: '', nickname: '', occupation: '', instructions: '' },
    occupations: [], limits: { full_name: 80, nickname: 40, instructions: 1500 } });
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: null, messages: [] });
  vi.mocked(api.deleteConversation).mockResolvedValue();
  Element.prototype.scrollTo = vi.fn();
  URL.createObjectURL = vi.fn(() => 'blob:voice');
  URL.revokeObjectURL = vi.fn();
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify(health()));
    if (url.endsWith('/speak')) return new Response('RIFF', { headers: { 'Content-Type': 'audio/wav', 'X-Peto-Voice-Used': '1436' } });
    throw new Error(`Không mong đợi ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('Audio', class {
    onended: (() => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(public src: string) {}
    play() {
      played.push(this.src);
      queueMicrotask(() => this.onended?.());
      return Promise.resolve();
    }
    pause() {}
  });
});

afterEach(() => vi.unstubAllGlobals());

/** /api/voice/health như máy chủ bây giờ trả: Giọng Peto (StepFun) còn 3.600 ký tự tháng này, máy nhà đang bật. */
function health(official: Record<string, unknown> = {}, home: Record<string, unknown> = {}) {
  const voices = ['stepfun:jilingshaonv', 'stepfun:lively-girl'];
  return {
    ok: true, voices: [...voices, 'playful-1', 'gentle-2'],
    home: { online: true, voices: ['playful-1', 'gentle-2'], ...home },
    official: { voices, allowed: true, used: 1400, limit: 5000, resets: '2026-10-01', ...official },
  };
}

const localCalls = () => fetchMock.mock.calls.filter(([url]) => String(url).startsWith('/api/voice'));
const speakBodies = () => fetchMock.mock.calls
  .filter(([url]) => String(url).endsWith('/speak'))
  .map(([, init]) => JSON.parse(String(init?.body)));
const chatColumn = () => within(screen.getByRole('region', { name: 'Trò chuyện trong Companion' }));

async function openCompanion() {
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Companion' }));
}

async function openSettings() {
  fireEvent.click(await screen.findByRole('button', { name: /Cài đặt · Demo/ }));
  return within(screen.getByRole('dialog', { name: 'Cài đặt' }));
}

async function sendInCompanion(text: string) {
  fireEvent.change(screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi' }));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalled());
}

it('chỉ gọi giọng nói qua VPS sau khi bật trong Cài đặt', async () => {
  await openCompanion();
  expect(await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' })).toBeTruthy();
  expect(window.location.hash).toBe('#companion');

  const settings = await openSettings();
  expect(localCalls()).toHaveLength(0);

  expect(settings.queryByRole('button', { name: 'Giọng Peto' })).toBeNull();
  fireEvent.click(settings.getByRole('switch', { name: 'Bật giọng nói' }));
  expect(await settings.findByText('3.600 / 5.000 ký tự')).toBeTruthy();
  expect(settings.getByRole('button', { name: 'Giọng Peto' }).getAttribute('aria-pressed')).toBe('true');
  expect(localCalls()).toHaveLength(1);
  expect(await chatColumn().findByRole('button', { name: 'Tắt tiếng' })).toBeTruthy();
});

it('đã bật từ trước thì tab Trò chuyện chưa dò, mở Companion mới dò', async () => {
  localStorage.setItem('peto-local-voice', '1');
  render(<App />);
  const companionTab = await screen.findByRole('button', { name: 'Companion' });
  expect(localCalls()).toHaveLength(0);

  fireEvent.click(companionTab);
  expect(await chatColumn().findByRole('button', { name: 'Tắt tiếng' })).toBeTruthy();
  expect(localCalls()).toHaveLength(1);
});

it('gửi ở chế độ Companion và Peto tự nói khi trả lời xong', async () => {
  localStorage.setItem('peto-local-voice', '1');
  localStorage.setItem('peto-local-voice-name', 'gentle-2');
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low');
    handlers.onDelta?.('Hey! Good to see you.');
    handlers.onDone?.();
  });
  await openCompanion();
  await chatColumn().findByRole('button', { name: 'Tắt tiếng' });

  await sendInCompanion('hi');
  expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({
    message: 'hi', conversationId: null, mode: 'companion', effort: 'low', webSearch: 'off',
  });
  await waitFor(() => expect(played).toHaveLength(1));
  expect(speakBodies()).toEqual([{ text: 'Hey! Good to see you.', voice: 'gentle-2' }]);
});

it('tắt tiếng ở cột chat thì Peto không tự nói, bấm nghe vẫn nghe lại được', async () => {
  localStorage.setItem('peto-local-voice', '1');
  localStorage.setItem('peto-companion-muted', '1');
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', messages: [
    { role: 'user', content: 'hi' },
    { role: 'assistant', content: 'Hey there.' },
  ] });
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low');
    handlers.onDelta?.('Sure thing.');
    handlers.onDone?.();
  });
  await openCompanion();
  await screen.findByText('Hey there.');
  const mute = await chatColumn().findByRole('button', { name: 'Tắt tiếng' });
  expect(mute.getAttribute('aria-pressed')).toBe('true');

  await sendInCompanion('ok');
  expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({ conversationId: 'C1' });
  await screen.findByText('Sure thing.');
  await waitFor(() => expect(screen.getAllByRole('button', { name: /Nghe Peto/ })).toHaveLength(2));
  expect(played).toHaveLength(0);

  fireEvent.click(screen.getAllByRole('button', { name: /Nghe Peto/ })[0]);
  await waitFor(() => expect(played).toHaveLength(1));
});

it('chưa thấy máy chủ thì cột chat báo, bấm Kiểm tra lại thì dò lại', async () => {
  localStorage.setItem('peto-local-voice', '1');
  let serverUp = false;
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/health')) {
      if (!serverUp) throw new TypeError('Failed to fetch');
      return new Response(JSON.stringify(health()));
    }
    throw new Error(`Không mong đợi ${url}`);
  });
  await openCompanion();
  const column = chatColumn();
  expect(await column.findByText('Chưa kết nối được máy chủ giọng nói. Peto chỉ nhắn chữ.')).toBeTruthy();
  expect(column.queryByRole('button', { name: 'Tắt tiếng' })).toBeNull();

  serverUp = true;
  fireEvent.click(column.getByRole('button', { name: 'Kiểm tra lại' }));
  expect(await column.findByRole('button', { name: 'Tắt tiếng' })).toBeTruthy();
  expect(column.queryByText(/Chưa kết nối được máy chủ giọng nói/)).toBeNull();
});

it('Giọng Peto là nguồn mặc định, gửi kèm Máy nhà làm giọng dự phòng', async () => {
  localStorage.setItem('peto-local-voice', '1');
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low');
    handlers.onDelta?.('Hey!');
    handlers.onDone?.();
  });
  await openCompanion();
  await chatColumn().findByRole('button', { name: 'Tắt tiếng' });
  await sendInCompanion('hi');
  await waitFor(() => expect(played).toHaveLength(1));
  expect(speakBodies()).toEqual([{ text: 'Hey!', voice: 'stepfun:jilingshaonv', fallback: 'playful-1' }]);
});

it('chọn Máy nhà trong Cài đặt, đổi giọng rồi Nghe thử thì đọc câu mẫu bằng giọng đó', async () => {
  localStorage.setItem('peto-local-voice', '1');
  render(<App />);
  const settings = await openSettings();
  fireEvent.click(await settings.findByRole('button', { name: 'Local Voice của Peto' }));
  const detail = within(settings.getByRole('group', { name: 'Local Voice của Peto' }));
  expect(detail.getByText(/Local Voice đang bật/)).toBeTruthy();
  fireEvent.click(detail.getByRole('combobox', { name: 'Giọng' }));
  fireEvent.click(detail.getByRole('option', { name: 'Dịu & vui vẻ' }));
  fireEvent.click(detail.getByRole('button', { name: 'Nghe thử' }));

  await waitFor(() => expect(played).toHaveLength(1));
  // Nghe thử chỉ thử đúng nguồn đang chọn, không kèm giọng dự phòng.
  expect(speakBodies()).toEqual([{ text: expect.stringContaining('Peto'), voice: 'gentle-2' }]);
  expect(localStorage.getItem('peto-voice-source')).toBe('home');
  expect(localStorage.getItem('peto-local-voice-name')).toBe('gentle-2');
});

it('chọn giọng StepFun của Giọng Peto, nghe thử thì trừ lượt và cập nhật số còn lại', async () => {
  localStorage.setItem('peto-local-voice', '1');
  render(<App />);
  const settings = await openSettings();
  const detail = within(await settings.findByRole('group', { name: 'Giọng Peto' }));
  expect(await detail.findByText('3.600 / 5.000 ký tự')).toBeTruthy();
  expect(detail.getByText(/làm mới ngày 01\/10/)).toBeTruthy();
  fireEvent.click(detail.getByRole('combobox', { name: 'Giọng' }));
  fireEvent.click(detail.getByRole('option', { name: 'Lively Girl' }));
  expect(speakBodies()).toHaveLength(0);
  fireEvent.click(detail.getByRole('button', { name: 'Nghe thử' }));

  await waitFor(() => expect(played).toHaveLength(1));
  expect(speakBodies()).toEqual([{ text: expect.stringContaining('Peto'), voice: 'stepfun:lively-girl' }]);
  expect(localStorage.getItem('peto-voice-official')).toBe('stepfun:lively-girl');
  expect(await detail.findByText('3.564 / 5.000 ký tự')).toBeTruthy();
});

it('hết lượt Giọng Peto thì không cho nghe thử, còn Companion đọc bằng Máy nhà và báo lý do', async () => {
  localStorage.setItem('peto-local-voice', '1');
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify(health({ used: 5000 })));
    if (url.endsWith('/speak')) return new Response('RIFF', { headers: { 'Content-Type': 'audio/wav' } });
    throw new Error(`Không mong đợi ${url}`);
  });
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', messages: [
    { role: 'user', content: 'hi' },
    { role: 'assistant', content: 'Hey there.' },
  ] });
  await openCompanion();
  await screen.findByText('Hey there.');
  fireEvent.click(await screen.findByRole('button', { name: /Nghe Peto/ }));
  await waitFor(() => expect(played).toHaveLength(1));
  expect(speakBodies()).toEqual([{ text: 'Hey there.', voice: 'playful-1' }]);
  expect(await chatColumn().findByText(
    /Đã hết lượt Giọng Peto tháng này; lượt mới có từ ngày 01\/10\. Đã chuyển sang giọng dự phòng: Local Voice của Peto/,
  )).toBeTruthy();

  const settings = await openSettings();
  const detail = within(settings.getByRole('group', { name: 'Giọng Peto' }));
  expect(detail.getByText(/Đã hết lượt tháng này/)).toBeTruthy();
  expect(detail.queryByRole('button', { name: 'Nghe thử' })).toBeNull();
});

it('khách thấy Giọng Peto dành cho tài khoản Discord và Google, không có số lượt', async () => {
  localStorage.setItem('peto-local-voice', '1');
  vi.mocked(api.getAuthState).mockResolvedValue({ authenticated: true, login_configured: true,
    providers: { discord: true, google: true, guest: true },
    user: { id: 'g-1', provider: 'guest', username: 'khach', display_name: 'Demo', avatar_url: '' } });
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify(health({ allowed: false, used: 0 })));
    throw new Error(`Không mong đợi ${url}`);
  });
  render(<App />);
  const settings = await openSettings();
  const detail = within(await settings.findByRole('group', { name: 'Giọng Peto' }));
  expect(await detail.findByText(/Lượt miễn phí dành cho tài khoản Discord và Google/)).toBeTruthy();
  expect(detail.queryByText(/ký tự/)).toBeNull();
  expect(detail.queryByRole('button', { name: 'Nghe thử' })).toBeNull();

  fireEvent.click(settings.getByRole('button', { name: 'Local Voice của Peto' }));
  fireEvent.click(settings.getByRole('combobox', { name: 'Khi nguồn chính không nói được' }));
  const fallback = within(settings.getByRole('listbox', { name: 'Khi nguồn chính không nói được' }));
  expect(fallback.queryByRole('option', { name: 'Dùng Giọng Peto nếu còn lượt' })).toBeNull();
  expect(fallback.getByRole('option', { name: 'Chỉ hiện chữ' })).toBeTruthy();
});

it('khóa OpenAI riêng: trình duyệt gọi thẳng OpenAI, máy chủ Peto không thấy khóa', async () => {
  localStorage.setItem('peto-local-voice', '1');
  const openai = vi.fn(async (_url: string, _init?: RequestInit) => new Response('RIFF', { headers: { 'Content-Type': 'audio/wav' } }));
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify(health()));
    if (url === 'https://api.openai.com/v1/audio/speech') return openai(url, init);
    throw new Error(`Không mong đợi ${url}`);
  });
  render(<App />);
  const settings = await openSettings();
  fireEvent.click(await within(settings.getByRole('tabpanel', { name: 'Peto nói' })).findByRole('button', { name: 'OpenAI' }));
  const detail = within(settings.getByRole('group', { name: 'OpenAI' }));
  expect(detail.getByText(/máy chủ Peto không nhận được khóa/)).toBeTruthy();
  expect(detail.getByRole('button', { name: 'Nghe thử' }).hasAttribute('disabled')).toBe(true);
  fireEvent.change(detail.getByLabelText('Khóa API OpenAI'), { target: { value: 'sk-user-key' } });
  fireEvent.click(detail.getByRole('button', { name: 'Nghe thử' }));

  await waitFor(() => expect(played).toHaveLength(1));
  const init = openai.mock.calls[0][1]!;
  expect((init.headers as Record<string, string>).Authorization).toBe('Bearer sk-user-key');
  expect(JSON.parse(String(init.body))).toMatchObject({ model: 'tts-1', voice: 'nova', response_format: 'wav' });
  expect(JSON.stringify(localCalls())).not.toContain('sk-user-key');
  expect(localStorage.getItem('peto-voice-keys')).toContain('sk-user-key');

  fireEvent.click(detail.getByRole('button', { name: 'Xóa khóa khỏi trình duyệt' }));
  expect(localStorage.getItem('peto-voice-keys')).not.toContain('sk-user-key');
  expect((detail.getByLabelText('Khóa API OpenAI') as HTMLInputElement).value).toBe('');
});

it('khóa StepFun riêng đi qua máy chủ Peto trong header, không nằm trong thân yêu cầu', async () => {
  localStorage.setItem('peto-local-voice', '1');
  localStorage.setItem('peto-voice-source', 'stepfun');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ stepfun: { key: 'step-user-key' } }));
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify(health()));
    if (url.endsWith('/relay')) return new Response('RIFF', { headers: { 'Content-Type': 'audio/wav' } });
    throw new Error(`Không mong đợi ${url}`);
  });
  render(<App />);
  const settings = await openSettings();
  const detail = within(await settings.findByRole('group', { name: 'StepFun' }));
  expect(detail.getByText(/Máy chủ chỉ chuyển tiếp, không lưu và không ghi lại khóa/)).toBeTruthy();
  fireEvent.click(detail.getByRole('button', { name: 'Nghe thử' }));

  await waitFor(() => expect(played).toHaveLength(1));
  const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/relay'))!;
  expect((init.headers as Record<string, string>)['X-Voice-Key']).toBe('step-user-key');
  expect(JSON.parse(String(init.body))).toEqual({
    provider: 'stepfun', text: expect.stringContaining('Peto'), voice: 'jilingshaonv', model: 'stepaudio-2.5-tts', region: 'intl',
  });
  expect(String(init.body)).not.toContain('step-user-key');
});

it('thẻ Alibaba Cloud: đổi sang CosyVoice v2 thì danh sách giọng đổi theo, Nghe thử gửi model và mã giọng mới', async () => {
  localStorage.setItem('peto-local-voice', '1');
  localStorage.setItem('peto-voice-source', 'qwen');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ qwen: { key: 'sk-ali-key', region: 'cn', voice: 'Serena' } }));
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify(health()));
    if (url.endsWith('/relay')) return new Response('RIFF', { headers: { 'Content-Type': 'audio/wav' } });
    throw new Error(`Không mong đợi ${url}`);
  });
  render(<App />);
  const settings = await openSettings();
  const detail = within(await settings.findByRole('group', { name: 'Alibaba Cloud' }));
  expect(detail.getByText(/CosyVoice cần gắn khóa vào kết nối/)).toBeTruthy();

  fireEvent.click(detail.getByRole('combobox', { name: 'Model' }));
  fireEvent.click(detail.getByRole('option', { name: /CosyVoice v2/ }));
  // Serena là giọng Qwen, CosyVoice không có: ô giọng về giọng mặc định của v2 và lưu lại model mới.
  const saved = () => JSON.parse(localStorage.getItem('peto-voice-keys')!).qwen;
  expect(saved()).toMatchObject({ key: 'sk-ali-key', model: 'cosyvoice-v2' });
  expect(saved().voice).toBeUndefined();
  expect((detail.getByRole('combobox', { name: 'Giọng' }) as HTMLInputElement).placeholder).toBe('龙小淳 · Long Xiaochun');

  fireEvent.click(detail.getByRole('button', { name: 'Xem danh sách gợi ý' }));
  fireEvent.click(detail.getByRole('option', { name: /龙婉 · Long Wan/ }));
  // Không gõ thì ô hiện tên như AIRI; mã thật nằm trong khóa đã lưu.
  fireEvent.blur(detail.getByRole('combobox', { name: 'Giọng' }));
  expect((detail.getByRole('combobox', { name: 'Giọng' }) as HTMLInputElement).value).toBe('龙婉 · Long Wan');
  expect(saved().voice).toBe('longwan_v2');
  fireEvent.click(detail.getByRole('button', { name: 'Nghe thử' }));

  await waitFor(() => expect(played).toHaveLength(1));
  const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/relay'))!;
  expect((init.headers as Record<string, string>)['X-Voice-Key']).toBe('sk-ali-key');
  expect(JSON.parse(String(init.body))).toEqual({
    provider: 'qwen', text: expect.stringContaining('Peto'), voice: 'longwan_v2', model: 'cosyvoice-v2', region: 'cn',
  });
});

it('khóa riêng bị từ chối: Nghe thử báo lỗi, còn Companion chuyển sang giọng dự phòng', async () => {
  localStorage.setItem('peto-local-voice', '1');
  localStorage.setItem('peto-voice-source', 'openai');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ openai: { key: 'sk-wrong' } }));
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify(health()));
    if (url.endsWith('/speak')) return new Response('RIFF', { headers: { 'Content-Type': 'audio/wav' } });
    if (url.startsWith('https://api.openai.com/')) return new Response('{}', { status: 401 });
    throw new Error(`Không mong đợi ${url}`);
  });
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', messages: [
    { role: 'user', content: 'hi' },
    { role: 'assistant', content: 'Hey there.' },
  ] });
  await openCompanion();
  await screen.findByText('Hey there.');
  fireEvent.click(await screen.findByRole('button', { name: /Nghe Peto/ }));
  await waitFor(() => expect(played).toHaveLength(1));
  expect(speakBodies()).toEqual([{ text: 'Hey there.', voice: 'playful-1' }]);
  expect(await chatColumn().findByText(/Khóa OpenAI không đúng.*Đã chuyển sang giọng dự phòng: Local Voice của Peto/)).toBeTruthy();

  const settings = await openSettings();
  const detail = within(settings.getByRole('group', { name: 'OpenAI' }));
  fireEvent.click(detail.getByRole('button', { name: 'Nghe thử' }));
  expect((await detail.findByRole('alert')).textContent).toMatch(/Khóa OpenAI không đúng/);
  expect(played).toHaveLength(1);
  expect(speakBodies()).toHaveLength(1);
});

it('chưa nhập khóa và không có giọng dự phòng thì Companion chỉ nhắn chữ, chỉ đường tới Cài đặt', async () => {
  localStorage.setItem('peto-local-voice', '1');
  localStorage.setItem('peto-voice-source', 'elevenlabs');
  localStorage.setItem('peto-voice-fallback', '');
  await openCompanion();
  const column = chatColumn();
  expect(await column.findByText('Chưa nhập đủ thông tin ElevenLabs trong Cài đặt → Giọng nói. Peto chỉ nhắn chữ.')).toBeTruthy();
  expect(column.queryByRole('button', { name: 'Kiểm tra lại' })).toBeNull();
  expect(column.queryByRole('button', { name: 'Tắt tiếng' })).toBeNull();
});

it('Bắt đầu lại xóa mạch cũ sau khi xác nhận', async () => {
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', messages: [
    { role: 'user', content: 'hi' },
    { role: 'assistant', content: 'Hey there.' },
  ] });
  await openCompanion();
  await screen.findByText('Hey there.');

  fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu lại' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa và bắt đầu lại' }));
  await waitFor(() => expect(api.deleteConversation).toHaveBeenCalledWith('C1'));
  await waitFor(() => expect(screen.queryByText('Hey there.')).toBeNull());
});

it('chuyển qua lại giữa Companion và Tạo ảnh không nhân đôi tab nào', async () => {
  const consoleError = vi.spyOn(console, 'error');
  await openCompanion();
  expect(await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' })).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  await waitFor(() => expect(api.listImagineJobs).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: 'Companion' }));
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));

  await waitFor(() => expect(document.querySelectorAll('main.imagine')).toHaveLength(1));
  expect(document.querySelectorAll('main.companion')).toHaveLength(1);
  expect(api.listImagineJobs).toHaveBeenCalledTimes(1);
  expect(consoleError.mock.calls.some((args) => args.some((arg) => String(arg).includes('same key')))).toBe(false);
});
