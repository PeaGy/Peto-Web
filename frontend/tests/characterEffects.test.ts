import { beforeEach, expect, it, vi } from 'vitest';
import { readEffects, watchEffects, withCharacterEffects, writeEffects } from '../src/characterEffects';
beforeEach(() => localStorage.clear());
it('keeps preferences separate by model and restores safe defaults for invalid storage', () => {
  const listener = vi.fn(); const unwatch = watchEffects('one', listener);
  writeEffects('two', { cursor: false, breath: false, physics: false });
  expect(listener).not.toHaveBeenCalled();
  expect(readEffects('one')).toEqual({ cursor: true, breath: true, physics: true, idleEyes: true });
  writeEffects('one', { cursor: false, breath: true, physics: true });
  expect(listener).toHaveBeenCalledOnce();
  unwatch(); writeEffects('one', { cursor: true, breath: true, physics: true });
  expect(listener).toHaveBeenCalledOnce();
  localStorage.setItem('peto-character-effects:one', 'broken');
  expect(readEffects('one').cursor).toBe(true);
});
it('defaults old saved preferences to idle eyes on and remembers disabling per model', () => {
  localStorage.setItem('peto-character-effects:old', JSON.stringify({ cursor: false, breath: false, physics: true }));
  expect(readEffects('old').idleEyes).toBe(true);
  writeEffects('old', { ...readEffects('old'), idleEyes: false });
  expect(readEffects('old').idleEyes).toBe(false);
  expect(readEffects('other').idleEyes).toBe(true);
});
it.each(['cursor', 'breath', 'physics'] as const)('disables only %s for a frame, then restores resources', key => {
  const physics = { evaluate: vi.fn() };
  const focus = vi.fn(), breath = vi.fn(), motion = vi.fn(), mouth = vi.fn();
  const model = { physics: physics as typeof physics | undefined, updateFocus: focus, updateNaturalMovements: breath };
  withCharacterEffects(model, { cursor: true, breath: true, physics: true, [key]: false }, () => {
    model.updateFocus(); model.updateNaturalMovements(33, 33); model.physics?.evaluate(); motion(); mouth();
  });
  expect(focus).toHaveBeenCalledTimes(key === 'cursor' ? 0 : 1);
  expect(breath).toHaveBeenCalledTimes(key === 'breath' ? 0 : 1);
  expect(physics.evaluate).toHaveBeenCalledTimes(key === 'physics' ? 0 : 1);
  expect(motion).toHaveBeenCalledOnce(); expect(mouth).toHaveBeenCalledOnce();
  expect(model.physics).toBe(physics); expect(model.updateFocus).toBe(focus); expect(model.updateNaturalMovements).toBe(breath);
});
it('restores physics even when the frame throws, so model disposal still owns it', () => {
  const physics = {}; const model = { physics, updateFocus() {}, updateNaturalMovements() {} };
  expect(() => withCharacterEffects(model, { cursor: false, breath: false, physics: false }, () => { throw Error('frame'); })).toThrow('frame');
  expect(model.physics).toBe(physics);
});
