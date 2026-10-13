import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useEffect } from 'react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { preloadLazyParts } from './lazyParts';
import App from '../src/app/App';
import * as api from '../src/shared/api/api';
import * as projectApi from '../src/features/projects/projectApi';
vi.mock('../src/features/projects/projectApi', async original => ({ ...await original<typeof import('../src/features/projects/projectApi')>(), listProjects: vi.fn() }));
import { loadHearingSettings, stopListening, setHearingPaused, getHearingState, setHearingSetting } from '../src/features/companion/speech/hearingEngine';
import { openMicrophone } from '../src/features/companion/speech/hearingCapture';
import { clearCompanionTimings, getCompanionTimings } from '../src/features/companion/speech/companionTiming';
vi.mock('../src/features/companion/prepareCompanionImage', async original => ({
  ...await original<typeof import('../src/features/companion/prepareCompanionImage')>(),
  prepareCompanionImage: (file: File) => Promise.resolve(file),
}));

vi.mock('../src/shared/api/api', async (original) => ({
  ...await original<typeof import('../src/shared/api/api')>(),
  getAuthState: vi.fn(), listConversations: vi.fn(), getMessages: vi.fn(), sendMessage: vi.fn(),
  listImagineJobs: vi.fn(), getProfile: vi.fn(), getAppInfo: vi.fn(), getCompanion: vi.fn(),
  deleteConversation: vi.fn(),
  getCompanionMemory: vi.fn(),
}));

// jsdom không dựng được Live2D thật; bộ kiểm tra micro vẫn phải chờ sân khấu sẵn sàng.
// Việc vẽ nhân vật trước khi mở ô nhắn được kiểm tra riêng trong Live2DStage và trên trình duyệt.
vi.mock('../src/features/companion/characters/Live2DStage', () => ({
  default: ({ onStatusChange }: { onStatusChange?: (status: 'loading' | 'ready' | 'error') => void }) => {
    useEffect(() => { onStatusChange?.('ready'); }, [onStatusChange]);
    return null;
  },
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
  /** Giữ để nói kết thúc có chốt bằng stop(); test tự gọi onresult/onend như trình duyệt. */
  stopRequested = false;
  stop() { this.stopRequested = true; }
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
  clearCompanionTimings();
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
    providers: { discord: true, google: true, github: true },
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

it.each(['playing', 'loading', 'finished'])('nói chen khi tiếng đang %s dừng tiếng và lượt nhưng giữ bộ nghe cùng bản nháp', async phase => {
  localStorage.setItem('peto-local-voice', '1');
  setHearingSetting('bargeIn', true);
  const audios: { pause: ReturnType<typeof vi.fn>; ready(): void }[] = [];
  URL.createObjectURL = vi.fn(() => 'blob:voice'); URL.revokeObjectURL = vi.fn();
  vi.stubGlobal('Audio', class {
    onended = null; onerror = null; pause = vi.fn(); ready!: () => void;
    constructor() { audios.push(this); }
    play() { return phase !== 'loading' ? Promise.resolve() : new Promise<void>(resolve => { this.ready = resolve; }); }
  });
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify({ ok: true, voices: ['stepfun:jilingshaonv'],
      official: { allowed: true, voices: ['stepfun:jilingshaonv'], used: 0, limit: 5000 }, home: { online: false, voices: [] } }));
    if (url.endsWith('/speak')) return new Response('RIFF');
    throw new Error(`Không mong đợi ${url}`);
  });
  let signal!: AbortSignal, old!: Parameters<typeof api.sendMessage>[1];
  vi.mocked(api.sendMessage).mockImplementation((_payload, handlers, abort) => new Promise(resolve => {
    signal = abort!; old = handlers;
    handlers.onMeta?.('C1', 'low', undefined, true); handlers.onDelta?.('Hello there. ');
    if (phase === 'finished') { handlers.onDone?.(); resolve(); }
    signal.addEventListener('abort', () => resolve(), { once: true });
  }));
  await openCompanion(); await screen.findByRole('button', { name: 'Tắt tiếng' });
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  act(() => lastRecognition().say('Hello', true));
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  await waitFor(() => expect(audios).toHaveLength(1));
  const recognition = lastRecognition();
  expect(recognition.aborted).toBe(false);
  fireEvent.change(composer(), { target: { value: 'Actually,' } });
  // Thanh âm lượng không tự ngắt giọng; nguồn trình duyệt cần sự kiện lời nói hoặc chữ.
  act(() => microphone.feed(0.2, 8));
  expect(signal.aborted).toBe(false);
  await act(async () => recognition.say('wait a moment', false));
  // Đã nhận hết chữ thì chỉ còn tiếng cần dừng, không còn yêu cầu chat để hủy.
  expect(signal.aborted).toBe(phase !== 'finished'); expect(audios[0].pause).toHaveBeenCalled();
  expect(recognition.aborted).toBe(false); expect(FakeRecognition.instances).toHaveLength(1);
  expect(composer().value).toBe('Actually, wait a moment');
  if (phase === 'loading') await act(async () => audios[0].ready());
  act(() => { old.onDelta?.('Late reply.'); old.onEmotion?.('angry', 0); old.onDone?.(); old.onError?.('Lỗi cũ'); });
  expect(screen.queryByText(/Late reply/)).toBeNull(); expect(screen.queryByText('Lỗi cũ')).toBeNull();
  act(() => recognition.say('wait a moment please', true));
  expect(composer().value).toBe('Actually, wait a moment please');
  expect(api.sendMessage).toHaveBeenCalledOnce();
  expect(getHearingState()).toMatchObject({ listening: true, testing: false, phase: 'waiting', autoSend: false });
});

