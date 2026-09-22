import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Live2DStage from '../src/Live2DStage';
import { CHARACTER } from '../src/characterConfig';
import { writeIdle } from '../src/live2dMotions';
import { writeEffects } from '../src/characterEffects';
import * as music from '../src/musicVibe';

const mocks = vi.hoisted(() => ({
  from: vi.fn(), destroy: vi.fn(), start: vi.fn(), stop: vi.fn(), tick: null as null | (() => void),
  mouth: 0, reduced: true, compact: false, resize: null as null | (() => void),
}));
vi.mock('pixi.js', () => ({ Application: class {
  view = document.createElement('canvas');
  stage = { addChild: vi.fn() };
  renderer = { resize: vi.fn() };
  ticker = { maxFPS: 0, deltaMS: 33, add: (callback: () => void) => { mocks.tick = callback; } };
  start = mocks.start; stop = mocks.stop;
  destroy = () => { this.view.remove(); mocks.destroy(); };
} }));
vi.mock('pixi-live2d-display/cubism4', () => ({ Live2DModel: { from: mocks.from }, MotionPreloadStrategy: { IDLE: 'IDLE' }, Cubism4ModelSettings: class {} }));
vi.mock('../src/voiceActivity', () => ({ voiceMouth: () => mocks.mouth }));

type Point = { x: number; y: number };
function fakeModel() {
  return { width: 1000, height: 2000, anchor: { set: vi.fn() },
    scale: { x: 1, y: 1, set: vi.fn(function (this: Point, value: number) { this.x = value; this.y = value; }) },
    position: { x: 0, y: 0, set: vi.fn(function (this: Point, x: number, y: number) { this.x = x; this.y = y; }) },
    destroy: vi.fn(), update: vi.fn(),
    internalModel: { on: vi.fn(), update: vi.fn(), focusController: { focus: vi.fn() },
      updateFocus: vi.fn(), updateNaturalMovements: vi.fn(),
      motionManager: { definitions: {}, groups: { idle: 'Idle' }, startRandomMotion: vi.fn().mockResolvedValue(true),
        startMotion: vi.fn().mockResolvedValue(true), loadMotion: vi.fn().mockResolvedValue({}), stopAllMotions: vi.fn() },
      coreModel: { setParameterValueById: vi.fn(), update: vi.fn(),
        getParameterIndex: (id: string) => ['ParamAngleX', 'ParamAngleY', 'ParamAngleZ'].indexOf(id),
        getParameterCount: () => 3, addParameterValueById: vi.fn() } } };
}

async function mount(motion?: 'system' | 'always') {
  const model = fakeModel();
  mocks.from.mockResolvedValue(model);
  const view = render(<Live2DStage name="Peto" motion={motion} />);
  await waitFor(() => expect(mocks.start).toHaveBeenCalled());
  const host = view.container.querySelector('.character-canvas') as HTMLElement;
  return { model, view, host };
}

function pointer(type: string, x: number, y: number, pointerType: string, pointerId = 1) {
  const event = new MouseEvent(type, { clientX: x, clientY: y, bubbles: true });
  Object.defineProperty(event, 'pointerType', { value: pointerType });
  Object.defineProperty(event, 'pointerId', { value: pointerId });
  return event;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mocks.mouth = 0;
  mocks.reduced = true;
  mocks.compact = false;
  vi.stubGlobal('Live2DCubismCore', {});
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { mocks.resize = callback; }
    observe() {}
    disconnect() {}
  });
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('reduce') ? mocks.reduced : query.includes('max-width') ? mocks.compact : false,
  }));
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  vi.spyOn(Element.prototype, 'clientWidth', 'get').mockReturnValue(800);
  vi.spyOn(Element.prototype, 'clientHeight', 'get').mockReturnValue(600);
});
afterEach(() => vi.unstubAllGlobals());

it('nhún theo nhạc cộng vào góc đầu, không ghi đè miệng và tôn trọng giảm chuyển động', async () => {
  const pose = vi.spyOn(music, 'musicPose').mockReturnValue({ yaw: 3, pitch: -2, roll: 1 });
  try {
    const { model, view } = await mount('always');
    const hook = model.internalModel.on.mock.calls.find(([name]) => name === 'beforeModelUpdate')![1];
    hook();
    expect(model.internalModel.coreModel.addParameterValueById).toHaveBeenCalledWith('ParamAngleX', 3);
    expect(model.internalModel.coreModel.setParameterValueById).toHaveBeenCalledWith('ParamMouthOpenY', 0);
    view.unmount(); mocks.start.mockClear();
    const reduced = await mount('system');
    reduced.model.internalModel.on.mock.calls.find(([name]) => name === 'beforeModelUpdate')![1]();
    expect(reduced.model.internalModel.coreModel.addParameterValueById).not.toHaveBeenCalled();
  } finally { pose.mockRestore(); }
});

