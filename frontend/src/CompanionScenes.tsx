import { useEffect, useRef, useState } from 'react';
import { importScene, readScenePreference, saveScenePreference, SCENES, sceneStorage, type Scene, type ScenePreference } from './sceneLibrary';

export function useCompanionScene(character: string) {
  const [preference, setPreference] = useState(() => readScenePreference(character));
  const [uploads, setUploads] = useState<Scene[]>([]);
  const [error, setError] = useState('');
  const refresh = async () => setUploads(await sceneStorage('list'));
  useEffect(() => {
    let alive = true;
    void sceneStorage('list').then(items => { if (alive) setUploads(items); }).catch(() => { if (alive) setError('Chưa mở được ảnh đã lưu trên thiết bị. Bạn vẫn có thể chọn nền mẫu.'); });
    return () => { alive = false; };
  }, []);
  useEffect(() => { setPreference(readScenePreference(character)); }, [character]);
  const [resolved, setResolved] = useState<Scene[]>([]);
  useEffect(() => {
    const items = uploads.map(item => ({ ...item, url: item.blob ? URL.createObjectURL(item.blob) : undefined }));
    setResolved(items);
    return () => items.forEach(item => { if (item.url) URL.revokeObjectURL(item.url); });
  }, [uploads]);
  const scenes = [...SCENES, ...resolved];
  const selected = scenes.find(item => item.id === preference.id) ?? SCENES[0];
  const update = (value: ScenePreference) => {
    setPreference(value);
    try { saveScenePreference(character, value); } catch { setError('Đã áp dụng, nhưng trình duyệt chưa cho phép nhớ lựa chọn này.'); }
  };
  return { preference, scenes, selected, update, refresh, error, setError };
}
export function SceneBackdrop({ scene }: { scene: ReturnType<typeof useCompanionScene> }) {
  return scene.selected.url ? <div className="scene-backdrop" aria-hidden="true">
    <img src={scene.selected.url} alt="" style={{ filter: `blur(${scene.preference.blur}px)` }} />
    <div style={{ background: `rgba(0,0,0,${scene.preference.dim / 100})` }} />
  </div> : null;
}
export function ScenePicker({ scene, onClose }: { scene: ReturnType<typeof useCompanionScene>; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close(); }, []);
  const run = async (action: () => Promise<void>) => {
    setBusy(true); scene.setError('');
    try { await action(); } catch (error) { scene.setError(error instanceof Error ? error.message : 'Chưa lưu được ảnh. Hãy kiểm tra dung lượng trình duyệt.'); }
    finally { setBusy(false); }
  };
  return <dialog ref={dialog} className="character-picker scene-picker" aria-labelledby="scene-title" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <div className="character-picker-head"><div><h2 id="scene-title">Bối cảnh</h2><p>Không gian của nhân vật · Lưu trên thiết bị này</p></div><button className="dialog-close" aria-label="Đóng bối cảnh" disabled={busy} onClick={onClose}>×</button></div>
    <div className="character-picker-body">
      <div className="scene-preview"><SceneBackdrop scene={scene} /><span>Xem trước nền</span></div>
      <div className="scene-toolbar"><button disabled={busy} onClick={() => input.current?.click()}>＋ Thêm ảnh</button><small>PNG, JPG, WebP, AVIF · Tối đa 12 MB</small></div>
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,image/avif" hidden onChange={event => {
        const file = event.target.files?.[0]; event.target.value = '';
        if (file) void run(async () => { const item = await importScene(file); await sceneStorage('put', item); await scene.refresh(); scene.update({ ...scene.preference, id: item.id }); });
      }} />
      {busy && <p role="status">Đang xử lý ảnh…</p>}
      {scene.error && <p role="alert" className="character-library-error">{scene.error}</p>}
      <div className="scene-grid">{scene.scenes.map(item => <div className="scene-card" key={item.id}>
        <button disabled={busy} aria-pressed={scene.selected.id === item.id} onClick={() => scene.update({ ...scene.preference, id: item.id })}>
          <div>{item.url ? <img src={item.url} alt="" /> : <span>◇</span>}</div><strong>{item.name}</strong>
        </button>
        {item.blob && <button className="scene-remove" disabled={busy} aria-label={`Xóa nền ${item.name}`} onClick={() => void run(async () => {
          await sceneStorage('delete', item); await scene.refresh();
          if (scene.preference.id === item.id) scene.update({ ...scene.preference, id: 'dark' });
        })}>Xóa</button>}
      </div>)}</div>
      <div className="scene-adjustments">
        <label>Độ tối <span>{scene.preference.dim}%</span><input type="range" min="0" max="80" value={scene.preference.dim} disabled={!scene.selected.url} onChange={event => scene.update({ ...scene.preference, dim: Number(event.target.value) })} /></label>
        <label>Làm mờ <span>{scene.preference.blur}px</span><input type="range" min="0" max="20" value={scene.preference.blur} disabled={!scene.selected.url} onChange={event => scene.update({ ...scene.preference, blur: Number(event.target.value) })} /></label>
      </div>
      <small className="scene-credit">Nền mẫu từ Project AIRI · <a href="/scenes/airi/AIRI-LICENSE.txt" target="_blank" rel="noreferrer">Giấy phép MIT</a></small>
    </div>
  </dialog>;
}