it('nói chen khi chỉ đang viết nhận chữ cả khi trình duyệt không báo speechstart; Tự gửi chỉ chờ câu chốt', async () => {
  setHearingSetting('bargeIn', true); setHearingSetting('autoSend', true);
  let signal!: AbortSignal;
  vi.mocked(api.sendMessage).mockImplementationOnce((_payload, handlers, abort) => new Promise(resolve => {
    signal = abort!; handlers.onMeta?.('C1', 'low'); handlers.onDelta?.('Thinking.');
    signal.addEventListener('abort', () => resolve(), { once: true });
  })).mockImplementationOnce(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low'); handlers.onDelta?.('New reply.'); handlers.onDone?.();
  });
  await openCompanion(); fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  fireEvent.change(composer(), { target: { value: 'Hi' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  vi.useFakeTimers();
  const recognition = lastRecognition();
  await act(async () => recognition.onresult?.({ resultIndex: 0, results: [{ isFinal: false, 0: { transcript: 'Wait please' } }] }));
  expect(signal.aborted).toBe(true);
  await act(async () => { vi.advanceTimersByTime(1200); });
  expect(api.sendMessage).toHaveBeenCalledOnce();
  act(() => recognition.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: 'Wait please' } }] }));
  await act(async () => { vi.advanceTimersByTime(1000); });
  expect(api.sendMessage).toHaveBeenCalledTimes(2);
  expect(vi.mocked(api.sendMessage).mock.calls[1][0].message).toBe('Wait please');
  expect(FakeRecognition.instances).toHaveLength(1);
});

it('phiên trình duyệt tự mở lại sau câu dở vẫn nhận được lần nói chen tiếp theo', async () => {
  setHearingSetting('bargeIn', true);
  let signal!: AbortSignal;
  vi.mocked(api.sendMessage).mockImplementation((_payload, handlers, abort) => new Promise(resolve => {
    signal = abort!; handlers.onMeta?.('C1', 'low'); handlers.onDelta?.('Let me explain.');
    signal.addEventListener('abort', () => resolve(), { once: true });
  }));
  await openCompanion(); fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  act(() => { lastRecognition().say('Hello', false); lastRecognition().onend?.(); });
  await waitFor(() => expect(FakeRecognition.instances).toHaveLength(2));
  expect(composer().value).toBe('Hello');
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  expect(signal.aborted).toBe(false);
  await act(async () => lastRecognition().say('Actually, wait', false));
  expect(signal.aborted).toBe(true);
  expect(composer().value).toBe('Actually, wait');
  expect(lastRecognition().aborted).toBe(false);
});

