import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useEffect } from 'react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { preloadLazyParts } from './lazyParts';
import App from '../src/app/App';
import * as api from '../src/shared/api/api';
import Companion from '../src/features/companion/Companion';
import { useLocalVoice } from '../src/features/companion/speech/LocalVoice';
import { DEFAULT_CHARACTER, type CharacterModel } from '../src/features/companion/characters/characterLibrary';
import { clearCompanionTimings, getCompanionTimings } from '../src/features/companion/speech/companionTiming';
import { prepareCompanionImage } from '../src/features/companion/prepareCompanionImage';
import { resetCompanionCards } from '../src/features/companion/cards/companionCards';
import { buildCardPackage } from '../src/features/companion/cards/cardPackage';
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
  listCompanionCards: vi.fn(), setActiveCompanionCard: vi.fn(), createCompanionCard: vi.fn(), updateCompanionCard: vi.fn(),
  listCompanionConversations: vi.fn(), newCompanionConversation: vi.fn(), openCompanionConversation: vi.fn(),
  deleteCompanionCard: vi.fn(), resetCompanionCard: vi.fn(), getCompanionCardPrompt: vi.fn(),
}));
// Sân khấu giả: chỉ để đọc cảm xúc Companion truyền xuống (Live2D thật cần WebGL).
const stageMock = vi.hoisted(() => ({ hold: false, notify: undefined as undefined | ((status: 'loading' | 'ready' | 'error') => void) }));
vi.mock('../src/features/companion/characters/Live2DStage', () => ({
  default: ({ emotion, activity, onStatusChange }: { emotion?: { emotion: string } | null; activity?: string; onStatusChange?: (status: 'loading' | 'ready' | 'error') => void }) => {
    useEffect(() => { stageMock.notify = onStatusChange; onStatusChange?.(stageMock.hold ? 'loading' : 'ready'); }, [onStatusChange]);
    return <div data-testid="stage" data-activity={activity} data-emotion={emotion?.emotion ?? ''} />;
  },
}));

const fetchMock = vi.fn();
const played: string[] = [];
const card = (id: string, name: string, extra: Partial<api.CompanionCard> = {}): api.CompanionCard => ({
  id, name, nickname: '', version: '1.0.0', description: '', notes: '', personality: '', scenario: '', system_prompt: 'You are Peto.',
  post_history: '', display_model: 'hiyori', greetings: [], modules: {}, is_default: id === 'peto', modified: false,
  created_at: 1, updated_at: 1, ...extra,
});
const PETO_CARD = card('peto', 'Peto');

beforeAll(preloadLazyParts);

beforeEach(() => {
  stageMock.hold = false; stageMock.notify = undefined;
  clearCompanionTimings();
  vi.resetAllMocks();
  vi.mocked(prepareCompanionImage).mockImplementation(async file => file);
  vi.mocked(api.getCompanionMemory).mockResolvedValue({ available: true, enabled: true, pending: false, sorting: false, limit: 20, memories: [] });
  localStorage.clear();
  played.length = 0;
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
  vi.mocked(api.deleteConversation).mockResolvedValue();
  resetCompanionCards();
  vi.mocked(api.listCompanionCards).mockResolvedValue({ active_card: 'peto', limit: 50, cards: [PETO_CARD] });
  vi.mocked(api.listCompanionConversations).mockResolvedValue({ active_card: 'peto', conversations: [] });
  vi.mocked(api.setActiveCompanionCard).mockResolvedValue();
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

it('giữ mặt đầu tiên qua nhiều đoạn tiếng dù máy chủ gửi thêm cảm xúc', async () => {
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
  expect(screen.getByTestId('stage').dataset.emotion).toBe('surprised');
  fireEvent.click(chatColumn().getByRole('button', { name: 'Dừng', exact: true }));
  expect(screen.getByTestId('stage').dataset.emotion).toBe('');
});

it('nghe lại tin cũ có nhiều mốc giữ một mặt qua nhiều đoạn tiếng', async () => {
  localStorage.setItem('peto-local-voice', '1'); localStorage.setItem('peto-companion-muted', '1');
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', messages: [{
    role: 'assistant', content: `Oh! ${'Great news! '.repeat(25).trim()}`, emotion: 'surprised',
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
  expect(screen.getByTestId('stage').dataset.emotion).toBe('surprised');
});

it('tắt tiếng vẫn giữ mặt đầu tiên khi có thêm thẻ và khi thay bản nháp', async () => {
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
  expect(screen.getByTestId('stage').dataset.emotion).toBe('surprised');
  act(() => { callbacks.onReplace?.(); callbacks.onEmotion?.('neutral', 0); callbacks.onDelta?.('Updated.'); });
  await act(async () => done());
  expect(screen.getByTestId('stage').dataset.emotion).toBe('surprised');
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

it.each(['hidden', 'pagehide', 'offline'])('trang %s dừng tiếng ngay, giữ bản nháp và không tự đọc phần chữ tới sau', async event => {
  localStorage.setItem('peto-local-voice', '1');
  let audio!: { onplaying: (() => void) | null; pause: ReturnType<typeof vi.fn> };
  let ready!: () => void;
  vi.stubGlobal('Audio', class {
    onended = null; onerror = null; onplaying: (() => void) | null = null; pause = vi.fn();
    constructor() { audio = this; }
    play() { return new Promise<void>(resolve => { ready = resolve; }); }
  });
  let handlers!: Parameters<typeof api.sendMessage>[1], finish!: () => void;
  vi.mocked(api.sendMessage).mockImplementationOnce((_payload, received) => new Promise(resolve => {
    handlers = received; handlers.onMeta?.('C1', 'low', undefined, true); finish = resolve;
  }));
  await openCompanion(); await screen.findByRole('button', { name: 'Tắt tiếng', exact: true });
  await sendInCompanion('First question');
  await act(async () => handlers.onDelta?.('A sentence to read. '));
  await waitFor(() => expect(ready).toBeTypeOf('function'));
  const latePlaying = audio.onplaying;
  fireEvent.change(screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }), { target: { value: 'Next draft' } });
  act(() => {
    if (event === 'hidden') {
      vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
      document.dispatchEvent(new Event('visibilitychange'));
    } else window.dispatchEvent(new Event(event));
  });
  expect(audio.pause).toHaveBeenCalled();
  await act(async () => {
    latePlaying?.(); ready();
    handlers.onDelta?.('Text still arrives.'); handlers.onDone?.(); finish();
  });
  act(() => {
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    document.dispatchEvent(new Event('visibilitychange')); window.dispatchEvent(new Event('pageshow'));
    window.dispatchEvent(new Event('online'));
  });
  expect(screen.getByTestId('stage').dataset.activity).not.toBe('speaking');
  expect((screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }) as HTMLTextAreaElement).value).toBe('Next draft');
  expect(speakBodies()).toHaveLength(1);
});

