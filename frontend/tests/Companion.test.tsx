import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { preloadLazyParts } from './lazyParts';
import App from '../src/app/App';
import * as api from '../src/shared/api/api';
import Companion from '../src/features/companion/Companion';
import { useLocalVoice } from '../src/features/companion/speech/LocalVoice';
import { DEFAULT_CHARACTER, type CharacterModel } from '../src/features/companion/characters/characterLibrary';
import { clearCompanionTimings, getCompanionTimings } from '../src/features/companion/speech/companionTiming';
import { prepareCompanionImage } from '../src/features/companion/prepareCompanionImage';
// Kiểm thử thu nhỏ ảnh thật nằm trong prepareCompanionImage và bài kiểm tra trình duyệt.
vi.mock('../src/features/companion/prepareCompanionImage', async original => ({
  ...await original<typeof import('../src/features/companion/prepareCompanionImage')>(),
  prepareCompanionImage: vi.fn(),
}));

vi.mock('../src/shared/api/api', async (original) => ({
  ...await original<typeof import('../src/shared/api/api')>(),
  getAuthState: vi.fn(), listConversations: vi.fn(), getMessages: vi.fn(), sendMessage: vi.fn(),
  listImagineJobs: vi.fn(), getProfile: vi.fn(), getAppInfo: vi.fn(), getCompanion: vi.fn(),
  deleteConversation: vi.fn(),
  getCompanionMemory: vi.fn(),
}));
// Sân khấu giả: chỉ để đọc cảm xúc Companion truyền xuống (Live2D thật cần WebGL).
vi.mock('../src/features/companion/characters/Live2DStage', () => ({
  default: ({ emotion, activity }: { emotion?: { emotion: string } | null; activity?: string }) => <div data-testid="stage" data-activity={activity} data-emotion={emotion?.emotion ?? ''} />,
}));
// Dòng "Peto vừa ghi nhớ" hỏi lại máy chủ sau vài giây; trong test hỏi ngay.
vi.mock('../src/features/companion/memoryNotice', async (original) => ({
  ...await original<typeof import('../src/features/companion/memoryNotice')>(),
  MEMORY_POLL_DELAYS: [0, 0, 0],
}));

const fetchMock = vi.fn();
const played: string[] = [];

beforeAll(preloadLazyParts);

beforeEach(() => {
  clearCompanionTimings();
  vi.resetAllMocks();
  vi.mocked(prepareCompanionImage).mockImplementation(async file => file);
  vi.mocked(api.getCompanionMemory).mockResolvedValue({ available: true, enabled: true, pending: false, limit: 50, memories: [] });
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

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

const sampleImage = (name = 'nhan-vat.png') => new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], name, { type: 'image/png' });
const chooseImages = async (files: File[]) => {
  fireEvent.change(screen.getByLabelText('Chọn ảnh cho Companion'), { target: { files } });
  await waitFor(() => expect(screen.queryByText('Đang chuẩn bị ảnh…')).toBeNull());
};

it('không gửi riêng câu hỏi trong lúc ảnh đang thu nhỏ; xử lý xong gửi đúng bản ảnh mới', async () => {
  await openCompanion();
  let finish!: (file: File) => void;
  vi.mocked(prepareCompanionImage).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const input = screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  fireEvent.change(input, { target: { value: 'What is this?' } });
  fireEvent.change(screen.getByLabelText('Chọn ảnh cho Companion'), { target: { files: [sampleImage()] } });
  expect(chatColumn().getByRole('button', { name: 'Gửi', exact: true })).toHaveProperty('disabled', true);
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(api.sendMessage).not.toHaveBeenCalled();
  await act(async () => finish(new File(['resized'], 'nhan-vat.png', { type: 'image/png' })));
  await screen.findByAltText('Ảnh chờ gửi: nhan-vat.png');
  fireEvent.click(chatColumn().getByRole('button', { name: 'Gửi', exact: true }));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalledOnce());
  expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({ message: 'What is this?', attachments: [{ data: btoa('resized') }] });
});

it('chọn ảnh có xem trước, bỏ ảnh và giới hạn loại/kích thước/số ảnh trong Companion', async () => {
  await openCompanion();
  await chooseImages([sampleImage(), sampleImage('thu-hai.png')]);
  expect(screen.getAllByAltText(/^Ảnh chờ gửi:/)).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: 'Gỡ nhan-vat.png' }));
  expect(screen.queryByAltText('Ảnh chờ gửi: nhan-vat.png')).toBeNull();
  expect(URL.revokeObjectURL).toHaveBeenCalled();
  await chooseImages([new File(['Hello'], 'doc.txt', { type: 'text/plain' })]);
  expect(screen.getByRole('alert').textContent).toContain('không phải ảnh');
  const large = sampleImage('qua-lon.png'); Object.defineProperty(large, 'size', { value: 20 * 1024 * 1024 + 1 });
  await chooseImages([large]);
  expect(screen.getByRole('alert').textContent).toContain('tối đa 20 MB');
  await chooseImages(Array.from({ length: 4 }, (_, i) => sampleImage(`anh-${i}.png`)));
  expect(screen.getAllByAltText(/^Ảnh chờ gửi:/)).toHaveLength(1);
  expect(screen.getByRole('alert').textContent).toContain('tối đa 4 ảnh');
  await chooseImages(Array.from({ length: 3 }, (_, i) => sampleImage(`anh-${i}.png`)));
  expect(screen.getAllByAltText(/^Ảnh chờ gửi:/)).toHaveLength(4);
  expect(api.sendMessage).not.toHaveBeenCalled();
});

