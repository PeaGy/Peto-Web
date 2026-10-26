/**
 * Gói thẻ nhân vật để chia sẻ, đúng định dạng của AIRI (services/airi-card-import-export.ts, commit 74ddd90): một ZIP có
 * `manifest.json` (format "airi-character-card", version 1), `card.json` (Character Card v3, như `exportToJSON` của
 * @proj-airi/ccc) và, nếu thẻ dùng model tự nhập, tệp model ở `models/body-model.zip` (Live2D) hay `.vrm`. Nhờ vậy gói
 * Peto xuất ra mở được trong AIRI và ngược lại.
 *
 * Như AIRI, đây không phải bản sao lưu đầy đủ: chỉ những trường trình sửa thẻ cho xem, và model đang chọn. Model có sẵn
 * (Hiyori) không đóng vào gói; thẻ chỉ ghi tên nó. Mô-đun của Peto (bộ não, giọng) đi trong `extensions.peto`; AIRI bỏ qua
 * phần đó. Đọc gói thì chỉ lấy đúng các trường đã biết, kiểm kích thước từng tệp, và model đi qua bước kiểm tra như khi
 * nhập model thường (characterImport).
 */
import type { CompanionCard, CompanionCardFields } from '../../../shared/api/api';
import type { CharacterAssets, CharacterFormat } from '../characters/characterLibrary';
import { modelPath, readZip, type ZipLimits } from '../characters/characterImport';
import { MAX_IMPORT_BYTES, MAX_JSON_BYTES, megabytes } from '../characters/characterLimits';

const FORMAT = 'airi-character-card';
const VERSION = 1;
const CARD_PATH = 'card.json';
const MANIFEST_PATH = 'manifest.json';
/** Số câu chào máy chủ nhận (MAX_GREETINGS của backend/features/companion/cards.py). */
const MAX_GREETINGS = 10;
const MAX_NAME = 60;
/** Gói = model (tối đa như khi nhập model) + vài tệp JSON nhỏ. */
const MAX_PACKAGE_BYTES = MAX_IMPORT_BYTES + 16 * 1024 * 1024;
/** Nhà cung cấp bộ não và nguồn giọng Peto biết (khớp providers/catalog.ts và speech/voiceProviders.ts; test so khớp). */
export const BRAIN_IDS = ['peto', 'xai', 'anthropic', 'openai', 'gemini', 'deepseek', 'mistral', 'azure-openai', 'ollama'];
export const VOICE_IDS = ['official', 'home', 'openai', 'elevenlabs', 'azure', 'gemini', 'minimax', 'qwen', 'stepfun', 'compat'];

export const INVALID_PACKAGE = 'Tệp này không phải gói thẻ nhân vật hợp lệ.';
const PACKAGE_ZIP: ZipLimits = {
  files: 64, fileBytes: MAX_IMPORT_BYTES, totalBytes: MAX_PACKAGE_BYTES,
  tooMany: 'Gói thẻ có quá nhiều tệp.', duplicate: 'Gói thẻ có đường dẫn tệp trùng nhau.',
  tooBigFile: `Model trong gói thẻ vượt quá ${megabytes(MAX_IMPORT_BYTES)}.`,
  tooBigTotal: `Gói thẻ sau giải nén quá lớn (tối đa ${megabytes(MAX_PACKAGE_BYTES)}).`,
};

/** Model đi kèm thẻ khi xuất: tệp model trong thư viện máy này, model có sẵn, hay không có. */
export type PackageModel =
  | { kind: 'file'; name: string; format: CharacterFormat; assets: CharacterAssets }
  | { kind: 'builtin'; id: string }
  | { kind: 'none' };

/** Thẻ đọc được từ gói: các trường để tạo thẻ, model (chưa nhập vào thư viện) và những gì đã bỏ qua. */
export interface ImportedPackage {
  fields: CompanionCardFields & { name: string };
  model?: { file: File; format: CharacterFormat; name: string };
  /** Thẻ Peto xuất với model có sẵn (Hiyori): máy nào cũng có, không cần tệp. */
  builtin?: string;
  warnings: string[];
}

