import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { preloadLazyParts } from './lazyParts';
import App from '../src/App';
import * as api from '../src/api';
import * as documentApi from '../src/documentApi';
import { DiagramCard, DiagramContext } from '../src/DiagramCard';

// Mermaid thật cần trình duyệt đo chữ; ở đây thay bằng bản giả trả SVG có viewBox, đủ để kiểm tra thẻ và bảng.
const mermaid = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(async (id: string, code: string) => {
    if (code.includes('SAI')) throw new Error('Parse error on line 2:\nExpecting SQE, got PS');
    return { svg: `<svg id="${id}" width="100%" style="max-width: 320px;" viewBox="0 0 320 160"><text>${code.length}</text></svg>` };
  }),
}));
vi.mock('mermaid', () => ({ default: mermaid }));
vi.mock('../src/documentApi', async original => ({ ...await original<typeof import('../src/documentApi')>(), listDocuments: vi.fn(), getDocument: vi.fn() }));
vi.mock('../src/api', async (original) => ({
  ...await original<typeof import('../src/api')>(),
  getAuthState: vi.fn(), listConversations: vi.fn(), getMessages: vi.fn(), conversationVersions: vi.fn(),
  listImagineJobs: vi.fn(), listAgentDevices: vi.fn(), getCompanionMemory: vi.fn(),
}));

const CLASSES = '---\ntitle: Sơ đồ lớp thư viện\n---\nclassDiagram\n  class DocGia\n  class Sach\n  DocGia --> Sach : mượn';
const SEQUENCE = 'sequenceDiagram\n  actor U as Người dùng\n  U->>Web: Đăng nhập';
const ANSWER = `Hai sơ đồ đây:\n\n\`\`\`mermaid\n${CLASSES}\n\`\`\`\n\nVà luồng đăng nhập:\n\n\`\`\`mermaid\n${SEQUENCE}\n\`\`\``;

beforeAll(preloadLazyParts);

beforeEach(() => {
  vi.resetAllMocks();
  mermaid.render.mockImplementation(async (id: string, code: string) => {
    if (code.includes('SAI')) throw new Error('Parse error on line 2:\nExpecting SQE, got PS');
    return { svg: `<svg id="${id}" width="100%" style="max-width: 320px;" viewBox="0 0 320 160"><text>${code.length}</text></svg>` };
  });
  localStorage.clear();
  sessionStorage.clear();
  window.history.replaceState(null, '', '/');
  vi.mocked(api.getAuthState).mockResolvedValue({ authenticated: true, login_configured: true,
    providers: { discord: true, google: true, guest: true },
    user: { id: 'acc-111', provider: 'discord', username: 'demo', display_name: 'Demo', avatar_url: '' } });
  vi.mocked(api.listConversations).mockResolvedValue({ conversations: [
    { id: 'A', title: 'A', created_at: 0, updated_at: 0, message_count: 2 },
    { id: 'B', title: 'B', created_at: 0, updated_at: 0, message_count: 0 },
  ], has_more: false });
  vi.mocked(api.conversationVersions).mockResolvedValue([]);
  vi.mocked(api.getMessages).mockImplementation(async (id: string) => id === 'A'
    ? [{ role: 'user', content: 'Vẽ sơ đồ lớp và sơ đồ tuần tự' }, { role: 'assistant', content: ANSWER }]
    : []);
  vi.mocked(api.listImagineJobs).mockResolvedValue([]);
  vi.mocked(api.listAgentDevices).mockResolvedValue({ devices: [], steps_used: 0, steps_limit: 200 });
  vi.mocked(api.getCompanionMemory).mockResolvedValue({ available: true, enabled: true, pending: false, limit: 50, memories: [] });
  vi.mocked(documentApi.listDocuments).mockResolvedValue({ documents: [] });
  Element.prototype.scrollTo = vi.fn();
});

afterEach(() => { document.documentElement.removeAttribute('data-theme'); });

async function openDiagrams() {
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'A', exact: true }, { timeout: 5000 }));
  return screen.findByRole('button', { name: /Sơ đồ lớp thư viện/ });
}

