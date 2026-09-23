export const EMOTIONS = ['happy', 'sad', 'surprised'] as const;
export type Emotion = typeof EMOTIONS[number];
export const emotionLabels: Record<Emotion, string> = { happy: 'Vui', sad: 'Buồn', surprised: 'Ngạc nhiên' };
export type ExpressionChoice = { id: string; index: number; label: string };
export type ExpressionPreferences = { enabled: boolean; mapping: Partial<Record<Emotion, string>> };
const eventName = 'peto-expression-settings';
const previewEvent = 'peto-expression-preview';
const key = (id: string) => `peto-expressions:${id}`;

export function expressionChoices(definitions: unknown): ExpressionChoice[] {
  if (!Array.isArray(definitions)) return [];
  return definitions.flatMap((entry, index) => entry && typeof entry.File === 'string'
    ? [{ id: entry.File, index, label: typeof entry.Name === 'string' ? entry.Name : entry.File }] : []).slice(0, 200);
}
function normalize(value: Partial<ExpressionPreferences> | null): ExpressionPreferences {
  const mapping: ExpressionPreferences['mapping'] = {};
  for (const emotion of EMOTIONS) if (typeof value?.mapping?.[emotion] === 'string') mapping[emotion] = value.mapping[emotion];
  return { enabled: value?.enabled !== false, mapping };
}
export function readExpressions(id: string) {
  try { return normalize(JSON.parse(localStorage.getItem(key(id)) || 'null')); } catch { return normalize(null); }
}
export function writeExpressions(id: string, preferences: ExpressionPreferences) {
  const value = normalize(preferences);
  try { localStorage.setItem(key(id), JSON.stringify(value)); } catch { /* Session only. */ }
  window.dispatchEvent(new CustomEvent(eventName, { detail: { id, value } }));
}
export function previewExpression(id: string, expression: string) {
  window.dispatchEvent(new CustomEvent(previewEvent, { detail: { id, expression } }));
}
export function watchExpressions(id: string, update: (value: ExpressionPreferences) => void, preview?: (id: string) => void) {
  const changed = (event: Event) => { const d = (event as CustomEvent).detail; if (d?.id === id) update(normalize(d.value)); };
  const stored = (event: StorageEvent) => { if (event.key === key(id) || event.key === null) update(readExpressions(id)); };
  const tryExpression = (event: Event) => { const d = (event as CustomEvent).detail; if (d?.id === id && typeof d.expression === 'string') preview?.(d.expression); };
  window.addEventListener(eventName, changed); window.addEventListener('storage', stored); window.addEventListener(previewEvent, tryExpression);
  return () => { window.removeEventListener(eventName, changed); window.removeEventListener('storage', stored); window.removeEventListener(previewEvent, tryExpression); };
}

// Conservative local cues, not sentiment analysis. Ambiguous replies keep a neutral face.
export function replyEmotion(text: string): Emotion | undefined {
  if (/😢|😭|😔|\b(sorry to hear|that sounds (?:hard|painful)|my condolences)\b|rất tiếc|chia buồn/iu.test(text)) return 'sad';
  if (/😮|😲|\b(wow|whoa|no way)\b|bất ngờ/iu.test(text)) return 'surprised';
  if (/😊|😄|🥰|🎉|\b(congratulations|congrats|happy for you|glad to hear)\b|chúc mừng/iu.test(text)) return 'happy';
  return undefined;
}
export function expressionFor(emotion: Emotion, choices: ExpressionChoice[], preferences: ExpressionPreferences) {
  const mapped = preferences.mapping[emotion];
  if (mapped !== undefined) return choices.find(choice => choice.id === mapped);
  const names = { happy: /(?:^|[\W_])(happy|smile|joy)(?:$|[\W_])/i, sad: /(?:^|[\W_])(sad|cry|sorrow)(?:$|[\W_])/i,
    surprised: /(?:^|[\W_])(surprise[d]?|shock)(?:$|[\W_])/i };
  return choices.find(choice => names[emotion].test(choice.label));
}

type Manager = { definitions: unknown; reserveExpressionIndex: number; defaultExpression: unknown; currentExpression: unknown;
  resetExpression(): void; setExpression(index: number): Promise<boolean> };
export function controlExpressions(manager: Manager, onError: () => void) {
  const choices = expressionChoices(manager.definitions);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let generation = 0, disposed = false;
  const reset = () => {
    generation++; clearTimeout(timer);
    manager.reserveExpressionIndex = -1;
    manager.currentExpression = manager.defaultExpression;
    manager.resetExpression();
  };
  return {
    reset,
    async show(id?: string) {
      if (disposed) return;
      reset();
      const choice = choices.find(item => item.id === id);
      if (!choice) return;
      const token = generation;
      try {
        const ok = await manager.setExpression(choice.index);
        if (disposed || token !== generation) return;
        if (!ok) { onError(); return; }
        timer = setTimeout(reset, 8000);
      } catch { if (!disposed && token === generation) onError(); }
    },
    dispose() { reset(); disposed = true; },
  };
}