it('xuống nền trước câu đầu vẫn nhận đủ chữ và không tạo giọng khi quay về', async () => {
  localStorage.setItem('peto-local-voice', '1');
  let handlers!: Parameters<typeof api.sendMessage>[1], finish!: () => void;
  vi.mocked(api.sendMessage).mockImplementationOnce((_payload, received) => new Promise(resolve => {
    handlers = received; handlers.onMeta?.('C1', 'low', undefined, true); finish = resolve;
  }));
  await openCompanion(); await screen.findByRole('button', { name: 'Tắt tiếng', exact: true });
  await sendInCompanion('Question');
  act(() => window.dispatchEvent(new Event('pagehide')));
  await act(async () => {
    handlers.onDelta?.('A complete reply.'); handlers.onDone?.(); finish();
    window.dispatchEvent(new Event('pageshow'));
  });
  expect(await screen.findByText('A complete reply.')).toBeTruthy();
  expect(speakBodies()).toHaveLength(0);
});

async function openCompanion() {
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Companion' }));
  await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Đính kèm ảnh' })).toHaveProperty('disabled', false));
}

it('Companion chờ cả nhân vật và lịch sử; quay lại tab phải chờ renderer mới', async () => {
  stageMock.hold = true;
  let finish!: (value: { conversation_id: null; messages: [] }) => void;
  vi.mocked(api.getCompanion).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Companion' }));
  await waitFor(() => expect(stageMock.notify).toBeTypeOf('function'));
  expect(screen.getByRole('status', { name: 'Loading' })).toBeTruthy();
  expect(screen.queryByRole('textbox', { name: 'Nhắn cho Peto trong Companion' })).toBeNull();
  act(() => stageMock.notify?.('ready'));
  expect(screen.getByRole('status', { name: 'Loading' })).toBeTruthy();
  await act(async () => finish({ conversation_id: null, messages: [] }));
  await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  expect(screen.queryByRole('status', { name: 'Loading' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Trò chuyện' }));
  fireEvent.click(screen.getByRole('button', { name: 'Companion' }));
  await screen.findByRole('status', { name: 'Loading' });
  expect(screen.queryByRole('textbox', { name: 'Nhắn cho Peto trong Companion' })).toBeNull();
  act(() => stageMock.notify?.('ready'));
  await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
});

it('lỗi tải model mở lại giao diện và thử tải lại tiếp tục dùng loading', async () => {
  stageMock.hold = true;
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Companion' }));
  await waitFor(() => expect(stageMock.notify).toBeTypeOf('function'));
  await waitFor(() => expect(api.getCompanion).toHaveBeenCalled());
  act(() => stageMock.notify?.('error'));
  await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  expect(screen.queryByRole('status', { name: 'Loading' })).toBeNull();
  act(() => stageMock.notify?.('loading'));
  expect(screen.getByRole('status', { name: 'Loading' })).toBeTruthy();
  act(() => stageMock.notify?.('ready'));
  await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
});

/**
 * Mở cài đặt như người dùng. Trí nhớ ở hộp Cài đặt chung (ô tài khoản → Cài đặt → Trí nhớ). Giọng nói và Tra web ở trang
 * Cài đặt Companion (/companion/settings/, từ 13/10/2026): bánh răng ở đầu cột chat → Mô-đun → trang cần xem.
 */
async function openSettings(section = 'Giọng nói') {
  if (section === 'Trí nhớ') {
    fireEvent.click(await screen.findByRole('button', { name: /Tài khoản · Demo/ }));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Cài đặt' }));
    const settings = within(screen.getByRole('dialog', { name: 'Cài đặt' }));
    fireEvent.click(settings.getByRole('button', { name: section }));
    expect(settings.getByRole('heading', { name: section })).toBeTruthy();
    return settings;
  }
  const page = await openCompanionSettings();
  fireEvent.click(page.getByRole('button', { name: /^Mô-đun/ }));
  fireEvent.click(await page.findByRole('button', { name: new RegExp(`^${section}`) }));
  await page.findByRole('heading', { level: 1, name: section });
  return page;
}

/** Trang đầu của Cài đặt Companion: bánh răng ở đầu cột chat (mở tab Companion trước nếu đang ở tab khác). */
async function openCompanionSettings() {
  if (!screen.queryByRole('region', { name: 'Trò chuyện trong Companion' })) {
    fireEvent.click(await screen.findByRole('button', { name: 'Companion', exact: true }));
  }
  const column = within(await screen.findByRole('region', { name: 'Trò chuyện trong Companion' }));
  fireEvent.click(await column.findByRole('button', { name: 'Cài đặt Companion' }));
  return within(await screen.findByRole('main', { name: 'Cài đặt' }));
}

/** Rời trang Cài đặt Companion về sân khấu, như bấm mục Companion trên thanh bên. */
async function leaveSettings() {
  fireEvent.click(screen.getByRole('button', { name: 'Companion', exact: true }));
  await screen.findByRole('region', { name: 'Trò chuyện trong Companion' });
}

async function sendInCompanion(text: string) {
  fireEvent.change(screen.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' }), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi' }));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalled());
}