it('giảm chuyển động vẫn áp dụng pose và giải phóng renderer khi rời trang', async () => {
  const { model, view } = await mount();
  mocks.tick!();
  expect(model.internalModel.update).toHaveBeenCalledWith(0, 0);
  expect(model.update).not.toHaveBeenCalled();
  view.unmount();
  expect(mocks.destroy).toHaveBeenCalledTimes(1);
});

it('chọn Luôn cử động thì nhân vật cử động dù thiết bị bật giảm chuyển động', async () => {
  const { model } = await mount('always');
  mocks.tick!();
  expect(model.update).toHaveBeenCalledWith(33);
  expect(model.internalModel.update).not.toHaveBeenCalled();
});

it('đổi idle trên sân khấu ngay mà không tải lại model', async () => {
  const { model } = await mount('always');
  act(() => writeIdle(CHARACTER.id, 'off'));
  expect(model.internalModel.motionManager.stopAllMotions).toHaveBeenCalled();
  expect(await model.internalModel.motionManager.startRandomMotion('Idle', 1)).toBe(false);
  expect(mocks.from).toHaveBeenCalledTimes(1);
});

it('tắt theo con trỏ dừng nhìn theo ngay và không dừng idle', async () => {
  const { model } = await mount('always');
  const focus = model.internalModel.focusController.focus;
  act(() => writeEffects(CHARACTER.id, { cursor: false, breath: true, physics: true }));
  expect(focus).toHaveBeenLastCalledWith(0, 0, true);
  focus.mockClear();
  fireEvent(window, pointer('pointermove', 700, 100, 'mouse'));
  expect(focus).not.toHaveBeenCalled();
  expect(model.internalModel.motionManager.stopAllMotions).not.toHaveBeenCalled();
  act(() => writeEffects(CHARACTER.id, { cursor: true, breath: true, physics: true }));
  focus.mockClear();
  fireEvent(window, pointer('pointermove', 700, 100, 'mouse'));
  expect(focus).toHaveBeenCalled();
});

it('cuộn chuột phóng to quanh con trỏ, bấm đúp về cỡ vừa khung và nhớ góc nhìn', async () => {
  const { model, view, host } = await mount();
  const fitted = model.scale.set.mock.calls.at(-1)![0];
  fireEvent.wheel(host, { deltaY: -100, clientX: 400, clientY: 300 });
  expect(model.scale.y).toBeGreaterThan(fitted);
  fireEvent.doubleClick(host);
  expect(model.scale.y).toBeCloseTo(fitted);
  fireEvent.wheel(host, { deltaY: -200, clientX: 400, clientY: 100 });
  view.unmount();
  expect(JSON.parse(localStorage.getItem('peto-character-view')!).zoom).toBeGreaterThan(1);
});

it('máy tính: giữ chuột giữa để dời nhân vật, kéo bằng chuột trái thì không', async () => {
  const { model, host } = await mount();
  const mouse = (type: string, x: number, button: number, buttons: number) => {
    const event = new MouseEvent(type, { clientX: x, clientY: 300, button, buttons, bubbles: true, cancelable: true });
    Object.defineProperty(event, 'pointerType', { value: 'mouse' });
    Object.defineProperty(event, 'pointerId', { value: 1 });
    return event;
  };
  const start = model.position.x;
  host.dispatchEvent(mouse('pointerdown', 400, 0, 1));
  host.dispatchEvent(mouse('pointermove', 470, 0, 1));
  host.dispatchEvent(mouse('pointerup', 470, 0, 0));
  expect(model.position.x).toBe(start);

  // Nút giữa: chặn cuộn tự động của trình duyệt rồi mới kéo.
  const press = mouse('mousedown', 400, 1, 4);
  host.dispatchEvent(press);
  expect(press.defaultPrevented).toBe(true);
  host.dispatchEvent(mouse('pointerdown', 400, 1, 4));
  host.dispatchEvent(mouse('pointermove', 470, 1, 4));
  const moved = model.position.x;
  expect(moved).toBeGreaterThan(start);
  // Nhả nút giữa nhưng vẫn giữ nút trái: không có pointerup, vẫn phải dừng kéo.
  host.dispatchEvent(mouse('pointermove', 520, 1, 1));
  host.dispatchEvent(mouse('pointermove', 560, 1, 1));
  expect(model.position.x).toBe(moved);
});

