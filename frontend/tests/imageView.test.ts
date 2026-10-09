import { describe, expect, it } from 'vitest';
import { boundImageView, fitImageScale, INITIAL_IMAGE_VIEW, transformImageView } from '../src/features/chat/imageView';

describe('zoom ảnh đính kèm', () => {
  it('vừa khung giữ trọn ảnh dọc/ngang và không phóng lớn ảnh nhỏ', () => {
    const viewport = { width: 832, height: 632 };
    expect(fitImageScale({ width: 1600, height: 900 }, viewport)).toBe(0.5);
    expect(fitImageScale({ width: 900, height: 1600 }, viewport)).toBe(0.375);
    expect(fitImageScale({ width: 100, height: 100 }, viewport)).toBe(1);
  });
  it('zoom giữ nguyên điểm ảnh dưới con trỏ', () => {
    const image = { width: 1600, height: 1200 }, viewport = { width: 832, height: 632 };
    const view = { scale: 0.5, x: 0, y: 0, fit: false }, anchor = { x: 100, y: -80 };
    const next = transformImageView(view, 1, anchor, anchor, image, viewport);
    expect((anchor.x - next.x) / next.scale).toBe((anchor.x - view.x) / view.scale);
    expect((anchor.y - next.y) / next.scale).toBe((anchor.y - view.y) / view.scale);
  });
  it('pinch có dịch tâm vẫn giữ đúng phần ảnh giữa hai ngón', () => {
    const image = { width: 1600, height: 1200 }, viewport = { width: 832, height: 632 };
    const view = { scale: 0.5, x: 0, y: 0, fit: false };
    const from = { x: 40, y: 50 }, to = { x: 80, y: 70 };
    const next = transformImageView(view, 1, from, to, image, viewport);
    expect((to.x - next.x) / next.scale).toBe(from.x / view.scale);
    expect((to.y - next.y) / next.scale).toBe(from.y / view.scale);
  });
  it('không kéo ảnh mất khỏi khung, ảnh vừa khung luôn về giữa', () => {
    const image = { width: 1000, height: 1000 }, viewport = { width: 532, height: 532 };
    expect(boundImageView({ scale: 2, x: 99999, y: -99999, fit: false }, image, viewport)).toEqual({ scale: 2, x: 750, y: -750, fit: false });
    expect(boundImageView({ ...INITIAL_IMAGE_VIEW, x: 100, y: 100 }, image, viewport)).toEqual({ scale: 0.5, x: 0, y: 0, fit: true });
  });
  it('giới hạn 800%, ảnh rất lớn vẫn thu được đủ để vừa khung', () => {
    const image = { width: 20000, height: 20000 }, viewport = { width: 432, height: 432 };
    expect(boundImageView({ scale: 100, x: 0, y: 0, fit: false }, image, viewport).scale).toBe(8);
    expect(boundImageView(INITIAL_IMAGE_VIEW, image, viewport).scale).toBe(0.02);
  });
});