it('gửi ảnh không cần chữ, xóa nháp khi được nhận và vẫn hiện ảnh trong bóng chat', async () => {
  vi.mocked(api.sendMessage).mockImplementation(async (payload, handlers) => {
    expect(payload).toMatchObject({ message: '', mode: 'companion', attachments: [{ name: 'nhan-vat.png', mime: 'image/png' }] });
    expect(payload.attachments![0].data).toBe(btoa(String.fromCharCode(137, 80, 78, 71, 13, 10, 26, 10)));
    handlers.onMeta?.('C1', 'low', { id: 1, role: 'user', content: '', attachments: [{
      id: 'img1', name: 'nhan-vat.png', mime: 'image/png', kind: 'image', size: 8, url: '/api/attachments/img1',
    }] });
    handlers.onDelta?.('That is a character.'); handlers.onDone?.();
  });
  await openCompanion(); await chooseImages([sampleImage()]);
  fireEvent.click(chatColumn().getByRole('button', { name: 'Gửi', exact: true }));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalledOnce());
  await waitFor(() => expect(screen.queryByAltText('Ảnh chờ gửi: nhan-vat.png')).toBeNull());
  expect(screen.getByAltText('nhan-vat.png').getAttribute('src')).toBe('/api/attachments/img1');
  expect(await screen.findByText('That is a character.')).toBeTruthy();
});

it('máy chủ chưa nhận thì giữ ảnh để gửi lại; nhận chậm không xóa ảnh và chữ của lời nhắn tiếp theo', async () => {
  vi.mocked(api.sendMessage).mockRejectedValueOnce(new Error('Chưa gửi được ảnh'));
  await openCompanion(); await chooseImages([sampleImage()]);
  await sendInCompanion('What is this?');
  await screen.findByText('Chưa gửi được ảnh');
  expect(screen.getByAltText('Ảnh chờ gửi: nhan-vat.png')).toBeTruthy();
  let old!: Parameters<typeof api.sendMessage>[1], finish!: () => void;
  vi.mocked(api.sendMessage).mockImplementationOnce((_payload, handlers) => new Promise(resolve => {
    old = handlers; finish = resolve;
  }));
  fireEvent.click(chatColumn().getByRole('button', { name: 'Gửi', exact: true }));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalledTimes(2));
  await chooseImages([sampleImage('anh-moi.png')]);
  fireEvent.change(screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }), { target: { value: 'Next question' } });
  act(() => old.onMeta?.('C1', 'low'));
  expect(screen.queryByAltText('Ảnh chờ gửi: nhan-vat.png')).toBeNull();
  expect(screen.getByAltText('Ảnh chờ gửi: anh-moi.png')).toBeTruthy();
  expect((screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }) as HTMLTextAreaElement).value).toBe('Next question');
  expect(screen.getByAltText('nhan-vat.png').getAttribute('src')).toMatch(/^data:image\/png;base64,/);
  await act(async () => { old.onDelta?.('That is a character.'); old.onDone?.(); finish(); });
});

it('tải lại Companion hiện ảnh đã lưu; dán ảnh từ clipboard vào ô nhắn', async () => {
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', messages: [{ role: 'user', content: 'Look!', attachments: [{
    id: 'img1', name: 'cu.png', mime: 'image/png', kind: 'image', size: 8, url: '/api/attachments/img1',
  }] }] });
  await openCompanion();
  expect(await screen.findByAltText('cu.png')).toBeTruthy();
  fireEvent.paste(screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }), { clipboardData: { files: [sampleImage()] } });
  expect(await screen.findByAltText('Ảnh chờ gửi: nhan-vat.png')).toBeTruthy();
});

it('Dừng trong khi đang đọc ảnh không gửi yêu cầu muộn và vẫn giữ ảnh nháp', async () => {
  await openCompanion();
  let finish!: () => void;
  vi.stubGlobal('FileReader', class {
    result = ''; onload: (() => void) | null = null; onerror = null;
    readAsDataURL() { finish = () => { this.result = 'data:image/png;base64,UE5H'; this.onload?.(); }; }
  });
  await chooseImages([sampleImage()]);
  fireEvent.click(chatColumn().getByRole('button', { name: 'Gửi', exact: true }));
  fireEvent.click(chatColumn().getByRole('button', { name: 'Dừng', exact: true }));
  await act(async () => finish());
  expect(api.sendMessage).not.toHaveBeenCalled();
  expect(screen.getByAltText('Ảnh chờ gửi: nhan-vat.png')).toBeTruthy();
  expect(chatColumn().getByRole('button', { name: 'Gửi', exact: true })).toHaveProperty('disabled', false);
});

