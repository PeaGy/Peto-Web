import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Live2DStage from '../src/features/companion/characters/Live2DStage';
import { CHARACTER } from '../src/features/companion/characters/characterConfig';
import { writeIdle } from '../src/features/companion/characters/live2dMotions';
import { readEffects, writeEffects } from '../src/features/companion/characters/characterEffects';
import { DEFAULT_MAGIC, writeMagic } from '../src/features/companion/characters/magic/magicSettings';
import * as music from '../src/features/companion/characters/musicVibe';
import { previewExpression, writeExpressions } from '../src/features/companion/characters/characterExpressions';
import { readCharacterView, watchCharacterView, writeCharacterView } from '../src/features/companion/characters/characterView';

const mocks = vi.hoisted(() => ({
  from: vi.fn(), destroy: vi.fn(), start: vi.fn(), stop: vi.fn(), render: vi.fn(), tick: null as null | (() => void),
  mouth: 0, reduced: true, compact: false, resize: null as null | (() => void), getAssets: vi.fn(),
}));
vi.mock('../src/shared/motion', async original => ({
  ...await original<typeof import('../src/shared/motion')>(), isReducedMotion: () => mocks.reduced,
}));
vi.mock('pixi.js', () => ({ Application: class {
  view = document.createElement('canvas');
  stage = { addChild: vi.fn() };
  renderer = { resize: vi.fn(), render: mocks.render, resolution: 1 };
  ticker = { maxFPS: 0, deltaMS: 33, add: (callback: () => void) => { mocks.tick = callback; } };
  start = mocks.start; stop = mocks.stop;
  destroy = () => { this.view.remove(); mocks.destroy(); };
} }));
vi.mock('pixi-live2d-display/cubism4', () => ({ Live2DModel: { from: mocks.from }, MotionPreloadStrategy: { IDLE: 'IDLE' }, Cubism4ModelSettings: class {} }));
vi.mock('../src/features/companion/speech/voiceActivity', () => ({ voiceMouth: () => mocks.mouth, voicePlaying: () => mocks.mouth > 0 }));
vi.mock('../src/features/companion/characters/characterLibrary', async (original) => ({
  ...await original<typeof import('../src/features/companion/characters/characterLibrary')>(),
  getCharacterAssets: mocks.getAssets,
}));

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

