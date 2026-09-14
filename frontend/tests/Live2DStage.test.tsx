import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Live2DStage from '../src/Live2DStage';

const mocks = vi.hoisted(() => ({ from: vi.fn(), destroy: vi.fn(), start: vi.fn(), stop: vi.fn(), tick: null as null | (() => void) }));
vi.mock('pixi.js', () => ({ Application: class {
  view = document.createElement('canvas');
  stage = { addChild: vi.fn() };
  renderer = { resize: vi.fn() };
  ticker = { maxFPS: 0, deltaMS: 33, add: (callback: () => void) => { mocks.tick = callback; } };
  start = mocks.start; stop = mocks.stop;
  destroy = () => { this.view.remove(); mocks.destroy(); };
} }));
vi.mock('pixi-live2d-display/cubism4', () => ({ Live2DModel: { from: mocks.from }, MotionPreloadStrategy: { IDLE: 'IDLE' } }));

function fakeModel() {
  return { width: 1000, height: 2000, anchor: { set: vi.fn() }, scale: { set: vi.fn() },
    position: { set: vi.fn() }, destroy: vi.fn(), update: vi.fn(),
    internalModel: { on: vi.fn(), update: vi.fn(), coreModel: { setParameterValueById: vi.fn(), update: vi.fn() } } };
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('Live2DCubismCore', {});
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('matchMedia', () => ({ matches: true }));
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
});
afterEach(() => vi.unstubAllGlobals());

it('giảm chuyển động vẫn áp dụng pose và giải phóng renderer khi rời trang', async () => {
  const model = fakeModel();
  mocks.from.mockResolvedValue(model);
  const view = render(<Live2DStage name="Peto" />);
  await waitFor(() => expect(mocks.start).toHaveBeenCalled());
  mocks.tick!();
  expect(model.internalModel.update).toHaveBeenCalledWith(0, 0);
  expect(model.update).not.toHaveBeenCalled();
  view.unmount();
  expect(mocks.destroy).toHaveBeenCalledTimes(1);
});

it('tải lỗi vẫn có thông báo và nút thử lại', async () => {
  mocks.from.mockRejectedValue(new Error('Không tải được model'));
  render(<Live2DStage name="Peto" />);
  expect(await screen.findByRole('button', { name: 'Thử tải lại nhân vật' })).toBeTruthy();
});

it('rời trang khi đang tải không để model về muộn chiếm tài nguyên', async () => {
  let resolve!: (value: ReturnType<typeof fakeModel>) => void;
  mocks.from.mockReturnValue(new Promise((yes) => { resolve = yes; }));
  const view = render(<Live2DStage name="Peto" />);
  await waitFor(() => expect(mocks.from).toHaveBeenCalled());
  view.unmount();
  const model = fakeModel();
  await act(async () => resolve(model));
  expect(model.destroy).toHaveBeenCalled();
  expect(mocks.start).not.toHaveBeenCalled();
});
