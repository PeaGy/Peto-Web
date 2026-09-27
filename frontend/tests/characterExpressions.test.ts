import { afterEach, expect, it, vi } from 'vitest';
import {
  BUILTIN_FACE, asStageEmotion, controlExpressions, expressionChoices, faceSource, previewExpression, readExpressions, replyEmotion,
  watchExpressions, writeExpressions,
} from '../src/characterExpressions';
afterEach(() => { localStorage.clear(); vi.useRealTimers(); });
const choices = expressionChoices([{ Name: 'Happy', File: 'happy.exp3.json' }, { Name: 'f02', File: '02.exp3.json' }]);
it('picks each emotion’s face: a file named after it, an explicit file, the built-in face or nothing', () => {
  expect(expressionChoices(undefined)).toEqual([]);
  const auto = readExpressions('a');
  expect(faceSource('happy', choices, auto, true)).toEqual({ kind: 'file', choice: choices[0] });
  expect(faceSource('sad', choices, auto, true)).toEqual({ kind: 'builtin' });
  expect(faceSource('sad', choices, auto, false)).toEqual({ kind: 'none' });
  writeExpressions('a', { enabled: true, mapping: { sad: '02.exp3.json', happy: '', think: BUILTIN_FACE, angry: 'gone.exp3.json' } });
  const mapped = readExpressions('a');
  expect(faceSource('sad', choices, mapped, true)).toEqual({ kind: 'file', choice: choices[1] });
  expect(faceSource('happy', choices, mapped, true)).toEqual({ kind: 'none' });
  expect(faceSource('think', choices, mapped, true)).toEqual({ kind: 'builtin' });
  // Tệp đã gán mà model không còn thì về mặt dựng sẵn.
  expect(faceSource('angry', choices, mapped, true)).toEqual({ kind: 'builtin' });
  expect(readExpressions('b').mapping).toEqual({});
});
it('knows the nine AIRI emotions and nothing else', () => {
  expect(['happy', 'think', 'curious', 'neutral'].map(asStageEmotion)).toEqual(['happy', 'think', 'curious', 'neutral']);
  expect(asStageEmotion('banana')).toBeUndefined();
  expect(asStageEmotion(undefined)).toBeUndefined();
});
it('uses conservative reply cues and leaves ordinary messages neutral', () => {
  expect(replyEmotion('Congratulations! 🎉')).toBe('happy');
  expect(replyEmotion('Sorry to hear that.')).toBe('sad');
  expect(replyEmotion('Wow, really?')).toBe('surprised');
  expect(replyEmotion('How was your day?')).toBeUndefined();
  expect(replyEmotion('That is not a happy ending.')).toBeUndefined();
});
it('notifies only the selected character, previews by emotion and unsubscribes', () => {
  const callback = vi.fn(); const preview = vi.fn(); const off = watchExpressions('a', callback, preview);
  writeExpressions('b', { enabled: false, mapping: {} }); expect(callback).not.toHaveBeenCalled();
  writeExpressions('a', { enabled: false, mapping: {} }); expect(callback).toHaveBeenCalledTimes(1);
  previewExpression('b', 'happy'); previewExpression('a', 'think'); expect(preview.mock.calls).toEqual([['think']]);
  off(); writeExpressions('a', { enabled: true, mapping: {} }); expect(callback).toHaveBeenCalledTimes(1);
});
function manager() { return { definitions: [{ Name: 'Happy', File: 'happy.exp3.json' }], reserveExpressionIndex: -1,
  currentExpression: {}, defaultExpression: {}, resetExpression: vi.fn(), setExpression: vi.fn().mockResolvedValue(true) }; }
it('holds an expression file until the stage resets it, and allows it again', async () => {
  vi.useFakeTimers(); const m = manager(); const controller = controlExpressions(m, vi.fn());
  await controller.show('happy.exp3.json'); expect(m.setExpression).toHaveBeenCalledWith(0);
  m.currentExpression = { smile: true };
  vi.advanceTimersByTime(30000); expect(m.currentExpression).toEqual({ smile: true });
  controller.reset(); expect(m.currentExpression).toBe(m.defaultExpression);
  await controller.show('happy.exp3.json'); expect(m.setExpression).toHaveBeenCalledTimes(2);
  controller.dispose(); expect(vi.getTimerCount()).toBe(0);
});
it('cancels pending loads on reset/dispose and reports failed resources', async () => {
  const m = manager(); const error = vi.fn(); const controller = controlExpressions(m, error);
  let finish!: (value: boolean) => void;
  m.setExpression.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = controller.show('happy.exp3.json'); controller.reset();
  expect(m.reserveExpressionIndex).toBe(-1);
  finish(false); await pending; expect(error).not.toHaveBeenCalled();
  m.setExpression.mockResolvedValueOnce(false); await controller.show('happy.exp3.json'); expect(error).toHaveBeenCalledOnce();
  controller.dispose(); await controller.show('happy.exp3.json'); expect(m.setExpression).toHaveBeenCalledTimes(2);
});
