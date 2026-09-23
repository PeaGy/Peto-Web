// @vitest-environment node
import { expect, it } from 'vitest';
import { zipSync, strToU8 } from 'fflate';
import { importCharacter, inspectLive2D, modelPath, validateLive2D, validateVRM } from '../src/characterImport';

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
it('reviews referenced and unreferenced resources without silently attaching orphan files', async () => {
  const report = await inspectLive2D([zip(settings(), {
    'folder/extra.motion3.json': strToU8('{}'), 'folder/smile.exp3.json': strToU8('{}'),
    '__MACOSX/._avatar.model3.json': strToU8('metadata'),
  })]);
  expect(report.entry).toBe('folder/avatar.model3.json');
  expect(report.files).toBe(6);
  expect(report.motions.found).toHaveLength(2); expect(report.motions.referenced).toHaveLength(1);
  expect(report.expressions.found).toHaveLength(1); expect(report.expressions.referenced).toHaveLength(0);
  expect(report.issues.filter(issue => issue.severity === 'warning')).toHaveLength(2);
  expect(report.prepared?.assets.files.some(file => file.path.endsWith('smile.exp3.json'))).toBe(false);
  expect(report.parameters).toBeNull();
});
it('collects missing references and blocks preparation even when warnings could be bypassed', async () => {
  const report = await inspectLive2D([zip({ Version: 3, FileReferences: {
    Moc: 'absent.moc3', Textures: ['absent.png'], Expressions: [{ File: 'gone.exp3.json' }],
  } } as ReturnType<typeof settings>)]);
  expect(report.prepared).toBeUndefined();
  expect(report.issues.filter(issue => issue.severity === 'error')).toHaveLength(3);
});
it('does not guess an entry for multiple models and labels parameter data from DisplayInfo', async () => {
  const ambiguous = await inspectLive2D([zip(settings(), { 'other.model3.json': strToU8('{}') })]);
  expect(ambiguous.prepared).toBeUndefined(); expect(ambiguous.issues[0].message).toContain('nhiều model');
  const json = { ...settings(), FileReferences: { ...settings().FileReferences, DisplayInfo: 'avatar.cdi3.json' } };
  const report = await inspectLive2D([zip(json, { 'folder/avatar.cdi3.json': strToU8(JSON.stringify({ Parameters: [{ Id: 'A' }, { Id: 'B' }, { Id: 'A' }] })) })]);
  expect(report.parameters).toBe(2); expect(report.prepared).toBeDefined();
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
