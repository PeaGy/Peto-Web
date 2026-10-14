import { useEffect, useRef, useState } from 'react';
import { characterError, type CharacterFormat } from './characterLibrary';
import type { CharacterLibrary } from './useCharacters';
import CharacterImportReview from './CharacterImportReview';
import type { Live2DImportReport } from './characterImport';
import { MAX_IMPORT_BYTES, megabytes } from './characterLimits';
import { CHARACTER } from './characterConfig';

/**
 * Hộp "Chọn nhân vật" của trang Cài đặt → Nhân vật, như ModelSelectorDialog của AIRI: chỉ có thư viện (chọn, nhập, đổi
 * tên, xóa). Cài đặt của nhân vật nằm ngay trên trang, cạnh sân khấu (chủ web chọn biến thể "Như AIRI" ngày 14/10/2026).
 * Chọn hay nhập xong thì hộp đóng lại để thấy ngay nhân vật mới trên sân khấu.
 */
export default function CharacterPicker({ library, onClose }: { library: CharacterLibrary; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const menu = useRef<HTMLDetailsElement>(null);
  const zip = useRef<HTMLInputElement>(null);
  const folder = useRef<HTMLInputElement>(null);
  const vrm = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [editing, setEditing] = useState('');
  const [name, setName] = useState('');
  const [deleting, setDeleting] = useState('');
  const [review, setReview] = useState<Live2DImportReport | null>(null);
  useEffect(() => {
    dialog.current?.showModal();
    folder.current?.setAttribute('webkitdirectory', '');
    return () => dialog.current?.close();
  }, []);
  const run = async (action: () => Promise<void>, message = '') => {
    setBusy(true); setError(''); setNotice('');
    try { await action(); setEditing(''); setDeleting(''); setNotice(message); }
    catch (reason) { setError(characterError(reason)); }
    finally { setBusy(false); }
  };
  const picked = (files: FileList | null, format: CharacterFormat) => {
    if (!files?.length) return;
    const input = Array.from(files);
    if (format === 'live2d') void run(async () => {
      const { inspectLive2D } = await import('./characterImport');
      setReview(await inspectLive2D(input));
    });
    else void run(async () => { await library.add(input, format); onClose(); });
  };
  const confirmImport = async (useControls = true) => {
    if (!review?.prepared || busy) return;
    setBusy(true); setError('');
    try {
      await library.addPrepared(useControls ? review.prepared : { ...review.prepared, assets: { ...review.prepared.assets, controls: undefined } });
      setReview(null); onClose();
    } catch (reason) { setError(characterError(reason)); }
    finally { setBusy(false); }
  };
  const chooseFile = (ref: { current: HTMLInputElement | null }) => { if (menu.current) menu.current.open = false; ref.current?.click(); };
  return <dialog ref={dialog} className="character-picker" aria-labelledby="character-picker-title" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    {review && <CharacterImportReview report={review} busy={busy} error={error}
      onCancel={() => { setReview(null); setError(''); }} onConfirm={useControls => void confirmImport(useControls)} />}
    <div className="character-picker-head">
      <div><h2 id="character-picker-title">Chọn nhân vật</h2><p>{library.models.length} nhân vật · Trên thiết bị này</p></div>
      <div className="character-picker-actions">
        <details ref={menu} className="character-import-menu">
          <summary aria-label="Thêm model" aria-disabled={busy}>＋ Thêm model</summary>
          <div>
            <button disabled={busy || library.loading} onClick={() => chooseFile(zip)}>Live2D <small>Tệp .zip</small></button>
            <button disabled={busy || library.loading} onClick={() => chooseFile(folder)}>Thư mục Live2D <small>Chọn toàn bộ thư mục</small></button>
            <button disabled={busy || library.loading} onClick={() => chooseFile(vrm)}>VRM <small>Tệp .vrm · Nhân vật 3D</small></button>
          </div>
        </details>
        <button className="dialog-close" aria-label="Đóng chọn nhân vật" disabled={busy} onClick={onClose}>×</button>
      </div>
    </div>
    <div className="character-picker-body">
      <input ref={zip} type="file" accept=".zip" hidden aria-label="Nhập ZIP Live2D" onChange={event => { picked(event.target.files, 'live2d'); event.target.value = ''; }} />
      <input ref={folder} type="file" multiple hidden aria-label="Nhập thư mục Live2D" onChange={event => { picked(event.target.files, 'live2d'); event.target.value = ''; }} />
      <input ref={vrm} type="file" accept=".vrm" hidden aria-label="Nhập VRM" onChange={event => { picked(event.target.files, 'vrm'); event.target.value = ''; }} />
      {busy && <p className="character-library-notice" role="status">Đang xử lý model…</p>}
      {(error || library.error) && <p className="character-library-error" role="alert">{error || library.error}</p>}
      {notice && <p className="character-library-notice" role="status">{notice}</p>}
      <div className="character-library-grid" aria-label="Thư viện nhân vật">
        {library.models.map(model => <article key={model.id} className={`character-card${library.selected.id === model.id ? ' selected' : ''}`}>
          <button className="character-card-art" disabled={busy} aria-label={`Chọn ${model.name}`} aria-pressed={library.selected.id === model.id}
            onClick={() => { library.select(model.id); onClose(); }}>
            {model.preview ? <img src={model.preview} alt={model.name} /> : <span className="character-card-placeholder"><b>{model.format === 'vrm' ? '3D' : '2D'}</b><span>{model.name}</span></span>}
            <span className="character-format">{model.format === 'vrm' ? 'VRM' : 'Live2D'}</span>
            {library.selected.id === model.id && <span className="character-selected-badge">✓ Đang dùng</span>}
          </button>
          <div className="character-card-info">
            {editing === model.id ? <form onSubmit={event => { event.preventDefault(); void run(() => library.rename(model.id, name)); }}>
              <input className="text-field" aria-label="Tên nhân vật mới" autoFocus maxLength={80} value={name} onChange={event => setName(event.target.value)} />
              <div className="character-card-actions"><button disabled={busy || !name.trim()}>Lưu tên</button><button type="button" disabled={busy} onClick={() => setEditing('')}>Hủy</button></div>
            </form> : <><strong>{model.name}</strong><small>{model.builtin ? 'Model mẫu · © Live2D Inc.' : `${(model.bytes / 1024 / 1024).toFixed(1)} MB${model.author ? ` · ${model.author}` : ''}`}</small></>}
            {!model.builtin && editing !== model.id && <div className="character-card-actions">
              <button disabled={busy} onClick={() => { setEditing(model.id); setName(model.name); setDeleting(''); }}>Đổi tên</button>
              <button disabled={busy} onClick={() => setDeleting(model.id)}>Xóa</button>
            </div>}
            {deleting === model.id && <div className="character-remove-confirm"><p>Xóa khỏi thư viện này? Tệp gốc của bạn vẫn còn.</p><div className="character-card-actions"><button disabled={busy} onClick={() => void run(() => library.remove(model.id), 'Đã xóa model khỏi thư viện.')}>Xóa model</button><button disabled={busy} onClick={() => setDeleting('')}>Giữ lại</button></div></div>}
          </div>
        </article>)}
      </div>
      <p className="character-library-footnote"><a href={CHARACTER.creditUrl} target="_blank" rel="noopener noreferrer">Hiyori Momose · © Live2D Inc.</a></p>
      <p className="character-library-footnote">Tối đa {megabytes(MAX_IMPORT_BYTES)} mỗi lần nhập. Model lưu trong trình duyệt này, chưa đồng bộ sang máy khác. Xóa dữ liệu trang web sẽ xóa thư viện. Chỉ nhập model bạn có quyền sử dụng.</p>
    </div>
  </dialog>;
}
