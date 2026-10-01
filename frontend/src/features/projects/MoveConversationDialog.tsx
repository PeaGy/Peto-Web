import {useEffect, useRef, useState} from 'react';
import type {Conversation} from '../../shared/api/api';
import type {Project} from './projectApi';

export default function MoveConversationDialog({item, projects, busy, error, loading, loadError, onRetry, onCreate, onClose, onSave}: {
  item:Conversation; projects:Project[]; busy:boolean; error?:string; loading:boolean; loadError?:string;
  onRetry:()=>void; onCreate:(name:string)=>Promise<Project|null>; onClose:()=>void; onSave:(id:string|null)=>void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [target,setTarget] = useState(item.project_id || '');
  const [creating,setCreating] = useState(false);
  const [name,setName] = useState('');
  const [created,setCreated] = useState<Project|null>(null);
  const alive = useRef(true);
  useEffect(() => {ref.current?.showModal();}, []);
  useEffect(() => {alive.current=true;return () => {alive.current=false;};}, []);
  const choices=created && !projects.some(project=>project.id===created.id) ? [...projects,created] : projects;
  const empty=!loading && !loadError && !choices.length && !item.project_id;
  const createMode=creating || empty;
  const unchanged=target===(item.project_id || '');
  async function submit() {
    if (busy || loading) return;
    if (!createMode) {if (!unchanged) onSave(target || null);return;}
    if (!name.trim()) return;
    const project=await onCreate(name.trim());
    if (!project || !alive.current) return;
    // Nếu chuyển lỗi, giữ đích vừa tạo để thử lại mà không tạo thêm dự án.
    setCreated(project);setTarget(project.id);setCreating(false);setName('');
    onSave(project.id);
  }
  return <dialog className="text-edit-dialog" ref={ref} aria-label="Chuyển hội thoại vào dự án" onCancel={e => {e.preventDefault();if(!busy)onClose();}}>
    <form onSubmit={e => {e.preventDefault();void submit();}}>
      <h2>Chuyển hội thoại</h2><p>“{item.title}”</p>
      {loading && <p role="status">Đang tải danh sách dự án…</p>}
      {loadError && <p role="alert">{loadError} <button type="button" disabled={busy || loading} onClick={onRetry}>Thử tải lại</button></p>}
      {empty && <p>Chưa có dự án. Đặt tên bên dưới để tạo và chuyển hội thoại vào đó.</p>}
      {createMode ? <><label htmlFor="move-project-name">Tên dự án mới</label><input id="move-project-name" autoFocus required maxLength={100} value={name} disabled={busy || loading} onChange={e=>setName(e.target.value)}/>{!empty && <button type="button" disabled={busy} onClick={()=>setCreating(false)}>Chọn dự án có sẵn</button>}</> : <>
        <label htmlFor="move-project">Nơi lưu hội thoại</label>
        <select id="move-project" value={target} disabled={busy || loading} onChange={e => setTarget(e.target.value)}>
          <option value="">Ngoài dự án · Gần đây</option>
          {item.project_id && !choices.some(project=>project.id===item.project_id) && <option value={item.project_id}>Dự án hiện tại</option>}
          {choices.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
        <button className="move-project-create" type="button" disabled={busy || loading} onClick={()=>setCreating(true)}>+ Tạo dự án mới</button>
      </>}
      {error && <p role="alert">{error}</p>}
      <div><button type="button" disabled={busy} onClick={onClose}>Hủy</button><button type="submit" disabled={busy || loading || (createMode ? !name.trim() : unchanged)}>{busy ? 'Đang xử lý…' : createMode ? 'Tạo và chuyển' : 'Chuyển'}</button></div>
    </form>
  </dialog>;
}