it('hai nét mặt theo đúng tiếng đang phát, không nhảy sang câu sau khi chữ đã tải xong', async () => {
  localStorage.setItem('peto-local-voice', '1');
  class HeldAudio {
    static all: HeldAudio[] = [];
    onended: (() => void) | null = null; onerror = null;
    ready!: () => void;
    constructor() { HeldAudio.all.push(this); }
    play() { return new Promise<void>(resolve => { this.ready = resolve; }); }
    pause() {}
  }
  vi.stubGlobal('Audio', HeldAudio);
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low', undefined, true);
    handlers.onEmotion?.('surprised', 0); handlers.onDelta?.('Oh!');
    handlers.onEmotion?.('happy', 3); handlers.onDelta?.(' Great news!'); handlers.onDone?.();
  });
  await openCompanion(); await chatColumn().findByRole('button', { name: 'Tắt tiếng' });
  await sendInCompanion('I passed');
  await waitFor(() => expect(HeldAudio.all).toHaveLength(1));
  expect(screen.getByTestId('stage').dataset.emotion).toBe('');
  await act(async () => HeldAudio.all[0].ready());
  expect(screen.getByTestId('stage').dataset.emotion).toBe('surprised');
  expect(chatColumn().getByText('Oh! Great news!')).toBeTruthy();
  act(() => HeldAudio.all[0].onended?.());
  await waitFor(() => expect(HeldAudio.all).toHaveLength(2));
  expect(screen.getByTestId('stage').dataset.emotion).toBe('surprised');
  await act(async () => HeldAudio.all[1].ready());
  expect(screen.getByTestId('stage').dataset.emotion).toBe('happy');
  fireEvent.click(chatColumn().getByRole('button', { name: 'Dừng', exact: true }));
  expect(screen.getByTestId('stage').dataset.emotion).toBe('');
});

it('nghe lại tin có nhiều mốc mặt dùng đúng mốc cũ sau khi tải lại hội thoại', async () => {
  localStorage.setItem('peto-local-voice', '1'); localStorage.setItem('peto-companion-muted', '1');
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', messages: [{
    role: 'assistant', content: 'Oh! Great news!', emotion: 'surprised',
    emotion_cues: [{ emotion: 'surprised', offset: 0 }, { emotion: 'happy', offset: 3 }],
  }] });
  const audios: { ready(): void; onended: (() => void) | null }[] = [];
  vi.stubGlobal('Audio', class {
    onended: (() => void) | null = null; onerror = null; ready!: () => void;
    constructor() { audios.push(this); }
    play() { return new Promise<void>(resolve => { this.ready = resolve; }); } pause() {}
  });
  await openCompanion();
  fireEvent.click(await screen.findByRole('button', { name: /Nghe Peto/ }));
  await waitFor(() => expect(audios).toHaveLength(1));
  expect(screen.getByTestId('stage').dataset.emotion).toBe('');
  await act(async () => audios[0].ready());
  expect(screen.getByTestId('stage').dataset.emotion).toBe('surprised');
  act(() => audios[0].onended?.()); await waitFor(() => expect(audios).toHaveLength(2));
  await act(async () => audios[1].ready());
  expect(screen.getByTestId('stage').dataset.emotion).toBe('happy');
});

it('tắt tiếng đổi biểu cảm theo chữ và replace bỏ các vị trí của bản nháp', async () => {
  localStorage.setItem('peto-companion-muted', '1');
  let callbacks!: Parameters<typeof api.sendMessage>[1], done!: () => void;
  vi.mocked(api.sendMessage).mockImplementation((_payload, handlers) => new Promise(resolve => {
    callbacks = handlers; done = () => { handlers.onDone?.(); resolve(); };
  }));
  await openCompanion(); await sendInCompanion('Hello');
  act(() => {
    callbacks.onMeta?.('C1', 'low'); callbacks.onEmotion?.('surprised', 0); callbacks.onDelta?.('Oh!');
  });
  expect(screen.getByTestId('stage').dataset.emotion).toBe('surprised');
  act(() => { callbacks.onEmotion?.('happy', 3); callbacks.onDelta?.(' Great news!'); });
  expect(screen.getByTestId('stage').dataset.emotion).toBe('happy');
  act(() => { callbacks.onReplace?.(); callbacks.onEmotion?.('neutral', 0); callbacks.onDelta?.('Updated.'); });
  await act(async () => done());
  expect(screen.getByTestId('stage').dataset.emotion).toBe('neutral');
  expect(chatColumn().queryByText('Oh! Great news!')).toBeNull();
  expect(speakBodies()).toEqual([]);
});

