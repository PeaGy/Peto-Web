import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import Docs from '../src/features/docs/Docs';

const pages = [
  { slug: 'bat-dau', title: 'Bắt đầu cùng Peto', group: 'Bắt đầu', description: 'Một nơi để trò chuyện.', keywords: [], body: '## Mở Peto\nNội dung.' },
  {
    slug: 'giong-noi', title: 'Giọng nói', group: 'Companion', description: 'Cấu hình giọng', keywords: ['tts'],
    body: '## Chọn giọng\nNội dung hướng dẫn.\n\n## Khi chưa nói được\nKiểm tra nguồn.\n\n```powershell\npeto status\n```',
  },
  { slug: 'nhan-vat', title: 'Nhân vật & bối cảnh', group: 'Companion', description: 'Nhập Live2D.', keywords: [], body: '## Nhập nhân vật\nNội dung.' },
  { slug: 'cai-agent', title: 'Cài Peto Agent', group: 'Agent CLI', description: 'Kết nối Peto.', keywords: ['cli'], body: '## Cài\n`irm`' },
];
const data = { version: '0.14.1', pages };
const REST = 'translate3d(0.0px, 0.0px, 0)';

function stubMotion(reduced: boolean) {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: query.includes('reduce') ? reduced : false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
}

function setScroll(value: number) {
  Object.defineProperty(window, 'scrollY', { value, configurable: true });
}

beforeEach(() => {
  localStorage.clear();
  history.replaceState({}, '', '/docs/');
  setScroll(0);
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => data }));
  stubMotion(false);
});
afterEach(() => { vi.unstubAllGlobals(); setScroll(0); });

