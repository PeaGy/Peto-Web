import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Download from '../src/features/download/Download';
import { formatSize, primaryInstaller, type Installer } from '../src/features/download/release';

const BASE = 'https://github.com/PeaGy/peto-harness/releases';
const windows: Installer = {
  os: 'windows', arch: 'x64', name: 'deepseek-harness-0.2.2-win-x64.exe', url: `${BASE}/download/v0.2.2-peto.1/win.exe`,
  size: 327_155_712, sha256: null,
};
const mac: Installer = { os: 'macos', arch: 'arm64', name: 'peto-arm64.dmg', url: `${BASE}/download/v0.2.2-peto.1/mac.dmg`, size: 1, sha256: null };
const release = {
  available: true, version: '0.2.2-peto.1', published_at: '2026-11-05T09:30:00Z', prerelease: false,
  notes_url: `${BASE}/tag/v0.2.2-peto.1`, releases_url: BASE, installers: [windows],
};

function serve(body: unknown, ok = true) {
  const fetch = vi.fn().mockResolvedValue({ ok, json: async () => body });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

function stubMotion(reduced: boolean) {
  document.documentElement.dataset.motion = reduced ? 'reduced' : 'full';
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
}

beforeEach(() => {
  localStorage.clear();
  history.replaceState({}, '', '/download/');
  stubMotion(false);
});
afterEach(() => { vi.unstubAllGlobals(); });

describe('nút tải', () => {
  it('links the main button to the latest Windows installer from the server', async () => {
    const fetch = serve(release);
    render(<Download />);
    const links = await screen.findAllByRole('link', { name: 'Tải cho Windows' });
    // Nút ở hero và nút ở khối cuối trang.
    expect(links.map(link => link.getAttribute('href'))).toEqual([windows.url, windows.url]);
    expect(screen.getByRole('link', { name: 'Tải xuống' }).getAttribute('href')).toBe(windows.url);
    expect(fetch).toHaveBeenCalledWith('/api/agent/desktop/release', expect.anything());
    expect(screen.getByText(/0\.2\.2-peto\.1/).closest('p')?.textContent).toMatch(/05\/11\/2026 · Windows 10\/11 · 64-bit · 312 MB/);
    expect(document.title).toBe('Tải Peto Agent · Peto');
  });

  it('opens the other downloads with macOS marked as coming and closes on Escape', async () => {
    serve(release);
    render(<Download />);
    const toggle = await screen.findByRole('button', { name: 'Các bản tải khác' });
    fireEvent.click(toggle);
    const menu = screen.getByRole('menu', { name: 'Các bản tải' });
    expect(menu.textContent).toContain('Sắp có');
    expect(document.activeElement?.getAttribute('href')).toBe(windows.url);
    expect(screen.getByRole('menuitem', { name: /Dòng lệnh/ }).getAttribute('href')).toBe('#cli');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    expect(document.activeElement).toBe(toggle);
  });

  it('falls back to the command line installer when no release exists yet', async () => {
    serve({ available: false, releases_url: null });
    render(<Download />);
    expect((await screen.findAllByRole('link', { name: 'Cài bản dòng lệnh' }))[0].getAttribute('href')).toBe('#cli');
    expect(screen.getByText(/Bộ cài cho Windows đang được chuẩn bị/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Các bản tải khác' })).toBeNull();
  });

  it('treats a failed or odd response as no release', async () => {
    serve({ available: true }, true);
    render(<Download />);
    expect(await screen.findByText(/Bộ cài cho Windows đang được chuẩn bị/)).toBeTruthy();
  });
});

describe('trang', () => {
  it('copies the real CLI install command for this site', async () => {
    serve(release);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    render(<Download />);
    fireEvent.click(screen.getByRole('button', { name: /Sao chép/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(`irm ${location.origin}/install.ps1 | iex`));
    expect(await screen.findByRole('button', { name: /Đã chép/ })).toBeTruthy();
  });

  it('pauses a looping demo from its button', async () => {
    serve(release);
    render(<Download />);
    const pause = screen.getAllByRole('button', { name: 'Tạm dừng minh họa' })[0];
    fireEvent.click(pause);
    expect(pause.getAttribute('aria-pressed')).toBe('true');
    expect(pause.closest('article')?.hasAttribute('data-paused')).toBe(true);
  });

  it('reveals blocks once they scroll into view and shows everything when motion is off', async () => {
    serve(release);
    const seen: Array<(entries: unknown[]) => void> = [];
    vi.stubGlobal('IntersectionObserver', class {
      constructor(callback: (entries: unknown[]) => void) { seen.push(callback); }
      observe() {}
      unobserve() {}
      disconnect() {}
    });
    const { container, unmount } = render(<Download />);
    const blocks = [...container.querySelectorAll<HTMLElement>('[data-reveal]')];
    expect(blocks.length).toBeGreaterThan(5);
    expect(blocks.every(block => !('shown' in block.dataset))).toBe(true);
    act(() => seen[0]([{ isIntersecting: true, target: blocks[0], boundingClientRect: { bottom: 100 } }]));
    expect('shown' in blocks[0].dataset).toBe(true);
    expect('shown' in blocks[1].dataset).toBe(false);
    unmount();

    localStorage.setItem('peto-docs-motion', 'off');
    const still = render(<Download />);
    expect([...still.container.querySelectorAll<HTMLElement>('[data-reveal]')].every(block => 'shown' in block.dataset)).toBe(true);
    expect(still.container.querySelector('.docs-motion')).toBeNull();
  });
});

describe('chọn bộ cài', () => {
  it('prefers the visitor system, then Windows 64-bit', () => {
    expect(primaryInstaller([mac, windows], 'windows')).toBe(windows);
    expect(primaryInstaller([windows, mac], 'macos')).toBe(mac);
    expect(primaryInstaller([mac, windows], 'other')).toBe(windows);
    expect(primaryInstaller([{ ...windows, arch: 'arm64' }, windows], 'windows')).toBe(windows);
  });

  it('formats sizes like Windows does', () => {
    expect(formatSize(327_155_712)).toBe('312 MB');
    expect(formatSize(1.5 * 1024 ** 3)).toBe('1,5 GB');
  });
});
