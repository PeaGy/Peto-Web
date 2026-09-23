import { expect, it } from 'vitest';
import { IdleEyes } from '../src/idleEyes';
it('moves gently, stays within eye limits, and fades out on cursor activity', () => {
  const eyes = new IdleEyes(() => 0.8);
  const first = eyes.step(1 / 30, true);
  expect(first.x).toBeGreaterThan(0); expect(first.x).toBeLessThan(0.1);
  let pose = first;
  for (let i = 0; i < 150; i++) pose = eyes.step(1 / 30, true);
  expect(Math.abs(pose.x)).toBeLessThanOrEqual(0.9);
  expect(Math.abs(pose.y)).toBeLessThanOrEqual(0.7);
  expect(pose.weight).toBeCloseTo(1, 4);
  for (let i = 0; i < 90; i++) pose = eyes.step(1 / 30, false);
  expect(pose.x).toBeCloseTo(0, 5); expect(pose.y).toBeCloseTo(0, 5);
  expect(pose.weight).toBeCloseTo(0, 5);
});
it('does not generate new targets every frame or catch up after a hidden tab', () => {
  let calls = 0;
  const eyes = new IdleEyes(() => { calls++; return 0.8; });
  eyes.step(0.03, true); const initial = calls;
  for (let i = 0; i < 30; i++) eyes.step(0.03, true);
  eyes.step(100, true);
  expect(calls).toBe(initial);
});