it('model nhập riêng dùng ánh xạ đầu, mắt và miệng; dừng giọng thì khép miệng riêng', async () => {
  const model = fakeModel(), internal = model.internalModel, core = internal.coreModel;
  const ids = ['ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'HeadInput', 'EyeInput', 'MouthInput'];
  core.getParameterIndex = id => ids.includes(id) ? ids.indexOf(id) : ids.length;
  core.getParameterCount = () => ids.length;
  Object.assign(core, { getParameterValueById: () => 0 });
  Object.assign(internal.focusController, { x: 0.5, y: 0 });
  const ranges = { inputMin: -30, inputMax: 30, outputMin: -20, outputMax: 20 };
  mocks.getAssets.mockResolvedValue({ id: 'custom', entry: 'model.model3.json', files: [{ path: 'model.model3.json', blob: new Blob([JSON.stringify({ Version: 3, FileReferences: {} })]) }],
    controls: { headX: { id: 'HeadInput', ...ranges }, eyeX: { id: 'EyeInput', inputMin: -1, inputMax: 1, outputMin: 1, outputMax: -1 },
      mouth: { id: 'MouthInput', inputMin: 0, inputMax: 1, outputMin: 0, outputMax: 2 } } });
  mocks.from.mockResolvedValue(model);
  mocks.mouth = 0.7;
  const view = render(<Live2DStage name="Avatar" motion="always" character={{ id: 'custom', name: 'Avatar', format: 'live2d', bytes: 0, createdAt: 0 }} />);
  await waitFor(() => expect(mocks.start).toHaveBeenCalled());
  internal.updateFocus();
  expect(core.setParameterValueById).toHaveBeenCalledWith('HeadInput', 10);
  expect(core.setParameterValueById).toHaveBeenCalledWith('EyeInput', -0.5);
  const beforePhysics = internal.on.mock.calls.find(([event]) => event === 'afterMotionUpdate')![1];
  const beforeDraw = internal.on.mock.calls.find(([event]) => event === 'beforeModelUpdate')![1];
  beforePhysics(); beforeDraw();
  expect(core.setParameterValueById.mock.calls.some(([id, value]) => id === 'MouthInput' && value > 0)).toBe(true);
  expect(core.setParameterValueById.mock.calls.some(([id]) => id === 'ParamMouthOpenY')).toBe(false);
  mocks.mouth = 0;
  beforePhysics(); beforeDraw();
  expect(core.setParameterValueById).toHaveBeenLastCalledWith('MouthInput', 0);
  view.unmount();
});

it('Live2D chỉ báo ready sau lần vẽ đầu tiên, lỗi vẽ vẫn cho phép thử lại', async () => {
  let finish!: (value: ReturnType<typeof fakeModel>) => void;
  mocks.from.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  const status = vi.fn((value: string) => { if (value === 'ready') expect(mocks.render).toHaveBeenCalled(); });
  const view = render(<Live2DStage name="Peto" onStatusChange={status} />);
  await waitFor(() => expect(mocks.from).toHaveBeenCalled());
  expect(status.mock.calls.map(([value]) => value)).toEqual(['loading']);
  await act(async () => finish(fakeModel()));
  expect(status.mock.calls.map(([value]) => value)).toEqual(['loading', 'ready']);
  fireEvent(view.container.querySelector('canvas')!, new Event('webglcontextlost', { cancelable: true }));
  expect(status).toHaveBeenLastCalledWith('error');
  mocks.render.mockImplementationOnce(() => { throw new Error('Lỗi vẽ thử'); });
  mocks.from.mockResolvedValue(fakeModel());
  fireEvent.click(screen.getByRole('button', { name: 'Thử tải lại nhân vật' }));
  await waitFor(() => expect(status.mock.calls.map(([value]) => value)).toEqual(['loading', 'ready', 'error', 'loading', 'error']));
});

it('idle eyes override motion eye values even with pointer tracking off and reduced motion on', async () => {
  const random = vi.spyOn(Math, 'random').mockReturnValue(0.8);
  writeEffects(CHARACTER.id, { cursor: false, breath: true, physics: true, idleEyes: true });
  const model = fakeModel();
  const core = model.internalModel.coreModel;
  core.getParameterIndex = id => ['ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'ParamEyeBallX', 'ParamEyeBallY'].indexOf(id);
  core.getParameterCount = () => 5;
  mocks.from.mockResolvedValue(model);
  const view = render(<Live2DStage name="Peto" motion="system" />);
  await waitFor(() => expect(mocks.start).toHaveBeenCalled());
  const hook = model.internalModel.on.mock.calls.find(([name]) => name === 'beforeModelUpdate')![1];
  for (let i = 0; i < 60; i++) hook();
  const eyes = core.setParameterValueById.mock.calls.filter(([id]) => id === 'ParamEyeBallX');
  expect(eyes.length).toBe(60);
  expect(eyes.at(-1)![1]).toBeGreaterThan(0.5);
  expect(core.addParameterValueById).not.toHaveBeenCalled();
  act(() => writeEffects(CHARACTER.id, { cursor: false, breath: true, physics: true, idleEyes: false }));
  for (let i = 0; i < 90; i++) hook();
  core.setParameterValueById.mockClear(); hook();
  expect(core.setParameterValueById.mock.calls.some(([id]) => id === 'ParamEyeBallX')).toBe(false);
  view.unmount(); random.mockRestore();
});

it('pauses when hidden and never restarts a lost WebGL context on visibility changes', async () => {
  const { view } = await mount();
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  expect(mocks.stop).toHaveBeenCalled();
  hidden.mockReturnValue(false); mocks.start.mockClear();
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  expect(mocks.start).toHaveBeenCalledOnce();
  fireEvent(view.container.querySelector('canvas')!, new Event('webglcontextlost', { cancelable: true }));
  mocks.start.mockClear();
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  expect(mocks.start).not.toHaveBeenCalled();
  hidden.mockRestore();
});

it('nhún theo nhạc cộng vào góc đầu, không ghi đè miệng và tôn trọng giảm chuyển động', async () => {
  writeEffects(CHARACTER.id, { cursor: true, breath: true, physics: true, idleEyes: false });
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

it('shows the emotion Peto chose with the model’s own file, even during loading, and stops when disabled', async () => {
  const model = fakeModel();
  const manager = { definitions: [{ Name: 'Happy', File: 'happy.exp3.json' }], reserveExpressionIndex: -1,
    currentExpression: {}, defaultExpression: {}, resetExpression: vi.fn(), update: vi.fn(), setExpression: vi.fn().mockResolvedValue(true) };
  Object.assign(model.internalModel.motionManager, { expressionManager: manager });
  mocks.from.mockResolvedValue(model);
  const view = render(<Live2DStage name="Peto" emotion={{ emotion: 'happy', key: 1 }} />);
  await waitFor(() => expect(manager.setExpression).toHaveBeenCalledWith(0));
  model.internalModel.on.mock.calls.find(([name]) => name === 'beforeModelUpdate')![1]();
  expect(manager.update).toHaveBeenCalled();
  act(() => writeExpressions(CHARACTER.id, { enabled: false, mapping: {} }));
  expect(manager.currentExpression).toBe(manager.defaultExpression);
  manager.setExpression.mockClear();
  view.rerender(<Live2DStage name="Peto" emotion={{ emotion: 'happy', key: 2 }} />);
  expect(manager.setExpression).not.toHaveBeenCalled();
  // Bấm thẻ trong bảng Nhân vật vẫn xem thử được khi đã tắt.
  act(() => previewExpression(CHARACTER.id, 'happy'));
  await waitFor(() => expect(manager.setExpression).toHaveBeenCalledWith(0));
  view.unmount(); expect(manager.reserveExpressionIndex).toBe(-1);
});

it('a model without expression files gets the built-in face after its motion, then fades back to normal', async () => {
  const model = fakeModel();
  const ids = ['ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'ParamEyeLSmile', 'ParamEyeRSmile', 'ParamMouthForm', 'ParamCheek',
    'ParamBrowLY', 'ParamBrowRY', 'ParamEyeLOpen', 'ParamEyeROpen'];
  Object.assign(model.internalModel.coreModel, {
    getParameterIndex: (id: string) => ids.indexOf(id), getParameterCount: () => ids.length,
    getParameterMinimumValue: () => -1, getParameterMaximumValue: () => 1, multiplyParameterValueById: vi.fn(),
  });
  mocks.from.mockResolvedValue(model);
  const view = render(<Live2DStage name="Peto" emotion={{ emotion: 'happy', key: 1 }} />);
  await waitFor(() => expect(model.internalModel.on).toHaveBeenCalledWith('beforeModelUpdate', expect.any(Function)));
  const update = model.internalModel.on.mock.calls.find(([name]) => name === 'beforeModelUpdate')![1];
  const set = model.internalModel.coreModel.setParameterValueById;
  const mouthForm = () => set.mock.calls.filter(([id]) => id === 'ParamMouthForm');
  for (let i = 0; i < 20; i++) update();
  expect(mouthForm().at(-1)).toEqual(['ParamMouthForm', 1, expect.closeTo(1, 1)]);

  view.rerender(<Live2DStage name="Peto" emotion={null} />);
  for (let i = 0; i < 120; i++) update();
  set.mockClear();
  update();
  expect(mouthForm()).toEqual([]);
  view.unmount();
});

it('giảm chuyển động vẫn áp dụng pose và giải phóng renderer khi rời trang', async () => {
  const { model, view } = await mount();
  expect(model.update).toHaveBeenCalledWith(0);
  model.update.mockClear();
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

it('điện thoại: cuộn, kéo hay bấm đúp không đổi góc nhìn; dùng góc nhìn riêng của điện thoại, chỉnh từ trang Nhân vật', async () => {
  mocks.compact = true;
  // Góc nhìn máy tính không áp lên khung điện thoại.
  localStorage.setItem('peto-character-view', JSON.stringify({ zoom: 3, panX: 0.4, panY: 1 }));
  localStorage.setItem(`peto-character-view-compact:${CHARACTER.id}`, JSON.stringify({ zoom: 0.8, panX: 0.1, panY: 0 }));
  const { model, view, host } = await mount();
  const frame = 600 * CHARACTER.compactHeight / 2000;
  // Độ dời ngang trên điện thoại tính theo chiều cao khung (bề ngang danh nghĩa 9 : 19,5), không theo bề ngang sân khấu.
  const unit = 600 * 9 / 19.5;
  expect(model.scale.y).toBeCloseTo(frame * 0.8);
  expect(model.position.x).toBeCloseTo(400 + 0.1 * unit);
  fireEvent.wheel(host, { deltaY: -200, clientX: 400, clientY: 300 });
  host.dispatchEvent(pointer('pointerdown', 400, 300, 'touch'));
  host.dispatchEvent(pointer('pointermove', 480, 360, 'touch'));
  fireEvent.doubleClick(host);
  expect(model.scale.y).toBeCloseTo(frame * 0.8);
  expect(model.position.x).toBeCloseTo(400 + 0.1 * unit);
  // Thanh trượt của trang Nhân vật trên điện thoại đổi khung điện thoại; góc nhìn máy tính gửi tới thì bỏ qua.
  act(() => writeCharacterView({ zoom: 1.5, panX: 0.1, panY: 0 }, CHARACTER.id, 'panel', false));
  expect(model.scale.y).toBeCloseTo(frame * 0.8);
  act(() => writeCharacterView({ zoom: 1.2, panX: -0.2, panY: 0.1 }, CHARACTER.id, 'panel', true));
  expect(model.scale.y).toBeCloseTo(frame * 1.2);
  expect(model.position.x).toBeCloseTo(400 - 0.2 * unit);
  view.unmount();
  // Sân khấu điện thoại không ghi đè góc nhìn máy tính (chỉ còn giá trị bên máy tính vừa ghi).
  expect(JSON.parse(localStorage.getItem('peto-character-view')!)).toEqual({ zoom: 1.5, panX: 0.1, panY: 0 });
  expect(readCharacterView(CHARACTER.id, true)).toEqual({ zoom: 1.2, panX: -0.2, panY: 0.1 });
});

it('điện thoại mở bàn phím: sân khấu thấp đi nhưng nhân vật giữ cỡ và chỗ đứng', async () => {
  mocks.compact = true;
  localStorage.setItem(`peto-character-view-compact:${CHARACTER.id}`, JSON.stringify({ zoom: 1.1, panX: 0, panY: 0.2 }));
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
  expect(model.scale.y).toBeCloseTo(340 * CHARACTER.compactHeight / 2000 * 1.1);
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
  const opened = model.internalModel.coreModel.setParameterValueById.mock.calls.at(-1)!;
  expect(opened[0]).toBe('ParamMouthOpenY');
  expect(opened[1]).toBeGreaterThan(0.6);
  expect(opened[1]).toBeLessThan(1);
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

it('bong bóng đi theo đầu khi phóng/dời và ẩn khi dừng trả lời hoặc mất WebGL', async () => {
  const model = fakeModel(); mocks.from.mockResolvedValue(model);
  const view = render(<Live2DStage name="Peto" thinking />);
  await waitFor(() => expect(mocks.start).toHaveBeenCalled());
  act(() => mocks.tick!());
  const bubble = screen.getByRole('status', { name: 'Peto đang nghĩ và trả lời' });
  expect(bubble.style.visibility).toBe('visible');
  const start = bubble.style.transform;
  fireEvent.wheel(view.container.querySelector('.character-canvas')!, { deltaY: -200, clientX: 100, clientY: 200 });
  act(() => mocks.tick!());
  expect(bubble.style.transform).not.toBe(start);
  view.rerender(<Live2DStage name="Peto" thinking={false} />);
  expect(screen.queryByRole('status', { name: 'Peto đang nghĩ và trả lời' })).toBeNull();
  view.rerender(<Live2DStage name="Peto" thinking />);
  fireEvent(view.container.querySelector('canvas')!, new Event('webglcontextlost', { cancelable: true }));
  expect(screen.queryByRole('status', { name: 'Peto đang nghĩ và trả lời' })).toBeNull();
});

it('model có vùng Head và Layout riêng đặt bong bóng đúng tọa độ đã biến đổi', async () => {
  const model = fakeModel();
  Object.assign(model.internalModel, { hitAreas: { Head: { index: 2 } },
    getDrawableBounds: () => ({ x: 200, y: 40, width: 200, height: 200 }),
    localTransform: { apply: (point: Point) => ({ x: point.x + 100, y: point.y + 200 }) } });
  mocks.from.mockResolvedValue(model);
  render(<Live2DStage name="Peto" thinking />);
  await waitFor(() => expect(mocks.start).toHaveBeenCalled());
  act(() => mocks.tick!());
  const transform = screen.getByRole('status', { name: 'Peto đang nghĩ và trả lời' }).style.transform;
  const [, x, y] = transform.match(/translate3d\(([^p]+)px, ([^p]+)px, 0\)/)!;
  expect(Number(x)).toBeCloseTo(335.2);
  expect(Number(y)).toBeCloseTo(31.12);
});

it('gõ trên máy tính ưu tiên ô chat dù tắt theo chuột; tắt toggle, blur, mobile và giảm chuyển động đều dừng nhìn', async () => {
  const model = fakeModel(); mocks.from.mockResolvedValue(model);
  const input = document.createElement('textarea'); document.body.append(input); input.focus();
  vi.spyOn(document, 'hasFocus').mockReturnValue(true);
  vi.spyOn(input, 'getBoundingClientRect').mockReturnValue({ x: 900, y: 500, left: 900, top: 500, width: 200, height: 50 } as DOMRect);
  writeEffects(CHARACTER.id, { cursor: false, breath: true, physics: true });
  const attention = { typing: true, input: { current: input } };
  const view = render(<Live2DStage name="Peto" motion="always" attention={attention} />);
  await waitFor(() => expect(mocks.start).toHaveBeenCalled());
  const focus = model.internalModel.focusController.focus;
  act(() => mocks.tick!());
  expect(focus).toHaveBeenLastCalledWith(1, expect.any(Number));
  const [, y] = focus.mock.calls.at(-1)!; expect(y).toBeLessThan(0);
  act(() => writeEffects(CHARACTER.id, { ...readEffects(CHARACTER.id), composerGaze: false }));
  act(() => mocks.tick!());
  expect(focus.mock.calls.at(-1)![0]).toBeGreaterThan(0.9);
  expect(focus.mock.calls.at(-1)![0]).toBeLessThan(1);
  act(() => { for (let i = 0; i < 200; i++) mocks.tick!(); });
  expect(focus).toHaveBeenLastCalledWith(0, 0);
  act(() => writeEffects(CHARACTER.id, { ...readEffects(CHARACTER.id), composerGaze: true }));
  input.focus(); act(() => mocks.tick!()); expect(focus).toHaveBeenLastCalledWith(1, expect.any(Number));
  input.blur(); act(() => mocks.tick!());
  expect(focus.mock.calls.at(-1)![0]).toBeGreaterThan(0.9);
  act(() => { for (let i = 0; i < 200; i++) mocks.tick!(); });
  expect(focus).toHaveBeenLastCalledWith(0, 0);
  input.focus();
  mocks.compact = true;
  view.unmount(); mocks.start.mockClear(); focus.mockClear();
  const mobile = render(<Live2DStage name="Peto" motion="always" attention={attention} />);
  await waitFor(() => expect(mocks.start).toHaveBeenCalled());
  act(() => mocks.tick!()); expect(focus).not.toHaveBeenCalled();
  mobile.unmount(); mocks.compact = false; mocks.start.mockClear();
  const reduced = render(<Live2DStage name="Peto" motion="system" attention={attention} />);
  await waitFor(() => expect(mocks.start).toHaveBeenCalled());
  act(() => mocks.tick!()); expect(focus).toHaveBeenLastCalledWith(0, 0, true);
  reduced.unmount(); input.remove();
});

it('Kích thước và vị trí ở trang Nhân vật: góc nhìn ghi từ thanh trượt đặt lại nhân vật ngay; chỉ đổi mức phóng thì phóng quanh đầu rồi báo lại', async () => {
  const { model, view } = await mount();
  // Sân khấu 800 × 600, model 1000 × 2000: vừa khung theo chiều cao, chân ở giữa đáy.
  expect(model.scale.x).toBeCloseTo(0.288);
  const head = () => model.position.y - 2000 * model.scale.y * CHARACTER.headHeight;
  const before = head();
  const seen: [unknown, unknown][] = [];
  const off = watchCharacterView(CHARACTER.id, (next, source) => seen.push([next, source]));
  act(() => writeCharacterView({ zoom: 2, panX: 0, panY: 0 }, CHARACTER.id, 'panel'));
  expect(model.scale.x).toBeCloseTo(0.576);
  expect(model.position.x).toBeCloseTo(400);
  expect(head()).toBeCloseTo(before);
  // Sân khấu báo độ dời mới (bên ghi là chính nó) để thanh Dọc đi theo, và lưu lại.
  expect(seen).toHaveLength(2);
  expect(seen.filter(([, source]) => source !== 'panel')).toHaveLength(1);
  expect(readCharacterView(CHARACTER.id).zoom).toBe(2);
  expect(readCharacterView(CHARACTER.id).panY).toBeGreaterThan(0);
  act(() => writeCharacterView({ zoom: 2, panX: 0.1, panY: 0.2 }, CHARACTER.id, 'panel'));
  expect(model.position.x).toBeCloseTo(480);
  expect(model.position.y).toBeCloseTo(594 + 120);
  expect(seen).toHaveLength(3);
  // Góc nhìn của nhân vật khác không đụng tới sân khấu này.
  act(() => writeCharacterView({ zoom: 3, panX: 0, panY: 0 }, 'khac', 'panel'));
  expect(model.scale.x).toBeCloseTo(0.576);
  off(); view.unmount();
});


it('MAGIC: học xong mới báo sẵn sàng, tắt idle và nhìn theo con trỏ, đầu chuyển động, về Hiện tại thì nhả quyền', async () => {
  writeMagic(CHARACTER.id, { ...DEFAULT_MAGIC, driver: 'magic' });
  const model = fakeModel(), internal = model.internalModel, core = internal.coreModel;
  const ids = ['ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'ParamBodyAngleX', 'ParamEyeBallX', 'ParamEyeBallY', 'ParamMouthForm', 'ParamEyeLOpen', 'ParamEyeROpen'];
  const values = new Map(ids.map(id => [id, 0]));
  Object.assign(core, { getParameterIndex: (id: string) => ids.indexOf(id), getParameterCount: () => ids.length,
    getParameterValueById: (id: string) => values.get(id) ?? 0, getParameterMinimumValue: () => -1, getParameterMaximumValue: () => 1,
    multiplyParameterValueById: vi.fn(), setParameterValueById: vi.fn((id: string, value: number) => { values.set(id, value); }) });
  mocks.from.mockResolvedValue(model);
  const status = vi.fn();
  const view = render(<Live2DStage name="Peto" motion="always" onStatusChange={status} />);
  await waitFor(() => expect(status).toHaveBeenLastCalledWith('ready'));
  expect(await internal.motionManager.startRandomMotion('Idle', 1)).toBe(false);
  const magic = internal.on.mock.calls.filter(([name]) => name === 'afterMotionUpdate').at(-1)![1];
  const angles = new Set<string>();
  for (let i = 0; i < 60; i++) { mocks.tick!(); magic(); angles.add(values.get('ParamAngleX')!.toFixed(2)); }
  expect(angles.size).toBeGreaterThan(5);
  expect(Math.max(...[...angles].map(Number).map(Math.abs))).toBeLessThanOrEqual(30);
  internal.focusController.focus.mockClear();
  act(() => { window.dispatchEvent(pointer('pointermove', 100, 100, 'mouse')); });
  expect(internal.focusController.focus).not.toHaveBeenCalled();
  // Về "Hiện tại": nhả quyền dần (gần hết sau 1 giây), khoảng 2 giây thì thôi ghi hẳn.
  act(() => writeMagic(CHARACTER.id, DEFAULT_MAGIC));
  for (let i = 0; i < 80; i++) { mocks.tick!(); magic(); }
  core.setParameterValueById.mockClear();
  magic();
  expect(core.setParameterValueById.mock.calls.some(([id]) => id === 'ParamAngleX')).toBe(false);
  expect(model.position.set).toHaveBeenLastCalledWith(model.position.x, model.position.y);
  expect(await internal.motionManager.startRandomMotion('Idle', 1)).toBe(true);
  view.unmount();
});
