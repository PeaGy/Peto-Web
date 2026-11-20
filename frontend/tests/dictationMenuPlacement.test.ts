import { expect, it } from 'vitest';
import { menuPlacement } from '../src/features/chat/DictationMenu';

// Menu micro không được tràn khỏi màn hình (chủ web gặp ngày 20/11/2026: ô nhắn ở giữa, menu mở lên mất phần đầu).

it('opens upward but never taller than the space above the button', () => {
  // Như ảnh chủ web gửi: nút ở khoảng giữa màn hình 1015 px, danh sách 10 micro dài hơn chỗ trống phía trên.
  const place = menuPlacement({ top: 568, bottom: 602 }, 1015, 900);
  expect(place.up).toBe(true);
  expect(place.maxHeight).toBeLessThanOrEqual(568 - 8 - 12);
});

it('opens downward when there is clearly more room below', () => {
  const place = menuPlacement({ top: 200, bottom: 234 }, 900, 400);
  expect(place).toEqual({ up: false, maxHeight: 460 });
});

it('stays upward when the menu fits above, as at the bottom of a long chat', () => {
  expect(menuPlacement({ top: 820, bottom: 854 }, 900, 300)).toEqual({ up: true, maxHeight: 460 });
});
