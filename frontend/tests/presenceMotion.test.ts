import { expect, it } from 'vitest';
import { BubbleMotion, ComposerGaze } from '../src/features/companion/characters/presenceMotion';

const head = { x: 200, y: 200, width: 100, height: 120 };
it('bong bóng theo đầu bằng lò xo: trễ nhẹ, vượt nhẹ rồi ổn định dù tốc độ khung hình khác nhau', () => {
  const result = [24, 30, 60].map(fps => {
    const motion = new BubbleMotion();
    const start = { ...motion.step(head, 800, 600, 0, true) };
    const moved = { ...head, x: head.x + 100, y: head.y + 20 };
    const first = { ...motion.step(moved, 800, 600, 1 / fps, true) };
    expect(first.x).toBeGreaterThan(start.x); expect(first.x).toBeLessThan(start.x + 25);
    let furthest = first.x;
    for (let i = 1; i < fps * 2; i++) furthest = Math.max(furthest, motion.step(moved, 800, 600, 1 / fps, true).x);
    const end = motion.step(moved, 800, 600, 1 / fps, true);
    expect(furthest).toBeGreaterThan(start.x + 100);
    expect(end.x).toBeCloseTo(start.x + 100, 3); expect(end.y).toBeCloseTo(start.y + 20, 3);
    return end;
  });
  expect(result[0].x).toBeCloseTo(result[2].x, 3);
});

it('giảm chuyển động bám chính xác; hiện lại không bay từ vị trí cũ', () => {
  const motion = new BubbleMotion();
  const start = { ...motion.step(head, 800, 600, 0, false) };
  expect(motion.step({ ...head, x: 300 }, 800, 600, 0.016, false).x).toBe(start.x + 100);
  motion.reset();
  expect(motion.step(head, 800, 600, 0.016, true)).toEqual(start);
});

it('hướng nhìn quay về nhẹ và giữ quyền điều khiển đến khi ổn định; gõ lại hủy đoạn quay về', () => {
  const gaze = new ComposerGaze(), normal = { x: 0, y: 0 };
  gaze.step({ x: 1, y: -1 }, normal, 1 / 60);
  const first = gaze.step(null, normal, 1 / 60);
  expect(first.x).toBeGreaterThan(0.95); expect(first.x).toBeLessThan(1);
  expect(gaze.owned).toBe(true);
  for (let i = 0; i < 30; i++) gaze.step(null, normal, 1 / 60);
  expect(gaze.step({ x: 0.5, y: -0.5 }, normal, 1 / 60)).toEqual({ x: 0.5, y: -0.5 });
  for (let i = 0; i < 200; i++) gaze.step(null, normal, 1 / 60);
  expect(gaze.owned).toBe(false);
  expect(gaze.step(null, normal, 1 / 60)).toEqual(normal);
});
