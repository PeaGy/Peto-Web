import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from '../src/App';
import * as api from '../src/api';
import { loadHearingSettings, stopListening } from '../src/hearingEngine';

vi.mock('../src/api', async (original) => ({
  ...await original<typeof import('../src/api')>(),
  getAuthState: vi.fn(), listConversations: vi.fn(), getMessages: vi.fn(), sendMessage: vi.fn(),
  listImagineJobs: vi.fn(), getProfile: vi.fn(), getAppInfo: vi.fn(), getCompanion: vi.fn(),
  deleteConversation: vi.fn(),
}));

// Micro giả: jsdom không có Web Audio. Test tự đẩy âm thanh vào qua `microphone.feed`.
const microphone = vi.hoisted(() => ({
  onChunk: null as ((samples: Float32Array) => void) | null,
  stops: 0,
  feed(amplitude: number, count: number) {
    for (let index = 0; index < count; index += 1) this.onChunk?.(new Float32Array(1024).fill(amplitude));
  },
}));
vi.mock('../src/hearingCapture', () => ({
  captureSupported: () => true,
  openMicrophone: vi.fn(async (_deviceId: string, onChunk: (samples: Float32Array) => void) => {
    microphone.onChunk = onChunk;
    return { sampleRate: 16000, stop: () => { microphone.stops += 1; microphone.onChunk = null; } };
  }),
  listMicrophones: vi.fn(async () => [{ id: 'mic-usb', label: 'Micro USB' }]),
}));

/** Nhận giọng giả của trình duyệt: test tự "nói" qua `say`. */
class FakeRecognition {
  static instances: FakeRecognition[] = [];
  lang = '';
  continuous = false;
  interimResults = false;
  started = false;
  aborted = false;
  onresult: ((event: unknown) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  onspeechstart: (() => void) | null = null;
  onspeechend: (() => void) | null = null;
  constructor() { FakeRecognition.instances.push(this); }
  start() { this.started = true; }
  stop() { this.aborted = true; }
  abort() { this.aborted = true; }
  say(text: string, isFinal: boolean) {
    this.onspeechstart?.();
    this.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript: text } }] });
  }
}
const lastRecognition = () => FakeRecognition.instances[FakeRecognition.instances.length - 1];

const fetchMock = vi.fn();

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  loadHearingSettings();
  FakeRecognition.instances = [];
  microphone.onChunk = null;
  microphone.stops = 0;
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
  Element.prototype.scrollTo = vi.fn();
  fetchMock.mockImplementation(async (url: string) => { throw new Error(`Không mong đợi ${url}`); });
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('SpeechRecognition', FakeRecognition);
});

afterEach(() => {
  stopListening();
  vi.unstubAllGlobals();
});

async function openCompanion() {
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Companion' }));
  await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
}

const composer = () => screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }) as HTMLTextAreaElement;
const micPanel = () => within(screen.getByRole('dialog', { name: 'Micro' }));

it('bấm micro thì nghe bằng trình duyệt: chữ hiện dần rồi vào ô nhắn, không tự gửi; bấm lại thì tắt', async () => {
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  const recognition = lastRecognition();
  expect(recognition).toMatchObject({ lang: 'en-US', continuous: true, interimResults: true });
  expect(await micPanel().findByText('Đang nghe')).toBeTruthy();

  act(() => recognition.say('Can you', false));
  expect(composer().value).toBe('Can you');
  expect(composer().readOnly).toBe(true);
  expect(micPanel().getByText('Bạn đang nói')).toBeTruthy();

  act(() => recognition.say('Can you hear me?', true));
  expect(composer().value).toBe('Can you hear me?');
  expect(composer().readOnly).toBe(false);
  await new Promise((resolve) => setTimeout(resolve, 900));
  expect(api.sendMessage).not.toHaveBeenCalled();

  fireEvent.click(screen.getAllByRole('button', { name: 'Tắt nghe' })[0]);
  expect(recognition.aborted).toBe(true);
  expect(microphone.stops).toBe(1);
  expect(screen.queryByRole('dialog', { name: 'Micro' })).toBeNull();
  expect(composer().value).toBe('Can you hear me?');
});

it('bật Tự gửi: nói xong một lúc là gửi; Peto đang trả lời thì tạm không nghe, trả lời xong nghe tiếp', async () => {
  localStorage.setItem('peto-hearing-autosend', '1');
  loadHearingSettings();
  let finish: () => void = () => {};
  vi.mocked(api.sendMessage).mockImplementation((_payload, handlers) => new Promise((resolve) => {
    handlers.onMeta?.('C1', 'low');
    handlers.onDelta?.('Loud and clear!');
    finish = () => { handlers.onDone?.(); resolve(); };
  }));
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  const first = lastRecognition();

  act(() => first.say('Can you hear me?', true));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalled());
  expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({ message: 'Can you hear me?', mode: 'companion' });
  // Đang trả lời: bộ nghe dừng, nút micro báo tạm dừng.
  await waitFor(() => expect(first.aborted).toBe(true));
  expect(composer().placeholder).toMatch(/tạm không nghe/);

  await act(async () => finish());
  await waitFor(() => expect(FakeRecognition.instances.length).toBe(2));
  expect(lastRecognition().started).toBe(true);
  expect(await screen.findByText('Loud and clear!')).toBeTruthy();
});

