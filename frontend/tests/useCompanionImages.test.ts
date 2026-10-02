import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useCompanionImages } from '../src/features/companion/useCompanionImages';
import { prepareCompanionImage } from '../src/features/companion/prepareCompanionImage';

vi.mock('../src/features/companion/prepareCompanionImage', async original => ({
  ...await original<typeof import('../src/features/companion/prepareCompanionImage')>(), prepareCompanionImage: vi.fn(),
}));
const file = (name: string, size = 1) => new File([new Uint8Array(size)], name, { type: 'image/png' });
beforeEach(() => {
  vi.mocked(prepareCompanionImage).mockReset().mockImplementation(async image => image);
  URL.createObjectURL = vi.fn(() => 'blob:prepared'); URL.revokeObjectURL = vi.fn();
});

it('giữ chỗ khi chọn liên tiếp, chỉ cho gửi sau xử lý và dùng bản đã thu nhỏ', async () => {
  const error = vi.fn();
  let finish!: (image: File) => void;
  vi.mocked(prepareCompanionImage).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const { result } = renderHook(() => useCompanionImages(error));
  let task!: Promise<void>;
  act(() => { task = result.current.add([file('first.png')]); });
  expect(result.current.isPreparing()).toBe(true);
  expect(result.current.pending).toBe(1);
  await act(async () => result.current.add(Array.from({ length: 4 }, (_, i) => file(`${i}.png`))));
  expect(error).toHaveBeenLastCalledWith('Mỗi tin chỉ gửi tối đa 4 ảnh.');
  const compressed = file('first.png', 10);
  await act(async () => { finish(compressed); await task; });
  expect(result.current.pending).toBe(0);
  expect(result.current.images[0].file).toBe(compressed);
  expect(URL.createObjectURL).toHaveBeenCalledWith(compressed);
});

it('tổng ảnh sau xử lý tối đa 3 MB, giữ ảnh cũ khi batch mới quá nặng', async () => {
  const error = vi.fn();
  const { result } = renderHook(() => useCompanionImages(error));
  await act(async () => result.current.add([file('first.png', 2 * 1024 * 1024)]));
  await act(async () => result.current.add([file('next.png', 2 * 1024 * 1024)]));
  expect(result.current.images).toHaveLength(1);
  expect(error).toHaveBeenLastCalledWith(expect.stringContaining('tối đa 3 MB'));
  expect(result.current.isPreparing()).toBe(false);
});

it.each(['reset', 'unmount'])('xử lý ảnh xong muộn sau %s không thêm vào chat hay báo lỗi cũ', async action => {
  const error = vi.fn();
  let finish!: (image: File) => void;
  vi.mocked(prepareCompanionImage).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const { result, unmount } = renderHook(() => useCompanionImages(error));
  let task!: Promise<void>;
  act(() => { task = result.current.add([file('old.png')]); });
  act(() => { if (action === 'reset') result.current.clear(); else unmount(); });
  await act(async () => { finish(file('old.png')); await task; });
  expect(URL.createObjectURL).not.toHaveBeenCalled();
  if (action === 'reset') {
    expect(result.current.images).toHaveLength(0);
    expect(result.current.pending).toBe(0);
    await act(async () => result.current.add([file('new.png')]));
    await waitFor(() => expect(result.current.images[0].file.name).toBe('new.png'));
  }
  expect(error.mock.calls.every(([message]) => message === null)).toBe(true);
});
