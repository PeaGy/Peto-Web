import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { preloadLazyParts } from './lazyParts';
import App from '../src/app/App';
import * as api from '../src/shared/api/api';
import * as projectApi from '../src/features/projects/projectApi';
vi.mock('../src/features/projects/projectApi', async original => ({ ...await original<typeof import('../src/features/projects/projectApi')>(), listProjects: vi.fn() }));
import { loadHearingSettings, stopListening, setHearingPaused } from '../src/features/companion/speech/hearingEngine';
import { openMicrophone } from '../src/features/companion/speech/hearingCapture';

vi.mock('../src/shared/api/api', async (original) => ({
  ...await original<typeof import('../src/shared/api/api')>(),
  getAuthState: vi.fn(), listConversations: vi.fn(), getMessages: vi.fn(), sendMessage: vi.fn(),
  listImagineJobs: vi.fn(), getProfile: vi.fn(), getAppInfo: vi.fn(), getCompanion: vi.fn(),
  deleteConversation: vi.fn(),
  getCompanionMemory: vi.fn(),
}));

// Micro giả: jsdom không có Web Audio. Test tự đẩy âm thanh vào qua `microphone.feed`.
const microphone = vi.hoisted(() => ({
  onChunk: null as ((samples: Float32Array) => void) | null,
  stops: 0,
  feed(amplitude: number, count: number) {
    for (let index = 0; index < count; index += 1) this.onChunk?.(new Float32Array(1024).fill(amplitude));
  },
}));
vi.mock('../src/features/companion/speech/hearingCapture', () => ({
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
  static autoReady = true;
  lang = '';
  continuous = false;
  interimResults = false;
  started = false;
  onstart: (() => void) | null = null;
  aborted = false;
  onresult: ((event: unknown) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  onspeechstart: (() => void) | null = null;
  onspeechend: (() => void) | null = null;
  constructor() { FakeRecognition.instances.push(this); }
  start() { this.started = true; if (FakeRecognition.autoReady) this.onstart?.(); }
  stop() { this.aborted = true; }
  abort() { this.aborted = true; }
  say(text: string, isFinal: boolean) {
    this.onspeechstart?.();
    this.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript: text } }] });
  }
}
const lastRecognition = () => FakeRecognition.instances[FakeRecognition.instances.length - 1];

const fetchMock = vi.fn();

beforeAll(preloadLazyParts);

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(projectApi.listProjects).mockResolvedValue([]);
  vi.mocked(api.getCompanionMemory).mockResolvedValue({ available: true, enabled: true, pending: false, limit: 50, memories: [] });
  localStorage.clear();
  loadHearingSettings();
  FakeRecognition.instances = [];
  FakeRecognition.autoReady = true;
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
  setHearingPaused(false);
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('câu mới đang nói hoãn tự gửi; chốt thêm câu rồi chỉ gửi một lượt', async () => {
  localStorage.setItem('peto-hearing-autosend', '1'); loadHearingSettings();
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low'); handlers.onDelta?.('Hello.'); handlers.onDone?.();
  });
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  vi.useFakeTimers();
  act(() => lastRecognition().say('Hello Peto.', true));
  act(() => vi.advanceTimersByTime(400));
  act(() => lastRecognition().onspeechstart?.());
  act(() => vi.advanceTimersByTime(1000));
  expect(api.sendMessage).not.toHaveBeenCalled();
  act(() => lastRecognition().say('How are you?', true));
  await act(async () => { vi.advanceTimersByTime(1000); });
  expect(api.sendMessage).toHaveBeenCalledOnce();
  expect(vi.mocked(api.sendMessage).mock.calls[0][0].message).toBe('Hello Peto. How are you?');
  await act(async () => { vi.advanceTimersByTime(2000); });
  expect(api.sendMessage).toHaveBeenCalledOnce();
});

