import { matchPath, type Location } from 'react-router';
import type { AppView } from './preferences';

export const VIEW_PATHS: Record<AppView, string> = { chat: '/', companion: '/companion', imagine: '/imagine' };
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

export function appView(pathname: string): AppView {
  if (matchPath('/companion', pathname)) return 'companion';
  if (matchPath('/imagine', pathname) || imageMatch(pathname)) return 'imagine';
  return 'chat';
}
