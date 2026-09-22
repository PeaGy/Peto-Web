export interface CharacterEffects { cursor: boolean; breath: boolean; physics: boolean }
const defaults: CharacterEffects = { cursor: true, breath: true, physics: true };
const eventName = 'peto-character-effects-change';
const key = (id: string) => `peto-character-effects:${id}`;
function normalize(value: Partial<CharacterEffects> | null): CharacterEffects {
  return { cursor: typeof value?.cursor === 'boolean' ? value.cursor : true,
    breath: typeof value?.breath === 'boolean' ? value.breath : true,
    physics: typeof value?.physics === 'boolean' ? value.physics : true };
}
export function readEffects(id: string): CharacterEffects {
  try { return normalize(JSON.parse(localStorage.getItem(key(id)) || 'null')); } catch { return { ...defaults }; }
}
export function writeEffects(id: string, value: CharacterEffects) {
  const effects = normalize(value);
  try { localStorage.setItem(key(id), JSON.stringify(effects)); } catch { /* Apply for this session. */ }
  window.dispatchEvent(new CustomEvent(eventName, { detail: { id, effects } }));
}
export function watchEffects(id: string, update: (value: CharacterEffects) => void) {
  const changed = (event: Event) => {
    const detail = (event as CustomEvent).detail;
    if (detail?.id === id) update(normalize(detail.effects));
  };
  const stored = (event: StorageEvent) => { if (event.key === key(id) || event.key === null) update(readEffects(id)); };
  window.addEventListener(eventName, changed); window.addEventListener('storage', stored);
  return () => { window.removeEventListener(eventName, changed); window.removeEventListener('storage', stored); };
}

/** Skip only additive runtime effects for this frame; leave motions, blink, pose and lip sync untouched. */
export function withCharacterEffects<T extends {
  physics?: unknown; updateFocus(): void; updateNaturalMovements(dt: number, now: number): void;
}>(model: T, effects: CharacterEffects, update: () => void) {
  const { physics, updateFocus, updateNaturalMovements } = model;
  try {
    if (!effects.physics) model.physics = undefined;
    if (!effects.cursor) model.updateFocus = () => {};
    if (!effects.breath) model.updateNaturalMovements = () => {};
    update();
  } finally {
    model.physics = physics;
    model.updateFocus = updateFocus;
    model.updateNaturalMovements = updateNaturalMovements;
  }
}
