import 'fake-indexeddb/auto';
import { expect, it } from 'vitest';
import { importScene, readScenePreference, saveScenePreference, sceneStorage } from '../src/sceneLibrary';

it('keeps scene settings per character and clamps corrupt settings', () => {
  saveScenePreference('scene-test-a', { id: 'tea', dim: 40, blur: 8 });
  expect(readScenePreference('scene-test-a')).toEqual({ id: 'tea', dim: 40, blur: 8 });
  expect(readScenePreference('scene-test-b').id).toBe('dark');
  localStorage.setItem('peto-scene:scene-test-a', '{"dim":200,"blur":-5}');
  expect(readScenePreference('scene-test-a')).toEqual({ id: 'dark', dim: 80, blur: 0 });
});
it('persists uploaded images and removes only the chosen image', async () => {
  const first = { id: 'test-a', name: 'A', blob: new Blob(['image']) };
  const second = { id: 'test-b', name: 'B', blob: new Blob(['image']) };
  await sceneStorage('put', first); await sceneStorage('put', second);
  expect((await sceneStorage('list')).map(item => item.id)).toEqual(['test-a', 'test-b']);
  await sceneStorage('delete', first);
  expect((await sceneStorage('list')).map(item => item.id)).toEqual(['test-b']);
  await sceneStorage('delete', second);
});
it('rejects unsupported and oversized uploads before decoding', async () => {
  await expect(importScene(new File(['<svg/>'], 'test.svg', { type: 'image/svg+xml' }))).rejects.toThrow('PNG');
  await expect(importScene(new File([new Uint8Array(13 * 1024 * 1024)], 'test.png', { type: 'image/png' }))).rejects.toThrow('12 MB');
});
