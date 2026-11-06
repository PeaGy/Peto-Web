import { useEffect, useState } from 'react';

/** Bản phát hành mới nhất của ứng dụng Peto Agent, máy chủ đọc từ GitHub Releases (/api/agent/desktop/release). */
export type Installer = { os: 'windows' | 'macos'; arch: string; name: string; url: string; size: number; sha256: string | null };
export type Release =
  | { available: true; version: string; published_at: string | null; prerelease: boolean; notes_url: string;
      releases_url: string; installers: Installer[] }
  | { available: false; releases_url: string | null };
export type ReleaseState = { kind: 'loading' } | { kind: 'ready'; release: Release };

const UNAVAILABLE: Release = { available: false, releases_url: null };

function valid(data: unknown): data is Release {
  if (!data || typeof data !== 'object') return false;
  const item = data as Record<string, unknown>;
  if (item.available !== true) return item.available === false;
  return typeof item.version === 'string' && Array.isArray(item.installers) && typeof item.notes_url === 'string';
}

/** Đọc một lần khi mở trang. Lỗi mạng hay dữ liệu lạ thì coi như chưa có bản phát hành: trang vẫn còn hướng dẫn CLI. */
export function useRelease(): ReleaseState {
  const [state, setState] = useState<ReleaseState>({ kind: 'loading' });
  useEffect(() => {
    const abort = new AbortController();
    fetch('/api/agent/desktop/release', { signal: abort.signal })
      .then(response => (response.ok ? response.json() : UNAVAILABLE))
      .then((data: unknown) => setState({ kind: 'ready', release: valid(data) ? data : UNAVAILABLE }))
      .catch((reason: unknown) => {
        if ((reason as Error)?.name !== 'AbortError') setState({ kind: 'ready', release: UNAVAILABLE });
      });
    return () => abort.abort();
  }, []);
  return state;
}

/** Hệ điều hành của máy đang xem trang, để chọn sẵn bộ cài phù hợp cho nút chính. */
export function visitorOs(): 'windows' | 'macos' | 'other' {
  const platform = ((navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform
    || navigator.userAgent).toLowerCase();
  if (/iphone|ipad|android/.test(platform)) return 'other';
  if (platform.includes('mac')) return 'macos';
  return platform.includes('win') ? 'windows' : 'other';
}

/** Bộ cài cho nút chính: đúng hệ điều hành của máy nếu có, không thì bản Windows 64-bit (đối tượng chính hiện nay). */
export function primaryInstaller(installers: Installer[], os = visitorOs()): Installer | undefined {
  const rank = (item: Installer) => (item.os === (os === 'other' ? 'windows' : os) ? 0 : 2)
    + (item.arch === 'x64' || item.arch === 'universal' || item.arch === '' ? 0 : 1);
  return [...installers].sort((a, b) => rank(a) - rank(b))[0];
}

export function installerLabel(item: Installer): string {
  if (item.os === 'macos') {
    return item.arch === 'arm64' ? 'macOS · Apple Silicon' : item.arch === 'x64' ? 'macOS · Intel' : 'macOS';
  }
  return item.arch === 'arm64' ? 'Windows 11 trên ARM' : 'Windows 10/11 · 64-bit';
}

export function osName(item: Installer): string {
  return item.os === 'macos' ? 'macOS' : 'Windows';
}

/** Cỡ tệp theo cách Windows hiện (1 MB = 1024² byte), dấu phẩy thập phân kiểu Việt. */
export function formatSize(bytes: number): string {
  const mb = bytes / 1024 ** 2;
  if (mb >= 1024) return `${(mb / 1024).toFixed(1).replace('.', ',')} GB`;
  return `${Math.max(1, Math.round(mb))} MB`;
}

export function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
}