it('tự gõ thì không tự gửi, kể cả đang bật Tự gửi', async () => {
  localStorage.setItem('peto-hearing-autosend', '1');
  loadHearingSettings();
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  fireEvent.change(composer(), { target: { value: 'typed by hand' } });
  await new Promise((resolve) => setTimeout(resolve, 900));
  expect(api.sendMessage).not.toHaveBeenCalled();
});

it('trình duyệt không có tính năng nghe (Firefox) thì báo và chỉ cách khác', async () => {
  vi.stubGlobal('SpeechRecognition', undefined);
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  expect((await screen.findByRole('alert')).textContent).toMatch(/chưa có tính năng nghe.*Chrome, Edge hoặc Safari/);
  expect(screen.getByRole('button', { name: 'Bật nghe' })).toBeTruthy();
});

it('nguồn Groq: tự cắt câu theo khoảng im lặng, gửi WAV đi chép, chữ vào ô nhắn', async () => {
  localStorage.setItem('peto-hearing-source', 'groq');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ groq: { key: 'gsk_user' } }));
  loadHearingSettings();
  fetchMock.mockImplementation(async (url: string) => {
    if (url === 'https://api.groq.com/openai/v1/audio/transcriptions') return new Response(JSON.stringify({ text: 'Hello Peto' }));
    throw new Error(`Không mong đợi ${url}`);
  });
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(microphone.onChunk).not.toBeNull());
  act(() => microphone.feed(0.2, 8));
  expect(micPanel().getByText('Bạn đang nói')).toBeTruthy();
  act(() => microphone.feed(0, 14));

  await waitFor(() => expect(composer().value).toBe('Hello Peto'));
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect((init.headers as Record<string, string>).Authorization).toBe('Bearer gsk_user');
  expect((init.body as FormData).get('language')).toBe('en');
  expect(FakeRecognition.instances).toHaveLength(0);
});

it('khóa Groq sai thì báo lỗi và thôi nghe', async () => {
  localStorage.setItem('peto-hearing-source', 'groq');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ groq: { key: 'gsk_wrong' } }));
  loadHearingSettings();
  fetchMock.mockImplementation(async () => new Response('{}', { status: 401 }));
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(microphone.onChunk).not.toBeNull());
  act(() => {
    microphone.feed(0.2, 8);
    microphone.feed(0, 14);
  });
  expect((await screen.findByRole('alert')).textContent).toMatch(/Khóa Groq không đúng/);
  expect(screen.getByRole('button', { name: 'Bật nghe' })).toBeTruthy();
  expect(microphone.stops).toBe(1);
});

it('Cài đặt → Peto nghe: khóa Azure dùng chung với phần Peto nói, nhập khóa Groq không làm mất khóa khác', async () => {
  localStorage.setItem('peto-local-voice', '1');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ azure: { key: 'az-key', region: 'eastus' } }));
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/api/voice/health')) return new Response(JSON.stringify({ ok: false, voices: [] }));
    throw new Error(`Không mong đợi ${url}`);
  });
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: /Cài đặt · Demo/ }));
  const settings = within(screen.getByRole('dialog', { name: 'Cài đặt' }));
  fireEvent.click(settings.getByRole('tab', { name: 'Peto nghe' }));
  expect(settings.getByRole('tab', { name: 'Peto nghe' }).getAttribute('aria-selected')).toBe('true');
  expect(settings.queryByRole('switch', { name: 'Bật giọng nói' })).toBeNull();

  const azure = settings.getByRole('button', { name: 'Azure Speech' });
  expect(azure.textContent).toContain('Đã có khóa');
  fireEvent.click(settings.getByRole('button', { name: 'Groq' }));
  const detail = within(settings.getByRole('group', { name: 'Groq' }));
  fireEvent.change(detail.getByLabelText('Khóa API Groq'), { target: { value: 'gsk_new' } });
  const stored = JSON.parse(localStorage.getItem('peto-voice-keys') ?? '{}');
  expect(stored).toEqual({ azure: { key: 'az-key', region: 'eastus' }, groq: { key: 'gsk_new' } });
  expect(localStorage.getItem('peto-hearing-source')).toBe('groq');

  fireEvent.click(settings.getByRole('tab', { name: 'Peto nói' }));
  expect(settings.getByRole('button', { name: 'Azure Speech' }).textContent).toContain('Đã lưu khóa');
});

it('Nghe thử trong Cài đặt: chữ nghe được hiện trong khung, không vào ô nhắn; đóng Cài đặt thì thôi nghe', async () => {
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: /Cài đặt · Demo/ }));
  const dialog = screen.getByRole('dialog', { name: 'Cài đặt' });
  const settings = within(dialog);
  fireEvent.click(settings.getByRole('tab', { name: 'Peto nghe' }));
  fireEvent.click(settings.getByRole('button', { name: 'Bắt đầu nghe thử' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  act(() => lastRecognition().say('Testing one two', true));
  expect(settings.getByText('“Testing one two”')).toBeTruthy();

  fireEvent.click(settings.getByRole('button', { name: 'Đóng cài đặt' }));
  await waitFor(() => expect(lastRecognition().aborted).toBe(true));
});

it('bảng Micro mở thẳng Cài đặt ở thẻ Peto nghe', async () => {
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  fireEvent.click(await micPanel().findByRole('button', { name: 'đổi trong Cài đặt' }));
  const settings = within(screen.getByRole('dialog', { name: 'Cài đặt' }));
  expect(settings.getByRole('tab', { name: 'Peto nghe' }).getAttribute('aria-selected')).toBe('true');
  expect(settings.getByRole('button', { name: 'Có sẵn trong trình duyệt' }).getAttribute('aria-pressed')).toBe('true');
});
