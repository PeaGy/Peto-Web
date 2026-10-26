/**
 * Cài đặt Companion → Nhà cung cấp và Mô-đun → Bộ não (biến thể "Như AIRI", 13/10/2026): nhập và kiểm tra khóa riêng,
 * chọn bộ não, khóa Tavily, và lượt Companion gửi kèm khóa trong header. Không gọi nhà cung cấp thật.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useEffect } from 'react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { preloadLazyParts } from './lazyParts';
import App from '../src/app/App';
import * as api from '../src/shared/api/api';
import { COMPANION_PROVIDER_IDS, companionProviderId, companionSettingsPage } from '../src/app/routes';
import { PROVIDER_PAGE_IDS } from '../src/features/companion/providers/catalog';

vi.mock('../src/shared/api/api', async (original) => ({
  ...await original<typeof import('../src/shared/api/api')>(),
  getAuthState: vi.fn(), listConversations: vi.fn(), getMessages: vi.fn(), sendMessage: vi.fn(),
  listImagineJobs: vi.fn(), getProfile: vi.fn(), getAppInfo: vi.fn(), getCompanion: vi.fn(),
  getCompanionMemory: vi.fn(), checkProvider: vi.fn(),
  listCompanionCards: vi.fn(),
}));
vi.mock('../src/features/companion/characters/Live2DStage', () => ({
  default: ({ onStatusChange }: { onStatusChange?: (status: 'loading' | 'ready' | 'error') => void }) => {
    useEffect(() => { onStatusChange?.('ready'); }, [onStatusChange]);
    return null;
  },
}));

beforeAll(preloadLazyParts);

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  window.history.replaceState(null, '', '/');
  vi.mocked(api.getAuthState).mockResolvedValue({ authenticated: true, login_configured: true,
    providers: { discord: true, google: true, github: true },
    user: { id: 'acc-111', provider: 'discord', username: 'demo', display_name: 'Demo', avatar_url: '' } });
  vi.mocked(api.listConversations).mockResolvedValue({ conversations: [], has_more: false });
  vi.mocked(api.getMessages).mockResolvedValue([]);
  vi.mocked(api.listImagineJobs).mockResolvedValue([]);
  vi.mocked(api.getAppInfo).mockRejectedValue(new Error('offline'));
  // Thẻ nhân vật không phải việc của các test này: không tải được thì Companion vẫn chạy như cũ.
  vi.mocked(api.listCompanionCards).mockRejectedValue(new Error('offline'));
  vi.mocked(api.getProfile).mockResolvedValue({ profile: { full_name: '', nickname: '', occupation: '', instructions: '' },
    occupations: [], limits: { full_name: 80, nickname: 40, instructions: 1500 } });
  vi.mocked(api.getCompanion).mockResolvedValue({ conversation_id: null, messages: [] });
  vi.mocked(api.getCompanionMemory).mockResolvedValue({ available: true, enabled: true, pending: false, sorting: false, limit: 20, memories: [] });
  vi.mocked(api.sendMessage).mockImplementation(async (_payload, handlers) => {
    handlers.onMeta?.('C1', 'low'); handlers.onDelta?.('Hello.'); handlers.onDone?.();
  });
  Element.prototype.scrollTo = vi.fn();
});

afterEach(() => { vi.unstubAllGlobals(); });

async function openCompanionSettings() {
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Companion', exact: true }));
  await screen.findByRole('region', { name: 'Trò chuyện trong Companion' });
  // Bánh răng ở hàng trên cùng cạnh nút Profile (Header của AIRI, từ 26/10/2026).
  fireEvent.click(await screen.findByRole('button', { name: 'Cài đặt Companion' }));
  return within(await screen.findByRole('main', { name: 'Cài đặt' }));
}

async function connect(page: ReturnType<typeof within>, name: string, key: string, models: string[]) {
  fireEvent.click(page.getByRole('button', { name: new RegExp(`^${name}`) }));
  await page.findByRole('heading', { level: 1, name });
  vi.mocked(api.checkProvider).mockResolvedValueOnce({ models, deployment: false });
  fireEvent.change(page.getByLabelText(`Khóa API ${name}`), { target: { value: key } });
  fireEvent.click(page.getByRole('button', { name: 'Kiểm tra kết nối' }));
  await page.findByText(`Đã kết nối · ${models.length} model`);
}

async function sendInCompanion(text: string) {
  fireEvent.click(screen.getByRole('button', { name: 'Companion', exact: true }));
  const input = await screen.findByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  fireEvent.change(input, { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi' }));
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalled());
  return vi.mocked(api.sendMessage).mock.calls.at(-1)![0];
}

it('đường dẫn trang nhà cung cấp khớp danh mục, kể cả mã lạ bị từ chối', () => {
  expect([...COMPANION_PROVIDER_IDS].sort()).toEqual([...PROVIDER_PAGE_IDS].sort());
  expect(companionProviderId('/companion/settings/providers/deepseek')).toBe('deepseek');
  expect(companionProviderId('/companion/settings/providers/azure-openai/')).toBe('azure-openai');
  expect(companionProviderId('/companion/settings/providers/evil')).toBeNull();
  expect(companionSettingsPage('/companion/settings/providers/deepseek')).toBe('provider');
  expect(companionSettingsPage('/companion/settings/providers')).toBe('providers');
  expect(companionSettingsPage('/companion/settings/modules/brain/')).toBe('brain');
});

it('Nhà cung cấp như AIRI: tab, lọc giá, nhập và kiểm tra khóa; Bộ não chọn được; Companion gửi kèm khóa trong header', async () => {
  const page = await openCompanionSettings();
  fireEvent.click(page.getByRole('button', { name: /^Nhà cung cấp/ }));
  await page.findByRole('heading', { level: 1, name: 'Nhà cung cấp' });
  expect(window.location.pathname).toBe('/companion/settings/providers');
  const cards = () => page.getAllByRole('button').filter(item => item.classList.contains('companion-provider-card'));
  expect(cards().map(card => card.querySelector('strong')!.textContent)).toEqual(
    ['Peto', 'xAI', 'Anthropic', 'OpenAI', 'Google Gemini', 'DeepSeek', 'Mistral', 'Azure OpenAI', 'Ollama']);
  fireEvent.click(page.getByRole('button', { name: 'Có gói miễn phí' }));
  expect(cards().map(card => card.querySelector('strong')!.textContent)).toEqual(['Peto', 'Google Gemini', 'Mistral', 'Ollama']);
  fireEvent.click(page.getByRole('tab', { name: 'Nghe' }));
  expect(cards()[0].textContent).toContain('Có sẵn trong trình duyệt');
  fireEvent.click(page.getByRole('tab', { name: 'Bộ não' }));

  await connect(page, 'DeepSeek', 'sk-deep-12345678', ['deepseek-chat', 'deepseek-reasoner']);
  expect(window.location.pathname).toBe('/companion/settings/providers/deepseek');
  expect(api.checkProvider).toHaveBeenCalledWith('deepseek', 'sk-deep-12345678', undefined, expect.any(AbortSignal));
  expect(page.getByText(/Bộ não: mỗi lượt, khóa đi qua máy chủ Peto tới DeepSeek rồi bị bỏ/)).toBeTruthy();

  fireEvent.click(page.getByRole('button', { name: 'Chọn ở Bộ não' }));
  await page.findByRole('heading', { level: 1, name: 'Bộ não' });
  expect(window.location.pathname).toBe('/companion/settings/modules/brain');
  fireEvent.click(page.getByRole('combobox', { name: 'Nhà cung cấp' }));
  fireEvent.click(page.getByRole('option', { name: /DeepSeek/ }));
  fireEvent.click(page.getByRole('combobox', { name: 'Model' }));
  fireEvent.click(page.getByRole('option', { name: 'deepseek-reasoner' }));
  expect(page.getByText('Đang dùng khóa DeepSeek của bạn')).toBeTruthy();
  expect(page.getByText(/Peto không ghi nhớ và không đọc Trí nhớ/)).toBeTruthy();

  const payload = await sendInCompanion('hello');
  expect(payload).toMatchObject({ mode: 'companion', provider: { id: 'deepseek', model: 'deepseek-reasoner' },
    providerKey: 'sk-deep-12345678', webSearch: 'off' });
  expect(payload.searchKey).toBeUndefined();
  // Khung chat như AIRI không còn dòng trạng thái; tên nhà cung cấp còn trong dòng đọc cho trình đọc màn hình.
  expect(document.querySelector('.companion-head .sr-only')?.textContent).toContain('DeepSeek');
});

it('khóa Tavily ở Tra web chỉ gửi kèm khi nhà cung cấp cần và Tra web đang bật', async () => {
  localStorage.setItem('peto-voice-keys', JSON.stringify({ deepseek: { key: 'sk-deep-12345678' }, openai: { key: 'sk-open-12345678' } }));
  localStorage.setItem('peto-provider-models', JSON.stringify({ deepseek: ['deepseek-chat'], openai: ['gpt-6-luna'] }));
  localStorage.setItem('peto-companion-brain', JSON.stringify({ provider: 'deepseek', model: 'deepseek-chat' }));
  const page = await openCompanionSettings();
  fireEvent.click(page.getByRole('button', { name: /^Mô-đun/ }));
  fireEvent.click(await page.findByRole('button', { name: /^Tra web/ }));
  fireEvent.click(await page.findByRole('switch', { name: 'Cho Peto tra web trong Companion' }));
  expect(page.getByRole('alert').textContent).toContain('chưa có khóa Tavily');
  fireEvent.change(page.getByLabelText('Khóa API Tavily'), { target: { value: 'tvly-12345678' } });
  expect(page.queryByRole('alert')).toBeNull();

  let payload = await sendInCompanion('news?');
  expect(payload).toMatchObject({ webSearch: 'auto', provider: { id: 'deepseek' }, searchKey: 'tvly-12345678' });

  // OpenAI có tìm kiếm riêng: không gửi khóa Tavily.
  localStorage.setItem('peto-companion-brain', JSON.stringify({ provider: 'openai', model: 'gpt-6-luna' }));
  window.dispatchEvent(new StorageEvent('storage', { key: 'peto-companion-brain' }));
  await waitFor(() => expect(document.querySelector('.companion-head .sr-only')?.textContent).toContain('OpenAI'));
  payload = await sendInCompanion('more news?');
  expect(payload).toMatchObject({ provider: { id: 'openai', model: 'gpt-6-luna' }, providerKey: 'sk-open-12345678' });
  expect(payload.searchKey).toBeUndefined();
});

it('đổi hay xóa khóa thì phải kiểm tra lại; bộ não đang dùng nhà đó quay về Peto', async () => {
  localStorage.setItem('peto-voice-keys', JSON.stringify({ deepseek: { key: 'sk-deep-12345678' } }));
  localStorage.setItem('peto-provider-models', JSON.stringify({ deepseek: ['deepseek-chat'] }));
  localStorage.setItem('peto-companion-brain', JSON.stringify({ provider: 'deepseek', model: 'deepseek-chat' }));
  window.history.replaceState(null, '', '/companion/settings/providers/deepseek');
  render(<App />);
  // Vùng trang mang tên trang đang mở; đi sang trang khác thì tên đổi theo, nên tìm lại theo vai trò.
  const page = within(await screen.findByRole('main', { name: 'DeepSeek' }));
  expect(page.getByText('Đã kết nối · 1 model')).toBeTruthy();
  fireEvent.change(page.getByLabelText('Khóa API DeepSeek'), { target: { value: 'sk-deep-new-1234' } });
  expect(page.queryByText(/Đã kết nối/)).toBeNull();
  expect(localStorage.getItem('peto-companion-brain')).toBeNull();
  vi.mocked(api.checkProvider).mockRejectedValueOnce(new Error('DeepSeek từ chối khóa này. Kiểm tra lại khóa rồi thử lại.'));
  fireEvent.click(page.getByRole('button', { name: 'Kiểm tra kết nối' }));
  expect((await page.findByRole('alert')).textContent).toContain('từ chối khóa');

  const payload = await sendInCompanion('hi');
  expect(payload.provider).toBeUndefined();
  expect(payload.providerKey).toBeUndefined();
});

it('Azure OpenAI cần địa chỉ tài nguyên và tên bản triển khai; lượt gửi dùng bản triển khai làm model', async () => {
  window.history.replaceState(null, '', '/companion/settings/providers/azure-openai');
  render(<App />);
  const page = within(await screen.findByRole('main', { name: 'Azure OpenAI' }));
  fireEvent.change(page.getByLabelText('Địa chỉ tài nguyên'), { target: { value: 'https://peto-res.openai.azure.com' } });
  fireEvent.change(page.getByLabelText('Khóa API Azure OpenAI'), { target: { value: 'azure-key-12345678' } });
  vi.mocked(api.checkProvider).mockResolvedValueOnce({ models: [], deployment: true });
  fireEvent.click(page.getByRole('button', { name: 'Kiểm tra kết nối' }));
  await page.findByText('Khóa dùng được; điền tên bản triển khai.');
  expect(api.checkProvider).toHaveBeenCalledWith('azure-openai', 'azure-key-12345678', 'https://peto-res.openai.azure.com', expect.any(AbortSignal));
  fireEvent.change(page.getByLabelText('Tên bản triển khai'), { target: { value: 'my-gpt' } });
  expect(page.getByText('Đã kết nối')).toBeTruthy();
  fireEvent.click(page.getByRole('button', { name: 'Chọn ở Bộ não' }));
  fireEvent.click(await page.findByRole('combobox', { name: 'Nhà cung cấp' }));
  fireEvent.click(page.getByRole('option', { name: /Azure OpenAI/ }));
  expect((page.getByRole('combobox', { name: 'Bản triển khai' }) as HTMLButtonElement).textContent).toContain('my-gpt');
  const payload = await sendInCompanion('hi');
  expect(payload).toMatchObject({ provider: { id: 'azure-openai', model: 'my-gpt', endpoint: 'https://peto-res.openai.azure.com' },
    providerKey: 'azure-key-12345678' });
});