it('nguồn dùng khóa bỏ tiếng cộp ngắn, lời đủ dài ngắt lượt và vẫn chép được âm đầu', async () => {
  setHearingSetting('bargeIn', true); setHearingSetting('source', 'groq');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ groq: { key: 'gsk_user' } }));
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ text: 'Wait, I meant something else.' })));
  let signal!: AbortSignal;
  vi.mocked(api.sendMessage).mockImplementation((_payload, handlers, abort) => new Promise(resolve => {
    signal = abort!; handlers.onMeta?.('C1', 'low'); handlers.onDelta?.('Let me explain.');
    signal.addEventListener('abort', () => resolve(), { once: true });
  }));
  await openCompanion(); fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(microphone.onChunk).not.toBeNull());
  fireEvent.change(composer(), { target: { value: 'Explain' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  act(() => { microphone.feed(0.2, 3); microphone.feed(0, 16); });
  expect(signal.aborted).toBe(false); expect(fetchMock).not.toHaveBeenCalled();
  await act(async () => microphone.feed(0.2, 5));
  expect(signal.aborted).toBe(true); expect(microphone.stops).toBe(0);
  await act(async () => microphone.feed(0, 14));
  await waitFor(() => expect(composer().value).toBe('Wait, I meant something else.'));
  expect(fetchMock).toHaveBeenCalledOnce();
  expect(getHearingState()).toMatchObject({ listening: true, phase: 'waiting', autoSend: false });
});

it('nói chen mặc định tắt; bật/tắt trong Cài đặt giữ lựa chọn tạm không nghe và không mở micro', async () => {
  await openCompanion();
  const settings = within(await openHearingSettings());
  const bargeIn = await settings.findByRole('switch', { name: 'Cho phép nói chen' });
  const pause = settings.getByRole('switch', { name: 'Tạm không nghe khi Peto đang nói' });
  expect(bargeIn).toHaveProperty('checked', false); expect(pause).toHaveProperty('checked', true);
  fireEvent.click(bargeIn);
  expect(pause).toHaveProperty('disabled', true); expect(localStorage.getItem('peto-hearing-barge-in')).toBe('1');
  expect(getHearingState()).toMatchObject({ listening: false, autoSend: false, pauseWhileSpeaking: true });
  fireEvent.click(bargeIn);
  expect(pause).toHaveProperty('disabled', false); expect(pause).toHaveProperty('checked', true);
  expect(FakeRecognition.instances).toHaveLength(0);
});

it('Nghe thử và lời tới muộn từ phiên micro cũ không ngắt câu trả lời', async () => {
  setHearingSetting('bargeIn', true);
  let signal!: AbortSignal;
  vi.mocked(api.sendMessage).mockImplementation((_payload, handlers, abort) => new Promise(resolve => {
    signal = abort!; handlers.onMeta?.('C1', 'low'); handlers.onDelta?.('Let me explain.');
    signal.addEventListener('abort', () => resolve(), { once: true });
  }));
  await openCompanion(); fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  const old = lastRecognition();
  fireEvent.change(composer(), { target: { value: 'Hi' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  // Mở trang cài đặt là rời sân khấu: micro của Companion tắt, nhưng câu trả lời vẫn chạy tiếp.
  const settings = within(await openHearingSettings());
  fireEvent.click(await settings.findByRole('button', { name: 'Bắt đầu nghe thử' }));
  act(() => { old.say('Old words', true); lastRecognition().say('Testing microphone', true); });
  expect(signal.aborted).toBe(false);
  expect(settings.getByText('“Testing microphone”')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Companion', exact: true }));
  expect(((await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' })) as HTMLTextAreaElement).value).toBe('');
  expect(signal.aborted).toBe(false);
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

it('lượt đo dùng mốc bộ nghe thật; gõ sửa không gán thời gian micro cũ cho lời nhắn mới', async () => {
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low'); handlers.onDelta?.('Hello.'); handlers.onDone?.();
  });
  await openCompanion(); fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  act(() => {
    lastRecognition().onspeechstart?.(); lastRecognition().onspeechend?.();
    lastRecognition().onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: 'Hello Peto' } }] });
  });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalledOnce());
  const record = getCompanionTimings()[0];
  expect(record).toMatchObject({ input: 'voice', hearingSource: 'browser', status: 'text-only' });
  expect(record.hearing!.endedAt).toBeLessThanOrEqual(record.hearing!.finalizedAt);
  expect(record.hearing!.finalizedAt).toBeLessThanOrEqual(record.sentAt);
  await waitFor(() => expect(lastRecognition()?.aborted).toBe(false));
  act(() => lastRecognition().say('Second message', true));
  fireEvent.change(composer(), { target: { value: 'Edited message' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi', exact: true }));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalledTimes(2));
  expect(getCompanionTimings()[0]).toMatchObject({ input: 'text' });
  expect(getCompanionTimings()[0].hearing).toBeUndefined();
});

/** Trang Nghe của Cài đặt Companion, như người dùng: bánh răng ở đầu cột chat → Mô-đun → Nghe. */
async function openHearingSettings() {
  if (!screen.queryByRole('region', { name: 'Trò chuyện trong Companion' })) {
    fireEvent.click(await screen.findByRole('button', { name: 'Companion', exact: true }));
  }
  const column = within(await screen.findByRole('region', { name: 'Trò chuyện trong Companion' }));
  fireEvent.click(await column.findByRole('button', { name: 'Cài đặt Companion' }));
  const page = await screen.findByRole('main', { name: 'Cài đặt' });
  fireEvent.click(within(page).getByRole('button', { name: /^Mô-đun/ }));
  fireEvent.click(await within(page).findByRole('button', { name: /^Nghe/ }));
  await within(page).findByRole('heading', { level: 1, name: 'Nghe' });
  return page;
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

it('ảnh chờ gửi đi cùng câu hỏi bằng micro; chọn ảnh không tự gửi, chưa chốt chữ cũng không gửi', async () => {
  setHearingSetting('autoSend', true);
  URL.createObjectURL = vi.fn(() => 'blob:image'); URL.revokeObjectURL = vi.fn();
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low'); handlers.onDelta?.('That looks lovely.'); handlers.onDone?.();
  });
  await openCompanion();
  fireEvent.change(screen.getByLabelText('Chọn ảnh cho Companion'), { target: { files: [new File(['PNG'], 'image.png', { type: 'image/png' })] } });
  await screen.findByAltText('Ảnh chờ gửi: image.png');
  expect(api.sendMessage).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  act(() => lastRecognition().say('What is', false));
  fireEvent.keyDown(composer(), { key: 'Enter' });
  expect(api.sendMessage).not.toHaveBeenCalled();
  act(() => lastRecognition().say('What is in this image?', true));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalledOnce(), { timeout: 2000 });
  expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({ message: 'What is in this image?', attachments: [{ name: 'image.png', data: btoa('PNG') }] });
  expect(screen.queryByAltText('Ảnh chờ gửi: image.png')).toBeNull();
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

it('Cài đặt Companion → Nghe: khóa Azure dùng chung với trang Giọng nói, nhập khóa Groq không làm mất khóa khác', async () => {
  localStorage.setItem('peto-local-voice', '1');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ azure: { key: 'az-key', region: 'eastus' } }));
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/api/voice/health')) return new Response(JSON.stringify({ ok: false, voices: [] }));
    throw new Error(`Không mong đợi ${url}`);
  });
  render(<App />);
  const settings = within(await openHearingSettings());
  expect(settings.queryByRole('switch', { name: 'Bật giọng nói' })).toBeNull();

  const azure = settings.getByRole('button', { name: 'Azure Speech' });
  expect(azure.textContent).toContain('Đã có khóa');
  fireEvent.click(settings.getByRole('button', { name: 'Groq' }));
  const detail = within(settings.getByRole('group', { name: 'Groq' }));
  fireEvent.change(detail.getByLabelText('Khóa API Groq'), { target: { value: 'gsk_new' } });
  const stored = JSON.parse(localStorage.getItem('peto-voice-keys') ?? '{}');
  expect(stored).toEqual({ azure: { key: 'az-key', region: 'eastus' }, groq: { key: 'gsk_new' } });
  expect(localStorage.getItem('peto-hearing-source')).toBe('groq');

  fireEvent.click(settings.getByRole('button', { name: 'Quay lại Mô-đun' }));
  fireEvent.click(await settings.findByRole('button', { name: /^Giọng nói/ }));
  expect((await settings.findByRole('button', { name: 'Azure Speech' })).textContent).toContain('Đã lưu khóa');
});