describe('tìm kiếm', () => {
  it('finds unaccented text from the header box and opens that section', async () => {
    render(<Docs />);
    const search = screen.getByRole('combobox', { name: 'Tìm trong Peto Docs' });
    fireEvent.focus(search);
    fireEvent.change(search, { target: { value: 'giong noi' } });
    fireEvent.click(await screen.findByRole('option', { name: /Giọng nói/ }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Giọng nói' })).toBeTruthy();
    expect(location.pathname).toBe('/docs/giong-noi/');
    expect(location.hash).toBe('#chon-giong');
    expect(document.title).toBe('Giọng nói · Peto Docs');
    expect(screen.getByRole('link', { name: 'Bản Markdown' }).getAttribute('href')).toBe('/api/docs/giong-noi.md');
  });

  it('suggests articles while empty and opens one with the keyboard', async () => {
    render(<Docs />);
    const search = screen.getByRole('combobox', { name: 'Tìm trong Peto Docs' });
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    expect(document.activeElement).toBe(search);
    fireEvent.focus(search);
    expect(await screen.findByRole('option', { name: /Bắt đầu cùng Peto/ })).toBeTruthy();
    fireEvent.keyDown(search, { key: 'ArrowDown' });
    expect(screen.getByRole('option', { name: /Cài Peto Agent/ }).getAttribute('aria-selected')).toBe('true');
    fireEvent.keyDown(search, { key: 'Enter' });
    expect(await screen.findByRole('heading', { level: 1, name: 'Cài Peto Agent' })).toBeTruthy();
    expect(screen.getByText('CLI 0.14.1')).toBeTruthy();
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('allows retry after a failed request', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
    render(<Docs />);
    const alert = await screen.findByRole('alert');
    fireEvent.click(within(alert).getByRole('button', { name: 'Thử lại' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    const search = screen.getByRole('combobox', { name: 'Tìm trong Peto Docs' });
    fireEvent.focus(search);
    fireEvent.change(search, { target: { value: 'giong' } });
    expect(await screen.findByRole('option', { name: /Giọng nói/ })).toBeTruthy();
  });
});

describe('trang bài', () => {
  it('marks the group and article, and moves with tabs, pager, drawer and the back button', async () => {
    history.replaceState({}, '', '/docs/giong-noi/');
    render(<Docs />);
    expect(await screen.findByRole('heading', { level: 1, name: 'Giọng nói' })).toBeTruthy();
    const tabs = screen.getByRole('navigation', { name: 'Nhóm hướng dẫn' });
    expect(within(tabs).getByRole('link', { name: 'Companion' }).getAttribute('aria-current')).toBe('true');
    expect(within(tabs).getByRole('link', { name: 'Agent CLI' }).getAttribute('href')).toBe('/docs/cai-agent/');
    const side = screen.getByRole('complementary', { name: 'Bài trong nhóm Companion' });
    expect(within(side).getByRole('link', { name: 'Giọng nói' }).getAttribute('aria-current')).toBe('page');
    const outline = screen.getByRole('navigation', { name: 'Trên trang này' });
    expect(within(outline).getByRole('link', { name: 'Khi chưa nói được' }).getAttribute('href')).toBe('#khi-chua-noi-duoc');

    fireEvent.click(screen.getByRole('link', { name: /Tiếp theo/ }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Nhân vật & bối cảnh' })).toBeTruthy();
    expect(location.pathname).toBe('/docs/nhan-vat/');

    const menu = screen.getByRole('button', { name: 'Danh mục' });
    fireEvent.click(menu);
    expect(menu.getAttribute('aria-expanded')).toBe('true');
    const drawer = screen.getByRole('dialog', { name: 'Danh mục hướng dẫn' });
    fireEvent.click(within(drawer).getByRole('link', { name: 'Bắt đầu cùng Peto' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Bắt đầu cùng Peto' })).toBeTruthy();
    expect(menu.getAttribute('aria-expanded')).toBe('false');

    act(() => {
      history.replaceState({}, '', '/docs/giong-noi/');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(await screen.findByRole('heading', { level: 1, name: 'Giọng nói' })).toBeTruthy();
  });

  it('keeps the header clear at the top of an article and frosts it once scrolled', async () => {
    history.replaceState({}, '', '/docs/giong-noi/');
    render(<Docs />);
    await screen.findByRole('heading', { level: 1, name: 'Giọng nói' });
    const header = screen.getByRole('banner');
    expect(header.hasAttribute('data-glass')).toBe(false);
    setScroll(240);
    act(() => { window.dispatchEvent(new Event('scroll')); });
    expect(header.hasAttribute('data-glass')).toBe(true);
    expect(screen.getByRole('navigation', { name: 'Nhóm hướng dẫn' }).hasAttribute('data-glass')).toBe(true);
  });

  it('copies a code block and the whole article as Markdown', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    history.replaceState({}, '', '/docs/giong-noi/');
    render(<Docs />);
    expect(await screen.findByText('PowerShell')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Sao chép khối này' }));
    expect(await screen.findByRole('button', { name: 'Đã sao chép' })).toBeTruthy();
    expect(writeText).toHaveBeenCalledWith('peto status\n');
    fireEvent.click(screen.getByRole('button', { name: 'Chép Markdown' }));
    expect(await screen.findByRole('button', { name: 'Đã chép' })).toBeTruthy();
    expect(writeText).toHaveBeenLastCalledWith(expect.stringMatching(/^# Giọng nói\n\n## Chọn giọng/));
  });

  it('says so when an article does not exist', async () => {
    history.replaceState({}, '', '/docs/khong-co/');
    render(<Docs />);
    expect(await screen.findByRole('heading', { level: 1, name: 'Không tìm thấy bài viết' })).toBeTruthy();
    // Tiêu đề tab cập nhật trong effect sau khi render; chờ nó khi cả bộ test chạy song song.
    await waitFor(() => expect(document.title).toBe('Không tìm thấy bài · Peto Docs'));
  });
});

describe('trang đầu và hiệu ứng', () => {
  it('moves the character layers with the mouse', async () => {
    render(<Docs />);
    expect(screen.getByRole('heading', { level: 1, name: 'Peto' })).toBeTruthy();
    const art = document.querySelector<HTMLElement>('.docs-cover img')!;
    expect(art.style.transform).toBe(REST);
    fireEvent.mouseMove(window, { clientX: innerWidth, clientY: innerHeight / 2 });
    await waitFor(() => expect(art.style.transform).toBe(`translate3d(${(-0.5 * 0.02 * innerWidth).toFixed(1)}px, 0.0px, 0)`));
  });

  it('follows the device reduced-motion setting until the switch is used', async () => {
    stubMotion(true);
    render(<Docs />);
    const toggle = screen.getByRole('switch', { name: 'Hiệu ứng chuyển động' });
    expect(toggle.getAttribute('aria-checked')).toBe('false');
    const art = document.querySelector<HTMLElement>('.docs-cover img')!;
    fireEvent.mouseMove(window, { clientX: innerWidth, clientY: innerHeight / 2 });
    await new Promise(resolve => setTimeout(resolve, 50));
    expect(art.style.transform).toBe(REST);

    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-checked')).toBe('true');
    expect(localStorage.getItem('peto-docs-motion')).toBe('on');
    expect(document.querySelector('.docs')!.classList.contains('docs-motion')).toBe(true);
  });

  it('takes "Luôn cử động" from Peto settings on the same site', () => {
    stubMotion(true);
    localStorage.setItem('peto-character-motion', 'always');
    render(<Docs />);
    expect(screen.getByRole('switch', { name: 'Hiệu ứng chuyển động' }).getAttribute('aria-checked')).toBe('true');
  });

  it('remembers the light theme', () => {
    render(<Docs />);
    const theme = screen.getByRole('switch', { name: 'Nền tối' });
    expect(theme.getAttribute('aria-checked')).toBe('true');
    fireEvent.click(theme);
    expect(theme.getAttribute('aria-checked')).toBe('false');
    expect(localStorage.getItem('peto-docs-theme')).toBe('light');
    expect(document.querySelector('.docs')!.classList.contains('docs-light')).toBe(true);
  });
});
