import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    if (url.endsWith('/health')) return new Response(JSON.stringify({ ok: true, voices: ['playful-1', 'gentle-2'] }));
    if (url.endsWith('/speak')) return new Response('RIFF', { headers: { 'Content-Type': 'audio/wav' } });
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

const localCalls = () => fetchMock.mock.calls.filter(([url]) => String(url).startsWith('http://127.0.0.1'));

async function openCompanion() {
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Companion' }));
}

async function sendInCompanion(text: string) {
  fireEvent.change(screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi' }));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalled());
}

it('mặc định không gọi tới 127.0.0.1 cho tới khi bật giọng nói', async () => {
  await openCompanion();
  expect(await screen.findByText(/Chào Peto một câu đi/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Bật giọng nói trên máy này' })).toBeTruthy();
  expect(window.location.hash).toBe('#companion');
  expect(localCalls()).toHaveLength(0);

  fireEvent.click(screen.getByRole('button', { name: 'Bật giọng nói trên máy này' }));
  expect(await screen.findByText(/Giọng nói đã sẵn sàng/)).toBeTruthy();
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
  await screen.findByText(/Giọng nói đã sẵn sàng/);

  await sendInCompanion('hi');
  expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({
    message: 'hi', conversationId: null, mode: 'companion', effort: 'low', webSearch: 'off',
  });
  await waitFor(() => expect(played).toHaveLength(1));
  const speakCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/speak'));
  expect(JSON.parse(String(speakCall?.[1]?.body))).toEqual({ text: 'Hey! Good to see you.', voice: 'gentle-2' });
});

it('tắt tiếng thì Peto không tự nói, bấm Nghe vẫn nghe lại được', async () => {
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
  await screen.findByText(/Giọng nói đã sẵn sàng/);
  expect(screen.getByRole('button', { name: 'Tắt tiếng' }).getAttribute('aria-pressed')).toBe('true');

  await sendInCompanion('ok');
  expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({ conversationId: 'C1' });
  await screen.findByText('Sure thing.');
  await waitFor(() => expect(screen.getAllByRole('button', { name: /Nghe Peto/ })).toHaveLength(2));
  expect(played).toHaveLength(0);

  fireEvent.click(screen.getAllByRole('button', { name: /Nghe Peto/ })[0]);
  await waitFor(() => expect(played).toHaveLength(1));
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
  expect(await screen.findByText(/Chào Peto một câu đi/)).toBeTruthy();
  expect(screen.queryByText('Hey there.')).toBeNull();
});