it('đo câu đầu và tạo tiếng riêng; chỉ ghi bắt đầu nói khi âm thanh phát thật', async () => {
  localStorage.setItem('peto-local-voice', '1');
  let ready!: () => void;
  vi.stubGlobal('Audio', class {
    onended = null; onerror = null;
    play() { return new Promise<void>(resolve => { ready = resolve; }); } pause() {}
  });
  let handlers!: Parameters<typeof api.sendMessage>[1];
  vi.mocked(api.sendMessage).mockImplementation((_payload, callbacks, signal) => new Promise(resolve => {
    handlers = callbacks; signal?.addEventListener('abort', () => resolve(), { once: true });
    callbacks.onMeta?.('C1', 'low', undefined, true); callbacks.onDelta?.('Hi there. ');
  }));
  await openCompanion(); await chatColumn().findByRole('button', { name: 'Tắt tiếng' });
  await sendInCompanion('Hello'); await waitFor(() => expect(ready).toBeTypeOf('function'));
  expect(getCompanionTimings()[0].marks).toMatchObject({ firstText: expect.any(Number), textReady: expect.any(Number), synthesis: expect.any(Number) });
  expect(getCompanionTimings()[0].marks.playing).toBeUndefined();
  await act(async () => ready());
  expect(getCompanionTimings()[0].marks.playing).toEqual(expect.any(Number));
  fireEvent.click(chatColumn().getByRole('button', { name: 'Dừng', exact: true }));
  await chatColumn().findByRole('button', { name: 'Gửi', exact: true });
  const saved = getCompanionTimings()[0];
  act(() => { handlers.onDelta?.('Late words. '); handlers.onDone?.(); });
  expect(saved.status).toBe('stopped'); expect(getCompanionTimings()[0]).toBe(saved);
});

it('đọc câu đầu trước khi trả lời xong, giữ chữ gõ mới và không đọc lặp bản đầy đủ', async () => {
  localStorage.setItem('peto-local-voice', '1');
  let handlers!: Parameters<typeof api.sendMessage>[1], finish!: () => void;
  vi.mocked(api.sendMessage).mockImplementation((_payload, callbacks) => new Promise(resolve => {
    handlers = callbacks; finish = () => { callbacks.onDone?.(); resolve(); };
  }));
  await openCompanion();
  await chatColumn().findByRole('button', { name: 'Tắt tiếng' });
  await sendInCompanion('Hello');
  const composer = screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  expect(composer).toHaveProperty('disabled', false);
  fireEvent.change(composer, { target: { value: 'Next message' } });
  act(() => { handlers.onMeta?.('C1', 'low', undefined, true); handlers.onDelta?.('Good to see you. '); });
  await waitFor(() => expect(played).toHaveLength(1));
  expect(composer).toHaveProperty('value', 'Next message');
  expect(chatColumn().getByRole('button', { name: 'Dừng', exact: true })).toBeTruthy();
  act(() => handlers.onDelta?.('How was your day?'));
  await act(async () => finish());
  await waitFor(() => expect(played).toHaveLength(2));
  const texts = fetchMock.mock.calls.filter(([url]) => url.endsWith('/speak')).map(([, init]) => JSON.parse(init.body).text);
  expect(texts).toEqual(['Good to see you.', 'How was your day?']);
  expect(composer).toHaveProperty('value', 'Next message');
});

it('Dừng hủy cả chữ và tiếng; kết quả cũ không chen vào lượt mới', async () => {
  localStorage.setItem('peto-local-voice', '1');
  const audios: { pause: ReturnType<typeof vi.fn> }[] = [];
  vi.stubGlobal('Audio', class {
    onended = null; onerror = null; pause = vi.fn();
    constructor() { audios.push(this); }
    play() { return Promise.resolve(); }
  });
  let old!: Parameters<typeof api.sendMessage>[1], signal!: AbortSignal;
  vi.mocked(api.sendMessage).mockImplementationOnce((_payload, handlers, requestSignal) => new Promise(resolve => {
    old = handlers; signal = requestSignal!;
    handlers.onMeta?.('C1', 'low', undefined, true); handlers.onDelta?.('First sentence. ');
    signal.addEventListener('abort', () => resolve(), { once: true });
  })).mockImplementationOnce(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low', undefined, true);
    handlers.onDelta?.('Fresh reply.'); handlers.onDone?.();
  });
  await openCompanion();
  await chatColumn().findByRole('button', { name: 'Tắt tiếng' });
  await sendInCompanion('Hello');
  await waitFor(() => expect(audios).toHaveLength(1));
  fireEvent.change(screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }), { target: { value: 'Next message' } });
  fireEvent.click(chatColumn().getByRole('button', { name: 'Dừng', exact: true }));
  expect(signal.aborted).toBe(true);
  expect(audios[0].pause).toHaveBeenCalled();
  fireEvent.click(await chatColumn().findByRole('button', { name: 'Gửi', exact: true }));
  await waitFor(() => expect(audios).toHaveLength(2));
  act(() => { old.onDelta?.('Late old reply. '); old.onError?.('Old error'); old.onDone?.(); });
  expect(chatColumn().queryByText(/Late old reply/)).toBeNull();
  expect(chatColumn().queryByText('Old error')).toBeNull();
  expect(audios[1].pause).not.toHaveBeenCalled();
  expect(vi.mocked(api.sendMessage).mock.calls[1][0].message).toBe('Next message');
});