type Json = Record<string, unknown>;

function record(value: unknown): Json {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Json : {};
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

/** Card v3 như `exportToJSON` của AIRI, kể cả các trường mặc định, để SillyTavern và AIRI đều đọc được. */
function characterCard(card: CompanionCard, model: PackageModel) {
  const voice = card.modules.voice;
  return {
    spec: 'chara_card_v3',
    spec_version: '3.0',
    data: {
      name: card.name,
      nickname: card.nickname || undefined,
      description: card.description,
      personality: card.personality,
      scenario: card.scenario,
      first_mes: card.greetings[0] ?? '',
      alternate_greetings: card.greetings.slice(1),
      group_only_greetings: [],
      character_version: card.version,
      creator: '',
      creator_notes: card.notes,
      system_prompt: card.system_prompt,
      post_history_instructions: card.post_history,
      mes_example: '',
      tags: [],
      extensions: {
        depth_prompt: { depth: 4, prompt: '', role: 'system' },
        fav: false,
        talkativeness: 0.5,
        // Mã nhà cung cấp của Peto và AIRI không trùng nhau, nên phần của AIRI để trống: AIRI dùng cài đặt chung.
        airi: {
          avatarModels: [],
          modules: { consciousness: { provider: '', model: '' }, vision: { provider: '', model: '' },
            speech: { provider: '', model: '', voice_id: '' }, artistry: {} },
          agents: {},
        },
        peto: {
          version: 1,
          display_model: model.kind === 'builtin' ? model.id : '',
          modules: {
            ...(card.modules.brain?.provider ? { brain: { ...card.modules.brain } } : {}),
            ...(voice?.source ? { voice: { ...voice } } : {}),
          },
        },
      },
    },
  };
}

type ZipEntry = { path: string; data: Blob; compress: boolean };

/**
 * Ghi ZIP có kích thước ngay trong đầu mỗi tệp (zipSync), không dùng data descriptor: bộ đọc theo luồng của Peto (và
 * nhiều trình giải nén khác) không đọc được tệp không nén kiểu đó. JSON được nén; ảnh và model giữ nguyên vì đã nén sẵn.
 */
async function writeZip(entries: ZipEntry[]): Promise<Blob> {
  const { zipSync } = await import('fflate');
  const input: Record<string, [Uint8Array, { level: 0 | 6 }]> = {};
  for (const entry of entries) input[entry.path] = [new Uint8Array(await entry.data.arrayBuffer()), { level: entry.compress ? 6 : 0 }];
  return new Blob([zipSync(input) as Uint8Array<ArrayBuffer>], { type: 'application/zip' });
}

const json = (value: unknown) => new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });

/** Gói ZIP của thẻ, như `exportAiriCardPackage` của AIRI. */
export async function buildCardPackage(card: CompanionCard, model: PackageModel): Promise<Blob> {
  let resource: { path: string; data: Blob; format: string; name: string } | undefined;
  if (model.kind === 'file') {
    if (model.format === 'vrm') {
      const file = model.assets.files.find(item => item.path === model.assets.entry) ?? model.assets.files[0];
      if (!file) throw new Error('Không đọc được tệp model của thẻ.');
      resource = { path: 'models/body-model.vrm', data: file.blob, format: 'vrm', name: `${model.name}.vrm` };
    } else {
      // Thư viện lưu model Live2D đã chuẩn hóa: model.model3.json ở gốc, mọi tham chiếu tính từ gốc. Gói lại đúng như vậy
      // là được một ZIP Live2D hợp lệ cho cả Peto và AIRI.
      const inner = await writeZip(model.assets.files.map(item => ({ path: item.path, data: item.blob, compress: item.path.endsWith('.json') })));
      resource = { path: 'models/body-model.zip', data: inner, format: 'live2d-zip', name: `${model.name}.zip` };
    }
  }
  const manifest = {
    format: FORMAT,
    version: VERSION,
    createdAt: new Date().toISOString(),
    card: { path: CARD_PATH, spec: 'chara_card_v3' },
    ...(resource ? { resources: { displayModel: { path: resource.path, format: resource.format, name: resource.name } } } : {}),
  };
  return writeZip([
    { path: MANIFEST_PATH, data: json(manifest), compress: true },
    { path: CARD_PATH, data: json(characterCard(card, model)), compress: true },
    ...(resource ? [{ path: resource.path, data: resource.data, compress: false }] : []),
  ]);
}

