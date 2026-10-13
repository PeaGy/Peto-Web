/**
 * Bộ não Companion (Cài đặt Companion → Mô-đun → Bộ não, như Consciousness của AIRI): Peto (Grok qua tài khoản Peto,
 * mặc định) hay một nhà cung cấp đã kết nối bằng khóa riêng của người dùng. Lưu theo trình duyệt, như khóa.
 *
 * "Đã kết nối" là đã bấm Kiểm tra kết nối thành công với khóa hiện tại; danh sách model nhận được giữ lại để trang Bộ não
 * cho chọn. Đổi khóa thì phải kiểm tra lại.
 */
import { useSyncExternalStore } from 'react';
import { getKeyConfigs, type KeyConfig } from '../speech/voiceProviders';
import { chatProvider, type ChatProviderId } from './catalog';

export interface Brain {
  provider: 'peto' | ChatProviderId;
  model: string;
}

const BRAIN_KEY = 'peto-companion-brain';
const MODELS_KEY = 'peto-provider-models';
const EVENT = 'peto-companion-brain-change';
const PETO: Brain = { provider: 'peto', model: '' };

let memory: { brain: string | null; models: string | null } = { brain: null, models: null };

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return key === BRAIN_KEY ? memory.brain : memory.models;
  }
}

function write(key: string, value: string | null) {
  if (key === BRAIN_KEY) memory = { ...memory, brain: value };
  else memory = { ...memory, models: value };
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* Chỉ giữ trong phiên này. */ }
  window.dispatchEvent(new Event(EVENT));
}

let brainSnapshot: { raw: string | null; value: Brain } = { raw: null, value: PETO };

export function readBrain(): Brain {
  const raw = read(BRAIN_KEY);
  if (raw === brainSnapshot.raw) return brainSnapshot.value;
  let value = PETO;
  try {
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed && typeof parsed.provider === 'string' && chatProvider(parsed.provider)) {
      value = { provider: parsed.provider, model: typeof parsed.model === 'string' ? parsed.model : '' };
    }
  } catch { /* Giá trị hỏng thì về Peto. */ }
  brainSnapshot = { raw, value };
  return value;
}

export function writeBrain(brain: Brain) {
  write(BRAIN_KEY, brain.provider === 'peto' ? null : JSON.stringify(brain));
}

export type ModelCache = Partial<Record<string, string[]>>;
let modelsSnapshot: { raw: string | null; value: ModelCache } = { raw: null, value: {} };

export function readModels(): ModelCache {
  const raw = read(MODELS_KEY);
  if (raw === modelsSnapshot.raw) return modelsSnapshot.value;
  let value: ModelCache = {};
  try {
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed && typeof parsed === 'object') value = parsed;
  } catch { /* Bỏ bản hỏng. */ }
  modelsSnapshot = { raw, value };
  return value;
}

/** Ghi danh sách model sau lần kiểm tra thành công; null là quên (khóa vừa đổi hoặc bị xóa). */
export function writeModels(id: string, models: string[] | null) {
  const next = { ...readModels() };
  if (models) next[id] = models;
  else delete next[id];
  write(MODELS_KEY, JSON.stringify(next));
  // Bộ não đang dùng nhà này mà khóa bị xóa hay đổi: về Peto, khỏi gửi khóa cũ.
  if (!models && readBrain().provider === id) writeBrain(PETO);
}

function subscribe(update: () => void) {
  const stored = (event: StorageEvent) => {
    if (event.key === BRAIN_KEY || event.key === MODELS_KEY || event.key === null) update();
  };
  window.addEventListener(EVENT, update);
  window.addEventListener('storage', stored);
  return () => {
    window.removeEventListener(EVENT, update);
    window.removeEventListener('storage', stored);
  };
}

export function useBrain(): Brain {
  return useSyncExternalStore(subscribe, readBrain, () => PETO);
}

export function useModels(): ModelCache {
  return useSyncExternalStore(subscribe, readModels, () => ({}));
}

/** Đã kiểm tra khóa thành công và khóa vẫn còn. */
export function connected(id: string, config: KeyConfig | undefined, models: ModelCache): boolean {
  const info = chatProvider(id);
  if (!info || !config?.key?.trim() || !models[id]) return false;
  return info.id !== 'azure-openai' || Boolean(config.endpoint?.trim() && config.deployment?.trim());
}

export interface BrainRequest {
  provider: { id: string; model: string; endpoint?: string };
  providerKey: string;
  searchKey?: string;
  label: string;
}

/** Phần gửi kèm một lượt Companion; null là dùng Peto (chưa chọn, hay khóa đã bị xóa). */
export function brainRequest(search: boolean): BrainRequest | null {
  const brain = readBrain();
  if (brain.provider === 'peto') return null;
  const info = chatProvider(brain.provider);
  const keys = getKeyConfigs();
  const config = keys[brain.provider];
  if (!info || !connected(brain.provider, config, readModels())) return null;
  const model = info.id === 'azure-openai' ? config!.deployment!.trim() : brain.model || readModels()[info.id]?.[0] || '';
  if (!model) return null;
  const tavily = keys.tavily?.key?.trim();
  return {
    provider: { id: info.id, model, ...(info.id === 'azure-openai' ? { endpoint: config!.endpoint!.trim() } : {}) },
    providerKey: config!.key!.trim(),
    // Chỉ gửi khóa Tavily khi thật sự cần: nhà không có tìm kiếm riêng và công tắc Tra web đang bật.
    ...(info.search === 'tavily' && search && tavily ? { searchKey: tavily } : {}),
    label: info.name,
  };
}