it('điện thoại khóa khung: cuộn, kéo hay bấm đúp đều không đổi góc nhìn', async () => {
  mocks.compact = true;
  localStorage.setItem('peto-character-view', JSON.stringify({ zoom: 3, panX: 0.4, panY: 1 }));
  const { model, view, host } = await mount();
  const locked = model.scale.y;
  expect(locked).toBeCloseTo(600 * CHARACTER.compactHeight / 2000);
  expect(model.position.x).toBe(400);
  fireEvent.wheel(host, { deltaY: -200, clientX: 400, clientY: 300 });
  host.dispatchEvent(pointer('pointerdown', 400, 300, 'touch'));
  host.dispatchEvent(pointer('pointermove', 480, 360, 'touch'));
  fireEvent.doubleClick(host);
  expect(model.scale.y).toBe(locked);
  expect(model.position.x).toBe(400);
  view.unmount();
  expect(JSON.parse(localStorage.getItem('peto-character-view')!)).toEqual({ zoom: 3, panX: 0.4, panY: 1 });
});

it('điện thoại mở bàn phím: sân khấu thấp đi nhưng nhân vật giữ cỡ và chỗ đứng', async () => {
  mocks.compact = true;
  const { model } = await mount();
  const scale = model.scale.y;
  const bottom = model.position.y;
  vi.spyOn(Element.prototype, 'clientHeight', 'get').mockReturnValue(340);
  mocks.resize!();
  expect(model.scale.y).toBe(scale);
  expect(model.position.y).toBe(bottom);
  // Xoay máy đổi bề ngang thì khung được tính lại theo chiều cao mới.
  vi.spyOn(Element.prototype, 'clientWidth', 'get').mockReturnValue(600);
  mocks.resize!();
  expect(model.scale.y).toBeCloseTo(340 * CHARACTER.compactHeight / 2000);
});

it('nhìn theo con trỏ khi được cử động, đứng yên thì không', async () => {
  const still = await mount();
  window.dispatchEvent(pointer('pointermove', 800, 0, 'mouse'));
  expect(still.model.internalModel.focusController.focus).not.toHaveBeenCalled();
  still.view.unmount();

  const moving = await mount('always');
  window.dispatchEvent(pointer('pointermove', 800, 0, 'mouse'));
  const [x, y] = moving.model.internalModel.focusController.focus.mock.calls.at(-1)!;
  expect(x).toBe(1);
  expect(y).toBeGreaterThan(0);
});

it('điện thoại: giữ ngón tay trên màn hình thì nhân vật nhìn theo, nhấc tay thì nhìn thẳng', async () => {
  mocks.compact = true;
  const { model } = await mount('always');
  const focus = model.internalModel.focusController.focus;
  window.dispatchEvent(pointer('pointerdown', 800, 0, 'touch', 7));
  const [x, y] = focus.mock.calls.at(-1)!;
  expect(x).toBe(1);
  expect(y).toBeGreaterThan(0);
  window.dispatchEvent(pointer('pointermove', 0, 600, 'touch', 8));
  expect(focus).toHaveBeenCalledTimes(1);
  window.dispatchEvent(pointer('pointerup', 800, 0, 'touch', 7));
  expect(focus).toHaveBeenLastCalledWith(0, 0);
});

it('máy tính: chạm màn hình để kéo, không làm nhân vật nhìn theo ngón tay', async () => {
  const { model } = await mount('always');
  window.dispatchEvent(pointer('pointerdown', 800, 0, 'touch', 3));
  window.dispatchEvent(pointer('pointermove', 700, 50, 'touch', 3));
  expect(model.internalModel.focusController.focus).not.toHaveBeenCalled();
});

it('miệng mở theo âm thanh đang phát và khép lại khi im lặng', async () => {
  const { model } = await mount();
  const [, beforeModelUpdate] = model.internalModel.on.mock.calls.find(([name]) => name === 'beforeModelUpdate')!;
  mocks.mouth = 1;
  beforeModelUpdate();
  expect(model.internalModel.coreModel.setParameterValueById).toHaveBeenLastCalledWith('ParamMouthOpenY', 0.7);
  mocks.mouth = 0;
  for (let i = 0; i < 12; i++) beforeModelUpdate();
  expect(model.internalModel.coreModel.setParameterValueById).toHaveBeenLastCalledWith('ParamMouthOpenY', 0);
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