/** Tên tệp tải về: tên thẻ, bỏ ký tự Windows không cho dùng. */
export function packageFileName(name: string) {
  const safe = name.replace(/[\\/:*?"<>|\x00-\x1f]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/^\.+/, '');
  return `${safe || 'the-nhan-vat'}.zip`;
}

async function readJson(blob: Blob | undefined, missing: string): Promise<Json> {
  if (!blob) throw new Error(missing);
  if (blob.size > MAX_JSON_BYTES) throw new Error(INVALID_PACKAGE);
  try {
    const value = JSON.parse(await blob.text());
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
    return value as Json;
  } catch {
    throw new Error(INVALID_PACKAGE);
  }
}

function brainChoice(value: unknown): Record<string, string> | undefined {
  const source = record(value);
  const provider = text(source.provider).trim();
  if (!BRAIN_IDS.includes(provider)) return undefined;
  const model = text(source.model).trim().slice(0, 100);
  return provider === 'peto' ? { provider } : { provider, ...(model ? { model } : {}) };
}

function voiceChoice(value: unknown, voiceKey = 'voice'): Record<string, string> | undefined {
  const source = record(value);
  const id = text(source.source ?? source.provider).trim();
  if (!VOICE_IDS.includes(id)) return undefined;
  const model = text(source.model).trim().slice(0, 100);
  const voice = text(source[voiceKey]).trim().slice(0, 100);
  return { source: id, ...(model ? { model } : {}), ...(voice ? { voice } : {}) };
}

/** Mô-đun của thẻ: bản Peto ghi trong `extensions.peto`; gói của AIRI thì chỉ nhận nhà cung cấp Peto cũng có. */
function modules(extensions: Json): CompanionCardFields['modules'] {
  const peto = record(extensions.peto);
  if (Object.keys(peto).length) {
    const source = record(peto.modules);
    const brain = brainChoice(source.brain);
    const voice = voiceChoice(source.voice);
    return { ...(brain ? { brain } : {}), ...(voice ? { voice } : {}) };
  }
  const airi = record(record(extensions.airi).modules);
  const brain = brainChoice(airi.consciousness);
  const voice = voiceChoice(airi.speech, 'voice_id');
  return { ...(brain && brain.provider !== 'peto' ? { brain } : {}), ...(voice && VOICE_IDS.indexOf(voice.source) > 1 ? { voice } : {}) };
}

/** Đọc gói ZIP của AIRI hay của Peto, như `importAiriCardPackage`: chỉ các trường đã biết, không chạy hay tải gì thêm. */
export async function readCardPackage(file: File): Promise<ImportedPackage> {
  if (file.size > MAX_PACKAGE_BYTES) throw new Error(PACKAGE_ZIP.tooBigTotal);
  let entries: Map<string, Blob>;
  try {
    entries = new Map((await readZip(file, PACKAGE_ZIP)).map(item => [item.path, item.blob]));
  } catch (error) {
    const message = error instanceof Error ? error.message : '';
    throw new Error([PACKAGE_ZIP.tooMany, PACKAGE_ZIP.duplicate, PACKAGE_ZIP.tooBigFile, PACKAGE_ZIP.tooBigTotal].includes(message)
      ? message : INVALID_PACKAGE);
  }
  const manifest = await readJson(entries.get(MANIFEST_PATH), 'Gói thẻ thiếu manifest.json.');
  const declared = record(manifest.card);
  if (manifest.format !== FORMAT || manifest.version !== VERSION || declared.path !== CARD_PATH || declared.spec !== 'chara_card_v3') {
    throw new Error('Gói này không phải thẻ nhân vật AIRI (phiên bản 1).');
  }
  const card = await readJson(entries.get(CARD_PATH), 'Gói thẻ thiếu card.json.');
  const data = record(card.data);
  if (card.spec !== 'chara_card_v3' || card.spec_version !== '3.0' || typeof data.name !== 'string') throw new Error(INVALID_PACKAGE);
  const name = data.name.replace(/\s+/g, ' ').trim();
  if (!name) throw new Error('Thẻ trong gói không có tên.');

  const warnings: string[] = [];
  const allGreetings = [data.first_mes, ...(Array.isArray(data.alternate_greetings) ? data.alternate_greetings : [])]
    .filter((item): item is string => typeof item === 'string' && item.trim() !== '');
  if (allGreetings.length > MAX_GREETINGS) warnings.push(`Thẻ có ${allGreetings.length} câu chào; Peto giữ ${MAX_GREETINGS} câu đầu.`);
  if (text(data.mes_example).trim()) warnings.push('Peto chưa dùng hội thoại mẫu (mes_example) của thẻ nên đã bỏ phần này.');
  if (name.length > MAX_NAME) warnings.push(`Tên thẻ dài quá ${MAX_NAME} ký tự nên đã được cắt bớt.`);
  const extensions = record(data.extensions);
  const fields: ImportedPackage['fields'] = {
    name: name.slice(0, MAX_NAME).trim(),
    nickname: text(data.nickname).trim(),
    version: text(data.character_version).trim() || '1.0.0',
    description: text(data.description),
    personality: text(data.personality),
    scenario: text(data.scenario),
    notes: text(data.creator_notes),
    system_prompt: text(data.system_prompt),
    post_history: text(data.post_history_instructions),
    greetings: allGreetings.slice(0, MAX_GREETINGS),
    modules: modules(extensions),
    display_model: '',
  };

  const result: ImportedPackage = { fields, warnings };
  const resource = record(record(manifest.resources).displayModel);
  if (Object.keys(resource).length) {
    let path: string;
    try { path = modelPath(text(resource.path)); } catch { throw new Error(INVALID_PACKAGE); }
    const blob = entries.get(path);
    if (!blob) throw new Error('Gói thẻ thiếu tệp model đã khai báo.');
    const format = resource.format === 'live2d-zip' ? 'live2d' : resource.format === 'vrm' ? 'vrm' : null;
    if (!format) {
      warnings.push(`Peto chưa dùng được model dạng "${text(resource.format, '?')}" nên thẻ được nhập không kèm model.`);
    } else {
      const extension = format === 'vrm' ? '.vrm' : '.zip';
      const base = text(resource.name).replace(/[\\/:*?"<>|\x00-\x1f]+/g, ' ').trim().replace(/\.(zip|vrm)$/i, '') || name;
      result.model = { file: new File([blob], `${base.slice(0, 80)}${extension}`), format, name: base.slice(0, 80) };
    }
  } else {
    const builtin = text(record(extensions.peto).display_model);
    if (builtin === 'hiyori') { result.builtin = builtin; fields.display_model = builtin; }
  }
  return result;
}

/** Tên chưa có trong danh sách thẻ: "Mika", rồi "Mika (2)", "Mika (3)"… (máy chủ không cho trùng tên). */
export function uniqueName(name: string, taken: string[]) {
  const used = new Set(taken.map(item => item.toLocaleLowerCase('vi')));
  if (!used.has(name.toLocaleLowerCase('vi'))) return name;
  for (let index = 2; ; index += 1) {
    const suffix = ` (${index})`;
    const candidate = `${name.slice(0, MAX_NAME - suffix.length).trimEnd()}${suffix}`;
    if (!used.has(candidate.toLocaleLowerCase('vi'))) return candidate;
  }
}
