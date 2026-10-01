import { useCallback, useEffect, useRef, useState } from 'react';
import { UnauthorizedError } from '../../shared/api/api';
import { getProject, type ProjectDetail } from './projectApi';
import { FolderIcon } from './ProjectSidebar';

export function ProjectConfirm({title, children, busy, onClose, onConfirm}: {title:string; children:React.ReactNode; busy:boolean; onClose:()=>void; onConfirm:()=>void}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {ref.current?.showModal();}, []);
  return <dialog className="confirm-dialog" ref={ref} aria-label={title} onCancel={e => {e.preventDefault(); if (!busy) onClose();}}><h2>{title}</h2>{children}<div className="dialog-actions"><button disabled={busy} onClick={onClose}>Hủy</button><button className="danger-button" disabled={busy} onClick={onConfirm}>{busy ? 'Đang xử lý…' : 'Xóa'}</button></div></dialog>;
}

export function useDetail(id:string, onUnauthorized:()=>void) {
  const [detail, setDetail] = useState<ProjectDetail|null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision(n => n+1), []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    void getProject(id,controller.signal).then(value => {if (!controller.signal.aborted) {setDetail(value);setError('');}}).catch(err => {
      if (controller.signal.aborted) return;
      if (err instanceof UnauthorizedError) onUnauthorized(); else setError(err instanceof Error ? err.message : 'Chưa mở được dự án.');
    }).finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [id,revision,onUnauthorized]);
  return {detail,error,loading,reload,setError};
}

export function ProjectContext({id, selected, onSelect, onOpen, onUnauthorized, disabled}: {id:string; selected:string[]; onSelect:(ids:string[])=>void; onOpen:()=>void; onUnauthorized:()=>void; disabled:boolean}) {
  const {detail,error,loading,reload} = useDetail(id,onUnauthorized);
  useEffect(() => {
    if (detail) {const valid = selected.filter(value => detail.files.some(file => file.id === value)); if (valid.length !== selected.length) onSelect(valid);}
  }, [detail, selected, onSelect]);
  return <div className="project-context">
    <button className="project-context-name" disabled={disabled} onClick={onOpen}><FolderIcon/><span>{detail?.name || 'Dự án'}</span></button>
    <details><summary>Tài liệu cho lượt này{selected.length ? ` · ${selected.length}` : ''}</summary><div className="project-file-picker"><p>Chỉ tài liệu bạn chọn được đọc trong lượt gửi này. Tối đa 4 tài liệu, tổng 32.000 ký tự; phần dài hơn sẽ bị cắt.</p>{loading && <p role="status">Đang tải…</p>}{error && <button onClick={reload}>Chưa tải được tài liệu. Thử lại</button>}{detail?.files.map(file => <label key={file.id}><input type="checkbox" checked={selected.includes(file.id)} disabled={disabled || (!selected.includes(file.id) && selected.length >= 4) || !['ready','partial'].includes(file.document?.status || '')} onChange={e => onSelect(e.target.checked ? [...selected,file.id] : selected.filter(value => value !== file.id))}/><span>{file.name}<small>{file.document?.notice}</small></span></label>)}{detail && !detail.files.length && <p>Thêm tài liệu ở trang dự án.</p>}</div></details>
  </div>;
}