it('lượt có thể tra web không đọc nháp; chỉ đọc câu chốt sau thay thế', async () => {
  localStorage.setItem('peto-local-voice', '1');
  let handlers!: Parameters<typeof api.sendMessage>[1], finish!: () => void;
  vi.mocked(api.sendMessage).mockImplementation((_payload, callbacks) => new Promise(resolve => {
    handlers = callbacks; finish = () => { callbacks.onDone?.(); resolve(); };
    callbacks.onMeta?.('C1', 'low', undefined, false); callbacks.onDelta?.('A provisional answer. ');
  }));
  await openCompanion();
  await chatColumn().findByRole('button', { name: 'Tắt tiếng' });
  await sendInCompanion('What happened today?');
  expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/speak'))).toBe(false);
  act(() => { handlers.onReplace?.(); handlers.onDelta?.('The checked answer.'); });
  await act(async () => finish());
  await waitFor(() => expect(played).toHaveLength(1));
  const texts = fetchMock.mock.calls.filter(([url]) => url.endsWith('/speak')).map(([, init]) => JSON.parse(init.body).text);
  expect(texts).toEqual(['The checked answer.']);
});

it('giọng đọc lỗi giữa luồng không đọc lại khi hoàn tất và không giữ nét mặt mãi', async () => {
  localStorage.setItem('peto-local-voice', '1');
  localStorage.setItem('peto-voice-fallback', '');
  const originalFetch = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation((url, init) => url.endsWith('/speak')
    ? Promise.resolve(new Response(JSON.stringify({ detail: 'Giọng đang lỗi' }), { status: 503 }))
    : originalFetch(url, init));
  let handlers!: Parameters<typeof api.sendMessage>[1], finish!: () => void;
  vi.mocked(api.sendMessage).mockImplementation((_payload, callbacks) => new Promise(resolve => {
    handlers = callbacks; finish = () => { callbacks.onDone?.(); resolve(); };
    callbacks.onMeta?.('C1', 'low', undefined, true); callbacks.onEmotion?.('sad'); callbacks.onDelta?.('Oh no. ');
  }));
  await openCompanion();
  await chatColumn().findByRole('button', { name: 'Tắt tiếng' });
  await sendInCompanion('Hello');
  await chatColumn().findByText('Giọng đang lỗi');
  vi.useFakeTimers();
  act(() => handlers.onDelta?.('I am sorry.'));
  await act(async () => finish());
  expect(speakBodies()).toHaveLength(1);
  expect(screen.getByTestId('stage').dataset.activity).toBe('idle');
  act(() => vi.advanceTimersByTime(6500));
  expect(screen.getByTestId('stage').dataset.emotion).toBe('');
});

it('chữ nháp còn trong ô nhắn không giữ nhân vật nghe mãi', async () => {
  await openCompanion();
  await screen.findByTestId('stage');
  const composer = await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  vi.useFakeTimers();
  fireEvent.change(composer, { target: { value: 'Still writing' } });
  expect(screen.getByTestId('stage').dataset.activity).toBe('listening');
  act(() => vi.advanceTimersByTime(2999));
  expect(screen.getByTestId('stage').dataset.activity).toBe('listening');
  act(() => vi.advanceTimersByTime(1));
  expect(screen.getByTestId('stage').dataset.activity).toBe('idle');
  expect((composer as HTMLTextAreaElement).value).toBe('Still writing');
});

it('chuẩn bị tiếng giữ mặt nhưng chưa nói; lỗi trước khi phát vẫn trả mặt về nghỉ', async () => {
  localStorage.setItem('peto-local-voice', '1');
  let fail!: (error: Error) => void;
  vi.stubGlobal('Audio', class {
    onended = null; onerror = null;
    play() { return new Promise<void>((_resolve, reject) => { fail = reject; }); }
    pause() {}
  });
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low'); handlers.onEmotion?.('sad');
    handlers.onDelta?.('Oh no.'); handlers.onDone?.();
  });
  await openCompanion();
  await chatColumn().findByRole('button', { name: 'Tắt tiếng' });
  await sendInCompanion('Hello');
  await waitFor(() => expect(fail).toBeTypeOf('function'));
  expect(screen.getByTestId('stage').dataset.activity).toBe('thinking');
  expect(screen.getByTestId('stage').dataset.emotion).toBe('sad');
  vi.useFakeTimers();
  await act(async () => { fail(new Error('Blocked')); });
  expect(screen.getByTestId('stage').dataset.activity).toBe('idle');
  act(() => vi.advanceTimersByTime(1600));
  expect(screen.getByTestId('stage').dataset.emotion).toBe('');
});

it('đổi nhân vật dừng tiếng và nét mặt cũ; tín hiệu phát muộn không làm nhân vật mới nói', async () => {
  localStorage.setItem('peto-local-voice', '1');
  let ready!: () => void;
  let audio!: { onplaying: (() => void) | null; pause: ReturnType<typeof vi.fn> };
  vi.stubGlobal('Audio', class {
    onended = null; onerror = null; onplaying: (() => void) | null = null;
    pause = vi.fn();
    constructor() { audio = this; }
    play() { return new Promise<void>(resolve => { ready = resolve; }); }
  });
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', messages: [
    { role: 'assistant', content: 'I hope you feel better soon.', emotion: 'sad' },
  ] });
  const callback = () => {};
  function Harness({ character }: { character: CharacterModel }) {
    const voice = useLocalVoice(true);
    return <Companion active appInfo={null} voice={voice} character={character} characterMotion="system"
      onUnauthorized={callback} onOpenSidebar={callback} />;
  }
  const view = render(<Harness character={DEFAULT_CHARACTER} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Nghe Peto đọc tin này' }));
  await waitFor(() => expect(ready).toBeTypeOf('function'));
  expect(screen.getByTestId('stage').dataset.emotion).toBe('sad');
  const latePlaying = audio.onplaying;
  view.rerender(<Harness character={{ ...DEFAULT_CHARACTER, id: 'new-character' }} />);
  expect(audio.pause).toHaveBeenCalled();
  await act(async () => { latePlaying?.(); ready(); });
  expect(screen.getByTestId('stage').dataset.activity).toBe('idle');
  expect(screen.getByTestId('stage').dataset.emotion).toBe('');
  view.unmount();
});

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
  await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Đính kèm ảnh' })).toHaveProperty('disabled', false));
}

