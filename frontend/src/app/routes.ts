import { matchPath, type Location } from 'react-router';
import type { AppView } from './preferences';

export const VIEW_PATHS: Record<AppView, string> = { chat: '/', companion: '/companion', imagine: '/imagine', admin: '/admin' };
const IMAGE_PATTERN = '/imagine/:rootId/:imageId';
const CHAT_PATTERN = '/chat/:conversationId';

export function chatRoute(id: string) { return `/chat/${encodeURIComponent(id)}`; }

export function chatId(pathname: string): string | null {
  const id = matchPath(CHAT_PATTERN, pathname)?.params.conversationId;
  if (!id) return null;
  try { return decodeURIComponent(id); } catch { return id; }
}

export function imageRoute(rootId: string, imageId: string) {
  return `/imagine/${encodeURIComponent(rootId)}/${encodeURIComponent(imageId)}`;
}

export function imageMatch(pathname: string) { return matchPath(IMAGE_PATTERN, pathname); }

/** Chỉ chuyển hash điều hướng cũ; anchor của Docs và các trang khác giữ nguyên. */
export function legacyPath(location: Pick<Location, 'pathname' | 'hash'>): string | null {
  if (!['/', '/index.html', '/companion', '/imagine'].includes(location.pathname)) return null;
  const path = location.hash.slice(1);
  if (path === 'companion' || path === 'imagine' || imageMatch('/' + path)) return '/' + path;
  return null;
}

export function appPath(location: Pick<Location, 'pathname' | 'hash'>) {
  return legacyPath(location) ?? location.pathname;
}

/**
 * Trang cài đặt riêng của Companion (chủ web chốt ngày 13/10/2026, theo Settings bản web của AIRI). Mỗi trang một
 * đường dẫn cố định; đường dẫn lạ dưới /companion/settings không phải trang của ứng dụng.
 */
export type CompanionSettingsPage =
  | 'home' | 'modules' | 'voice' | 'hearing' | 'web-search' | 'beat-sync' | 'scene' | 'memory' | 'diagnostics';

const COMPANION_SETTINGS_PATHS: Record<CompanionSettingsPage, string> = {
  home: '/companion/settings/',
  modules: '/companion/settings/modules',
  voice: '/companion/settings/modules/voice',
  hearing: '/companion/settings/modules/hearing',
  'web-search': '/companion/settings/modules/web-search',
  'beat-sync': '/companion/settings/modules/beat-sync',
  scene: '/companion/settings/scene',
  memory: '/companion/settings/memory',
  diagnostics: '/companion/settings/diagnostics',
};

export function companionSettingsRoute(page: CompanionSettingsPage) { return COMPANION_SETTINGS_PATHS[page]; }

/** Trang cài đặt Companion của đường dẫn, có hay không có dấu "/" cuối; null nếu không phải trang đó. */
export function companionSettingsPage(pathname: string): CompanionSettingsPage | null {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
  for (const [page, route] of Object.entries(COMPANION_SETTINGS_PATHS) as [CompanionSettingsPage, string][]) {
    if (path === route.replace(/\/+$/, '')) return page;
  }
  return null;
}

export function appView(pathname: string): AppView {
  if (matchPath('/companion', pathname) || companionSettingsPage(pathname)) return 'companion';
  if (matchPath('/imagine', pathname) || imageMatch(pathname)) return 'imagine';
  if (matchPath('/admin', pathname)) return 'admin';
  return 'chat';
}