it('Nghe thử trong Cài đặt Companion: chữ nghe được hiện trong khung, không vào ô nhắn; rời trang thì thôi nghe', async () => {
  render(<App />);
  const settings = within(await openHearingSettings());
  fireEvent.click(settings.getByRole('button', { name: 'Bắt đầu nghe thử' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  act(() => lastRecognition().say('Testing one two', true));
  expect(settings.getByText('“Testing one two”')).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'Companion', exact: true }));
  await waitFor(() => expect(lastRecognition().aborted).toBe(true));
  expect((await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }) as HTMLTextAreaElement).value).toBe('');
});

it('bảng Micro mở thẳng trang Nghe của Cài đặt Companion, rời sân khấu thì thôi nghe', async () => {
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  fireEvent.click(await micPanel().findByRole('button', { name: 'đổi trong Cài đặt' }));
  const settings = within(await screen.findByRole('main', { name: 'Nghe' }));
  expect(window.location.pathname).toBe('/companion/settings/modules/hearing');
  expect(settings.getByText('Mô-đun')).toBeTruthy();
  expect(settings.getByRole('button', { name: 'Có sẵn trong trình duyệt' }).getAttribute('aria-pressed')).toBe('true');
  expect(getHearingState().listening).toBe(false);
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
  expect(openMicrophone).toHaveBeenCalledWith('', expect.any(Function), expect.any(Function));
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

/* ---------- Giữ để nói (biến thể "Bật rồi giữ", chủ web chọn ngày 13/10/2026) ---------- */
const pause = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
const space = { key: ' ', code: 'Space' };
const holdStrip = () => document.querySelector('.hearing-strip-title')?.textContent ?? '';

it('Giữ để nói: bật micro chưa mở micro; giữ Space ngoài ô nhắn thì nghe, thả ra thì trình duyệt chốt câu vào ô nhắn', async () => {
  setHearingSetting('mode', 'hold');
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật Giữ để nói' }));
  expect(holdStrip()).toBe('Giữ Space hay micro để nói');
  expect(screen.queryByRole('dialog', { name: 'Micro' })).toBeNull();
  expect(FakeRecognition.instances).toHaveLength(0);
  expect(openMicrophone).not.toHaveBeenCalled();

  // Space trong ô nhắn vẫn là gõ chữ.
  fireEvent.keyDown(composer(), space);
  expect(FakeRecognition.instances).toHaveLength(0);

  fireEvent.keyDown(document.body, space);
  const recognition = lastRecognition();
  expect(recognition.started).toBe(true);
  expect(holdStrip()).toBe('Đang nghe');
  act(() => recognition.say('Can you', false));
  expect(composer().value).toBe('Can you');
  await pause(350);
  fireEvent.keyUp(document.body, space);
  expect(recognition.stopRequested).toBe(true);
  expect(recognition.aborted).toBe(false);
  expect(holdStrip()).toBe('Đang chép lời…');
  act(() => {
    recognition.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: 'Can you hear me?' } }] });
    recognition.onend?.();
  });
  expect(composer().value).toBe('Can you hear me?');
  expect(composer().readOnly).toBe(false);
  expect(holdStrip()).toBe('Giữ Space hay micro để nói');
  expect(microphone.stops).toBe(1);
  await pause(100);
  expect(api.sendMessage).not.toHaveBeenCalled();

  // Esc trong lúc giữ thì bỏ, không thêm chữ.
  fireEvent.keyDown(document.body, space);
  act(() => lastRecognition().say('Never mind', false));
  fireEvent.keyDown(document.body, { key: 'Escape', code: 'Escape' });
  expect(lastRecognition().aborted).toBe(true);
  expect(composer().value).toBe('Can you hear me?');

  // Rời cửa sổ giữa lúc giữ: chữ dở thành bản nháp để sửa, không tự gửi.
  setHearingSetting('autoSend', true);
  fireEvent.keyDown(document.body, space);
  act(() => lastRecognition().say('Wait for', false));
  act(() => { window.dispatchEvent(new Event('blur')); });
  expect(composer().value).toBe('Can you hear me? Wait for');
  expect(holdStrip()).toMatch(/Đã thôi nghe khi rời trang/);
  await pause(100);
  expect(api.sendMessage).not.toHaveBeenCalled();
});

