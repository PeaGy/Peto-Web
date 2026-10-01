import { useEffect, useRef, useState } from 'react';
import { UnauthorizedError, type Conversation } from '../../shared/api/api';
import { fileToBase64, MAX_FILE_BYTES } from '../chat/attachments';
import { deleteProjectFile, updateProject, uploadProjectFile, type ProjectFile } from './projectApi';
import { FolderIcon } from './ProjectSidebar';
import { ProjectConfirm, useDetail } from './ProjectControls';

export default function ProjectWorkspace({id, name, chats, chatsLoading, more, onMore, onChat, onNewChat, onUpdated, onUnauthorized, onSidebar, onOptions, disabled}: {
  id:string; name?:string; chats:Conversation[]; chatsLoading:boolean; more:boolean; onMore:()=>void; onChat:(id:string)=>void;
  onNewChat:()=>void; onUpdated:()=>void; onUnauthorized:()=>void; onSidebar:()=>void; onOptions:(rect:DOMRect)=>void; disabled:boolean;
}) {
  const {detail,error,loading,reload,setError} = useDetail(id,onUnauthorized);
  const [instructions, setInstructions] = useState('');
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [remove, setRemove] = useState<ProjectFile|null>(null);
  const input = useRef<HTMLInputElement>(null);
  const alive = useRef(true);
  useEffect(() => {alive.current=true; return () => {alive.current=false;};}, []);
  const initialized = useRef(false);
  useEffect(() => {if (detail && !initialized.current) {setInstructions(detail.instructions);initialized.current=true;}}, [detail]);
  async function mutate(action:()=>Promise<unknown>) {
    if (busy || disabled) return;
    setBusy(true); setError('');setSaved(false);
    try {await action(); if (alive.current) {reload();onUpdated();setRemove(null);setSaved(true);}}
    catch(err) {if (alive.current) {if (err instanceof UnauthorizedError) onUnauthorized(); else setError(err instanceof Error ? err.message : 'Chưa lưu được thay đổi.');}}
    finally {if (alive.current) setBusy(false);}
  }
  async function upload(file:File) {
    if (file.size > MAX_FILE_BYTES) {setError('Mỗi tài liệu tối đa 8 MB.'); return;}
    await mutate(async () => uploadProjectFile(id,{name:file.name,mime:file.type,data:await fileToBase64(file)}));
  }
  async function saveInstructions() {
    const value=instructions;
    await mutate(async () => {
      await updateProject(id,{instructions:value});
      if (alive.current) setInstructions(value.trim());
    });
  }
  return <main className="project-workspace">
    <header className="project-mobile-header"><button className="menu-btn" aria-label="Mở danh sách hội thoại" onClick={onSidebar}>☰</button><span>Dự án</span></header>
    {loading && !detail ? <p role="status">Đang mở dự án…</p> : !detail ? <div role="alert"><p>{error}</p><button onClick={reload}>Thử lại</button></div> : <div className="project-content">
      <div className="project-title-row"><div><span className="project-eyebrow"><FolderIcon/> Dự án</span><h1>{name || detail.name}</h1></div><button className="project-options" aria-label={`Tùy chọn dự án ${name || detail.name}`} disabled={disabled || busy} onClick={e => onOptions(e.currentTarget.getBoundingClientRect())}>⋯</button></div>
      <p className="project-intro">Một nơi cho hội thoại, tài liệu và hướng dẫn của công việc này.</p>
      {error && <p className="project-error" role="alert">{error}</p>}
      {saved && <p className="project-saved" role="status">Đã lưu thay đổi.</p>}
      <div className="project-resources">
        <section className="project-card"><div className="project-card-head"><h2>Hướng dẫn riêng</h2></div><label htmlFor="project-instructions">Peto nên trả lời và làm việc thế nào trong dự án này?</label><textarea id="project-instructions" value={instructions} maxLength={8000} rows={5} disabled={busy || disabled} placeholder="Ví dụ: trả lời bằng tiếng Việt, giải thích ngắn và đưa ví dụ…" onChange={e => {setInstructions(e.target.value);setSaved(false);}}/><div className="project-card-foot"><span>{instructions.length.toLocaleString('vi-VN')} / 8.000</span><button disabled={busy || disabled || instructions === detail.instructions} onClick={() => void saveInstructions()}>Lưu hướng dẫn</button></div></section>
        <section className="project-card"><div className="project-card-head"><h2>Tài liệu</h2><button disabled={busy || disabled || detail.files.length >= 20} onClick={() => input.current?.click()}>+ Thêm tài liệu</button></div><p>PDF, Word hoặc tệp chữ/code. Chọn tài liệu cần đọc trong ô chat trước khi gửi.</p><input hidden ref={input} type="file" aria-label="Thêm tài liệu dự án" accept=".pdf,.docx,.txt,.md,.csv,.json,.py,.js,.ts,.tsx,.jsx,.css,.html,.xml,.yml,.yaml,.rs,.go,.java,.c,.cpp,.h,.sql,.log" onChange={e => {const file=e.currentTarget.files?.[0];e.currentTarget.value='';if(file) void upload(file);}}/>
          <div className="project-files">{detail.files.map(file => <div className="project-file" key={file.id}><div><a href={file.url} download>{file.name}</a><span>{Math.max(1,Math.ceil(file.size/1024))} KB · {file.document?.notice || 'Chưa có nội dung đọc sẵn.'}</span></div><button aria-label={`Xóa tài liệu ${file.name}`} disabled={busy || disabled} onClick={() => setRemove(file)}>×</button></div>)}{!detail.files.length && <p className="empty-hint">Chưa có tài liệu dùng chung.</p>}</div>
          {busy && <p role="status">Đang lưu hoặc đọc tài liệu…</p>}
        </section>
      </div>
      <section className="project-conversations"><div className="project-card-head"><h2>Hội thoại</h2><button className="project-primary" disabled={disabled || busy} onClick={onNewChat}>+ Chat mới trong dự án</button></div>{chats.map(chat => <button className="project-chat-link" key={chat.id} disabled={disabled} onClick={() => onChat(chat.id)}><span>{chat.title || 'Chưa có tiêu đề'}</span><span>→</span></button>)}{!chats.length && !chatsLoading && <p className="empty-hint">Bắt đầu hội thoại đầu tiên hoặc chuyển một chat từ menu ⋯.</p>}{chatsLoading && <p role="status">Đang tải hội thoại…</p>}{more && <button disabled={chatsLoading || disabled} onClick={onMore}>Xem thêm hội thoại</button>}</section>
    </div>}
    {remove && <ProjectConfirm title="Xóa tài liệu này?" busy={busy} onClose={() => setRemove(null)} onConfirm={() => void mutate(() => deleteProjectFile(id,remove.id))}><p>“{remove.name}” sẽ không còn dùng chung trong dự án. Tin nhắn đã có vẫn được giữ.</p></ProjectConfirm>}
  </main>;
}

