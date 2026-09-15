// @vitest-environment node
import { expect, it } from 'vitest';
import { zipSync, strToU8 } from 'fflate';
import { importCharacter, modelPath, validateLive2D, validateVRM } from '../src/characterImport';

const settings = (file = 'avatar.moc3') => ({ Version: 3, FileReferences: { Moc: file, Textures: ['textures/顔.png'], Motions: { Idle: [{ File: 'idle.motion3.json', Sound: 'https://external.test/sound.wav' }] } } });
const zip = (json = settings(), extra = {}) => new File([zipSync({
  'folder/avatar.model3.json': strToU8(JSON.stringify(json)), 'folder/avatar.moc3': strToU8('MOC3sample'),
  'folder/textures/顔.png': new Uint8Array([137, 80, 78, 71]), 'folder/idle.motion3.json': strToU8('{}'), ...extra,
})], 'Avatar.zip');

it('nhập ZIP có thư mục con và tên Unicode, chuẩn hóa tham chiếu và bỏ tiếng motion', async () => {
  const imported = await importCharacter([zip()], 'live2d');
  expect(imported.model.format).toBe('live2d');
  const json = JSON.parse(await imported.assets.files[0].blob.text());
  expect(json.FileReferences.Moc).toBe('folder/avatar.moc3');
  expect(json.FileReferences.Textures).toEqual(['folder/textures/顔.png']);
  expect(json.FileReferences.Motions.Idle[0]).not.toHaveProperty('Sound');
});
it('chặn tài nguyên ngoài gói, đường dẫn thoát gói và thiếu tệp bắt buộc', async () => {
  for (const value of ['https://external.test/a.moc3', '../../escape.moc3', 'missing.moc3']) {
    await expect(importCharacter([zip(settings(value))], 'live2d')).rejects.toThrow();
  }
  expect(() => modelPath('C:\\secret')).toThrow();
  expect(() => modelPath('%2e%2e/file')).toThrow();
});
it('không tự đoán model khi một gói có nhiều entry', async () => {
  await expect(importCharacter([zip(settings(), { 'second.model3.json': strToU8('{}') })], 'live2d')).rejects.toThrow('nhiều model');
});
it('từ chối moc giả và ZIP cụt', async () => {
  await expect(validateLive2D([{ path: 'model.model3.json', blob: new Blob([JSON.stringify(settings())]) }, { path: 'avatar.moc3', blob: new Blob(['fake']) }])).rejects.toThrow('.moc3');
  await expect(importCharacter([new File([new Uint8Array([80, 75, 3, 4])], 'bad.zip')], 'live2d')).rejects.toThrow();
});
function glb(json: object) {
  const text = JSON.stringify(json), data = new TextEncoder().encode(text + ' '.repeat((4 - text.length % 4) % 4));
  const buffer = new ArrayBuffer(20 + data.length), view = new DataView(buffer);
  view.setUint32(0, 0x46546c67, true); view.setUint32(4, 2, true); view.setUint32(8, buffer.byteLength, true);
  view.setUint32(12, data.length, true); view.setUint32(16, 0x4e4f534a, true); new Uint8Array(buffer, 20).set(data);
  return buffer;
}
it('nhận VRM 0/1 và lấy tên tác giả', () => {
  expect(validateVRM(glb({ extensions: { VRMC_vrm: { meta: { name: 'Avatar', authors: ['Artist'] } } } }))).toEqual({ name: 'Avatar', author: 'Artist' });
  expect(validateVRM(glb({ extensions: { VRM: { meta: { title: 'Legacy', author: 'Creator' } } } })).name).toBe('Legacy');
});
it('chặn GLB thường, GLB sai kích thước và mọi texture/buffer ngoài VRM', () => {
  expect(() => validateVRM(glb({}))).toThrow('không có nhân vật VRM');
  expect(() => validateVRM(new ArrayBuffer(20))).toThrow();
  for (const uri of ['https://external.test/a.png', '../a.png', 'data:image/png;base64,AA==']) {
    expect(() => validateVRM(glb({ extensions: { VRMC_vrm: {} }, images: [{ uri }] }))).toThrow('bên trong');
  }
});