it('micro chờ tiếng kết thúc mới nghe tiếp; tắt chủ động trong lúc chờ không bật lại', async () => {
  localStorage.setItem('peto-local-voice', '1');
  const audios: { onended: (() => void) | null }[] = [];
  URL.createObjectURL = vi.fn(() => 'blob:voice'); URL.revokeObjectURL = vi.fn();
  vi.stubGlobal('Audio', class {
    onended: (() => void) | null = null; onerror = null;
    constructor() { audios.push(this); }
    play() { return Promise.resolve(); } pause() {}
  });
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify({ ok: true, voices: ['stepfun:jilingshaonv'],
      official: { allowed: true, voices: ['stepfun:jilingshaonv'], used: 0, limit: 5000 }, home: { online: false, voices: [] } }));
    if (url.endsWith('/speak')) return new Response('RIFF');
    throw new Error(`Không mong đợi ${url}`);
  });
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low', undefined, true); handlers.onDelta?.('Hello Peto. '); handlers.onDone?.();
  });
  await openCompanion();
  await screen.findByRole('button', { name: 'Tắt tiếng' });
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  act(() => lastRecognition().say('Hello', true));
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  await waitFor(() => expect(audios).toHaveLength(1));
  expect(FakeRecognition.instances).toHaveLength(1);
  expect(lastRecognition().aborted).toBe(true);
  await act(async () => audios[0].onended?.());
  await waitFor(() => expect(FakeRecognition.instances).toHaveLength(2));
  act(() => lastRecognition().say('Another message', true));
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  await waitFor(() => expect(audios).toHaveLength(2));
  fireEvent.click(screen.getByRole('button', { name: 'Tắt nghe', exact: true }));
  await act(async () => audios[1].onended?.());
  expect(FakeRecognition.instances).toHaveLength(2);
  expect(screen.getByRole('button', { name: 'Bật nghe' })).toBeTruthy();
});

it('tạm dừng hủy chép bằng khóa; chữ cũ về sau nghe tiếp không vào bản nháp mới', async () => {
  localStorage.setItem('peto-hearing-source', 'groq');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ groq: { key: 'gsk_user' } })); loadHearingSettings();
  let finishOld!: (response: Response) => void, oldSignal!: AbortSignal;
  fetchMock.mockImplementationOnce((_url, init) => { oldSignal = init.signal;
    return new Promise<Response>(resolve => { finishOld = resolve; });
  }).mockResolvedValueOnce(new Response(JSON.stringify({ text: 'Fresh words' })));
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(microphone.onChunk).not.toBeNull());
  act(() => { microphone.feed(0.2, 8); microphone.feed(0, 14); });
  await waitFor(() => expect(finishOld).toBeTypeOf('function'));
  act(() => { setHearingPaused(true); setHearingPaused(false); });
  expect(oldSignal.aborted).toBe(true);
  await act(async () => finishOld(new Response(JSON.stringify({ text: 'Old words' }))));
  expect(composer().value).toBe('');
  act(() => { microphone.feed(0.2, 8); microphone.feed(0, 14); });
  await waitFor(() => expect(composer().value).toBe('Fresh words'));
});

async function openCompanion() {
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Companion' }));
  await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
}

const composer = () => screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }) as HTMLTextAreaElement;
const micPanel = () => within(screen.getByRole('dialog', { name: 'Micro' }));

