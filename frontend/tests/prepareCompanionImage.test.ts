import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { prepareCompanionImage, MAX_COMPANION_IMAGE_BYTES } from '../src/features/companion/prepareCompanionImage';

let width: number, height: number, decodeFails: boolean;
const draw = vi.fn();
const encode = vi.fn();
beforeEach(() => {
  width = 4000; height = 3000; decodeFails = false;
  URL.createObjectURL = vi.fn(() => 'blob:original'); URL.revokeObjectURL = vi.fn();
  vi.stubGlobal('Image', class {
    naturalWidth = width; naturalHeight = height;
    onload: (() => void) | null = null; onerror: (() => void) | null = null;
    set src(_value: string) { queueMicrotask(() => decodeFails ? this.onerror?.() : this.onload?.()); }
  });
  draw.mockReset(); encode.mockReset();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: draw } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(encode);
  encode.mockImplementation((callback: BlobCallback, type: string) => callback(new Blob(['compressed'], { type })));
});
afterEach(() => vi.unstubAllGlobals());

it.each([[4000, 3000, 1920, 1440], [3000, 4000, 1440, 1920]])('thu nhỏ %s × %s giữ tỷ lệ và gửi bản %s × %s', async (w, h, outW, outH) => {
  width = w; height = h;
  const original = new File(['original'], 'photo.jpg', { type: 'image/jpeg', lastModified: 123 });
  const result = await prepareCompanionImage(original);
  expect(draw.mock.calls[0].slice(1)).toEqual([0, 0, outW, outH]);
  expect(encode.mock.calls[0].slice(1)).toEqual(['image/jpeg', 0.85]);
  expect(result).not.toBe(original);
  expect(result).toMatchObject({ name: original.name, type: 'image/jpeg', lastModified: 123 });
  expect(await result.text()).toBe('compressed');
  expect(original.size).toBe(8);
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:original');
});

it('ảnh nhỏ giữ nguyên, GIF không giải mã lại để giữ chuyển động', async () => {
  width = 640; height = 480;
  const small = new File(['small'], 'small.png', { type: 'image/png' });
  expect(await prepareCompanionImage(small)).toBe(small);
  const gif = new File(['animation'], 'motion.gif', { type: 'image/gif' });
  expect(await prepareCompanionImage(gif)).toBe(gif);
  const unknownGif = new File(['animation'], 'motion.gif', { type: 'application/octet-stream' });
  expect(await prepareCompanionImage(unknownGif)).toBe(unknownGif);
  expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  expect(encode).not.toHaveBeenCalled();
});

it('PNG giữ định dạng có độ trong suốt và giảm thêm cạnh khi bản mã hóa còn nặng', async () => {
  const heavy = new Blob([new Uint8Array(MAX_COMPANION_IMAGE_BYTES + 1)], { type: 'image/png' });
  encode.mockImplementationOnce((callback: BlobCallback) => callback(heavy));
  const result = await prepareCompanionImage(new File(['png'], 'transparent.png', { type: 'image/png' }));
  expect(draw.mock.calls[1].slice(1)).toEqual([0, 0, 1536, 1152]);
  expect(result.type).toBe('image/png');
  expect(encode.mock.calls[1].slice(1)).toEqual(['image/png', undefined]);
});

it('ảnh không đọc được hoặc không mã hóa được báo lỗi và thu hồi URL tạm', async () => {
  const file = new File(['bad'], 'bad.png', { type: 'image/png' });
  decodeFails = true;
  await expect(prepareCompanionImage(file)).rejects.toThrow('Không đọc được ảnh');
  decodeFails = false; encode.mockImplementation((callback: BlobCallback) => callback(null));
  await expect(prepareCompanionImage(file)).rejects.toThrow('Không thu nhỏ được ảnh');
  expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2);
});
