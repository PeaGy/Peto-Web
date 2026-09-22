import { CHARACTER } from './characterConfig';
import { getCharacterAssets, type CharacterModel } from './characterLibrary';

export interface IdleMotion { id: string; group: string; index: number; file: string; label: string }
export const IDLE_CHANGE = 'peto-idle-motion-change';
const key = (id: string) => `peto-idle-motion:${id}`;

export function motionChoices(definitions: unknown): IdleMotion[] {
  if (!definitions || typeof definitions !== 'object' || Array.isArray(definitions)) return [];
  const result: IdleMotion[] = [];
  for (const [group, entries] of Object.entries(definitions)) {
    if (!Array.isArray(entries)) continue;
    entries.forEach((entry, index) => {
      if (result.length >= 200 || !entry || typeof entry.File !== 'string') return;
      const file = entry.File;
      result.push({ id: JSON.stringify([group, index, file]), group, index, file,
        label: file.split(/[\\/]/).pop() || file });
    });
  }
  return result;
}

export async function loadMotionChoices(character: CharacterModel): Promise<IdleMotion[]> {
  return (await loadMotionInfo(character)).choices;
}
export async function loadMotionInfo(character: CharacterModel): Promise<{ choices: IdleMotion[]; physics: boolean }> {
  if (character.format !== 'live2d') return { choices: [], physics: false };
  let json;
  if (character.builtin) {
    const response = await fetch(CHARACTER.modelUrl);
    if (!response.ok) throw new Error('Chưa đọc được danh sách chuyển động.');
    json = await response.json();
  } else {
    const assets = await getCharacterAssets(character.id);
    const entry = assets?.files.find(file => file.path === assets.entry);
    if (!entry) throw new Error('Không tìm thấy cấu hình model. Hãy nhập lại model.');
    json = JSON.parse(await entry.blob.text());
  }
  return { choices: motionChoices(json.FileReferences?.Motions), physics: !!json.FileReferences?.Physics };
}

export function readIdle(id: string): string {
  try { return localStorage.getItem(key(id)) || 'auto'; } catch { return 'auto'; }
}
export function writeIdle(id: string, value: string) {
  try { localStorage.setItem(key(id), value); } catch { /* Still update the open stage. */ }
  window.dispatchEvent(new CustomEvent(IDLE_CHANGE, { detail: { id, value } }));
}
export function watchIdle(id: string, update: (value: string) => void): () => void {
  const changed = (event: Event) => {
    const detail = (event as CustomEvent).detail;
    if (detail?.id === id && typeof detail.value === 'string') update(detail.value);
  };
  const stored = (event: StorageEvent) => { if (event.key === key(id) || event.key === null) update(readIdle(id)); };
  window.addEventListener(IDLE_CHANGE, changed);
  window.addEventListener('storage', stored);
  return () => { window.removeEventListener(IDLE_CHANGE, changed); window.removeEventListener('storage', stored); };
}

interface MotionManager {
  groups: { idle: string };
  startRandomMotion(group: string, priority?: number): Promise<boolean>;
  startMotion(group: string, index: number, priority?: number): Promise<boolean>;
  loadMotion(group: string, index: number): Promise<unknown>;
  stopAllMotions(): void;
}

/** Intercept only automatic idle requests. Serialize async loads so an old selection cannot restart later. */
export function controlIdle(manager: MotionManager, choices: IdleMotion[], onError: () => void) {
  const original = manager.startRandomMotion;
  let selected = 'auto', enabled = true, generation = 0, busy = false, disposed = false, failed = false;
  manager.startRandomMotion = async (group, priority) => {
    if (group !== manager.groups.idle) return original.call(manager, group, priority);
    if (disposed || !enabled || selected === 'off' || busy || failed) return false;
    const epoch = generation;
    busy = true;
    try {
      const choice = choices.find(item => item.id === selected);
      let started: boolean;
      if (choice) {
        const loaded = await manager.loadMotion(choice.group, choice.index);
        if (disposed || epoch !== generation) return false;
        if (!loaded) throw new Error('motion load failed');
        started = await manager.startMotion(choice.group, choice.index, priority);
      } else {
        started = await original.call(manager, group, priority);
      }
      if (disposed || epoch !== generation) {
        if (!disposed) manager.stopAllMotions();
        return false;
      }
      return started;
    } catch {
      if (!disposed && epoch === generation) { failed = true; onError(); }
      return false;
    } finally { busy = false; }
  };
  return {
    select(value: string) {
      const next = value === 'off' || choices.some(item => item.id === value) ? value : 'auto';
      if (next === selected && !failed) return;
      generation++; selected = next; failed = false; manager.stopAllMotions();
    },
    enable(value: boolean) {
      if (enabled === value) return;
      generation++; enabled = value; manager.stopAllMotions();
    },
    dispose() { disposed = true; generation++; manager.stopAllMotions(); manager.startRandomMotion = original; },
  };
}