/** Ô tài khoản → Cài đặt trong menu → mục Giọng nói. */
async function openVoiceSettings() {
  fireEvent.click(await screen.findByRole('button', { name: /Tài khoản · Demo/ }));
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Cài đặt' }));
  const dialog = screen.getByRole('dialog', { name: 'Cài đặt' });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Giọng nói' }));
  await within(dialog).findByRole('tab', { name: 'Peto nói' });
  return dialog;
}

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
  const settings = within(await openVoiceSettings());
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
  const settings = within(await openVoiceSettings());
  fireEvent.click(settings.getByRole('tab', { name: 'Peto nghe' }));
  fireEvent.click(settings.getByRole('button', { name: 'Bắt đầu nghe thử' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  act(() => lastRecognition().say('Testing one two', true));
  expect(settings.getByText('“Testing one two”')).toBeTruthy();

  fireEvent.click(settings.getByRole('button', { name: 'Đóng cài đặt' }));
  await waitFor(() => expect(lastRecognition().aborted).toBe(true));
});

it('bảng Micro mở thẳng Cài đặt ở mục Giọng nói, thẻ Peto nghe', async () => {
  await openCompanion();
  // Mục Giọng nói đã mở một lần (đang ở thẻ Peto nói) nên còn trong hộp: đường dẫn phải đổi được sang thẻ Peto nghe.
  fireEvent.click(within(await openVoiceSettings()).getByRole('button', { name: 'Đóng cài đặt' }));
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  fireEvent.click(await micPanel().findByRole('button', { name: 'đổi trong Cài đặt' }));
  const settings = within(screen.getByRole('dialog', { name: 'Cài đặt' }));
  expect(settings.getByRole('heading', { name: 'Giọng nói' })).toBeTruthy();
  expect(settings.getByRole('button', { name: 'Giọng nói' }).getAttribute('aria-current')).toBe('page');
  expect((await settings.findByRole('tab', { name: 'Peto nghe' })).getAttribute('aria-selected')).toBe('true');
  expect(settings.getByRole('button', { name: 'Có sẵn trong trình duyệt' }).getAttribute('aria-pressed')).toBe('true');
});

it('nguồn trình duyệt khởi động trước thanh đo, dùng micro mặc định dù còn lưu micro USB', async () => {
  localStorage.setItem('peto-hearing-device', 'mic-usb');
  loadHearingSettings();
  FakeRecognition.autoReady = false;
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  expect(micPanel().getByText('Đang kết nối nguồn nghe…')).toBeTruthy();
  expect(openMicrophone).not.toHaveBeenCalled();
  act(() => lastRecognition().onstart?.());
  expect(micPanel().getByText('Đang nghe')).toBeTruthy();
  expect(openMicrophone).toHaveBeenCalledWith('', expect.any(Function));
  expect(micPanel().getByRole('combobox', { name: 'Micro' })).toHaveProperty('disabled', true);
  act(() => lastRecognition().say('Hello Peto', true));
  expect(composer().value).toBe('Hello Peto');
  expect(localStorage.getItem('peto-hearing-device')).toBe('mic-usb');
});

it('tắt micro chủ động giữ chữ dở để sửa và không tự gửi; kết quả đến muộn bị bỏ', async () => {
  localStorage.setItem('peto-hearing-autosend', '1');
  loadHearingSettings();
  await openCompanion();
  fireEvent.change(composer(), { target: { value: 'Existing draft.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  const first = lastRecognition();
  act(() => first.say('Can you hear', false));
  fireEvent.keyDown(composer(), { key: 'Enter' });
  expect(api.sendMessage).not.toHaveBeenCalled();
  fireEvent.click(screen.getAllByRole('button', { name: 'Tắt nghe' })[0]);
  expect(composer().value).toBe('Existing draft. Can you hear');
  expect(composer().readOnly).toBe(false);
  act(() => first.say('Can you hear me?', true));
  await new Promise(resolve => setTimeout(resolve, 900));
  expect(composer().value).toBe('Existing draft. Can you hear');
  expect(api.sendMessage).not.toHaveBeenCalled();
});

it('có âm lượng nhưng không có chữ thì báo rõ, dịch vụ hồi phục vẫn chép vào ô nhắn', async () => {
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(microphone.onChunk).not.toBeNull());
  vi.useFakeTimers();
  act(() => {
    microphone.feed(0.2, 8);
    vi.advanceTimersByTime(8000);
  });
  expect(screen.getByRole('alert').textContent).toMatch(/có âm thanh.*chưa trả chữ/);
  expect(screen.getAllByRole('button', { name: 'Tắt nghe' }).length).toBeGreaterThan(0);
  act(() => lastRecognition().say('It works now', true));
  expect(composer().value).toBe('It works now');
  expect(screen.queryByRole('alert')).toBeNull();
});

it('mất phiên giữa câu giữ chữ chưa chốt nhưng không tự gửi', async () => {
  localStorage.setItem('peto-hearing-autosend', '1');
  loadHearingSettings();
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  act(() => lastRecognition().say('Can you hear', false));
  act(() => lastRecognition().onend?.());
  expect(composer().value).toBe('Can you hear');
  expect(composer().readOnly).toBe(false);
  expect(screen.getByRole('alert').textContent).toMatch(/câu chưa được chốt/);
  await waitFor(() => expect(FakeRecognition.instances.length).toBeGreaterThan(1));
  act(() => lastRecognition().say('me now?', true));
  await new Promise(resolve => setTimeout(resolve, 900));
  expect(composer().value).toBe('Can you hear me now?');
  expect(api.sendMessage).not.toHaveBeenCalled();
});

it('thanh đo không mở được vẫn giữ bộ nhận giọng và nhận chữ', async () => {
  vi.mocked(openMicrophone).mockRejectedValueOnce(new Error('Không mở được thanh đo'));
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  expect((await screen.findByRole('alert')).textContent).toMatch(/Bộ nhận giọng vẫn nghe/);
  act(() => lastRecognition().say('Hello from the default microphone', true));
  expect(composer().value).toBe('Hello from the default microphone');
  expect(screen.queryByRole('alert')).toBeNull();
});
