import { useEffect, useRef, useState } from 'react';
import { characterError, type CharacterFormat } from './characterLibrary';
import type { CharacterLibrary } from './useCharacters';
import IdleMotionPicker from './IdleMotionPicker';
import CharacterImportReview from './CharacterImportReview';
import type { Live2DImportReport } from './characterImport';
import { CHARACTER } from './characterConfig';
import { useRenderQuality, writeRenderQuality } from './renderQuality';

export default function CharacterPicker({ library, onClose }: { library: CharacterLibrary; onClose: () => void }) {
  const quality = useRenderQuality();
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
      setNotice('');
      const { inspectLive2D } = await import('./characterImport');
      setReview(await inspectLive2D(input));
    });
    else void run(() => library.add(input, format), 'Đã thêm và chọn nhân vật. Đóng cửa sổ này để xem trên sân khấu.');
  };
  const confirmImport = async () => {
    if (!review?.prepared || busy) return;
    setBusy(true); setError('');
    try {
      await library.addPrepared(review.prepared);
      setReview(null); setNotice('Đã thêm và chọn nhân vật. Đóng cửa sổ này để xem trên sân khấu.');
    } catch (reason) { setError(characterError(reason)); }
    finally { setBusy(false); }
  };
  const chooseFile = (ref: { current: HTMLInputElement | null }) => { if (menu.current) menu.current.open = false; ref.current?.click(); };
  return <dialog ref={dialog} className="character-picker" aria-labelledby="character-picker-title" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    {review && <CharacterImportReview report={review} busy={busy} error={error}
      onCancel={() => { setReview(null); setError(''); }} onConfirm={() => void confirmImport()} />}
    <div className="character-picker-head">
      <div><h2 id="character-picker-title">Nhân vật</h2><p>Chọn gương mặt đồng hành cùng bạn.</p></div>
      <button className="dialog-close" aria-label="Đóng chọn nhân vật" disabled={busy} onClick={onClose}>×</button>
    </div>
    <div className="character-picker-body">
      <div className="character-library-bar">
        <span>{library.models.length} nhân vật · Trên thiết bị này</span>
        <details ref={menu} className="character-import-menu">
          <summary aria-label="Thêm model" aria-disabled={busy}>＋ Thêm model</summary>
          <div>
            <button disabled={busy || library.loading} onClick={() => chooseFile(zip)}>Live2D <small>Tệp .zip</small></button>
            <button disabled={busy || library.loading} onClick={() => chooseFile(folder)}>Thư mục Live2D <small>Chọn toàn bộ thư mục</small></button>
            <button disabled={busy || library.loading} onClick={() => chooseFile(vrm)}>VRM <small>Tệp .vrm · Nhân vật 3D</small></button>
          </div>
        </details>
      </div>
      <input ref={zip} type="file" accept=".zip" hidden aria-label="Nhập ZIP Live2D" onChange={event => { picked(event.target.files, 'live2d'); event.target.value = ''; }} />
      <input ref={folder} type="file" multiple hidden aria-label="Nhập thư mục Live2D" onChange={event => { picked(event.target.files, 'live2d'); event.target.value = ''; }} />
      <input ref={vrm} type="file" accept=".vrm" hidden aria-label="Nhập VRM" onChange={event => { picked(event.target.files, 'vrm'); event.target.value = ''; }} />
      {busy && <p className="character-library-notice" role="status">Đang xử lý model…</p>}
      {(error || library.error) && <p className="character-library-error" role="alert">{error || library.error}</p>}
      {notice && <p className="character-library-notice" role="status">{notice}</p>}
      <div className="character-library-grid" aria-label="Thư viện nhân vật">
        {library.models.map(model => <article key={model.id} className={`character-card${library.selected.id === model.id ? ' selected' : ''}`}>
          <button className="character-card-art" disabled={busy} aria-label={`Chọn ${model.name}`} aria-pressed={library.selected.id === model.id} onClick={() => { library.select(model.id); setNotice('Đã chọn nhân vật. Đóng cửa sổ này để xem trên sân khấu.'); }}>
            {model.preview ? <img src={model.preview} alt={model.name} /> : <span className="character-card-placeholder"><b>{model.format === 'vrm' ? '3D' : '2D'}</b><span>{model.name}</span></span>}
            <span className="character-format">{model.format === 'vrm' ? 'VRM' : 'Live2D'}</span>
            {library.selected.id === model.id && <span className="character-selected-badge">✓ Đang dùng</span>}
          </button>
          <div className="character-card-info">
            {editing === model.id ? <form onSubmit={event => { event.preventDefault(); void run(() => library.rename(model.id, name)); }}>
              <input aria-label="Tên nhân vật mới" autoFocus maxLength={80} value={name} onChange={event => setName(event.target.value)} />
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
      <section className="mobile-render-settings" aria-label="Hiển thị trên điện thoại">
        <h3>Hiển thị trên điện thoại</h3>
        <label>Chất lượng hình ảnh <select value={quality.sharp ? 'high' : 'normal'} onChange={e => writeRenderQuality({ ...quality, sharp: e.target.value === 'high' })}><option value="normal">Tiết kiệm · 1×</option><option value="high">Cao · tối đa 2×</option></select></label>
        <label>Độ mượt <select value={quality.smooth ? 'high' : 'normal'} onChange={e => writeRenderQuality({ ...quality, smooth: e.target.value === 'high' })}><option value="normal">Tiết kiệm · 24 FPS</option><option value="high">Cao · tối đa 60 FPS</option></select></label>
        <p>Áp dụng cho Live2D và VRM trên thiết bị này. Mức cao có thể dùng nhiều pin và làm máy ấm hơn.</p>
      </section>
      {library.selected.format === 'live2d' && <details className="character-motion-settings" key={library.selected.id}>
        <summary>Cài đặt nhân vật <span>Chuyển động · Biểu cảm · Nhún theo nhạc</span></summary>
        <IdleMotionPicker character={library.selected} />
      </details>}
      <p className="character-library-footnote"><a href={CHARACTER.creditUrl} target="_blank" rel="noopener noreferrer">Hiyori Momose · © Live2D Inc.</a></p>
      <p className="character-library-footnote">Tối đa 80 MB mỗi lần nhập. Model lưu trong trình duyệt này, chưa đồng bộ sang máy khác. Xóa dữ liệu trang web sẽ xóa thư viện. Chỉ nhập model bạn có quyền sử dụng.</p>
    </div>
  </dialog>;
}
