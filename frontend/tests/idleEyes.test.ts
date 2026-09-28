import { expect, it } from 'vitest';
import { Blinker, IdleEyes } from '../src/idleEyes';
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
it('VRM blinks at random gaps, closes fully, and sometimes blinks twice in a row', () => {
  // 0,5 → chờ 3,75 s; 0,1 → chớp lại ngay; 0,9 → chờ 5,55 s.
  const draws = [0.5, 0.1, 0.9];
  const blinker = new Blinker(() => draws.shift() ?? 0.9);
  const starts: number[] = [];
  let previous = 0, closed = false;
  for (let t = 0.02; t < 10.5; t += 0.02) {
    const value = blinker.step(0.02);
    expect(value).toBeGreaterThanOrEqual(0); expect(value).toBeLessThanOrEqual(1);
    if (value === 1) closed = true;
    if (previous === 0 && value > 0) starts.push(t);
    previous = value;
  }
  expect(closed).toBe(true);
  expect(starts).toHaveLength(3);
  expect(starts[0]).toBeCloseTo(3.75, 1);
  expect(starts[1] - starts[0]).toBeLessThan(0.5);
  expect(starts[2] - starts[1]).toBeGreaterThan(5);
  // Tab ẩn lâu rồi quay lại: không chớp bù.
  const late = new Blinker(() => 0.9);
  expect(late.step(100)).toBe(0);
});
