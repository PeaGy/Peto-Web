import { act, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { BoxGeometry, Group, Mesh, MeshBasicMaterial, Object3D, Vector3 } from 'three';
import VRMStage from '../src/features/companion/characters/VRMStage';

const mocks = vi.hoisted(() => ({ parse: vi.fn(), dispose: vi.fn(), rendererDispose: vi.fn(), frame: null as null | ((time: number) => void), mouth: 0 }));
vi.mock('three', async original => ({ ...await original<typeof import('three')>(), WebGLRenderer: class {
  domElement = document.createElement('canvas');
  setPixelRatio() {} setClearColor() {} setSize() {} render() {} forceContextLoss() {}
  dispose = mocks.rendererDispose;
} }));
vi.mock('three/addons/loaders/GLTFLoader.js', () => ({ GLTFLoader: class { register() {} parseAsync = mocks.parse; } }));
vi.mock('three/addons/controls/OrbitControls.js', () => ({ OrbitControls: class { target = new Vector3(); update() {} dispose() {} } }));
vi.mock('@pixiv/three-vrm', () => ({ VRMLoaderPlugin: class {}, VRMUtils: { rotateVRM0() {}, deepDispose: mocks.dispose } }));
vi.mock('../src/features/companion/characters/characterLibrary', () => ({ getCharacterAssets: async () => ({ entry: 'test.vrm', files: [{ path: 'test.vrm', blob: { arrayBuffer: async () => new ArrayBuffer(0) } }] }) }));
vi.mock('../src/features/companion/characters/characterImport', () => ({ validateVRM() {} }));
vi.mock('../src/features/companion/speech/voiceActivity', () => ({ voiceMouth: () => mocks.mouth, voicePlaying: () => mocks.mouth > 0 }));
const character = { id: 'vrm-test', name: 'VRM', format: 'vrm' as const, bytes: 1, createdAt: 0 };
function avatar() {
  const scene = new Group(); scene.add(new Mesh(new BoxGeometry(1, 2, 1), new MeshBasicMaterial()));
  const presets = ['aa', 'blink', 'happy', 'sad', 'angry', 'surprised', 'relaxed'];
  return { scene, humanoid: { setNormalizedPose: vi.fn(), getNormalizedBoneNode: () => new Object3D(), getRawBoneNode: () => new Object3D() },
    expressionManager: { setValue: vi.fn(), getExpression: (name: string) => presets.includes(name) ? {} : null }, update: vi.fn() };
}
beforeEach(() => {
  vi.clearAllMocks(); mocks.mouth = 0;
  vi.spyOn(performance, 'now').mockReturnValue(0);
  vi.stubGlobal('requestAnimationFrame', (callback: (time: number) => void) => { mocks.frame = callback; return 1; });
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce') }));
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
});
afterEach(() => vi.unstubAllGlobals());
it('VRM đứng yên vẫn mở miệng theo âm thanh, dừng đọc thì khép miệng; rời trang giải phóng model', async () => {
  const vrm = avatar(); mocks.parse.mockResolvedValue({ userData: { vrm }, scene: vrm.scene });
  const view = render(<VRMStage character={character} motion="system" />);
  await waitFor(() => expect(mocks.frame).toBeTypeOf('function'));
  mocks.mouth = 1; act(() => mocks.frame!(40));
  const opened = vrm.expressionManager.setValue.mock.calls.find(([name]) => name === 'aa')!;
  expect(opened[1]).toBeGreaterThan(0.6);
  expect(opened[1]).toBeLessThan(1);
  mocks.mouth = 0;
  act(() => { for (let i = 2; i < 14; i++) mocks.frame!(40 * i); });
  expect(vrm.expressionManager.setValue).toHaveBeenCalledWith('aa', 0);
  view.unmount();
  expect(mocks.dispose).toHaveBeenCalledWith(vrm.scene);
  expect(mocks.rendererDispose).toHaveBeenCalled();
});
it('model VRM tải về sau khi rời trang vẫn được giải phóng', async () => {
  let resolve!: (value: unknown) => void;
  mocks.parse.mockReturnValue(new Promise(done => { resolve = done; }));
  const view = render(<VRMStage character={character} motion="always" />);
  await waitFor(() => expect(mocks.parse).toHaveBeenCalled());
  view.unmount();
  const vrm = avatar();
  await act(async () => resolve({ userData: { vrm }, scene: vrm.scene }));
  expect(mocks.dispose).toHaveBeenCalledWith(vrm.scene);
});

it('VRM làm mặt theo cảm xúc Peto chọn bằng biểu cảm có sẵn, về bình thường thì trả biểu cảm về 0', async () => {
  const vrm = avatar(); mocks.parse.mockResolvedValue({ userData: { vrm }, scene: vrm.scene });
  const view = render(<VRMStage character={character} motion="system" emotion={{ emotion: 'surprised', key: 1 }} />);
  await waitFor(() => expect(mocks.frame).toBeTypeOf('function'));
  act(() => { for (let i = 1; i < 30; i++) mocks.frame!(40 * i); });
  const surprised = vrm.expressionManager.setValue.mock.calls.filter(([name]) => name === 'surprised');
  expect(surprised.at(-1)![1]).toBeGreaterThan(0.9);
  // Ngạc nhiên hé miệng sẵn khi Peto im lặng.
  expect(vrm.expressionManager.setValue).toHaveBeenCalledWith('aa', expect.closeTo(0.4, 1));

  view.rerender(<VRMStage character={character} motion="system" emotion={null} />);
  act(() => { for (let i = 30; i < 200; i++) mocks.frame!(40 * i); });
  expect(vrm.expressionManager.setValue.mock.calls.filter(([name]) => name === 'surprised').at(-1)).toEqual(['surprised', 0]);
  view.unmount();
});

it('VRM liếc mắt khi con trỏ đứng yên 3 giây, đầu nghiêng theo, và chớp mắt', async () => {
  const random = vi.spyOn(Math, 'random').mockReturnValue(0.8);
  const vrm = { ...avatar(), lookAt: { target: null as Object3D | null } };
  const head = new Object3D();
  vrm.humanoid.getNormalizedBoneNode = (name?: string) => name === 'head' ? head : new Object3D();
  mocks.parse.mockResolvedValue({ userData: { vrm }, scene: vrm.scene });
  const view = render(<VRMStage character={character} motion="always" />);
  await waitFor(() => expect(mocks.frame).toBeTypeOf('function'));
  const target = vrm.lookAt.target!;
  act(() => window.dispatchEvent(new MouseEvent('pointermove', { clientX: 0, clientY: 0 })));
  act(() => { for (let i = 1; i <= 50; i++) mocks.frame!(40 * i); });
  // Con trỏ vừa đưa: nhìn đúng chỗ con trỏ, chưa liếc.
  const pointed = target.position.clone();
  expect(head.rotation.y).toBeCloseTo(0, 3);
  act(() => { for (let i = 51; i <= 200; i++) mocks.frame!(40 * i); });
  expect(target.position.distanceTo(pointed)).toBeGreaterThan(0.1);
  expect(head.rotation.y).toBeGreaterThan(0.03);
  const blinks = vrm.expressionManager.setValue.mock.calls.filter(([name]) => name === 'blink').map(([, value]) => value as number);
  expect(Math.max(...blinks)).toBe(1);
  view.unmount(); random.mockRestore();
});

it('giảm chuyển động: VRM không chớp, đầu đứng yên, nhưng mắt vẫn liếc như Live2D, kể cả khi con trỏ đang di chuyển', async () => {
  const random = vi.spyOn(Math, 'random').mockReturnValue(0.8);
  const vrm = { ...avatar(), lookAt: { target: null as Object3D | null } };
  const head = new Object3D();
  vrm.humanoid.getNormalizedBoneNode = (name?: string) => name === 'head' ? head : new Object3D();
  mocks.parse.mockResolvedValue({ userData: { vrm }, scene: vrm.scene });
  const view = render(<VRMStage character={character} motion="system" />);
  await waitFor(() => expect(mocks.frame).toBeTypeOf('function'));
  const target = vrm.lookAt.target!;
  const viewer = target.position.clone();
  act(() => window.dispatchEvent(new MouseEvent('pointermove', { clientX: 0, clientY: 0 })));
  act(() => { for (let i = 1; i <= 200; i++) mocks.frame!(40 * i); });
  expect(target.position.distanceTo(viewer)).toBeGreaterThan(0.1);
  expect(head.rotation.y).toBe(0);
  expect(vrm.expressionManager.setValue.mock.calls.filter(([name]) => name === 'blink').every(([, value]) => value === 0)).toBe(true);
  view.unmount(); random.mockRestore();
});