it('Giữ để nói với Tự gửi: chữ chốt giữa lúc giữ chưa gửi, thả ra là gửi; giữ lúc Peto đang trả lời thì ngắt lượt đó', async () => {
  setHearingSetting('mode', 'hold');
  setHearingSetting('autoSend', true);
  const signals: AbortSignal[] = [];
  vi.mocked(api.sendMessage).mockImplementation((_payload, handlers, abort) => new Promise(resolve => {
    signals.push(abort!);
    handlers.onMeta?.('C1', 'low'); handlers.onDelta?.('Thinking about it');
    abort!.addEventListener('abort', () => resolve(), { once: true });
  }));
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật Giữ để nói' }));
  fireEvent.keyDown(document.body, space);
  act(() => lastRecognition().say('Hello Peto', true));
  await pause(350);
  expect(api.sendMessage).not.toHaveBeenCalled();
  fireEvent.keyUp(document.body, space);
  act(() => lastRecognition().onend?.());
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalledOnce());
  expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({ message: 'Hello Peto', mode: 'companion' });
  expect(signals[0].aborted).toBe(false);

  fireEvent.keyDown(document.body, space);
  expect(signals[0].aborted).toBe(true);
  expect(lastRecognition().started).toBe(true);
});

it('nút micro ở Giữ để nói: bấm để bật, Space trên nút đang có tiêu điểm hay giữ chuột là nói, bấm nhanh là tắt', async () => {
  setHearingSetting('mode', 'hold');
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật Giữ để nói' }));
  const mic = screen.getByRole('button', { name: 'Giữ để nói, bấm để tắt' });
  expect(document.activeElement).toBe(mic);
  expect(mic.getAttribute('aria-pressed')).toBe('true');

  // Nhấn nhanh Space ngay sau khi bật: không tắt micro, chỉ nhắc cách giữ.
  fireEvent.keyDown(mic, space);
  expect(lastRecognition().started).toBe(true);
  fireEvent.keyUp(mic, space);
  expect(lastRecognition().aborted).toBe(true);
  expect(holdStrip()).toBe('Giữ trong lúc nói, thả ra là xong.');
  expect(mic.getAttribute('aria-pressed')).toBe('true');

  fireEvent.keyDown(mic, space);
  act(() => lastRecognition().say('Hi', false));
  await pause(350);
  fireEvent.keyUp(mic, space);
  act(() => lastRecognition().onend?.());
  expect(composer().value).toBe('Hi');

  fireEvent.pointerDown(mic, { pointerId: 1, button: 0 });
  act(() => lastRecognition().say('there', true));
  await pause(350);
  fireEvent.pointerUp(mic, { pointerId: 1, button: 0 });
  fireEvent.click(mic);
  act(() => lastRecognition().onend?.());
  expect(composer().value).toBe('Hi there');
  expect(mic.getAttribute('aria-pressed')).toBe('true');

  fireEvent.pointerDown(mic, { pointerId: 2, button: 0 });
  fireEvent.pointerUp(mic, { pointerId: 2, button: 0 });
  fireEvent.click(mic);
  expect(screen.getByRole('button', { name: 'Bật Giữ để nói' }).getAttribute('aria-pressed')).toBe('false');
  expect(document.querySelector('.hearing-strip')).toBeNull();
});

