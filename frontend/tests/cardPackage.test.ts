// @vitest-environment node
import { expect, it } from 'vitest';
import { strToU8, unzipSync, zipSync } from 'fflate';
import type { CompanionCard } from '../src/shared/api/api';
import {
  BRAIN_IDS, INVALID_PACKAGE, VOICE_IDS, buildCardPackage, packageFileName, readCardPackage, uniqueName,
} from '../src/features/companion/cards/cardPackage';
import { importCharacter } from '../src/features/companion/characters/characterImport';
import { CHAT_PROVIDERS } from '../src/features/companion/providers/catalog';
import { KEY_PROVIDERS } from '../src/features/companion/speech/voiceProviders';

const card = (extra: Partial<CompanionCard> = {}): CompanionCard => ({
  id: '0123456789abcdef0123456789abcdef', name: 'Mika', nickname: 'Mi', version: '1.2.0', description: 'Cáo tinh trông tiệm trà.',
  notes: 'Viết cho Minh.', personality: 'Sleepy, teasing.', scenario: 'Rainy evening.', system_prompt: 'You are {{char}}.',
  post_history: 'Keep it short.', display_model: 'model-1', greetings: ['Ngồi đi.', 'Trà vừa pha xong.'],
  modules: { brain: { provider: 'deepseek', model: 'deepseek-chat' }, voice: { source: 'official', voice: 'stepfun:lively-girl' } },
  is_default: false, modified: false, created_at: 1, updated_at: 1, ...extra,
});

function glb(json: object) {
  const text = JSON.stringify(json), data = new TextEncoder().encode(text + ' '.repeat((4 - text.length % 4) % 4));
  const buffer = new ArrayBuffer(20 + data.length), view = new DataView(buffer);
  view.setUint32(0, 0x46546c67, true); view.setUint32(4, 2, true); view.setUint32(8, buffer.byteLength, true);
  view.setUint32(12, data.length, true); view.setUint32(16, 0x4e4f534a, true); new Uint8Array(buffer, 20).set(data);
  return buffer;
}
const live2dZip = () => new File([zipSync({
  'folder/avatar.model3.json': strToU8(JSON.stringify({ Version: 3, FileReferences: { Moc: 'avatar.moc3', Textures: ['textures/顔.png'],
    Motions: { Idle: [{ File: 'idle.motion3.json' }] } } })),
  'folder/avatar.moc3': strToU8('MOC3sample'), 'folder/textures/顔.png': new Uint8Array([137, 80, 78, 71]),
  'folder/idle.motion3.json': strToU8('{}'),
})], 'Avatar.zip');
const files = async (blob: Blob) => unzipSync(new Uint8Array(await blob.arrayBuffer()));
const json = (bytes: Uint8Array) => JSON.parse(new TextDecoder().decode(bytes));
const pack = (entries: Record<string, unknown>) => new File([zipSync(Object.fromEntries(Object.entries(entries).map(([path, value]) =>
  [path, value instanceof Uint8Array ? value : strToU8(JSON.stringify(value))])))], 'card.zip');
const manifest = (extra: object = {}) => ({ format: 'airi-character-card', version: 1, card: { path: 'card.json', spec: 'chara_card_v3' }, ...extra });

it('xuất gói đúng định dạng AIRI: manifest, Card v3 như exportToJSON, mô-đun Peto trong extensions.peto', async () => {
  const entries = await files(await buildCardPackage(card(), { kind: 'none' }));
  expect(Object.keys(entries).sort()).toEqual(['card.json', 'manifest.json']);
  expect(json(entries['manifest.json'])).toMatchObject(manifest());
  const exported = json(entries['card.json']);
  expect(exported).toMatchObject({ spec: 'chara_card_v3', spec_version: '3.0' });
  expect(exported.data).toMatchObject({
    name: 'Mika', nickname: 'Mi', character_version: '1.2.0', description: 'Cáo tinh trông tiệm trà.', personality: 'Sleepy, teasing.',
    scenario: 'Rainy evening.', first_mes: 'Ngồi đi.', alternate_greetings: ['Trà vừa pha xong.'], creator_notes: 'Viết cho Minh.',
    system_prompt: 'You are {{char}}.', post_history_instructions: 'Keep it short.', mes_example: '', tags: [],
  });
  expect(exported.data.extensions.depth_prompt).toEqual({ depth: 4, prompt: '', role: 'system' });
  // Mã nhà cung cấp của Peto không trùng AIRI: phần của AIRI để trống, mô-đun thật đi trong extensions.peto.
  expect(exported.data.extensions.airi.modules.consciousness).toEqual({ provider: '', model: '' });
  expect(exported.data.extensions.peto.modules).toEqual(card().modules);
});