/** Mở Cài đặt như người dùng: ô tài khoản → Cài đặt trong menu → mục cần xem (mặc định Giọng nói). */
async function openSettings(section = 'Giọng nói') {
  fireEvent.click(await screen.findByRole('button', { name: /Tài khoản · Demo/ }));
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Cài đặt' }));
  const settings = within(screen.getByRole('dialog', { name: 'Cài đặt' }));
  fireEvent.click(settings.getByRole('button', { name: section }));
  expect(settings.getByRole('heading', { name: section })).toBeTruthy();
  // Mục Giọng nói tải riêng lúc mở lần đầu.
  if (section === 'Giọng nói') await settings.findByRole('tab', { name: 'Peto nói' });
  return settings;
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

it('bàn phím điện thoại làm khung tin thấp lại thì vẫn thấy tin mới nhất, trừ khi đã cuộn lên đọc tin cũ', async () => {
  const observers: { callback: ResizeObserverCallback; target?: Element }[] = [];
  vi.stubGlobal('ResizeObserver', class {
    target?: Element;
    constructor(public callback: ResizeObserverCallback) { observers.push(this); }
    observe(target: Element) { this.target = target; }
    unobserve() {}
    disconnect() {}
  });
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', messages: [
    { role: 'user', content: 'hi' },
    { role: 'assistant', content: 'Hey there.' },
  ] });
  await openCompanion();
  await screen.findByText('Hey there.');
  const list = document.querySelector('.companion-messages') as HTMLElement;
  const resized = () => {
    const observer = observers.find((item) => item.target === list)!;
    observer.callback([], observer as unknown as ResizeObserver);
  };
  let scrollTop = 600;
  let clientHeight = 400;
  Object.defineProperty(list, 'scrollHeight', { configurable: true, get: () => 1000 });
  Object.defineProperty(list, 'clientHeight', { configurable: true, get: () => clientHeight });
  Object.defineProperty(list, 'scrollTop', { configurable: true, get: () => scrollTop, set: (value: number) => { scrollTop = value; } });

  // Đang ở cuối; bàn phím mở làm khung thấp còn 250 mà vị trí cuộn giữ nguyên: phải bám lại cuối.
  fireEvent.scroll(list);
  clientHeight = 250;
  resized();
  expect(scrollTop).toBe(1000);

  // Đã cuộn lên đọc tin cũ thì khung đổi cỡ cũng không kéo xuống.
  scrollTop = 100;
  fireEvent.scroll(list);
  clientHeight = 400;
  resized();
  expect(scrollTop).toBe(100);
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

const MEMORY: api.CompanionMemoryState = { available: true, enabled: true, pending: false, limit: 50, memories: [] };

/** Mỗi lượt Companion trả lời xong ngay bằng câu kế tiếp trong `replies`. */
function replyWith(...replies: string[]) {
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low');
    handlers.onDelta?.(replies.shift() ?? 'Okay.');
    handlers.onDone?.();
  });
}

it('ghi nhớ xong thì cột chat báo ngay dưới câu trả lời, bấm Xem mở Cài đặt ở mục Trí nhớ với danh sách mới', async () => {
  const note = { id: 7, text: 'Đang học năm hai ngành điện', created_at: 100, updated_at: 100 };
  vi.mocked(api.getCompanionMemory)
    .mockResolvedValueOnce(MEMORY) // lúc mở tab: mốc để so
    .mockResolvedValueOnce(MEMORY) // mở mục Trí nhớ lần đầu
    .mockResolvedValueOnce({ ...MEMORY, pending: true }) // lần hỏi đầu sau lượt chat: máy chủ còn đang ghi
    .mockResolvedValue({ ...MEMORY, memories: [note] });
  replyWith('Electrical engineering, nice!');
  await openCompanion();
  await waitFor(() => expect(api.getCompanionMemory).toHaveBeenCalledTimes(1));
  // Mục Trí nhớ đã mở một lần nên vẫn còn trong hộp (chỉ ẩn đi): bấm Xem thì nó phải tải lại, không hiện danh sách cũ.
  const first = await openSettings('Trí nhớ');
  expect(await first.findByText(/Chưa có ghi nhớ nào/)).toBeTruthy();
  fireEvent.click(first.getByRole('button', { name: 'Đóng cài đặt' }));
  await waitFor(() => expect(api.getCompanionMemory).toHaveBeenCalledTimes(2));

  await sendInCompanion('mình đang học năm hai ngành điện');
  const notice = await chatColumn().findByText('Peto vừa ghi nhớ: Đang học năm hai ngành điện');
  expect(notice.closest('article')?.textContent).toContain('Electrical engineering, nice!');
  expect(api.getCompanionMemory).toHaveBeenCalledTimes(4);

  fireEvent.click(within(notice.closest('p')!).getByRole('button', { name: 'Xem' }));
  const settings = within(screen.getByRole('dialog', { name: 'Cài đặt' }));
  expect(settings.getByRole('heading', { name: 'Trí nhớ' })).toBeTruthy();
  expect(settings.getByRole('button', { name: 'Trí nhớ' }).getAttribute('aria-current')).toBe('page');
  expect(await settings.findByText('Đang học năm hai ngành điện')).toBeTruthy();
  expect(api.getCompanionMemory).toHaveBeenCalledTimes(5);

  // Mở Cài đặt bình thường sau đó thì về mục đầu, không còn đứng ở Trí nhớ.
  fireEvent.click(settings.getByRole('button', { name: 'Đóng cài đặt' }));
  fireEvent.click(await screen.findByRole('button', { name: /Tài khoản · Demo/ }));
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Cài đặt' }));
  expect(within(screen.getByRole('dialog', { name: 'Cài đặt' })).getByRole('heading', { name: 'Giao diện' })).toBeTruthy();
});