it('Giữ để nói với nguồn Groq: cả lần giữ thành một tệp WAV, thả ra mới gửi đi chép; giữ mà im lặng thì không gửi', async () => {
  localStorage.setItem('peto-hearing-source', 'groq');
  localStorage.setItem('peto-hearing-mode', 'hold');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ groq: { key: 'gsk_user' } }));
  loadHearingSettings();
  fetchMock.mockImplementation(async (url: string) => {
    if (url === 'https://api.groq.com/openai/v1/audio/transcriptions') return new Response(JSON.stringify({ text: 'Hello Peto' }));
    throw new Error(`Không mong đợi ${url}`);
  });
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật Giữ để nói' }));
  expect(openMicrophone).not.toHaveBeenCalled();

  fireEvent.keyDown(document.body, space);
  await waitFor(() => expect(microphone.onChunk).not.toBeNull());
  act(() => microphone.feed(0, 6));
  await pause(350);
  fireEvent.keyUp(document.body, space);
  expect(microphone.stops).toBe(1);
  expect(fetchMock).not.toHaveBeenCalled();
  expect(holdStrip()).toMatch(/Chưa nghe thấy tiếng nói/);

  fireEvent.keyDown(document.body, space);
  await waitFor(() => expect(microphone.onChunk).not.toBeNull());
  // Im lặng giữa câu không cắt câu như Luôn nghe: thả ra mới gửi một lần.
  act(() => { microphone.feed(0.2, 8); microphone.feed(0, 30); microphone.feed(0.2, 4); });
  await pause(350);
  fireEvent.keyUp(document.body, space);
  await waitFor(() => expect(composer().value).toBe('Hello Peto'));
  expect(fetchMock).toHaveBeenCalledOnce();
  const file = ((fetchMock.mock.calls[0] as [string, RequestInit])[1].body as FormData).get('file') as Blob;
  expect(file.size).toBe(44 + 42 * 1024 * 2);
});

