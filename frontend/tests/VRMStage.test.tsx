import { act, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { BoxGeometry, Group, Mesh, MeshBasicMaterial, Object3D, Vector3 } from 'three';
import VRMStage from '../src/VRMStage';

const mocks = vi.hoisted(() => ({ parse: vi.fn(), dispose: vi.fn(), rendererDispose: vi.fn(), frame: null as null | ((time: number) => void), mouth: 0 }));
vi.mock('three', async original => ({ ...await original<typeof import('three')>(), WebGLRenderer: class {
  domElement = document.createElement('canvas');
  setPixelRatio() {} setClearColor() {} setSize() {} render() {} forceContextLoss() {}
  dispose = mocks.rendererDispose;
} }));
vi.mock('three/addons/loaders/GLTFLoader.js', () => ({ GLTFLoader: class { register() {} parseAsync = mocks.parse; } }));
vi.mock('three/addons/controls/OrbitControls.js', () => ({ OrbitControls: class { target = new Vector3(); update() {} dispose() {} } }));
vi.mock('@pixiv/three-vrm', () => ({ VRMLoaderPlugin: class {}, VRMUtils: { rotateVRM0() {}, deepDispose: mocks.dispose } }));
vi.mock('../src/characterLibrary', () => ({ getCharacterAssets: async () => ({ entry: 'test.vrm', files: [{ path: 'test.vrm', blob: { arrayBuffer: async () => new ArrayBuffer(0) } }] }) }));
vi.mock('../src/characterImport', () => ({ validateVRM() {} }));
vi.mock('../src/voiceActivity', () => ({ voiceMouth: () => mocks.mouth }));
const character = { id: 'vrm-test', name: 'VRM', format: 'vrm' as const, bytes: 1, createdAt: 0 };
function avatar() {
  const scene = new Group(); scene.add(new Mesh(new BoxGeometry(1, 2, 1), new MeshBasicMaterial()));
  return { scene, humanoid: { setNormalizedPose: vi.fn(), getNormalizedBoneNode: () => new Object3D() }, expressionManager: { setValue: vi.fn() }, update: vi.fn() };
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
  expect(vrm.expressionManager.setValue).toHaveBeenCalledWith('aa', 0.7);
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