it('sửa một dòng cũ và thêm một dòng mới trong cùng lượt thì dòng báo nêu dòng đầu kèm số còn lại', async () => {
  const old = { id: 3, text: 'Nuôi một con mèo', created_at: 100, updated_at: 100 };
  vi.mocked(api.getCompanionMemory)
    .mockResolvedValueOnce({ ...MEMORY, memories: [old] })
    .mockResolvedValue({ ...MEMORY, memories: [
      { ...old, text: 'Nuôi một con mèo tên Mướp', updated_at: 300 },
      { id: 9, text: 'Thích nghe mưa', created_at: 300, updated_at: 300 },
    ] });
  replyWith('Mướp is a cute name.');
  await openCompanion();
  await waitFor(() => expect(api.getCompanionMemory).toHaveBeenCalledTimes(1));

  await sendInCompanion('con mèo nhà mình tên Mướp, mình cũng thích nghe mưa');
  expect(await chatColumn().findByText('Peto vừa ghi nhớ: Nuôi một con mèo tên Mướp (và 1 điều khác)')).toBeTruthy();
});

it('lượt không có gì mới, hay trí nhớ đang tắt, thì không có dòng báo', async () => {
  const note = { id: 7, text: 'Nuôi một con mèo tên Mướp', created_at: 100, updated_at: 100 };
  vi.mocked(api.getCompanionMemory).mockResolvedValue({ ...MEMORY, memories: [note] });
  replyWith('Cool.', 'Rain is cozy.');
  await openCompanion();
  await waitFor(() => expect(api.getCompanionMemory).toHaveBeenCalledTimes(1));

  await sendInCompanion('ok');
  await screen.findByText('Cool.');
  await waitFor(() => expect(api.getCompanionMemory).toHaveBeenCalledTimes(2));

  vi.mocked(api.getCompanionMemory).mockResolvedValue({ ...MEMORY, enabled: false, memories: [
    note, { id: 8, text: 'Thích nghe mưa', created_at: 200, updated_at: 200 },
  ] });
  await sendInCompanion('trời đang mưa');
  await screen.findByText('Rain is cozy.');
  await waitFor(() => expect(api.getCompanionMemory).toHaveBeenCalledTimes(3));
  expect(screen.queryByText(/Peto vừa ghi nhớ/)).toBeNull();
});

it('hộp Bắt đầu lại nói rõ ghi nhớ vẫn giữ khi đang có ghi nhớ, và chỉ xóa mạch trò chuyện', async () => {
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', messages: [
    { role: 'user', content: 'hi' },
    { role: 'assistant', content: 'Hey there.' },
  ] });
  await openCompanion();
  await screen.findByText('Hey there.');
  const kept = /Những điều Peto ghi nhớ về bạn vẫn được giữ/;

  // Chưa có ghi nhớ nào: hộp không nhắc tới.
  fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu lại' }));
  const dialog = await screen.findByRole('dialog', { name: 'Bắt đầu lại với Peto?' });
  await waitFor(() => expect(api.getCompanionMemory).toHaveBeenCalledTimes(2));
  expect(within(dialog).queryByText(kept)).toBeNull();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Giữ lại' }));

  // Có ghi nhớ (vd. vừa ghi ở lượt trước): mở lại hộp thì hỏi lại máy chủ và nhắc.
  vi.mocked(api.getCompanionMemory).mockResolvedValue({ ...MEMORY, memories: [
    { id: 7, text: 'Nuôi một con mèo tên Mướp', created_at: 100, updated_at: 100 },
  ] });
  fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu lại' }));
  expect(await within(dialog).findByText(kept)).toBeTruthy();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xóa và bắt đầu lại' }));
  await waitFor(() => expect(api.deleteConversation).toHaveBeenCalledWith('C1'));
  expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith('/api/companion/memory'))).toBe(false);
});

