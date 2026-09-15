// @vitest-environment node
import { beforeEach, expect, it, vi } from 'vitest';
import { IDBFactory } from 'fake-indexeddb';
import { DEFAULT_CHARACTER, getCharacterAssets, listCharacters, removeCharacter, saveCharacter, updateCharacter } from '../src/characterLibrary';
beforeEach(() => vi.stubGlobal('indexedDB', new IDBFactory()));
const data = () => ({ model: { id: 'custom', name: 'My avatar', format: 'vrm' as const, bytes: 4, createdAt: 1 }, assets: { id: 'custom', entry: 'model.vrm', files: [{ path: 'model.vrm', blob: new Blob(['test']) }] } });

it('lưu xong thì có cả metadata lẫn tài nguyên, mở lại vẫn đọc được', async () => {
  await saveCharacter(data());
  expect((await listCharacters()).map(model => model.id)).toEqual([DEFAULT_CHARACTER.id, 'custom']);
  expect(await (await getCharacterAssets('custom'))!.files[0].blob.text()).toBe('test');
});
it('đổi tên và thumbnail không ghi đè nhau, xóa dọn cả tài nguyên', async () => {
  await saveCharacter(data());
  await updateCharacter('custom', { name: 'New name' });
  await updateCharacter('custom', { preview: 'data:image/png;base64,AA' });
  expect((await listCharacters())[1].name).toBe('New name');
  await removeCharacter('custom');
  await updateCharacter('custom', { preview: 'late preview' });
  expect(await getCharacterAssets('custom')).toBeUndefined();
  expect(await listCharacters()).toHaveLength(1);
});
it('luôn giữ model mặc định để phục hồi', async () => {
  await removeCharacter(DEFAULT_CHARACTER.id);
  expect((await listCharacters())[0]).toEqual(DEFAULT_CHARACTER);
});
