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
  | 'home' | 'character' | 'modules' | 'brain' | 'voice' | 'hearing' | 'web-search' | 'beat-sync' | 'providers' | 'provider'
  | 'scene' | 'memory' | 'diagnostics' | 'cards' | 'card-new' | 'card' | 'card-edit';
/** Trang có đường dẫn cố định; trang một nhà cung cấp ('provider') và một thẻ ('card', 'card-edit') có thêm mã ở cuối. */
export type FixedCompanionSettingsPage = Exclude<CompanionSettingsPage, 'provider' | 'card' | 'card-edit'>;

const COMPANION_SETTINGS_PATHS: Record<FixedCompanionSettingsPage, string> = {
  home: '/companion/settings/',
  character: '/companion/settings/character',
  modules: '/companion/settings/modules',
  brain: '/companion/settings/modules/brain',
  providers: '/companion/settings/providers',
  voice: '/companion/settings/modules/voice',
  hearing: '/companion/settings/modules/hearing',
  'web-search': '/companion/settings/modules/web-search',
  'beat-sync': '/companion/settings/modules/beat-sync',
  scene: '/companion/settings/scene',
  memory: '/companion/settings/memory',
  diagnostics: '/companion/settings/diagnostics',
  cards: '/companion/settings/cards',
  'card-new': '/companion/settings/cards/new',
};

export function companionSettingsRoute(page: FixedCompanionSettingsPage) { return COMPANION_SETTINGS_PATHS[page]; }

/**
 * Mã nhà cung cấp có trang riêng trong Cài đặt Companion → Nhà cung cấp. Khớp PROVIDER_PAGE_IDS
 * (features/companion/providers/catalog.ts, test so khớp) và _COMPANION_SETTINGS trong backend/core/static_files.py; viết
 * thẳng ở đây để vỏ ứng dụng không phải tải danh mục giọng nói.
 */
export const COMPANION_PROVIDER_IDS = ['xai', 'anthropic', 'openai', 'gemini', 'deepseek', 'mistral', 'azure-openai', 'ollama',
  'elevenlabs', 'azure', 'minimax', 'qwen', 'stepfun', 'compat', 'groq', 'deepgram'];

export function companionProviderRoute(id: string) { return `/companion/settings/providers/${id}`; }

/** Mã nhà cung cấp trong đường dẫn /companion/settings/providers/<mã>; null nếu không phải trang đó. */
export function companionProviderId(pathname: string): string | null {
  const id = /^\/companion\/settings\/providers\/([a-z-]+)\/?$/.exec(pathname)?.[1];
  return id && COMPANION_PROVIDER_IDS.includes(id) ? id : null;
}

/**
 * Trang một thẻ nhân vật như AIRI (/settings/airi-card/:id và /:id/edit): /companion/settings/cards/<mã> và …/<mã>/edit.
 * Mã là "peto" (thẻ mặc định) hay 32 chữ hex máy chủ cấp; khớp CARD_ID của backend/features/companion/cards.py.
 */
const CARD_PATH = /^\/companion\/settings\/cards\/(peto|[0-9a-f]{32})(\/edit)?\/?$/;

export function companionCardRoute(id: string, edit = false) {
  return `/companion/settings/cards/${encodeURIComponent(id)}${edit ? '/edit' : ''}`;
}

/** Mã thẻ trong đường dẫn trang thẻ (chi tiết hay trình sửa); null nếu không phải trang đó. */
export function companionCardId(pathname: string): string | null {
  return CARD_PATH.exec(pathname)?.[1] ?? null;
}

/** Trang cài đặt Companion của đường dẫn, có hay không có dấu "/" cuối; null nếu không phải trang đó. */
export function companionSettingsPage(pathname: string): CompanionSettingsPage | null {
  if (companionProviderId(pathname)) return 'provider';
  const card = CARD_PATH.exec(pathname);
  if (card) return card[2] ? 'card-edit' : 'card';
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
  for (const [page, route] of Object.entries(COMPANION_SETTINGS_PATHS) as [FixedCompanionSettingsPage, string][]) {
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
