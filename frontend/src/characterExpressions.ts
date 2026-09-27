/** Chín cảm xúc của AIRI (chủ web chọn ngày 2026-09-27); "neutral" không gán gì, nghĩa là về mặt bình thường. */
export const EMOTIONS = ['happy', 'sad', 'angry', 'think', 'surprised', 'awkward', 'question', 'curious'] as const;
export type Emotion = typeof EMOTIONS[number];
export type StageEmotion = Emotion | 'neutral';
/** Một lần đổi mặt: `key` tăng mỗi lần, để hai câu liền nhau cùng cảm xúc vẫn là lần mới. */
export type StageCue = { emotion: StageEmotion; key: number };
export const emotionLabels: Record<Emotion, string> = {
  happy: 'Vui', sad: 'Buồn', angry: 'Giận', think: 'Suy nghĩ', surprised: 'Ngạc nhiên', awkward: 'Ngại', question: 'Thắc mắc',
  curious: 'Tò mò',
};
export const NEUTRAL_LABEL = 'Bình thường';
/** Giá trị gán nghĩa là dùng mặt dựng sẵn (builtinFaces.ts) thay vì tệp biểu cảm của model. */
export const BUILTIN_FACE = '@builtin';
export type ExpressionChoice = { id: string; index: number; label: string };
export type ExpressionPreferences = { enabled: boolean; mapping: Partial<Record<Emotion, string>> };
export type FaceSource = { kind: 'file'; choice: ExpressionChoice } | { kind: 'builtin' } | { kind: 'none' };
const eventName = 'peto-expression-settings';
const previewEvent = 'peto-expression-preview';
const key = (id: string) => `peto-expressions:${id}`;

export function asStageEmotion(value: unknown): StageEmotion | undefined {
  return value === 'neutral' || (EMOTIONS as readonly unknown[]).includes(value) ? value as StageEmotion : undefined;
}
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
/** Bấm thẻ cảm xúc trong bảng Nhân vật: sân khấu làm mặt đó một lúc để xem thử. */
export function previewExpression(id: string, emotion: StageEmotion) {
  window.dispatchEvent(new CustomEvent(previewEvent, { detail: { id, emotion } }));
}
const snapshotEvent = 'peto-expression-snapshot';
/** Sân khấu chụp mặt vừa xem thử: bảng Nhân vật che sân khấu, nên thẻ cảm xúc hiện ảnh này thay cho sân khấu. */
export function publishSnapshot(id: string, emotion: StageEmotion, image: string) {
  window.dispatchEvent(new CustomEvent(snapshotEvent, { detail: { id, emotion, image } }));
}
export function watchSnapshots(id: string, update: (emotion: StageEmotion, image: string) => void) {
  const listener = (event: Event) => {
    const d = (event as CustomEvent).detail; const emotion = asStageEmotion(d?.emotion);
    if (d?.id === id && emotion && typeof d.image === 'string') update(emotion, d.image);
  };
  window.addEventListener(snapshotEvent, listener);
  return () => window.removeEventListener(snapshotEvent, listener);
}
export function watchExpressions(id: string, update: (value: ExpressionPreferences) => void, preview?: (emotion: StageEmotion) => void) {
  const changed = (event: Event) => { const d = (event as CustomEvent).detail; if (d?.id === id) update(normalize(d.value)); };
  const stored = (event: StorageEvent) => { if (event.key === key(id) || event.key === null) update(readExpressions(id)); };
  const tryExpression = (event: Event) => {
    const d = (event as CustomEvent).detail; const emotion = asStageEmotion(d?.emotion);
    if (d?.id === id && emotion) preview?.(emotion);
  };
  window.addEventListener(eventName, changed); window.addEventListener('storage', stored); window.addEventListener(previewEvent, tryExpression);
  return () => { window.removeEventListener(eventName, changed); window.removeEventListener('storage', stored); window.removeEventListener(previewEvent, tryExpression); };
}

// Dấu hiệu cục bộ, thận trọng, chỉ dùng khi Peto quên gắn thẻ cảm xúc. Câu mơ hồ thì để mặt bình thường.
export function replyEmotion(text: string): Emotion | undefined {
  if (/😢|😭|😔|\b(sorry to hear|that sounds (?:hard|painful)|my condolences)\b|rất tiếc|chia buồn/iu.test(text)) return 'sad';
  if (/😮|😲|\b(wow|whoa|no way)\b|bất ngờ/iu.test(text)) return 'surprised';
  if (/😊|😄|🥰|🎉|\b(congratulations|congrats|happy for you|glad to hear)\b|chúc mừng/iu.test(text)) return 'happy';
  return undefined;
}
const NAMES: Record<Emotion, RegExp> = {
  happy: /(?:^|[\W_])(happy|smile|joy|glad)(?:$|[\W_])/i,
  sad: /(?:^|[\W_])(sad|cry|sorrow|tears?)(?:$|[\W_])/i,
  angry: /(?:^|[\W_])(angry|anger|mad|pout|annoyed?)(?:$|[\W_])/i,
  think: /(?:^|[\W_])(think|thinking|ponder)(?:$|[\W_])/i,
  surprised: /(?:^|[\W_])(surprised?|shock(?:ed)?)(?:$|[\W_])/i,
  awkward: /(?:^|[\W_])(awkward|shy|embarrass(?:ed)?|blush)(?:$|[\W_])/i,
  question: /(?:^|[\W_])(question|confused?|puzzled?)(?:$|[\W_])/i,
  curious: /(?:^|[\W_])(curious|interest(?:ed)?)(?:$|[\W_])/i,
};
/**
 * Nhân vật lấy mặt cho một cảm xúc từ đâu. Chưa gán ("Tự động"): tệp biểu cảm trùng tên nếu có, không thì mặt dựng sẵn.
 * Tệp đã gán mà model không còn thì cũng về mặt dựng sẵn.
 */
export function faceSource(emotion: Emotion, choices: ExpressionChoice[], preferences: ExpressionPreferences, builtin: boolean): FaceSource {
  const mapped = preferences.mapping[emotion];
  const fallback: FaceSource = builtin ? { kind: 'builtin' } : { kind: 'none' };
  if (mapped === '') return { kind: 'none' };
  if (mapped === BUILTIN_FACE) return fallback;
  const choice = mapped !== undefined ? choices.find(item => item.id === mapped) : choices.find(item => NAMES[emotion].test(item.label));
  return choice ? { kind: 'file', choice } : fallback;
}

type Manager = { definitions: unknown; reserveExpressionIndex: number; defaultExpression: unknown; currentExpression: unknown;
  resetExpression(): void; setExpression(index: number): Promise<boolean> };
/** Bật tệp biểu cảm của model và giữ tới khi reset: sân khấu tự quyết lúc nào về mặt bình thường. */
export function controlExpressions(manager: Manager, onError: () => void) {
  const choices = expressionChoices(manager.definitions);
  let generation = 0, disposed = false;
  const reset = () => {
    generation++;
    manager.reserveExpressionIndex = -1;
    manager.currentExpression = manager.defaultExpression;
    manager.resetExpression();
  };
  return {
    choices,
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
        if (!ok) onError();
      } catch { if (!disposed && token === generation) onError(); }
    },
    dispose() { reset(); disposed = true; },
  };
}
