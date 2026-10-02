import { expect, it } from 'vitest';
import { bubblePlacement } from '../src/features/companion/characters/stageInteraction';

it('bong bóng ưu tiên trên đầu, thiếu chỗ thì sang bên và không rung ở ranh giới', () => {
  const head = { x: 180, y: 120, width: 80, height: 100 };
  expect(bubblePlacement(head, 440, 600)).toEqual({ x: 184, y: 64, side: 'above' });
  const side = bubblePlacement({ ...head, y: 30 }, 440, 600);
  expect(side.side).toBe('right');
  expect(side.x).toBeGreaterThanOrEqual(head.x + head.width);
  expect(bubblePlacement({ ...head, y: 67 }, 440, 600, 'right').side).toBe('right');
  expect(bubblePlacement({ ...head, y: 75 }, 440, 600, 'right').side).toBe('above');
  const edge = bubblePlacement({ x: -40, y: -10, width: 100, height: 100 }, 100, 90);
  expect(edge.x).toBeGreaterThanOrEqual(8);
  expect(edge.x + 72).toBeLessThanOrEqual(92);
  expect(edge.y).toBeGreaterThanOrEqual(8);
  expect(edge.y + 42).toBeLessThanOrEqual(82);
});
