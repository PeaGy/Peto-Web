import { useEffect, useRef } from 'react';

export default function TextEditDialog({title, description, value, onChange, onClose, onSave, busy, multiline=false}: {
  title:string; description?:string; value:string; onChange:(value:string)=>void;
  onClose:()=>void; onSave:()=>void; busy:boolean; multiline?:boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} className="text-edit-dialog" aria-labelledby="text-edit-title" onCancel={e => {e.preventDefault(); if (!busy) onClose();}}>
    <form onSubmit={e => {e.preventDefault(); if (!busy) onSave();}}>
      <h2 id="text-edit-title">{title}</h2>
      {description && <p>{description}</p>}
      {multiline ? <textarea autoFocus aria-label={title} value={value} onChange={e => onChange(e.target.value)} rows={7}/> :
        <input autoFocus aria-label={title} maxLength={120} required value={value} onChange={e => onChange(e.target.value)}/>}
      <div><button type="button" disabled={busy} onClick={onClose}>Hủy</button><button type="submit" disabled={busy}>{multiline ? 'Lưu và gửi' : 'Lưu'}</button></div>
    </form>
  </dialog>;
}