it('xuất rồi nhập lại thẻ có model VRM: giữ mọi trường, mô-đun và tệp model', async () => {
  const vrm = glb({ extensions: { VRMC_vrm: { meta: { name: 'Mika VRM' } } } });
  const blob = await buildCardPackage(card(), { kind: 'file', name: 'Mika VRM', format: 'vrm',
    assets: { id: 'model-1', entry: 'model.vrm', files: [{ path: 'model.vrm', blob: new Blob([vrm]) }] } });
  expect(json((await files(blob))['manifest.json']).resources.displayModel).toEqual({ path: 'models/body-model.vrm', format: 'vrm', name: 'Mika VRM.vrm' });
  const imported = await readCardPackage(new File([blob], 'Mika.zip'));
  expect(imported.fields).toMatchObject({ name: 'Mika', nickname: 'Mi', version: '1.2.0', greetings: ['Ngồi đi.', 'Trà vừa pha xong.'],
    notes: 'Viết cho Minh.', post_history: 'Keep it short.', modules: card().modules, display_model: '' });
  expect(imported.warnings).toEqual([]);
  expect(imported.model).toMatchObject({ format: 'vrm', name: 'Mika VRM' });
  expect(new Uint8Array(await imported.model!.file.arrayBuffer())).toEqual(new Uint8Array(vrm));
  expect((await importCharacter([imported.model!.file], 'vrm')).model.name).toBe('Mika VRM');
});

it('model Live2D đã nhập vào thư viện xuất thành ZIP Live2D mà Peto (và AIRI) nhập lại được', async () => {
  const stored = await importCharacter([live2dZip()], 'live2d');
  const blob = await buildCardPackage(card(), { kind: 'file', name: 'Avatar', format: 'live2d', assets: stored.assets });
  const imported = await readCardPackage(new File([blob], 'Mika.zip'));
  expect(imported.model).toMatchObject({ format: 'live2d', name: 'Avatar' });
  const again = await importCharacter([imported.model!.file], 'live2d');
  expect(again.assets.files.map(file => file.path).sort()).toEqual(stored.assets.files.map(file => file.path).sort());
  const settings = JSON.parse(await again.assets.files[0].blob.text());
  expect(settings.FileReferences.Textures).toEqual(['folder/textures/顔.png']);
});

it('model có sẵn (Hiyori) không đóng vào gói, thẻ nhập lại vẫn dùng Hiyori', async () => {
  const blob = await buildCardPackage(card({ display_model: 'hiyori', modules: {} }), { kind: 'builtin', id: 'hiyori' });
  expect(Object.keys(await files(blob))).not.toContain('models/body-model.zip');
  const imported = await readCardPackage(new File([blob], 'Mika.zip'));
  expect(imported).toMatchObject({ builtin: 'hiyori', fields: { display_model: 'hiyori', modules: {} } });
  expect(imported.model).toBeUndefined();
});

it('nhập gói do AIRI xuất: câu chào, mô-đun nhà cung cấp Peto cũng có, báo phần bỏ qua', async () => {
  const imported = await readCardPackage(pack({
    'manifest.json': manifest({ createdAt: '2026-10-20T00:00:00.000Z',
      resources: { displayModel: { path: 'models/body-model.tachie.zip', format: 'tachie-zip', name: 'Lain.tachie.zip' } } }),
    'card.json': { spec: 'chara_card_v3', spec_version: '3.0', data: {
      name: '  Lain   Iwakura ', character_version: '', description: 'Wired.', first_mes: 'Present day.',
      alternate_greetings: Array.from({ length: 11 }, (_, index) => `Greeting ${index}`), mes_example: '<START>\n{{user}}: hi',
      extensions: { airi: { modules: { consciousness: { provider: 'openai', model: 'gpt-x' },
        speech: { provider: 'elevenlabs', model: 'eleven_v3', voice_id: 'voice-1' } } }, depth_prompt: { depth: 4 } },
    } },
    'models/body-model.tachie.zip': new Uint8Array([1, 2, 3]),
  }));
  expect(imported.fields).toMatchObject({ name: 'Lain Iwakura', version: '1.0.0', description: 'Wired.', nickname: '',
    modules: { brain: { provider: 'openai', model: 'gpt-x' }, voice: { source: 'elevenlabs', model: 'eleven_v3', voice: 'voice-1' } } });
  expect(imported.fields.greetings).toHaveLength(10);
  expect(imported.fields.greetings?.[0]).toBe('Present day.');
  expect(imported.model).toBeUndefined();
  expect(imported.warnings.join(' ')).toMatch(/12 câu chào.*mes_example.*tachie-zip/s);
});

