import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/app/App';
import * as api from '../src/shared/api/api';
import * as routes from '../src/app/routes';
import * as projectApi from '../src/features/projects/projectApi';
import * as documentApi from '../src/features/documents/documentApi';

// Companion bản AIRI (cờ companion_airi của /api/auth/me, từ 15/11/2026): mọi lối vào Companion là điều hướng thật sang
// /companion/, và mã Companion React không được tải. Cờ tắt thì như cũ.

// Mô-đun chỉ được nạp một lần trong tệp: các test "bật" đứng trước nên `loaded` còn false là chưa ai tải Companion React.
const companionModule = vi.hoisted(() => ({ loaded: false }));
vi.mock('../src/features/companion/Companion', () => {
  companionModule.loaded = true;
  return { default: () => <main aria-label="Companion React" /> };
});
vi.mock('../src/app/routes', async original => ({
  ...await original<typeof import('../src/app/routes')>(), openAiriCompanion: vi.fn(),
}));
vi.mock('../src/features/projects/projectApi', async original => ({ ...await original<typeof import('../src/features/projects/projectApi')>(), listProjects: vi.fn() }));
vi.mock('../src/features/documents/documentApi', async original => ({ ...await original<typeof import('../src/features/documents/documentApi')>(), listDocuments: vi.fn() }));
vi.mock('../src/shared/api/api', async original => ({
  ...await original<typeof import('../src/shared/api/api')>(),
  getAuthState: vi.fn(), getAppInfo: vi.fn(), listConversations: vi.fn(), getMessages: vi.fn(), getChatTurnReceipt: vi.fn(),
  conversationVersions: vi.fn(), listImagineJobs: vi.fn(), getCompanionMemory: vi.fn(), listCompanionCards: vi.fn(),
}));

function signedIn(companionAiri: boolean | undefined) {
  vi.mocked(api.getAuthState).mockResolvedValue({ authenticated: true, login_configured: true, companion_airi: companionAiri,
    providers: { discord: true, google: true, github: true },
    user: { id: 'acc-111', provider: 'discord', username: 'demo', display_name: 'Demo', avatar_url: '' } });
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  window.history.replaceState(null, '', '/');
  vi.mocked(api.getAppInfo).mockResolvedValue({ name: 'Peto', avatar_url: null });
  vi.mocked(projectApi.listProjects).mockResolvedValue([]);
  vi.mocked(documentApi.listDocuments).mockResolvedValue({ documents: [] });
  vi.mocked(api.listConversations).mockResolvedValue({ conversations: [], has_more: false });
  vi.mocked(api.getMessages).mockResolvedValue([]);
  vi.mocked(api.conversationVersions).mockResolvedValue([]);
  vi.mocked(api.getChatTurnReceipt).mockResolvedValue({ state: 'missing' });
  vi.mocked(api.listImagineJobs).mockResolvedValue([]);
  vi.mocked(api.listCompanionCards).mockRejectedValue(new Error('không dùng'));
  vi.mocked(api.getCompanionMemory).mockResolvedValue({ available: true, enabled: true, pending: false, sorting: false, limit: 20, memories: [] });
  Element.prototype.scrollTo = vi.fn();
});

async function openApp() {
  render(<App />);
  await screen.findByLabelText('Nhắn cho Peto', {}, { timeout: 5000 });
}

const companionButton = () => screen.getByRole('button', { name: 'Companion', exact: true });

describe('Companion bản AIRI bật', () => {
  it('nút Companion trên thanh bên điều hướng thật sang /companion/, không tải Companion React', async () => {
    signedIn(true);
    await openApp();
    fireEvent.pointerEnter(companionButton());
    fireEvent.focus(companionButton());
    fireEvent.click(companionButton());
    expect(routes.openAiriCompanion).toHaveBeenCalledOnce();
    expect(vi.mocked(routes.openAiriCompanion).mock.calls[0][0]).toBeFalsy();
    expect(window.location.pathname).toBe('/');
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 50)); });
    expect(companionModule.loaded).toBe(false);
    expect(screen.queryByRole('main', { name: 'Companion React' })).toBeNull();
  });

  it.each(['/#companion', '/companion', '/companion/settings/modules/voice'])(
    'đường dẫn %s trong ứng dụng React chuyển hẳn sang /companion/ (thay mục lịch sử)', async path => {
      signedIn(true);
      window.history.replaceState(null, '', path);
      render(<App />);
      await waitFor(() => expect(routes.openAiriCompanion).toHaveBeenCalledWith(true));
      expect(screen.getByLabelText('Đang mở Companion')).toBeTruthy();
      expect(companionModule.loaded).toBe(false);
    });

  it('React đang ở chính /companion/ (Vite lúc dev) thì không tự tải lại mãi', async () => {
    signedIn(true);
    window.history.replaceState(null, '', '/companion/');
    render(<App />);
    expect(await screen.findByText(/Companion mới chỉ mở được qua máy chủ Peto/)).toBeTruthy();
    expect(routes.openAiriCompanion).not.toHaveBeenCalled();
    expect(companionModule.loaded).toBe(false);
  });

  it('Trí nhớ không còn nói Companion dùng trí nhớ này', async () => {
    signedIn(true);
    await openApp();
    fireEvent.click(screen.getByRole('button', { name: /^Tài khoản · / }));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Cài đặt' }));
    const dialog = within(screen.getByRole('dialog', { name: 'Cài đặt' }));
    fireEvent.click(dialog.getByRole('button', { name: 'Trí nhớ', exact: true }));
    expect(await dialog.findByText(/Peto ghi lại điều bạn kể trong Chat, kể cả/)).toBeTruthy();
    expect(dialog.queryByText(/trong Chat và Companion/)).toBeNull();
  });
});

describe('Companion bản AIRI tắt (như cũ)', () => {
  it.each([false, undefined])('companion_airi=%s: nút Companion mở Companion React trong ứng dụng', async flag => {
    signedIn(flag);
    await openApp();
    fireEvent.click(companionButton());
    await waitFor(() => expect(window.location.pathname).toBe('/companion'));
    expect(await screen.findByRole('main', { name: 'Companion React' })).toBeTruthy();
    expect(routes.openAiriCompanion).not.toHaveBeenCalled();
    expect(companionModule.loaded).toBe(true);
  });
});
