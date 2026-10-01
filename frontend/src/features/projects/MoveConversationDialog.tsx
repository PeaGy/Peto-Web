import {useEffect, useRef, useState} from 'react';
import type {Conversation} from '../../shared/api/api';
import type {Project} from './projectApi';

export default function MoveConversationDialog({item, projects, busy, error, onClose, onSave}: {item:Conversation; projects:Project[]; busy:boolean; error?:string; onClose:()=>void; onSave:(id:string|null)=>void}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [target,setTarget] = useState(item.project_id || '');
  useEffect(() => {ref.current?.showModal();}, []);
  return <dialog className="text-edit-dialog" ref={ref} aria-label="Chuyển hội thoại vào dự án" onCancel={e => {e.preventDefault();if(!busy)onClose();}}><form onSubmit={e => {e.preventDefault();if(!busy)onSave(target || null);}}><h2>Chuyển hội thoại</h2><p>“{item.title}”</p><label htmlFor="move-project">Nơi lưu hội thoại</label><select id="move-project" value={target} disabled={busy} onChange={e => setTarget(e.target.value)}><option value="">Ngoài dự án · Gần đây</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select>{error && <p role="alert">{error}</p>}<div><button type="button" disabled={busy} onClick={onClose}>Hủy</button><button type="submit" disabled={busy}>Chuyển</button></div></form></dialog>;
}