it('Peto chọn cảm xúc: nhân vật đổi mặt ngay khi bắt đầu trả lời; câu không có thẻ thì đoán theo từ khóa', async () => {
  let resume!: () => void;
  vi.mocked(api.sendMessage)
    .mockImplementationOnce(async (_payload, handlers) => {
      handlers.onMeta?.('C1', 'low');
      handlers.onEmotion?.('think');
      await new Promise<void>((resolve) => { resume = resolve; });
      handlers.onDelta?.('Hmm, let me think.');
      handlers.onDone?.();
    })
    .mockImplementationOnce(async (_payload, handlers) => {
      handlers.onMeta?.('C1', 'low');
      handlers.onEmotion?.('banana');
      handlers.onDelta?.('Congratulations!');
      handlers.onDone?.();
    });
  await openCompanion();
  await screen.findByTestId('stage');

  await sendInCompanion('Câu này khó nè');
  await waitFor(() => expect(screen.getByTestId('stage').dataset.emotion).toBe('think'));
  expect(screen.queryByText('Hmm, let me think.')).toBeNull();
  resume();
  await screen.findByText('Hmm, let me think.');
  expect(screen.getByTestId('stage').dataset.emotion).toBe('think');

  fireEvent.change(screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }), { target: { value: 'Mình thi đậu rồi' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi' }));
  await screen.findByText('Congratulations!');
  await waitFor(() => expect(screen.getByTestId('stage').dataset.emotion).toBe('happy'));
});

it('nghe lại tin cũ thì nhân vật làm lại đúng mặt đã chọn cho tin đó', async () => {
  localStorage.setItem('peto-local-voice', '1');
  localStorage.setItem('peto-companion-muted', '1');
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', messages: [
    { role: 'user', content: 'My cat is sick' },
    { role: 'assistant', content: 'Oh no, I hope she gets better soon.', emotion: 'sad' },
  ] });
  await openCompanion();
  await screen.findByText('Oh no, I hope she gets better soon.');
  expect(screen.getByTestId('stage').dataset.emotion).toBe('');
  fireEvent.click(await screen.findByRole('button', { name: /Nghe Peto/ }));
  await waitFor(() => expect(screen.getByTestId('stage').dataset.emotion).toBe('sad'));
});

it('Peto tự tra web khi cần: báo Đang tra web, bỏ chữ viết trước lúc tra, và không hiện nguồn (phương án C)', async () => {
  localStorage.setItem('peto-companion-web-search', '1');
  let resume!: () => void;
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low');
    handlers.onEmotion?.('think');
    handlers.onDelta?.('Let me check.');
    handlers.onReplace?.();
    handlers.onSearch?.('searching');
    await new Promise<void>((resolve) => { resume = resolve; });
    handlers.onSearch?.('completed');
    handlers.onSources?.([{ url: 'https://example.com/weather', title: 'Weather today' }]);
    handlers.onDelta?.("It's sunny in Saigon.");
    handlers.onDone?.();
  });
  await openCompanion();
  await screen.findByTestId('stage');
  await sendInCompanion('Weather in Saigon today?');
  expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({ mode: 'companion', webSearch: 'auto' });
  // Dòng trạng thái (đọc cho trình đọc màn hình) và bong bóng đang chờ cùng báo.
  await waitFor(() => expect(chatColumn().getAllByText('Đang tra web…')).toHaveLength(2));
  expect(chatColumn().queryByText('Let me check.')).toBeNull();
  expect(screen.getByTestId('stage').dataset.emotion).toBe('think');

  resume();
  expect(await chatColumn().findByText("It's sunny in Saigon.")).toBeTruthy();
  expect(chatColumn().queryByText('Đang tra web…')).toBeNull();
  expect(screen.queryByText('Weather today')).toBeNull();
  expect(document.querySelector('a[href="https://example.com/weather"]')).toBeNull();
  expect(screen.getByTestId('stage').dataset.emotion).toBe('think');
});

it('tra web trong Companion mặc định tắt như AIRI; bật ở Cài đặt → Tra web thì lượt sau Peto được tra', async () => {
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low');
    handlers.onDelta?.('Sure.');
    handlers.onDone?.();
  });
  await openCompanion();
  await sendInCompanion('hi');
  expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({ mode: 'companion', webSearch: 'off' });
  await chatColumn().findByText('Sure.');

  const settings = await openSettings('Tra web');
  const toggle = await settings.findByRole('switch', { name: 'Cho Peto tra web trong Companion' });
  expect((toggle as HTMLInputElement).checked).toBe(false);
  expect(settings.getByText(/Đang tắt: trong Companion, Peto trả lời bằng những gì đã biết/)).toBeTruthy();
  fireEvent.click(toggle);
  expect((toggle as HTMLInputElement).checked).toBe(true);
  expect(localStorage.getItem('peto-companion-web-search')).toBe('1');
  fireEvent.click(settings.getByRole('button', { name: 'Đóng cài đặt' }));

  await sendInCompanion('What is the weather today?');
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.sendMessage).mock.calls[1][0]).toMatchObject({ mode: 'companion', webSearch: 'auto' });
});
