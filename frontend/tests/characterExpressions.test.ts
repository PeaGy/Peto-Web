import { afterEach, expect, it, vi } from 'vitest';
import { controlExpressions, expressionChoices, expressionFor, readExpressions, replyEmotion, watchExpressions, writeExpressions } from '../src/characterExpressions';
afterEach(() => { localStorage.clear(); vi.useRealTimers(); });
const choices = expressionChoices([{ Name: 'Happy', File: 'happy.exp3.json' }, { Name: 'f02', File: '02.exp3.json' }]);
it('discovers declared files and permits explicit mappings for opaque names', () => {
  expect(expressionChoices(undefined)).toEqual([]);
  expect(expressionFor('happy', choices, readExpressions('a'))?.index).toBe(0);
  expect(expressionFor('sad', choices, readExpressions('a'))).toBeUndefined();
  writeExpressions('a', { enabled: true, mapping: { sad: '02.exp3.json', happy: '' } });
  expect(expressionFor('sad', choices, readExpressions('a'))?.index).toBe(1);
  expect(expressionFor('happy', choices, readExpressions('a'))).toBeUndefined();
  expect(readExpressions('b').mapping).toEqual({});
});
it('uses conservative reply cues and leaves ordinary messages neutral', () => {
  expect(replyEmotion('Congratulations! 🎉')).toBe('happy');
  expect(replyEmotion('Sorry to hear that.')).toBe('sad');
  expect(replyEmotion('Wow, really?')).toBe('surprised');
  expect(replyEmotion('How was your day?')).toBeUndefined();
  expect(replyEmotion('That is not a happy ending.')).toBeUndefined();
});
it('notifies only the selected character and unsubscribes', () => {
  const callback = vi.fn(); const off = watchExpressions('a', callback);
  writeExpressions('b', { enabled: false, mapping: {} }); expect(callback).not.toHaveBeenCalled();
  writeExpressions('a', { enabled: false, mapping: {} }); expect(callback).toHaveBeenCalledTimes(1);
  off(); writeExpressions('a', { enabled: true, mapping: {} }); expect(callback).toHaveBeenCalledTimes(1);
});
function manager() { return { definitions: [{ Name: 'Happy', File: 'happy.exp3.json' }], reserveExpressionIndex: -1,
  currentExpression: {}, defaultExpression: {}, resetExpression: vi.fn(), setExpression: vi.fn().mockResolvedValue(true) }; }
it('returns to neutral after eight seconds and allows the same expression again', async () => {
  vi.useFakeTimers(); const m = manager(); const controller = controlExpressions(m, vi.fn());
  await controller.show('happy.exp3.json'); expect(m.setExpression).toHaveBeenCalledWith(0);
  m.currentExpression = { smile: true };
  vi.advanceTimersByTime(8000); expect(m.currentExpression).toBe(m.defaultExpression);
  await controller.show('happy.exp3.json'); expect(m.setExpression).toHaveBeenCalledTimes(2);
  controller.dispose(); expect(vi.getTimerCount()).toBe(0);
});
it('cancels pending loads on reset/dispose and reports failed resources', async () => {
  vi.useFakeTimers(); const m = manager(); const error = vi.fn(); const controller = controlExpressions(m, error);
  let finish!: (value: boolean) => void;
  m.setExpression.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = controller.show('happy.exp3.json'); controller.reset();
  expect(m.reserveExpressionIndex).toBe(-1);
  finish(true); await pending; expect(vi.getTimerCount()).toBe(0);
  m.setExpression.mockResolvedValueOnce(false); await controller.show('happy.exp3.json'); expect(error).toHaveBeenCalledOnce();
  controller.dispose(); await controller.show('happy.exp3.json'); expect(m.setExpression).toHaveBeenCalledTimes(2);
});
