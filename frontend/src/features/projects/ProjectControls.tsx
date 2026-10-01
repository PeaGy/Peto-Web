import { useEffect, useRef } from 'react';

export function ProjectConfirm({title, children, busy, onClose, onConfirm}: {title:string; children:React.ReactNode; busy:boolean; onClose:()=>void; onConfirm:()=>void}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {ref.current?.showModal();}, []);
  return <dialog className="confirm-dialog" ref={ref} aria-label={title} onCancel={e => {e.preventDefault(); if (!busy) onClose();}}><h2>{title}</h2>{children}<div className="dialog-actions"><button disabled={busy} onClick={onClose}>Hủy</button><button className="danger-button" disabled={busy} onClick={onConfirm}>{busy ? 'Đang xử lý…' : 'Xóa'}</button></div></dialog>;
}
