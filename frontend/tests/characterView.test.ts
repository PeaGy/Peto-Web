import { beforeEach, expect, it } from 'vitest';
import {
  CHARACTER_VIEW_KEY, DEFAULT_VIEW, MAX_ZOOM, MIN_ZOOM, clampView, lookTarget, motionEnabled, panBy, placement,
  readCharacterMotion, readCharacterView, wheelZoomFactor, writeCharacterMotion, zoomAt,
} from '../src/characterView';

const box = { width: 800, height: 600, baseX: 400, baseY: 594, baseScale: 0.3 };

beforeEach(() => localStorage.clear());

it('phóng quanh con trỏ giữ nguyên chỗ đang chỉ trên nhân vật', () => {
  const before = placement(DEFAULT_VIEW, box);
  const next = zoomAt(DEFAULT_VIEW, 2, 250, 300, box);
  const after = placement(next, box);
  const localX = (250 - before.x) / before.scale;
  const localY = (300 - before.y) / before.scale;
  expect(next.zoom).toBe(2);
  expect(after.x + localX * after.scale).toBeCloseTo(250);
  expect(after.y + localY * after.scale).toBeCloseTo(300);
});

it('giới hạn mức phóng, độ dời và bỏ qua số hỏng', () => {
  expect(zoomAt(DEFAULT_VIEW, 100, 0, 0, box).zoom).toBe(MAX_ZOOM);
  expect(zoomAt(DEFAULT_VIEW, 0.01, 0, 0, box).zoom).toBe(MIN_ZOOM);
  expect(panBy(DEFAULT_VIEW, 1e6, -1e6, box)).toEqual({ zoom: 1, panX: 0.85, panY: -0.5 });
  expect(clampView({ zoom: Number.NaN, panX: Number.NaN, panY: 3 })).toEqual({ zoom: 1, panX: 0, panY: 1 });
});

it('cuộn lên là phóng to, cuộn xuống là thu nhỏ, cuộn theo dòng quy ra pixel', () => {
  expect(wheelZoomFactor(-100, 0)).toBeGreaterThan(1);
  expect(wheelZoomFactor(100, 0)).toBeLessThan(1);
  expect(wheelZoomFactor(-3, 1)).toBeCloseTo(wheelZoomFactor(-48, 0));
});

it('con trỏ bên phải và phía trên đầu cho hướng nhìn dương, xa quá thì giới hạn ở 1', () => {
  const upRight = lookTarget(800, 0, 400, 200, 800, 600);
  expect(upRight.x).toBe(1);
  expect(upRight.y).toBeCloseTo(2 / 3);
  expect(lookTarget(-5000, 5000, 400, 200, 800, 600)).toEqual({ x: -1, y: -1 });
});

it('Theo máy nhường cho giảm chuyển động, Luôn cử động thì không', () => {
  expect(motionEnabled('system', true)).toBe(false);
  expect(motionEnabled('system', false)).toBe(true);
  expect(motionEnabled('always', true)).toBe(true);
});

it('đọc lại lựa chọn đã lưu và bỏ qua dữ liệu hỏng', () => {
  expect(readCharacterMotion()).toBe('system');
  writeCharacterMotion('always');
  expect(readCharacterMotion()).toBe('always');
  localStorage.setItem(CHARACTER_VIEW_KEY, '{không phải json');
  expect(readCharacterView()).toEqual(DEFAULT_VIEW);
  localStorage.setItem(CHARACTER_VIEW_KEY, JSON.stringify({ zoom: 9, panX: 0.2, panY: 0 }));
  expect(readCharacterView()).toEqual({ zoom: MAX_ZOOM, panX: 0.2, panY: 0 });
});
