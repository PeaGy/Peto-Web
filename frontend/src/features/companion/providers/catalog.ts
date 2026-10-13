/**
 * Nhà cung cấp cho bộ não Companion khi dùng khóa API riêng (Cài đặt Companion → Nhà cung cấp, chủ web chọn biến thể
 * "Như AIRI" ngày 13/10/2026). Danh sách khớp `PROVIDERS` trong backend/ai/byok.py: máy chủ chỉ gọi đúng các nhà này.
 *
 * Khóa lưu chung kho `peto-voice-keys` với khóa giọng nói và nghe, theo mã nhà cung cấp: một khóa OpenAI hay Gemini dùng
 * được cho cả bộ não, giọng nói và nghe.
 */
import { HEARING_PROVIDERS } from '../speech/hearingProviders';
import { KEY_PROVIDERS } from '../speech/voiceProviders';

export type ChatProviderId = 'xai' | 'anthropic' | 'openai' | 'gemini' | 'deepseek' | 'mistral' | 'azure-openai' | 'ollama';
export type ChatField = 'endpoint' | 'key' | 'deployment';

export interface ChatProviderInfo {
  id: ChatProviderId;
  name: string;
  /** Dòng phụ trên thẻ. */
  site: string;
  /** Nơi lấy khóa. */
  keySite: string;
  keyHint: string;
  /** Tra web: tìm kiếm có sẵn của nhà cung cấp, hay cần khóa Tavily. */
  search: 'native' | 'tavily';
  /** Có gói miễn phí. */
  free?: boolean;
  fields: ChatField[];
}

export const CHAT_PROVIDERS: ChatProviderInfo[] = [
  { id: 'xai', name: 'xAI', site: 'x.ai', keySite: 'console.x.ai', keyHint: 'xai-…', search: 'native', fields: ['key'] },
  { id: 'anthropic', name: 'Anthropic', site: 'anthropic.com', keySite: 'console.anthropic.com', keyHint: 'sk-ant-…',
    search: 'native', fields: ['key'] },
  { id: 'openai', name: 'OpenAI', site: 'openai.com', keySite: 'platform.openai.com', keyHint: 'sk-…', search: 'native',
    fields: ['key'] },
  { id: 'gemini', name: 'Google Gemini', site: 'aistudio.google.com', keySite: 'aistudio.google.com', keyHint: 'AIza…',
    search: 'native', free: true, fields: ['key'] },
  { id: 'deepseek', name: 'DeepSeek', site: 'deepseek.com', keySite: 'platform.deepseek.com', keyHint: 'sk-…',
    search: 'tavily', fields: ['key'] },
  { id: 'mistral', name: 'Mistral', site: 'mistral.ai', keySite: 'console.mistral.ai', keyHint: 'Khóa Mistral',
    search: 'tavily', free: true, fields: ['key'] },
  { id: 'azure-openai', name: 'Azure OpenAI', site: 'azure.com', keySite: 'portal.azure.com', keyHint: 'Khóa của tài nguyên',
    search: 'tavily', fields: ['endpoint', 'key', 'deployment'] },
  { id: 'ollama', name: 'Ollama', site: 'ollama.com (đám mây)', keySite: 'ollama.com/settings/keys', keyHint: 'Khóa Ollama',
    search: 'tavily', free: true, fields: ['key'] },
];

export function chatProvider(id: string): ChatProviderInfo | undefined {
  return CHAT_PROVIDERS.find(item => item.id === id);
}

/** Mọi mã có trang riêng trong Nhà cung cấp (khớp đường dẫn ở app/routes.ts và core/static_files.py). */
export const PROVIDER_PAGE_IDS: string[] = [
  ...CHAT_PROVIDERS.map(item => item.id),
  ...KEY_PROVIDERS.map(item => item.id).filter(id => !CHAT_PROVIDERS.some(item => item.id === id)),
  ...HEARING_PROVIDERS.map(item => item.id).filter(id => !CHAT_PROVIDERS.some(item => item.id === id)
    && !KEY_PROVIDERS.some(item => item.id === id)),
];

export function providerName(id: string): string {
  return chatProvider(id)?.name ?? KEY_PROVIDERS.find(item => item.id === id)?.name
    ?? HEARING_PROVIDERS.find(item => item.id === id)?.name ?? id;
}

/** Khóa này dùng cho những gì: bộ não, giọng nói, nghe. */
export function providerUses(id: string): ('chat' | 'voice' | 'hearing')[] {
  return [
    ...(chatProvider(id) ? ['chat' as const] : []),
    ...(KEY_PROVIDERS.some(item => item.id === id) ? ['voice' as const] : []),
    ...(HEARING_PROVIDERS.some(item => item.id === id) ? ['hearing' as const] : []),
  ];
}
