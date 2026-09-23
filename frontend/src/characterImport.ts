import type { CharacterFile, CharacterFormat, CharacterImport } from './characterLibrary';

export const MAX_IMPORT_BYTES = 80 * 1024 * 1024;
export const MAX_EXPANDED_BYTES = 160 * 1024 * 1024;
const MAX_FILES = 512;
const MAX_FILE_BYTES = 64 * 1024 * 1024;
const MAX_JSON_BYTES = 4 * 1024 * 1024;
type Json = Record<string, any>;

/** Chỉ tham chiếu tài nguyên bên trong gói, tuyệt đối không tải URL do model cung cấp. */
export function modelPath(path: string, base = ''): string {
  if (!path || /[\x00-\x1f:?#%]/.test(path) || /^[\\/]/.test(path)) throw new Error('Model có đường dẫn tài nguyên không hợp lệ.');
  const parts = base.split('/').filter(Boolean);
  for (const part of path.replaceAll('\\', '/').split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') {
      if (!parts.length) throw new Error('Model trỏ tới tệp nằm ngoài gói.');
      parts.pop();
    } else parts.push(part);
  }
  return parts.join('/');
}

async function readZip(file: File): Promise<CharacterFile[]> {
  const { Unzip, UnzipInflate } = await import('fflate');
  const bytes = new Uint8Array(await file.arrayBuffer());
  const files: CharacterFile[] = [];
  let total = 0, count = 0, pending = 0;
  const seen = new Set<string>();
  const archive = new Unzip(entry => {
    if (++count > MAX_FILES) throw new Error('Gói model có quá nhiều tệp (tối đa 512).');
    const path = modelPath(entry.name);
    if (entry.name.endsWith('/') || path.startsWith('__MACOSX/') || path.split('/').some(part => part.startsWith('.'))) return;
    if (seen.has(path.toLowerCase())) throw new Error('Gói model có đường dẫn tệp trùng nhau.');
    seen.add(path.toLowerCase());
    if ((entry.originalSize ?? 0) > MAX_FILE_BYTES) throw new Error('Một tệp trong model vượt quá 64 MB.');
    let size = 0;
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    pending++;
    entry.ondata = (error, data, final) => {
      if (error) throw new Error('Không giải nén được ZIP. Hãy dùng gói ZIP không có mật khẩu.');
      size += data.length; total += data.length;
      if (size > MAX_FILE_BYTES || total > MAX_EXPANDED_BYTES) throw new Error('Model sau giải nén quá lớn (tối đa 160 MB, 64 MB mỗi tệp).');
      chunks.push(new Uint8Array(data));
      if (final) { files.push({ path, blob: new Blob(chunks) }); pending--; }
    };
    entry.start();
  });
  archive.register(UnzipInflate);
  // Đẩy từng khối nhỏ để kiểm tra kích thước thực sau giải nén, không tin số byte trong ZIP header.
  for (let offset = 0; offset < bytes.length; offset += 16384) {
    archive.push(bytes.subarray(offset, offset + 16384), offset + 16384 >= bytes.length);
    if (offset % (256 * 1024) === 0) await new Promise(resolve => setTimeout(resolve, 0));
  }
  if (pending || !files.length) throw new Error('ZIP bị thiếu dữ liệu hoặc không có tệp model.');
  return files;
}

async function jsonFile(file: CharacterFile): Promise<Json> {
  if (file.blob.size > MAX_JSON_BYTES) throw new Error('Tệp cấu hình model quá lớn.');
  try {
    const value = JSON.parse(await file.blob.text());
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
    return value;
  } catch { throw new Error(`Không đọc được cấu hình ${file.path}.`); }
}

export async function validateLive2D(files: CharacterFile[]): Promise<{ entry: string; files: CharacterFile[] }> {
  const entries = files.filter(file => file.path.toLowerCase().endsWith('.model3.json'));
  if (entries.length !== 1) throw new Error(entries.length ? 'Gói này có nhiều model. Hãy nhập riêng thư mục của một model.' : 'Thiếu tệp .model3.json. Hãy chọn toàn bộ thư mục model Cubism 3/4/5 hoặc ZIP của nó.');
  const entry = entries[0];
  const settings = await jsonFile(entry);
  if (settings.Version !== 3 || !settings.FileReferences || typeof settings.FileReferences !== 'object') throw new Error('Cấu hình Live2D không hợp lệ. Peto hỗ trợ model Cubism 3 trở lên.');
  const base = entry.path.split('/').slice(0, -1).join('/');
  const map = new Map(files.map(file => [file.path, file]));
  const used = new Map<string, CharacterFile>();
  const requireFile = async (value: unknown, extension: RegExp) => {
    if (typeof value !== 'string') throw new Error('Model thiếu đường dẫn tài nguyên bắt buộc.');
    const path = modelPath(value, base);
    const file = map.get(path);
    if (!file) throw new Error(`Thiếu tệp trong model: ${path}`);
    if (!extension.test(path)) throw new Error(`Định dạng tài nguyên không được hỗ trợ: ${path}`);
    used.set(path, file);
    if (path.endsWith('.json')) await jsonFile(file);
    return path; // Chuẩn hóa mọi tham chiếu thành đường dẫn tính từ gốc gói.
  };
  const source = settings.FileReferences;
  const refs: Json = { Moc: await requireFile(source.Moc, /\.moc3$/i), Textures: [] };
  const magic = new Uint8Array(await map.get(refs.Moc)!.blob.slice(0, 4).arrayBuffer());
  if (String.fromCharCode(...magic) !== 'MOC3') throw new Error('Tệp .moc3 không phải model Live2D hợp lệ.');
  if (!Array.isArray(source.Textures) || !source.Textures.length || source.Textures.length > 16) throw new Error('Model cần từ 1 đến 16 ảnh texture.');
  for (const texture of source.Textures) refs.Textures.push(await requireFile(texture, /\.(png|jpe?g|webp)$/i));
  for (const field of ['Physics', 'Pose', 'UserData', 'DisplayInfo']) {
    if (source[field]) refs[field] = await requireFile(source[field], /\.json$/i);
  }
  if (source.Expressions) {
    if (!Array.isArray(source.Expressions) || source.Expressions.length > 100) throw new Error('Danh sách biểu cảm không hợp lệ.');
    refs.Expressions = await Promise.all(source.Expressions.map(async (item: Json) => ({ Name: String(item.Name ?? '').slice(0, 100), File: await requireFile(item.File, /\.json$/i) })));
  }
  if (source.Motions) {
    refs.Motions = Object.create(null);
    let count = 0;
    for (const [group, motions] of Object.entries(source.Motions)) {
      if (['__proto__', 'constructor', 'prototype'].includes(group)) throw new Error('Tên nhóm chuyển động không hợp lệ.');
      if (!Array.isArray(motions) || (count += motions.length) > 200) throw new Error('Danh sách chuyển động quá lớn hoặc không hợp lệ.');
      refs.Motions[group] = await Promise.all(motions.map(async (item: Json) => ({
        File: await requireFile(item.File, /\.json$/i),
        ...(Number.isFinite(item.FadeInTime) ? { FadeInTime: item.FadeInTime } : {}),
        ...(Number.isFinite(item.FadeOutTime) ? { FadeOutTime: item.FadeOutTime } : {}),
      })));
    }
  }
  const groups = Array.isArray(settings.Groups) ? settings.Groups.filter((group: Json) => group && group.Target === 'Parameter' && ['EyeBlink', 'LipSync'].includes(group.Name) && Array.isArray(group.Ids)).map((group: Json) => ({ Target: 'Parameter', Name: group.Name, Ids: group.Ids.filter((id: unknown) => typeof id === 'string' && id.length <= 128).slice(0, 16) })) : [];
  const normalized = { Version: 3, FileReferences: refs, Groups: groups, HitAreas: settings.HitAreas, Layout: settings.Layout };
  return { entry: 'model.model3.json', files: [{ path: 'model.model3.json', blob: new Blob([JSON.stringify(normalized)], { type: 'application/json' }) }, ...used.values()] };
}

/** VRM phải là GLB tự chứa; chặn URL ngoài trước khi GLTFLoader chạm vào tài nguyên. */
export function validateVRM(buffer: ArrayBuffer): { name?: string; author?: string } {
  const view = new DataView(buffer);
  if (buffer.byteLength < 20 || view.getUint32(0, true) !== 0x46546c67 || view.getUint32(4, true) !== 2 || view.getUint32(8, true) !== buffer.byteLength) throw new Error('Tệp này không phải VRM/GLB hợp lệ.');
  const length = view.getUint32(12, true);
  if (view.getUint32(16, true) !== 0x4e4f534a || length > MAX_JSON_BYTES || length + 20 > buffer.byteLength) throw new Error('Cấu hình VRM bị lỗi hoặc quá lớn.');
  let json: Json;
  try { json = JSON.parse(new TextDecoder().decode(buffer.slice(20, 20 + length))); } catch { throw new Error('Không đọc được cấu hình VRM.'); }
  const vrm = json.extensions?.VRMC_vrm ?? json.extensions?.VRM;
  if (!vrm) throw new Error('Tệp GLB này không có nhân vật VRM. Hãy xuất bằng định dạng .vrm.');
  for (const entry of [...(json.buffers ?? []), ...(json.images ?? [])]) {
    if (entry.uri !== undefined) throw new Error('VRM cần chứa toàn bộ texture và dữ liệu bên trong tệp, không tham chiếu URL hoặc tệp rời.');
  }
  if ((json.nodes?.length ?? 0) > 10000 || (json.meshes?.length ?? 0) > 1000) throw new Error('Model VRM quá phức tạp cho bản web này.');
  const meta = vrm.meta ?? {};
  return { name: String(meta.name ?? meta.title ?? '').slice(0, 80) || undefined, author: String(meta.authors?.join(', ') ?? meta.author ?? '').slice(0, 200) || undefined };
}

function checkInput(input: File[]) {
  if (!input.length) throw new Error('Bạn chưa chọn tệp model.');
  if (input.length > MAX_FILES || input.reduce((size, file) => size + file.size, 0) > MAX_IMPORT_BYTES) throw new Error('Model nhập vào tối đa 80 MB và 512 tệp.');
}
async function liveFiles(input: File[]) {
  checkInput(input);
  const files = input.length === 1 && input[0].name.toLowerCase().endsWith('.zip')
    ? await readZip(input[0])
    : input.map(file => ({ path: modelPath(file.webkitRelativePath || file.name), blob: file }));
  if (files.some(file => file.blob.size > MAX_FILE_BYTES)) throw new Error('Một tệp trong model vượt quá 64 MB.');
  if (new Set(files.map(file => file.path.toLowerCase())).size !== files.length) throw new Error('Model có tệp trùng đường dẫn.');
  return files;
}
export interface Live2DImportReport {
  name: string; entry: string; files: number; bytes: number;
  motions: { found: string[]; referenced: string[] }; expressions: { found: string[]; referenced: string[] };
  textures: string[]; parameters: number | null; physics: boolean;
  issues: { severity: 'error' | 'warning'; message: string; paths?: string[] }[];
  prepared?: CharacterImport;
}
/** Inspect bounded archive data without saving it or loading an executable model runtime. */
export async function inspectLive2D(input: File[]): Promise<Live2DImportReport> {
  const files = await liveFiles(input);
  const name = input.length > 1 ? (input[0].webkitRelativePath || input[0].name).split('/')[0] : input[0].name.replace(/\.zip$/i, '');
  const report: Live2DImportReport = { name, entry: '', files: files.length, bytes: files.reduce((sum, file) => sum + file.blob.size, 0),
    motions: { found: files.filter(file => /\.motion3\.json$/i.test(file.path)).map(file => file.path), referenced: [] },
    expressions: { found: files.filter(file => /\.exp3\.json$/i.test(file.path)).map(file => file.path), referenced: [] },
    textures: [], parameters: null, physics: false, issues: [] };
  const entries = files.filter(file => /\.model3\.json$/i.test(file.path));
  const error = (message: string) => { if (!report.issues.some(issue => issue.message === message)) report.issues.push({ severity: 'error', message }); };
  if (entries.length === 1) {
    report.entry = entries[0].path;
    try {
      const json = await jsonFile(entries[0]);
      const refs = json.FileReferences ?? {};
      const base = report.entry.split('/').slice(0, -1).join('/');
      const map = new Map(files.map(file => [file.path, file]));
      const reference = (value: unknown) => {
        if (typeof value !== 'string') return undefined;
        try {
          const path = modelPath(value, base);
          if (!map.has(path)) error(`Thiếu tệp trong model: ${path}`);
          return path;
        } catch (reason) { error(reason instanceof Error ? reason.message : 'Đường dẫn không hợp lệ.'); return undefined; }
      };
      const paths = (values: unknown[]) => [...new Set(values.map(reference).filter((path): path is string => !!path))];
      report.textures = paths(Array.isArray(refs.Textures) ? refs.Textures : []);
      report.expressions.referenced = paths(Array.isArray(refs.Expressions) ? refs.Expressions.map((item: Json) => item?.File) : []);
      report.motions.referenced = paths(refs.Motions && typeof refs.Motions === 'object'
        ? Object.values(refs.Motions).flatMap(items => Array.isArray(items) ? items.map(item => item?.File) : []) : []);
      const moc = reference(refs.Moc);
      for (const field of ['Physics', 'Pose', 'UserData', 'DisplayInfo']) if (refs[field]) reference(refs[field]);
      report.physics = typeof refs.Physics === 'string' && map.has(modelPath(refs.Physics, base));
      if (moc && (map.get(moc)?.blob.size ?? 0) > 10 * 1024 * 1024) report.issues.push({ severity: 'warning', message: 'Tệp MOC lớn hơn 10 MB, có thể tải chậm hoặc giảm độ mượt trên điện thoại.' });
      if (typeof refs.DisplayInfo === 'string') {
        const display = map.get(modelPath(refs.DisplayInfo, base));
        if (display) {
          const info = await jsonFile(display);
          if (Array.isArray(info.Parameters)) report.parameters = new Set(info.Parameters.filter((p: Json) => typeof p?.Id === 'string').map((p: Json) => p.Id)).size;
        }
      }
      for (const [resources, label] of [[report.motions, 'chuyển động'], [report.expressions, 'biểu cảm']] as const) {
        const extra = resources.found.filter(path => !resources.referenced.includes(path));
        if (extra.length) report.issues.push({ severity: 'warning', message: `${extra.length} tệp ${label} chưa được khai báo trong .model3.json nên sẽ không được nhập. Hãy bổ sung khai báo nếu muốn sử dụng.`, paths: extra });
      }
    } catch (reason) { error(reason instanceof Error ? reason.message : 'Không đọc được cấu hình model.'); }
  }
  try {
    const data = await validateLive2D(files);
    if (!report.issues.some(issue => issue.severity === 'error')) {
      const id = crypto.randomUUID();
      report.prepared = { model: { id, name: name.slice(0, 80), format: 'live2d', bytes: data.files.reduce((sum, file) => sum + file.blob.size, 0), createdAt: Date.now() }, assets: { id, ...data } };
    }
  } catch (reason) { error(reason instanceof Error ? reason.message : 'Model không hợp lệ.'); }
  return report;
}

export async function importCharacter(input: File[], format: CharacterFormat): Promise<CharacterImport> {
  checkInput(input);
  const id = crypto.randomUUID();
  let name = input[0].name.replace(/\.(zip|vrm)$/i, ''), author: string | undefined;
  let data: { entry: string; files: CharacterFile[] };
  if (format === 'vrm') {
    if (input.length !== 1 || !input[0].name.toLowerCase().endsWith('.vrm')) throw new Error('Hãy chọn một tệp .vrm.');
    const meta = validateVRM(await input[0].arrayBuffer());
    name = meta.name ?? name; author = meta.author;
    data = { entry: 'model.vrm', files: [{ path: 'model.vrm', blob: input[0] }] };
  } else {
    const files = await liveFiles(input);
    if (input.length > 1) name = (input[0].webkitRelativePath || input[0].name).split('/')[0];
    data = await validateLive2D(files);
  }
  return { model: { id, name: name.slice(0, 80), format, author, bytes: data.files.reduce((size, file) => size + file.blob.size, 0), createdAt: Date.now() }, assets: { id, ...data } };
}