it('chỉ gọi giọng nói qua VPS sau khi bật trong Cài đặt', async () => {
  await openCompanion();
  expect(await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' })).toBeTruthy();
  expect(window.location.pathname).toBe('/companion');

  const settings = await openSettings();
  expect(localCalls()).toHaveLength(0);

  expect(settings.queryByRole('button', { name: 'Giọng Peto' })).toBeNull();
  fireEvent.click(settings.getByRole('switch', { name: 'Bật giọng nói' }));
  expect(await settings.findByText('3.600 / 5.000 ký tự')).toBeTruthy();
  expect(settings.getByRole('button', { name: 'Giọng Peto' }).getAttribute('aria-pressed')).toBe('true');
  expect(localCalls()).toHaveLength(1);
  await leaveSettings();
  expect(await chatColumn().findByRole('button', { name: 'Tắt tiếng' })).toBeTruthy();
});

it('đã bật từ trước thì tab Trò chuyện chưa dò, mở Companion mới dò', async () => {
  localStorage.setItem('peto-local-voice', '1');
  render(<App />);
  const companionTab = await screen.findByRole('button', { name: 'Companion' });
  expect(localCalls()).toHaveLength(0);

  fireEvent.click(companionTab);
  await screen.findByRole('region', { name: 'Trò chuyện trong Companion' });
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

it('tài khoản chưa có lượt Giọng Peto chỉ thấy lời giải thích, không có số lượt', async () => {
  localStorage.setItem('peto-local-voice', '1');
  vi.mocked(api.getAuthState).mockResolvedValue({ authenticated: true, login_configured: true,
    providers: { discord: true, google: true, github: true },
    user: { id: 'g-1', provider: 'github', username: 'demo', display_name: 'Demo', avatar_url: '' } });
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/health')) return new Response(JSON.stringify(health({ allowed: false, used: 0 })));
    throw new Error(`Không mong đợi ${url}`);
  });
  render(<App />);
  const settings = await openSettings();
  const detail = within(await settings.findByRole('group', { name: 'Giọng Peto' }));
  expect(await detail.findByText(/Lượt miễn phí chưa mở cho tài khoản này/)).toBeTruthy();
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
  fireEvent.click(await settings.findByRole('button', { name: 'OpenAI' }));
  let detail = within(settings.getByRole('group', { name: 'OpenAI' }));
  expect(detail.getByRole('button', { name: 'Nghe thử' }).hasAttribute('disabled')).toBe(true);
  // Khóa nhập ở Nhà cung cấp (biến thể "Như AIRI"), trang Giọng nói chỉ còn chọn.
  expect(detail.getByText('Chưa có khóa OpenAI.')).toBeTruthy();
  fireEvent.click(detail.getByRole('button', { name: 'Nhập khóa ở Nhà cung cấp' }));
  await settings.findByRole('heading', { level: 1, name: 'OpenAI' });
  expect(settings.getByText(/Giọng nói và nghe: trình duyệt gọi thẳng OpenAI, máy chủ Peto không nhận khóa/)).toBeTruthy();
  fireEvent.change(settings.getByLabelText('Khóa API OpenAI'), { target: { value: 'sk-user-key' } });
  fireEvent.click(settings.getByRole('button', { name: 'Mở Giọng nói' }));
  await settings.findByRole('heading', { level: 1, name: 'Giọng nói' });
  detail = within(settings.getByRole('group', { name: 'OpenAI' }));
  expect(detail.getByText('Đã có khóa OpenAI.')).toBeTruthy();
  fireEvent.click(detail.getByRole('button', { name: 'Nghe thử' }));

  await waitFor(() => expect(played).toHaveLength(1));
  const init = openai.mock.calls[0][1]!;
  expect((init.headers as Record<string, string>).Authorization).toBe('Bearer sk-user-key');
  expect(JSON.parse(String(init.body))).toMatchObject({ model: 'tts-1', voice: 'nova', response_format: 'wav' });
  expect(JSON.stringify(localCalls())).not.toContain('sk-user-key');
  expect(localStorage.getItem('peto-voice-keys')).toContain('sk-user-key');

  fireEvent.click(detail.getByRole('button', { name: 'Sửa ở Nhà cung cấp' }));
  await settings.findByRole('heading', { level: 1, name: 'OpenAI' });
  fireEvent.click(settings.getByRole('button', { name: 'Xóa khóa khỏi trình duyệt' }));
  expect(localStorage.getItem('peto-voice-keys')).not.toContain('sk-user-key');
  expect((settings.getByLabelText('Khóa API OpenAI') as HTMLInputElement).value).toBe('');
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
  expect(detail.getByText('Đã có khóa StepFun.')).toBeTruthy();
  fireEvent.click(detail.getByRole('button', { name: 'Nghe thử' }));

  await waitFor(() => expect(played).toHaveLength(1));
  const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/relay'))!;
  expect((init.headers as Record<string, string>)['X-Voice-Key']).toBe('step-user-key');
  expect(JSON.parse(String(init.body))).toEqual({
    provider: 'stepfun', text: expect.stringContaining('Peto'), voice: 'jilingshaonv', model: 'stepaudio-2.5-tts', region: 'intl',
  });
  expect(String(init.body)).not.toContain('step-user-key');
  fireEvent.click(detail.getByRole('button', { name: 'Sửa ở Nhà cung cấp' }));
  await settings.findByRole('heading', { level: 1, name: 'StepFun' });
  expect(settings.getByText(/StepFun không cho trình duyệt gọi thẳng, nên khóa đi qua máy chủ Peto, không lưu và không ghi log/)).toBeTruthy();
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
  expect(detail.getByText('Đã có khóa Alibaba Cloud.')).toBeTruthy();

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
  expect(await column.findByText('Chưa nhập đủ thông tin ElevenLabs trong Cài đặt Companion → Giọng nói. Peto chỉ nhắn chữ.')).toBeTruthy();
  expect(column.queryByRole('button', { name: 'Kiểm tra lại' })).toBeNull();
  expect(column.queryByRole('button', { name: 'Tắt tiếng' })).toBeNull();
});

it('trang Cài đặt Companion: mở từ bánh răng, đi từng tầng theo đường dẫn, Back và nút quay lại về đúng chỗ', async () => {
  await openCompanion();
  const page = await openCompanionSettings();
  expect(window.location.pathname).toBe('/companion/settings/');
  expect(page.getByText('Companion')).toBeTruthy();
  const cards = page.getAllByRole('button').map(button => button.textContent ?? '');
  for (const name of ['Nhân vật', 'Mô-đun', 'Bối cảnh', 'Trí nhớ', 'Chẩn đoán']) {
    expect(cards.some(text => text.startsWith(name))).toBe(true);
  }
  // Sân khấu nhường chỗ: cột chat không còn trong cây trợ năng, thanh bên vẫn sáng mục Companion.
  expect(screen.queryByRole('region', { name: 'Trò chuyện trong Companion' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Companion', exact: true }).getAttribute('aria-current')).toBe('page');

  fireEvent.click(page.getByRole('button', { name: /^Mô-đun/ }));
  expect(await page.findByRole('heading', { level: 1, name: 'Mô-đun' })).toBeTruthy();
  expect(window.location.pathname).toBe('/companion/settings/modules');
  expect(page.getByRole('button', { name: /^Giọng nói/ }).textContent).toContain('Đang tắt');
  expect(page.getByRole('button', { name: /^Tra web/ }).textContent).toContain('Đang tắt');

  fireEvent.click(page.getByRole('button', { name: /^Tra web/ }));
  const heading = await page.findByRole('heading', { level: 1, name: 'Tra web' });
  expect(window.location.pathname).toBe('/companion/settings/modules/web-search');
  // Đổi trang thì tiêu điểm lên tiêu đề, để bàn phím và trình đọc màn hình theo kịp.
  await waitFor(() => expect(document.activeElement).toBe(heading));
  expect(page.getByRole('switch', { name: 'Cho Peto tra web trong Companion' })).toBeTruthy();

  act(() => window.history.back());
  expect(await page.findByRole('heading', { level: 1, name: 'Mô-đun' })).toBeTruthy();
  fireEvent.click(page.getByRole('button', { name: 'Quay lại Cài đặt' }));
  expect(await page.findByRole('heading', { level: 1, name: 'Cài đặt' })).toBeTruthy();
  fireEvent.click(page.getByRole('button', { name: 'Quay lại Companion' }));
  expect(await screen.findByRole('region', { name: 'Trò chuyện trong Companion' })).toBeTruthy();
  expect(window.location.pathname).toBe('/companion');
});

it('trang Nhân vật như AIRI: mở từ nút Nhân vật cạnh sân khấu và thẻ ở Cài đặt, nhân vật đứng cạnh các khối cài đặt', async () => {
  await openCompanion();
  fireEvent.click(within(document.querySelector('.companion-scene-tools') as HTMLElement).getByRole('button', { name: 'Nhân vật' }));
  let page = within(await screen.findByRole('main', { name: 'Nhân vật' }));
  expect(window.location.pathname).toBe('/companion/settings/character');
  // Sân khấu Companion nhường chỗ; trang có sân khấu xem trước của riêng nó.
  expect(screen.queryByRole('region', { name: 'Trò chuyện trong Companion' })).toBeNull();
  expect(await within(page.getByRole('region', { name: /^Sân khấu xem trước/ })).findByTestId('stage')).toBeTruthy();
  expect(page.getByRole('button', { name: 'Kích thước và vị trí' }).getAttribute('aria-expanded')).toBe('true');
  expect(page.queryByText(/hỗ trợ nhân vật 2D và 3D/)).toBeNull();

  fireEvent.click(page.getByRole('button', { name: 'Chuyển động' }));
  const group = await page.findByRole('radiogroup', { name: 'Nhân vật cử động' });
  expect((within(group).getByRole('radio', { name: /Theo cài đặt chung/ }) as HTMLInputElement).checked).toBe(true);
  fireEvent.click(within(group).getByRole('radio', { name: /Luôn cử động/ }));
  expect(localStorage.getItem('peto-character-motion')).toBe('always');

  fireEvent.click(page.getByRole('button', { name: 'Chọn nhân vật' }));
  const dialog = within(await screen.findByRole('dialog', { name: 'Chọn nhân vật' }));
  fireEvent.click(dialog.getByRole('button', { name: 'Đóng chọn nhân vật' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Chọn nhân vật' })).toBeNull());

  fireEvent.click(page.getByRole('button', { name: 'Quay lại Cài đặt' }));
  const home = within(await screen.findByRole('main', { name: 'Cài đặt' }));
  fireEvent.click(home.getByRole('button', { name: /^Nhân vật/ }));
  page = within(await screen.findByRole('main', { name: 'Nhân vật' }));
  expect(window.location.pathname).toBe('/companion/settings/character');
  expect(page.getByRole('button', { name: 'Chọn nhân vật' })).toBeTruthy();
});

it('mở thẳng đường dẫn trang cài đặt (F5, link sâu) và Trí nhớ ở đây cùng danh sách với Cài đặt chung', async () => {
  vi.mocked(api.getCompanionMemory).mockResolvedValue({ ...MEMORY,
    memories: [{ id: 3, section: 'you', title: 'Hồ sơ', summary: 'Thích câu trả lời ngắn', details: ['Thích câu trả lời ngắn'], fixed: true, legacy: false, created_at: 1, updated_at: 1 }] });
  window.history.replaceState(null, '', '/companion/settings/memory');
  render(<App />);
  const page = within(await screen.findByRole('main', { name: 'Trí nhớ' }));
  expect(page.getByText('Cài đặt')).toBeTruthy();
  expect(await page.findByText('Thích câu trả lời ngắn')).toBeTruthy();
  expect(screen.queryByRole('region', { name: 'Trò chuyện trong Companion' })).toBeNull();
});

const ROWS: api.CompanionConversation[] = [
  { id: 'C1', card_id: 'peto', card_name: 'Peto', preview: 'hi', message_count: 2, created_at: 1, updated_at: Date.now() / 1000 - 60, active: true },
  { id: 'C2', card_id: 'mika', card_name: 'Mika', preview: 'Trà gì?', message_count: 3, created_at: 1, updated_at: Date.now() / 1000 - 5 * 86400, active: false },
];

it('danh sách hội thoại như AIRI: mở mạch của thẻ khác, hội thoại mới có câu chào, xóa phải bấm hai lần', async () => {
  vi.mocked(api.listCompanionCards).mockResolvedValue({ active_card: 'peto', limit: 50, cards: [PETO_CARD, card('mika', 'Mika')] });
  vi.mocked(api.getCompanion).mockImplementation(async (_signal, id) => id === 'C2'
    ? { conversation_id: 'C2', card_id: 'mika', title: 'Trà gì?', messages: [{ role: 'assistant', content: 'Trà hoa nhài.' }] }
    : { conversation_id: 'C1', card_id: 'peto', title: 'hi', messages: [{ role: 'user', content: 'hi' }, { role: 'assistant', content: 'Hey there.' }] });
  vi.mocked(api.listCompanionConversations).mockResolvedValue({ active_card: 'peto', conversations: ROWS });
  vi.mocked(api.openCompanionConversation).mockResolvedValue({ conversation_id: 'C2', card_id: 'mika' });
  vi.mocked(api.newCompanionConversation).mockResolvedValue({ conversation_id: 'C3', card_id: 'mika', title: '',
    messages: [{ role: 'assistant', content: 'Ồ, khách tới rồi.' }] });
  await openCompanion();
  await screen.findByText('Hey there.');
  expect(await screen.findByRole('button', { name: 'Profile: Peto' })).toBeTruthy();

  fireEvent.click(chatColumn().getByRole('button', { name: 'Hội thoại: hi' }));
  let menu = within(await screen.findByRole('dialog', { name: 'Hội thoại' }));
  expect(await menu.findByText('Trà gì?')).toBeTruthy();
  expect(menu.getByText(/· Mika$/)).toBeTruthy();
  fireEvent.click(menu.getByText('Trà gì?'));
  await waitFor(() => expect(api.openCompanionConversation).toHaveBeenCalledWith('C2'));
  expect(await screen.findByText('Trà hoa nhài.')).toBeTruthy();
  expect(await screen.findByRole('button', { name: 'Profile: Mika' })).toBeTruthy();
  expect(screen.getByRole('textbox', { name: 'Nhắn cho Mika trong Companion' })).toBeTruthy();

  fireEvent.click(chatColumn().getByRole('button', { name: 'Hội thoại: Trà gì?' }));
  menu = within(await screen.findByRole('dialog', { name: 'Hội thoại' }));
  fireEvent.click(menu.getByRole('button', { name: /Hội thoại mới/ }));
  await waitFor(() => expect(api.newCompanionConversation).toHaveBeenCalledWith('mika'));
  expect(await screen.findByText('Ồ, khách tới rồi.')).toBeTruthy();
  expect(chatColumn().getByRole('button', { name: 'Hội thoại: Hội thoại mới' })).toBeTruthy();

  // Xóa: lần bấm đầu chỉ hỏi lại, lần hai mới xóa; xóa mạch khác thì mạch đang mở giữ nguyên.
  fireEvent.click(chatColumn().getByRole('button', { name: 'Hội thoại: Hội thoại mới' }));
  menu = within(await screen.findByRole('dialog', { name: 'Hội thoại' }));
  fireEvent.click(await menu.findByRole('button', { name: 'Xóa hội thoại: hi' }));
  expect(api.deleteConversation).not.toHaveBeenCalled();
  fireEvent.click(menu.getByRole('button', { name: 'Xác nhận xóa: hi' }));
  await waitFor(() => expect(api.deleteConversation).toHaveBeenCalledWith('C1'));
  await waitFor(() => expect(menu.queryByText('hi')).toBeNull());
  expect(screen.getByText('Ồ, khách tới rồi.')).toBeTruthy();
});

it('Profile như AIRI: đổi thẻ mở mạch của thẻ đó, lưu thẻ đang dùng thành Profile mới, không cho trùng tên', async () => {
  vi.mocked(api.listCompanionCards).mockResolvedValue({ active_card: 'peto', limit: 50, cards: [PETO_CARD, card('mika', 'Mika')] });
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', card_id: 'peto', title: 'hi', messages: [{ role: 'assistant', content: 'Hey there.' }] });
  await openCompanion();
  await screen.findByText('Hey there.');

  fireEvent.click(await screen.findByRole('button', { name: 'Profile: Peto' }));
  let menu = within(await screen.findByRole('dialog', { name: 'Profile' }));
  expect(menu.getByRole('button', { name: /Peto/ }).getAttribute('aria-current')).toBe('true');
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: null, card_id: 'mika', title: '', messages: [] });
  fireEvent.click(menu.getByRole('button', { name: 'Mika' }));
  await waitFor(() => expect(api.setActiveCompanionCard).toHaveBeenCalledWith('mika'));
  expect(await screen.findByRole('button', { name: 'Profile: Mika' })).toBeTruthy();
  await waitFor(() => expect(screen.queryByText('Hey there.')).toBeNull());

  fireEvent.click(screen.getByRole('button', { name: 'Profile: Mika' }));
  menu = within(await screen.findByRole('dialog', { name: 'Profile' }));
  fireEvent.click(menu.getByRole('button', { name: /Lưu thành Profile mới/ }));
  const input = menu.getByRole('textbox', { name: 'Tên Profile mới' }) as HTMLInputElement;
  expect(input.value).toBe('Mika');
  fireEvent.change(input, { target: { value: 'Peto' } });
  expect(await menu.findByText('Đã có Profile tên này.')).toBeTruthy();
  expect(menu.getByRole('button', { name: 'Lưu thành Profile mới' })).toHaveProperty('disabled', true);
  vi.mocked(api.createCompanionCard).mockResolvedValue(card('c3', 'Mika học bài', { is_default: false }));
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: null, card_id: 'c3', title: '', messages: [] });
  fireEvent.change(input, { target: { value: 'Mika học bài' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  await waitFor(() => expect(api.createCompanionCard).toHaveBeenCalled());
  expect(vi.mocked(api.createCompanionCard).mock.calls[0][0]).toMatchObject({ name: 'Mika học bài', system_prompt: 'You are Peto.' });
  expect(vi.mocked(api.createCompanionCard).mock.calls[0][0]).not.toHaveProperty('id');
  await waitFor(() => expect(api.setActiveCompanionCard).toHaveBeenCalledWith('c3'));
  expect(await screen.findByRole('button', { name: 'Profile: Mika học bài' })).toBeTruthy();
});

const MIKA = '0123456789abcdef0123456789abcdef';
const HANA = 'fedcba9876543210fedcba9876543210';

it('Thẻ nhân vật như AIRI: lưới thẻ, tìm, trang một thẻ, prompt đầy đủ, dùng thẻ, tạo thẻ mới', async () => {
  const mika = card(MIKA, 'Mika', { description: 'Cáo tinh trông tiệm trà.', greetings: ['Ngồi đi.'], created_at: 5 });
  vi.mocked(api.listCompanionCards).mockResolvedValue({ active_card: 'peto', limit: 50, cards: [PETO_CARD, mika] });
  vi.mocked(api.getCompanionCardPrompt).mockResolvedValue({ prompt: 'You are Mika.\n\nFIXED RULE', memory: false });
  window.history.replaceState(null, '', '/companion/settings/');
  render(<App />);
  const home = within(await screen.findByRole('main', { name: 'Cài đặt' }));
  fireEvent.click(await home.findByRole('button', { name: /^Thẻ nhân vật/ }));
  expect(window.location.pathname).toBe('/companion/settings/cards');
  let page = within(await screen.findByRole('main', { name: 'Thẻ nhân vật' }));
  expect(await page.findByRole('button', { name: 'Xem thẻ: Peto' })).toBeTruthy();
  // Tìm không phân biệt dấu, cả trong mô tả.
  fireEvent.change(page.getByRole('searchbox', { name: 'Tìm thẻ' }), { target: { value: 'tra' } });
  expect(page.queryByRole('button', { name: 'Xem thẻ: Peto' })).toBeNull();
  fireEvent.click(page.getByRole('button', { name: 'Xem thẻ: Mika' }));
  expect(window.location.pathname).toBe(`/companion/settings/cards/${MIKA}`);

  page = within(await screen.findByRole('main', { name: 'Mika' }));
  expect(page.getAllByText('Cáo tinh trông tiệm trà.').length).toBeGreaterThan(0);
  expect(page.getByText('Ngồi đi.')).toBeTruthy();
  expect(page.getByText('Chưa có (chỉ thẻ Peto dùng trí nhớ)')).toBeTruthy();
  fireEvent.click(page.getByRole('button', { name: 'Prompt đầy đủ' }));
  const prompt = within(await screen.findByRole('dialog', { name: 'Prompt đầy đủ · Mika' }));
  expect(await prompt.findByText(/FIXED RULE/)).toBeTruthy();
  expect(api.getCompanionCardPrompt).toHaveBeenCalledWith(MIKA, expect.anything());
  fireEvent.click(prompt.getByRole('button', { name: 'Đóng' }));

  fireEvent.click(page.getByRole('button', { name: 'Dùng thẻ này' }));
  await waitFor(() => expect(api.setActiveCompanionCard).toHaveBeenCalledWith(MIKA));
  expect(await page.findByRole('button', { name: 'Đang dùng' })).toHaveProperty('disabled', true);

  fireEvent.click(screen.getByRole('button', { name: 'Quay lại Thẻ nhân vật' }));
  page = within(await screen.findByRole('main', { name: 'Thẻ nhân vật' }));
  fireEvent.click(page.getByRole('button', { name: 'Tạo thẻ mới' }));
  expect(window.location.pathname).toBe('/companion/settings/cards/new');
  page = within(await screen.findByRole('main', { name: 'Thẻ mới' }));
  fireEvent.click(page.getByRole('button', { name: 'Tạo thẻ' }));
  expect(await page.findByText('Cần đặt tên cho thẻ.')).toBeTruthy();
  expect(api.createCompanionCard).not.toHaveBeenCalled();
  fireEvent.change(page.getByRole('textbox', { name: /^Tên/ }), { target: { value: 'mika' } });
  fireEvent.click(page.getByRole('button', { name: 'Tạo thẻ' }));
  expect(await page.findByText('Đã có thẻ tên "mika".')).toBeTruthy();
  fireEvent.change(page.getByRole('textbox', { name: /^Tên/ }), { target: { value: 'Hana' } });
  fireEvent.click(page.getByRole('button', { name: 'Hành vi' }));
  expect(window.location.search).toBe('?section=behavior');
  fireEvent.change(page.getByRole('textbox', { name: 'Câu chào' }), { target: { value: 'Chào cậu!\n\nĐi chơi không?' } });
  vi.mocked(api.createCompanionCard).mockResolvedValue(card(HANA, 'Hana', { is_default: false, greetings: ['Chào cậu!'] }));
  fireEvent.click(page.getByRole('button', { name: 'Tạo và dùng' }));
  await waitFor(() => expect(api.createCompanionCard).toHaveBeenCalled());
  expect(vi.mocked(api.createCompanionCard).mock.calls[0][0]).toMatchObject({
    name: 'Hana', version: '1.0.0', greetings: ['Chào cậu!', 'Đi chơi không?'], modules: {},
    personality: 'You are a regular human, curious about everything.', display_model: 'hiyori',
  });
  await waitFor(() => expect(api.setActiveCompanionCard).toHaveBeenCalledWith(HANA));
  await waitFor(() => expect(window.location.pathname).toBe(`/companion/settings/cards/${HANA}`));
  expect(await screen.findByRole('main', { name: 'Hana' })).toBeTruthy();
});

it('nhập gói thẻ AIRI ở trang Thẻ nhân vật: tên trùng thêm số, báo phần bỏ qua; gói hỏng thì báo lỗi, không tạo thẻ', async () => {
  vi.mocked(api.listCompanionCards).mockResolvedValue({ active_card: 'peto', limit: 50, cards: [PETO_CARD, card(MIKA, 'Mika')] });
  window.history.replaceState(null, '', '/companion/settings/cards');
  render(<App />);
  const page = within(await screen.findByRole('main', { name: 'Thẻ nhân vật' }));
  await page.findByRole('button', { name: 'Xem thẻ: Mika' });
  const upload = page.getByLabelText('Chọn gói thẻ nhân vật (.zip)') as HTMLInputElement;
  expect(upload.accept).toContain('.zip');

  const shared = card(HANA, 'Mika', { is_default: false, greetings: ['Ngồi đi.'], description: 'Cáo tinh.', display_model: 'hiyori',
    system_prompt: 'You are {{char}}.', modules: { brain: { provider: 'peto' } } });
  const packageFile = new File([await buildCardPackage({ ...shared, greetings: Array.from({ length: 12 }, (_, index) => `Câu ${index}`) },
    { kind: 'builtin', id: 'hiyori' })], 'Mika.zip', { type: 'application/zip' });
  vi.mocked(api.createCompanionCard).mockResolvedValue(card(HANA, 'Mika (2)', { is_default: false }));
  fireEvent.change(upload, { target: { files: [packageFile] } });
  await waitFor(() => expect(api.createCompanionCard).toHaveBeenCalled());
  expect(vi.mocked(api.createCompanionCard).mock.calls[0][0]).toMatchObject({
    name: 'Mika (2)', description: 'Cáo tinh.', system_prompt: 'You are {{char}}.', display_model: 'hiyori',
    modules: { brain: { provider: 'peto' } },
  });
  expect(vi.mocked(api.createCompanionCard).mock.calls[0][0].greetings).toHaveLength(10);
  expect(await screen.findByText('Đã nhập thẻ Mika (2).')).toBeTruthy();
  expect(await page.findByText('Thẻ có 12 câu chào; Peto giữ 10 câu đầu.')).toBeTruthy();
  expect(await page.findByRole('button', { name: 'Xem thẻ: Mika (2)' })).toBeTruthy();

  vi.mocked(api.createCompanionCard).mockClear();
  fireEvent.change(upload, { target: { files: [new File([new Uint8Array([1, 2, 3])], 'hong.zip')] } });
  expect(await page.findByText('Tệp này không phải gói thẻ nhân vật hợp lệ.')).toBeTruthy();
  expect(api.createCompanionCard).not.toHaveBeenCalled();
});

it('xuất thẻ thành gói .zip theo tên thẻ, model có sẵn không đóng vào gói', async () => {
  vi.mocked(api.listCompanionCards).mockResolvedValue({ active_card: 'peto', limit: 50, cards: [PETO_CARD] });
  const downloads: { name: string; blob: Blob }[] = [];
  let made: Blob | undefined;
  URL.createObjectURL = vi.fn((blob: Blob) => { made = blob; return 'blob:card'; });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    if (made) downloads.push({ name: this.download, blob: made });
  });
  window.history.replaceState(null, '', '/companion/settings/cards/peto');
  render(<App />);
  const page = within(await screen.findByRole('main', { name: 'Peto' }));
  fireEvent.click(await page.findByRole('button', { name: 'Xuất thẻ' }));
  await waitFor(() => expect(downloads).toHaveLength(1));
  expect(downloads[0].name).toBe('Peto.zip');
  expect(await screen.findByText('Đã xuất thẻ Peto.')).toBeTruthy();
  const { unzipSync, strFromU8 } = await import('fflate');
  const entries = unzipSync(new Uint8Array(await downloads[0].blob.arrayBuffer()));
  expect(Object.keys(entries).sort()).toEqual(['card.json', 'manifest.json']);
  const exported = JSON.parse(strFromU8(entries['card.json']));
  expect(exported.data).toMatchObject({ name: 'Peto', system_prompt: 'You are Peto.' });
  expect(exported.data.extensions.peto.display_model).toBe('hiyori');
  click.mockRestore();
});

it('sửa thẻ chỉ gửi ô đã đổi, hỏi trước khi bỏ chỗ chưa lưu; khôi phục thẻ Peto; xóa thẻ cùng hội thoại của nó', async () => {
  vi.mocked(api.listCompanionCards).mockResolvedValue({ active_card: 'peto', limit: 50, cards: [PETO_CARD, card(MIKA, 'Mika')] });
  vi.mocked(api.listCompanionConversations).mockResolvedValue({ active_card: 'peto', conversations: [
    { ...ROWS[1], card_id: MIKA },
  ] });
  window.history.replaceState(null, '', '/companion/settings/cards/peto/edit');
  render(<App />);
  let page = within(await screen.findByRole('main', { name: 'Sửa thẻ' }));
  fireEvent.change(await page.findByRole('textbox', { name: /^Biệt danh/ }), { target: { value: 'Pe' } });
  expect(page.getByText('Chưa lưu')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Quay lại Peto' }));
  const leave = within(await screen.findByRole('dialog', { name: 'Bỏ thay đổi?' }));
  fireEvent.click(leave.getByRole('button', { name: 'Sửa tiếp' }));
  expect(window.location.pathname).toBe('/companion/settings/cards/peto/edit');
  vi.mocked(api.updateCompanionCard).mockResolvedValue({ ...PETO_CARD, nickname: 'Pe', modified: true });
  fireEvent.click(page.getByRole('button', { name: 'Lưu' }));
  await waitFor(() => expect(api.updateCompanionCard).toHaveBeenCalledWith('peto', { nickname: 'Pe' }));
  await waitFor(() => expect(window.location.pathname).toBe('/companion/settings/cards/peto'));

  page = within(await screen.findByRole('main', { name: 'Peto' }));
  expect(page.queryByRole('button', { name: 'Xóa' })).toBeNull();
  vi.mocked(api.resetCompanionCard).mockResolvedValue(PETO_CARD);
  fireEvent.click(page.getByRole('button', { name: 'Khôi phục bản gốc' }));
  fireEvent.click(within(await screen.findByRole('dialog', { name: 'Khôi phục thẻ Peto?' })).getByRole('button', { name: 'Khôi phục' }));
  await waitFor(() => expect(api.resetCompanionCard).toHaveBeenCalled());
  await waitFor(() => expect(page.queryByRole('button', { name: 'Khôi phục bản gốc' })).toBeNull());

  fireEvent.click(screen.getByRole('button', { name: 'Quay lại Thẻ nhân vật' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Xem thẻ: Mika' }));
  page = within(await screen.findByRole('main', { name: 'Mika' }));
  fireEvent.click(page.getByRole('button', { name: 'Xóa' }));
  const confirm = within(await screen.findByRole('dialog', { name: 'Xóa thẻ Mika?' }));
  expect(await confirm.findByText(/Xóa luôn 1 hội thoại của thẻ này/)).toBeTruthy();
  vi.mocked(api.deleteCompanionCard).mockResolvedValue({ conversations_deleted: 1, active_card: 'peto' });
  fireEvent.click(confirm.getByRole('button', { name: 'Xóa thẻ' }));
  await waitFor(() => expect(api.deleteCompanionCard).toHaveBeenCalledWith(MIKA));
  await waitFor(() => expect(window.location.pathname).toBe('/companion/settings/cards'));
  expect(await screen.findByText('Đã xóa thẻ Mika và 1 hội thoại.')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Xem thẻ: Mika' })).toBeNull();
});

it('đổi thẻ ở trang Thẻ nhân vật thì Companion mở mạch của thẻ đó; bộ não và giọng riêng của thẻ được dùng', async () => {
  localStorage.setItem('peto-local-voice', '1');
  localStorage.setItem('peto-voice-keys', JSON.stringify({ deepseek: { key: 'sk-deep-12345678' } }));
  localStorage.setItem('peto-provider-models', JSON.stringify({ deepseek: ['deepseek-chat'] }));
  const mika = card(MIKA, 'Mika', { modules: { brain: { provider: 'deepseek', model: 'deepseek-chat' },
    voice: { source: 'official', voice: 'stepfun:lively-girl' } } });
  vi.mocked(api.listCompanionCards).mockResolvedValue({ active_card: 'peto', limit: 50, cards: [PETO_CARD, mika] });
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C1', card_id: 'peto', title: 'hi', messages: [{ role: 'assistant', content: 'Hey there.' }] });
  await openCompanion();
  await screen.findByText('Hey there.');

  const settings = await openCompanionSettings();
  fireEvent.click(await settings.findByRole('button', { name: /^Thẻ nhân vật/ }));
  fireEvent.click(await screen.findByRole('button', { name: 'Xem thẻ: Mika' }));
  const page = within(await screen.findByRole('main', { name: 'Mika' }));
  expect(page.getByText('DeepSeek · deepseek-chat')).toBeTruthy();
  expect(page.getByText('Giọng Peto · Lively Girl')).toBeTruthy();
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: 'C2', card_id: MIKA, title: 'Trà gì?', messages: [{ role: 'assistant', content: 'Trà hoa nhài.' }] });
  fireEvent.click(page.getByRole('button', { name: 'Dùng thẻ này' }));
  await waitFor(() => expect(api.setActiveCompanionCard).toHaveBeenCalledWith(MIKA));

  await leaveSettings();
  expect(await screen.findByText('Trà hoa nhài.')).toBeTruthy();
  expect(await screen.findByRole('button', { name: 'Profile: Mika' })).toBeTruthy();
  expect(chatColumn().getByText(/DeepSeek/)).toBeTruthy();

  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C2', 'low');
    handlers.onDelta?.('Jasmine, of course.');
    handlers.onDone?.();
  });
  fireEvent.change(screen.getByRole('textbox', { name: 'Nhắn cho Mika trong Companion' }), { target: { value: 'Trà gì?' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi' }));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalled());
  expect(vi.mocked(api.sendMessage).mock.calls[0][0]).toMatchObject({ provider: { id: 'deepseek', model: 'deepseek-chat' },
    providerKey: 'sk-deep-12345678' });
  await waitFor(() => expect(played).toHaveLength(1));
  expect(speakBodies()[0]).toMatchObject({ text: 'Jasmine, of course.', voice: 'stepfun:lively-girl' });
});

it('chưa tải được thẻ nhân vật thì vẫn trò chuyện được, chỉ không có nút Profile', async () => {
  vi.mocked(api.listCompanionCards).mockRejectedValue(new Error('offline'));
  await openCompanion();
  expect(screen.queryByRole('button', { name: /^Profile:/ })).toBeNull();
  expect(chatColumn().getByRole('button', { name: 'Hội thoại: Hội thoại mới' })).toBeTruthy();
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

const MEMORY: api.CompanionMemoryState = { available: true, enabled: true, pending: false, sorting: false, limit: 20, memories: [] };

/** Mỗi lượt Companion trả lời xong ngay bằng câu kế tiếp trong `replies`. */
function replyWith(...replies: string[]) {
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low');
    handlers.onDelta?.(replies.shift() ?? 'Okay.');
    handlers.onDone?.();
  });
}

it('Companion không báo "Peto vừa ghi nhớ" hay hỏi lại trí nhớ sau lượt; mục Trí nhớ tải lại mỗi lần mở', async () => {
  // Chủ web thấy dòng báo dưới câu trả lời là thừa (11/10/2026): ghi nhớ chỉ xem trong Cài đặt → Trí nhớ.
  const note = { id: 7, section: 'you', title: 'Hồ sơ', summary: 'Đang học năm hai ngành điện', details: ['Đang học năm hai ngành điện'], fixed: true, legacy: false, created_at: 100, updated_at: 100 };
  vi.mocked(api.getCompanionMemory)
    .mockResolvedValueOnce(MEMORY) // mở mục Trí nhớ lần đầu
    .mockResolvedValue({ ...MEMORY, memories: [note] });
  replyWith('Electrical engineering, nice!');
  await openCompanion();
  const first = await openSettings('Trí nhớ');
  expect(await first.findByText(/Chưa có ghi nhớ nào/)).toBeTruthy();
  fireEvent.click(first.getByRole('button', { name: 'Đóng cài đặt' }));

  await sendInCompanion('mình đang học năm hai ngành điện');
  await screen.findByText('Electrical engineering, nice!');
  expect(screen.queryByText(/vừa ghi nhớ/)).toBeNull();
  expect(api.getCompanionMemory).toHaveBeenCalledTimes(1);

  // Mục đã mở một lần vẫn còn trong hộp (chỉ ẩn): mở lại thì nó tải lại, không hiện danh sách cũ.
  const again = await openSettings('Trí nhớ');
  expect(await again.findByText('Đang học năm hai ngành điện')).toBeTruthy();
  expect(api.getCompanionMemory).toHaveBeenCalledTimes(2);
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
  await waitFor(() => expect(chatColumn().getAllByText(/Đang tra web…/)).toHaveLength(2));
  expect(chatColumn().queryByText('Let me check.')).toBeNull();
  expect(screen.getByTestId('stage').dataset.emotion).toBe('think');

  resume();
  expect(await chatColumn().findByText("It's sunny in Saigon.")).toBeTruthy();
  expect(chatColumn().queryByText(/Đang tra web…/)).toBeNull();
  expect(screen.queryByText('Weather today')).toBeNull();
  expect(document.querySelector('a[href="https://example.com/weather"]')).toBeNull();
  expect(screen.getByTestId('stage').dataset.emotion).toBe('think');
});

it('tra web trong Companion mặc định tắt như AIRI; bật ở Cài đặt Companion → Tra web thì lượt sau Peto được tra', async () => {
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
  await leaveSettings();

  await sendInCompanion('What is the weather today?');
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.sendMessage).mock.calls[1][0]).toMatchObject({ mode: 'companion', webSearch: 'auto' });
});