it('gói AIRI chọn nhà cung cấp Peto không có thì thẻ theo cài đặt chung', async () => {
  const imported = await readCardPackage(pack({ 'manifest.json': manifest(), 'card.json': { spec: 'chara_card_v3', spec_version: '3.0',
    data: { name: 'Aki', extensions: { airi: { modules: { consciousness: { provider: 'openrouter-ai', model: 'x' },
      speech: { provider: 'official', voice_id: 'y' } } } } } } }));
  expect(imported.fields.modules).toEqual({});
});

it('từ chối tệp không phải gói thẻ, gói thiếu tệp, sai định dạng và đường dẫn model thoát khỏi gói', async () => {
  await expect(readCardPackage(new File([new Uint8Array([1, 2, 3, 4])], 'x.zip'))).rejects.toThrow(INVALID_PACKAGE);
  await expect(readCardPackage(pack({ 'card.json': {} }))).rejects.toThrow('thiếu manifest.json');
  await expect(readCardPackage(pack({ 'manifest.json': { ...manifest(), format: 'something-else' } }))).rejects.toThrow('không phải thẻ nhân vật AIRI');
  await expect(readCardPackage(pack({ 'manifest.json': manifest() }))).rejects.toThrow('thiếu card.json');
  await expect(readCardPackage(pack({ 'manifest.json': manifest(), 'card.json': { spec: 'chara_card_v2', data: { name: 'A' } } }))).rejects.toThrow(INVALID_PACKAGE);
  await expect(readCardPackage(pack({ 'manifest.json': manifest(), 'card.json': { spec: 'chara_card_v3', spec_version: '3.0', data: { name: '  ' } } })))
    .rejects.toThrow('không có tên');
  const valid = { spec: 'chara_card_v3', spec_version: '3.0', data: { name: 'A' } };
  await expect(readCardPackage(pack({ 'manifest.json': manifest({ resources: { displayModel: { path: '../evil.vrm', format: 'vrm', name: 'e.vrm' } } }),
    'card.json': valid }))).rejects.toThrow(INVALID_PACKAGE);
  await expect(readCardPackage(pack({ 'manifest.json': manifest({ resources: { displayModel: { path: 'models/body-model.vrm', format: 'vrm', name: 'a.vrm' } } }),
    'card.json': valid }))).rejects.toThrow('thiếu tệp model');
});

it('tên thẻ trùng thì thêm số, tên tệp tải về bỏ ký tự Windows không cho', () => {
  expect(uniqueName('Mika', ['Peto'])).toBe('Mika');
  expect(uniqueName('Mika', ['mika', 'Mika (2)'])).toBe('Mika (3)');
  expect(uniqueName('x'.repeat(60), ['x'.repeat(60)])).toBe(`${'x'.repeat(56)} (2)`);
  expect(packageFileName('Mika: "cáo" / trà?')).toBe('Mika cáo trà.zip');
  expect(packageFileName('...')).toBe('the-nhan-vat.zip');
});

it('danh sách nhà cung cấp gói thẻ nhận khớp danh mục bộ não và giọng của Peto', () => {
  expect(BRAIN_IDS.filter(id => id !== 'peto').sort()).toEqual(CHAT_PROVIDERS.map(item => item.id).sort());
  expect(VOICE_IDS.filter(id => id !== 'official' && id !== 'home').sort()).toEqual(KEY_PROVIDERS.map(item => item.id).sort());
});
