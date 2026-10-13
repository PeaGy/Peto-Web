/**
 * Cách chuyển động của từng nhân vật Live2D, như Cài đặt → Models → Animation → Motion driver của AIRI. Chủ web chọn ngày
 * 14/10/2026 sau khi thử trang mẫu: mặc định là "Hiện tại" (AIRI cũng để Universal mặc định), giữ công tắc dáng miệng.
 * "Theo lúc nói" là thêm của Peto: AIRI bắt người dùng chọn một bộ.
 */
export type MotionDriver = 'universal' | 'magic';
export type MagicProfile = 'excited' | 'calm' | 'speech';
export interface MagicSettings {
  driver: MotionDriver;
  /** Bộ chuyển động; mặc định Hào hứng như AIRI ("Speaking / excited"). */
  profile: MagicProfile;
  /** Mắt nhìn thẳng khi đầu lắc (AIRI: "Force forward view target", mặc định bật). */
  viewTarget: boolean;
  /** MAGIC điều khiển dáng miệng; tắt thì giữ dáng miệng mặc định của model. AIRI luôn bật. */
  mouthForm: boolean;
}

export const DEFAULT_MAGIC: MagicSettings = { driver: 'universal', profile: 'excited', viewTarget: true, mouthForm: true };
const eventName = 'peto-character-magic-change';
const key = (id: string) => `peto-character-magic:${id}`;

function normalize(value: Partial<MagicSettings> | null): MagicSettings {
  return {
    driver: value?.driver === 'magic' ? 'magic' : 'universal',
    profile: value?.profile === 'calm' || value?.profile === 'speech' ? value.profile : 'excited',
    viewTarget: typeof value?.viewTarget === 'boolean' ? value.viewTarget : true,
    mouthForm: typeof value?.mouthForm === 'boolean' ? value.mouthForm : true,
  };
}

export function readMagic(id: string): MagicSettings {
  try { return normalize(JSON.parse(localStorage.getItem(key(id)) || 'null')); } catch { return { ...DEFAULT_MAGIC }; }
}

export function writeMagic(id: string, value: MagicSettings) {
  const settings = normalize(value);
  try { localStorage.setItem(key(id), JSON.stringify(settings)); } catch { /* Vẫn áp dụng trong phiên này. */ }
  window.dispatchEvent(new CustomEvent(eventName, { detail: { id, settings } }));
}

export function watchMagic(id: string, update: (value: MagicSettings) => void) {
  const changed = (event: Event) => {
    const detail = (event as CustomEvent).detail;
    if (detail?.id === id) update(normalize(detail.settings));
  };
  const stored = (event: StorageEvent) => { if (event.key === key(id) || event.key === null) update(readMagic(id)); };
  window.addEventListener(eventName, changed);
  window.addEventListener('storage', stored);
  return () => { window.removeEventListener(eventName, changed); window.removeEventListener('storage', stored); };
}