it('khối mermaid thành thẻ; bấm thì bảng bên phải mở, chuyển qua lại, xem mã và đóng', async () => {
  const first = await openDiagrams();
  // Thẻ hiện ngay, ảnh thu nhỏ vẽ xong một nhịp sau.
  // Tên đã bắt đầu bằng loại ("Sơ đồ lớp …") nên thẻ không ghi lặp loại.
  expect(await within(first).findByText('Bấm để xem lớn')).toBeTruthy();
  expect(screen.getByRole('button', { name: /Sơ đồ tuần tự/ })).toBeTruthy();
  expect(document.querySelector('.code-block')).toBeNull(); // không còn hiện như khối code thường

  fireEvent.click(first);
  const panel = await screen.findByRole('dialog', { name: 'Sơ đồ trong hội thoại' });
  expect(first.getAttribute('aria-pressed')).toBe('true');
  expect(within(panel).getByText('1 / 2')).toBeTruthy();
  expect(within(panel).getByTitle('Sơ đồ lớp thư viện')).toBeTruthy();
  expect(document.querySelector('.chat-layout')!.className).toContain('documents-open');

  fireEvent.click(within(panel).getByRole('button', { name: 'Sơ đồ sau' }));
  expect(within(panel).getByText('2 / 2')).toBeTruthy();
  expect(within(panel).getByTitle('Sơ đồ tuần tự')).toBeTruthy();
  expect((within(panel).getByRole('button', { name: 'Sơ đồ sau' }) as HTMLButtonElement).disabled).toBe(true);

  fireEvent.click(within(panel).getByRole('tab', { name: 'Mã' }));
  expect(panel.querySelector('pre')!.textContent).toBe(SEQUENCE);
  fireEvent.click(within(panel).getByRole('button', { name: 'Tải' }));
  expect(within(panel).getAllByRole('menuitem').map((item) => item.querySelector('strong')!.textContent)).toEqual(['Ảnh PNG', 'Ảnh SVG', 'PDF']);
  await waitFor(() => expect(within(panel).getByText('draw.io').closest('a')!.getAttribute('href')).toMatch(/^https:\/\/app\.diagrams\.net\/.*#create=/));

  fireEvent.click(within(panel).getByRole('button', { name: 'Đóng bảng sơ đồ' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Sơ đồ trong hội thoại' })).toBeNull());
  expect(document.querySelector('.chat-layout')!.className).not.toContain('documents-open');
});

it('mở bảng tài liệu thì bảng sơ đồ nhường chỗ, đổi hội thoại thì bảng sơ đồ đóng', async () => {
  fireEvent.click(await openDiagrams());
  await screen.findByRole('dialog', { name: 'Sơ đồ trong hội thoại' });
  fireEvent.click(screen.getByRole('button', { name: 'Mở bảng tài liệu' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Sơ đồ trong hội thoại' })).toBeNull());

  fireEvent.click(screen.getByRole('button', { name: /Sơ đồ tuần tự/ }));
  await screen.findByRole('dialog', { name: 'Sơ đồ trong hội thoại' });
  expect(screen.queryByRole('complementary', { name: 'Tài liệu trong hội thoại' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'B', exact: true }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Sơ đồ trong hội thoại' })).toBeNull());
});

it('sơ đồ viết sai hiện lỗi kèm mã; tin đang viết chỉ báo đang vẽ, chưa gọi Mermaid', async () => {
  const open = vi.fn();
  const { rerender } = render(
    <DiagramContext.Provider value={{ current: null, open }}>
      <DiagramCard source={'flowchart LR\n  B[Gọi API (POST /login)] SAI'} pending={false} />
    </DiagramContext.Provider>,
  );
  expect(await screen.findByText('Chưa vẽ được sơ đồ này.')).toBeTruthy();
  expect(screen.getByText(/Lỗi cú pháp ở dòng 2 của mã sơ đồ/)).toBeTruthy();
  expect(screen.getByText(/B\[Gọi API \(POST \/login\)\] SAI/)).toBeTruthy();

  mermaid.render.mockClear();
  rerender(
    <DiagramContext.Provider value={{ current: null, open }}>
      <DiagramCard source={'classDiagram\n  class A'} pending />
    </DiagramContext.Provider>,
  );
  expect(screen.getByRole('status').textContent).toContain('Đang vẽ sơ đồ…');
  expect(mermaid.render).not.toHaveBeenCalled();

  rerender(
    <DiagramContext.Provider value={{ current: null, open }}>
      <DiagramCard source={'classDiagram\n  class A'} pending={false} />
    </DiagramContext.Provider>,
  );
  fireEvent.click(await screen.findByRole('button', { name: /Sơ đồ lớp/ }));
  expect(open).toHaveBeenCalledWith('classDiagram\n  class A');
});

it('đổi nền sáng tối thì vẽ lại sơ đồ theo màu mới', async () => {
  document.documentElement.dataset.theme = 'dark';
  render(<DiagramCard source={'classDiagram\n  class A'} pending={false} />);
  await screen.findByRole('button', { name: /Sơ đồ lớp/ });
  await waitFor(() => expect(mermaid.initialize).toHaveBeenLastCalledWith(expect.objectContaining({ darkMode: true })));
  document.documentElement.dataset.theme = 'light';
  await waitFor(() => expect(mermaid.initialize).toHaveBeenLastCalledWith(expect.objectContaining({ darkMode: false })));
  expect(mermaid.initialize).toHaveBeenLastCalledWith(expect.objectContaining({ securityLevel: 'strict', htmlLabels: false }));
});

it('sơ đồ phân làn đẩy tên sơ đồ lên trên hàng tên làn, lưu đồ thường giữ lề mặc định', async () => {
  const margin = () => (mermaid.initialize.mock.lastCall?.[0] as { flowchart?: { titleTopMargin?: number } }).flowchart?.titleTopMargin;
  const { unmount } = render(<DiagramCard source={'swimlane-beta\n  subgraph DG["Độc giả"]\n    A(Chọn sách)\n  end'} pending={false} />);
  await screen.findByRole('button', { name: /Sơ đồ phân làn/ });
  await waitFor(() => expect(margin()).toBeGreaterThan(25));
  unmount();
  render(<DiagramCard source={'flowchart TD\n  A --> B'} pending={false} />);
  await screen.findByRole('button', { name: /Lưu đồ/ });
  await waitFor(() => expect(margin()).toBe(25));
});