it('Cài đặt Companion → Nghe: chọn Giữ để nói được lưu, ẩn hai công tắc chỉ dành cho Luôn nghe', async () => {
  render(<App />);
  const settings = within(await openHearingSettings());
  expect(settings.getByRole('radio', { name: 'Luôn nghe' })).toHaveProperty('checked', true);
  expect(settings.getByRole('switch', { name: 'Cho phép nói chen' })).toBeTruthy();
  fireEvent.click(settings.getByRole('radio', { name: 'Giữ để nói' }));
  expect(localStorage.getItem('peto-hearing-mode')).toBe('hold');
  expect(getHearingState().mode).toBe('hold');
  expect(settings.queryByRole('switch', { name: 'Cho phép nói chen' })).toBeNull();
  expect(settings.queryByRole('switch', { name: 'Tạm không nghe khi Peto đang nói' })).toBeNull();
  expect(settings.getByText(/Thả ra là gửi luôn/)).toBeTruthy();
  fireEvent.click(settings.getByRole('button', { name: 'Quay lại Mô-đun' }));
  expect((await settings.findByRole('button', { name: /^Nghe/ })).textContent).toContain('Giữ để nói');
});

it('thanh nghe trên điện thoại ẩn Tự gửi lúc đang kết nối nguồn nghe, kết nối xong thì hiện lại', async () => {
  FakeRecognition.autoReady = false;
  await openCompanion();
  fireEvent.click(screen.getByRole('button', { name: 'Bật nghe' }));
  await waitFor(() => expect(lastRecognition()?.started).toBe(true));
  const bar = document.querySelector('.hearing-bar') as HTMLElement;
  expect(bar.textContent).toContain('Đang kết nối nguồn nghe…');
  expect(within(bar).queryByRole('switch')).toBeNull();
  act(() => lastRecognition().onstart?.());
  expect(within(bar).getByRole('switch', { name: 'Tự gửi khi nói xong' })).toBeTruthy();
});
