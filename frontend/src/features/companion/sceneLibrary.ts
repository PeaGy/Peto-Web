export interface Scene { id: string; name: string; url?: string; blob?: Blob }
export interface ScenePreference { id: string; dim: number; blur: number }
export const SCENES: Scene[] = [
  { id: 'dark', name: 'Nền mặc định' },
  { id: 'tea', name: 'Góc trà pastel', url: '/scenes/airi/cozy-tea-corner-in-pastel-hues.avif' },
  { id: 'room', name: 'Phòng streaming', url: '/scenes/airi/cute-streaming-room-with-pastel-decor.avif' },
];
export function readScenePreference(character: string): ScenePreference {
  try {
    const value = JSON.parse(localStorage.getItem(`peto-scene:${character}`) || '{}');
    return { id: typeof value.id === 'string' ? value.id : 'dark',
      dim: Number.isFinite(value.dim) ? Math.max(0, Math.min(80, value.dim)) : 20,
      blur: Number.isFinite(value.blur) ? Math.max(0, Math.min(20, value.blur)) : 0 };
  } catch { return { id: 'dark', dim: 20, blur: 0 }; }
}
export function saveScenePreference(character: string, value: ScenePreference) {
  localStorage.setItem(`peto-scene:${character}`, JSON.stringify(value));
}
export async function sceneStorage(action: 'list' | 'put' | 'delete', scene?: Scene): Promise<Scene[]> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('peto-scenes', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('images', { keyPath: 'id' });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('Hãy đóng tab Peto cũ rồi thử lại.'));
  });
  return new Promise((resolve, reject) => {
    const tx = db.transaction('images', action === 'list' ? 'readonly' : 'readwrite');
    const store = tx.objectStore('images');
    if (action === 'put' && scene) store.put(scene);
    if (action === 'delete' && scene) store.delete(scene.id);
    const request = store.getAll();
    tx.oncomplete = () => { db.close(); resolve(request.result); };
    tx.onabort = tx.onerror = () => { db.close(); reject(tx.error); };
  });
}
export async function importScene(file: File): Promise<Scene> {
  if (!['image/png', 'image/jpeg', 'image/webp', 'image/avif'].includes(file.type)) throw new Error('Chọn ảnh PNG, JPG, WebP hoặc AVIF.');
  if (file.size > 12 * 1024 * 1024) throw new Error('Chọn ảnh nhỏ hơn 12 MB nhé.');
  const bitmap = await createImageBitmap(file);
  const tooLarge = bitmap.width * bitmap.height > 32_000_000;
  bitmap.close();
  if (tooLarge) throw new Error('Ảnh quá lớn. Hãy giảm xuống dưới 32 megapixel.');
  return { id: `upload-${crypto.randomUUID()}`, name: file.name, blob: file };
}
