import { expect, it } from 'vitest';
import { CompanionMotion, stageQuality } from '../src/companionMotion';

it('blends states gradually and returns to neutral without reducing lip sync input', () => {
  const motion = new CompanionMotion();
  expect(motion.step('idle', 1 / 30, 0).pitch).toBe(0);
  const first = motion.step('thinking', 1 / 30, 0);
  expect(first.pitch).toBeGreaterThan(0); expect(first.pitch).toBeLessThan(0.3);
  for (let i = 0; i < 90; i++) motion.step('thinking', 1 / 30, 0);
  const thought = motion.step('thinking', 1 / 30, 0);
  expect(thought.pitch).toBeCloseTo(2, 2); expect(thought.musicWeight).toBeCloseTo(0.45, 2);
  const changed = motion.step('speaking', 1 / 30, 1);
  expect(Math.abs(changed.pitch - thought.pitch)).toBeLessThan(0.4);
  for (let i = 0; i < 120; i++) motion.step('idle', 1 / 30, 0);
  const idle = motion.step('idle', 1 / 30, 0);
  expect(idle.pitch).toBeCloseTo(0, 3); expect(idle.musicWeight).toBeCloseTo(1, 3);
});
it('keeps transitions consistent at mobile and desktop frame rates and bounds long gaps', () => {
  const sample = (fps: number) => {
    const motion = new CompanionMotion(); let pose;
    for (let i = 0; i < fps; i++) pose = motion.step('listening', 1 / fps, 0);
    return pose!;
  };
  expect(sample(24).pitch).toBeCloseTo(sample(30).pitch, 5);
  expect(new CompanionMotion().step('thinking', 60, 0).pitch).toBeLessThan(0.3);
  expect(stageQuality(true, 3)).toEqual({ fps: 24, resolution: 1 });
  expect(stageQuality(false, 3)).toEqual({ fps: 30, resolution: 1.5 });
});
it('allows independent mobile sharpness and FPS upgrades without changing desktop limits', () => {
  expect(stageQuality(true, 3, { sharp: true, smooth: false })).toEqual({ fps: 24, resolution: 2 });
  expect(stageQuality(true, 3, { sharp: false, smooth: true })).toEqual({ fps: 60, resolution: 1 });
  expect(stageQuality(true, 1, { sharp: true, smooth: true })).toEqual({ fps: 60, resolution: 1 });
  expect(stageQuality(false, 3, { sharp: true, smooth: true })).toEqual({ fps: 30, resolution: 1.5 });
});
