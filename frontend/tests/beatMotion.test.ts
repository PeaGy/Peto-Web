import { expect, it } from 'vitest';
import { BeatPulse } from '../src/beatMotion';

it('keeps position continuous at incoming beats instead of flipping the head', () => {
  const motion = new BeatPulse(); motion.beat(0); motion.beat(500);
  for (let t = 500; t < 1000; t += 16) motion.pose(t, 1);
  const before = motion.pose(1000, 1);
  motion.beat(1000);
  expect(motion.pose(1000, 1)).toEqual(before);
  expect(Math.abs(motion.pose(1016, 1).pitch - before.pitch)).toBeLessThan(1);
});
it.each([30, 60, 144])('nods through positive and negative pitch smoothly at %i fps', fps => {
  const motion = new BeatPulse(); let nextBeat = 0; let min = 0, max = 0, previous = 0;
  for (let t = 0; t < 6000; t += 1000 / fps) {
    if (t >= nextBeat) { motion.beat(t); nextBeat += 500; }
    const pose = motion.pose(t, 1);
    expect(pose.yaw).toBe(0);
    expect(Math.abs(pose.pitch - previous)).toBeLessThan(3);
    expect(Math.abs(pose.roll)).toBeLessThan(12);
    min = Math.min(min, pose.pitch); max = Math.max(max, pose.pitch); previous = pose.pitch;
  }
  expect(min).toBeLessThan(-5); expect(max).toBeGreaterThan(5);
});
it('handles a long hidden-tab gap without runaway spring values', () => {
  const motion = new BeatPulse(); motion.beat(0); motion.beat(500); motion.pose(650, 1);
  const pose = motion.pose(60000, 1);
  expect(Number.isFinite(pose.pitch)).toBe(true); expect(Math.abs(pose.pitch)).toBeLessThan(12);
});
