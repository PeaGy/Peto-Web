import { CHARACTER } from './characterConfig';

export type CharacterFormat = 'live2d' | 'vrm';
export interface CharacterModel {
  id: string;
  name: string;
  format: CharacterFormat;
  bytes: number;
  createdAt: number;
  builtin?: boolean;
  preview?: string;
  author?: string;
}
export interface CharacterFile { path: string; blob: Blob }
export interface CharacterAssets { id: string; entry: string; files: CharacterFile[] }
export interface CharacterImport { model: CharacterModel; assets: CharacterAssets }

export const DEFAULT_CHARACTER: CharacterModel = {
  id: CHARACTER.id, name: CHARACTER.name, format: 'live2d', bytes: 0, createdAt: 0, builtin: true,
};
export const SELECTED_CHARACTER_KEY = 'peto-selected-character';

function openLibrary(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') return reject(new Error('Trình duyệt này chưa cho phép lưu model.'));
    const request = indexedDB.open('peto-characters', 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore('models', { keyPath: 'id' });
      request.result.createObjectStore('assets', { keyPath: 'id' });
    };
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('Hãy đóng các tab Peto cũ rồi thử lại.'));
    request.onsuccess = () => resolve(request.result);
  });
}

async function transaction<T>(stores: string[], mode: IDBTransactionMode, run: (tx: IDBTransaction) => IDBRequest<T>): Promise<T> {
  const db = await openLibrary();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(stores, mode);
    let result: T;
    try {
      const request = run(tx);
      request.onsuccess = () => { result = request.result; };
    } catch (error) { tx.abort(); db.close(); reject(error); return; }
    tx.oncomplete = () => { db.close(); resolve(result); };
    tx.onabort = tx.onerror = () => { db.close(); reject(tx.error ?? new Error('Không lưu được thư viện nhân vật.')); };
  });
}

export async function listCharacters(): Promise<CharacterModel[]> {
  const all = await transaction<CharacterModel[]>(['models'], 'readonly', tx => tx.objectStore('models').getAll());
  const preset = all.find(item => item.id === DEFAULT_CHARACTER.id);
  return [{ ...DEFAULT_CHARACTER, preview: preset?.preview }, ...all.filter(item => !item.builtin).sort((a, b) => b.createdAt - a.createdAt)];
}
export function getCharacterAssets(id: string): Promise<CharacterAssets | undefined> {
  return transaction(['assets'], 'readonly', tx => tx.objectStore('assets').get(id));
}
export async function saveCharacter(data: CharacterImport) {
  await transaction(['models', 'assets'], 'readwrite', tx => {
    tx.objectStore('assets').put(data.assets);
    return tx.objectStore('models').put(data.model);
  });
}
export async function updateCharacter(id: string, patch: { name?: string; preview?: string }) {
  await transaction(['models'], 'readwrite', tx => {
    const store = tx.objectStore('models');
    const request = store.get(id);
    request.addEventListener('success', () => {
      const current = request.result ?? (id === DEFAULT_CHARACTER.id ? DEFAULT_CHARACTER : null);
      // Không làm sống lại một model vừa bị xóa bởi tab khác hoặc lúc thumbnail về muộn.
      if (current) store.put({ ...current, ...patch });
    });
    return request;
  });
}
export async function removeCharacter(id: string) {
  if (id === DEFAULT_CHARACTER.id) return;
  await transaction(['models', 'assets'], 'readwrite', tx => {
    tx.objectStore('assets').delete(id);
    return tx.objectStore('models').delete(id);
  });
}
export function readSelectedCharacter() {
  try { return localStorage.getItem(SELECTED_CHARACTER_KEY) || DEFAULT_CHARACTER.id; } catch { return DEFAULT_CHARACTER.id; }
}
export function writeSelectedCharacter(id: string) {
  try { localStorage.setItem(SELECTED_CHARACTER_KEY, id); } catch { /* Model vẫn dùng được trong phiên hiện tại. */ }
}
export function characterError(error: unknown): string {
  if (error instanceof DOMException && error.name === 'QuotaExceededError') return 'Bộ nhớ trình duyệt đã đầy. Hãy xóa bớt model rồi thử lại.';
  return error instanceof Error ? error.message : 'Không xử lý được model. Bạn hãy thử lại.';
}

/** Chụp ngay sau khi render, trước khi WebGL xóa drawing buffer. */
export function characterThumbnail(canvas: HTMLCanvasElement): string {
  const sample = document.createElement('canvas');
  const ratio = Math.min(1, 512 / Math.max(canvas.width, canvas.height));
  sample.width = Math.max(1, Math.round(canvas.width * ratio)); sample.height = Math.max(1, Math.round(canvas.height * ratio));
  const sampleContext = sample.getContext('2d', { willReadFrequently: true })!;
  sampleContext.drawImage(canvas, 0, 0, sample.width, sample.height);
  const pixels = sampleContext.getImageData(0, 0, sample.width, sample.height).data;
  let left = sample.width, top = sample.height, right = 0, bottom = 0;
  for (let y = 0; y < sample.height; y++) for (let x = 0; x < sample.width; x++) {
    if (pixels[(y * sample.width + x) * 4 + 3] > 16) {
      left = Math.min(left, x); top = Math.min(top, y); right = Math.max(right, x); bottom = Math.max(bottom, y);
    }
  }
  if (right <= left || bottom <= top) throw new Error('Nhân vật chưa sẵn sàng chụp ảnh.');
  const output = document.createElement('canvas');
  output.width = 256; output.height = 320;
  const ctx = output.getContext('2d')!;
  const width = right - left + 1, height = bottom - top + 1;
  const scale = Math.min(output.width / width, output.height / height) * 0.94;
  ctx.drawImage(sample, left, top, width, height, (output.width - width * scale) / 2, (output.height - height * scale) / 2, width * scale, height * scale);
  return output.toDataURL('image/png');
}
