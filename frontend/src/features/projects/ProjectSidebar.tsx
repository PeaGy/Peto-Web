import { useEffect, useState } from 'react';
import { EditIcon } from '../../shared/ui/EditIcon';
import type { Conversation } from '../../shared/api/api';
import type { Project } from './projectApi';
import type { useProjects } from './useProjects';

const SECTION_COLLAPSED_KEY = 'peto-projects-section-collapsed';

function ProjectLoading({label}:{label:string}) {
  return <div className="project-loading" role="status" aria-label={label}><span/><span/></div>;
}

export function FolderIcon({open=false}:{open?:boolean}) { return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true"><path d={open ? 'M3 17V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v2M3 20h16l3-10H6L3 20Z' : 'M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z'}/>{!open && <path d="M3 9h18"/>}</svg>; }

export default function ProjectSidebar({state, activeId, conversationId, disabled, onCreate, onNewChat, onChat, onMenu, onConversationMenu}: {
  state: ReturnType<typeof useProjects>; activeId:string|null; conversationId:string|null; disabled:boolean;
  onCreate:()=>void; onNewChat:(id:string)=>void; onChat:(id:string)=>void;
  onMenu:(item:Project, rect:DOMRect)=>void; onConversationMenu:(item:Conversation, rect:DOMRect)=>void;
}) {
  const [sectionOpen, setSectionOpen] = useState(() => {
    try {return localStorage.getItem(SECTION_COLLAPSED_KEY) !== '1';} catch {return true;}
  });
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  useEffect(() => {if (activeId) setExpanded(old=>new Set(old).add(activeId));}, [activeId]);
  function changeSection(open:boolean) {
    setSectionOpen(open);
    try {localStorage.setItem(SECTION_COLLAPSED_KEY,open ? '0' : '1');} catch { /* Vẫn đóng/mở được khi trình duyệt chặn lưu tùy chọn. */ }
  }
  function toggle(id:string) {
    const open=expanded.has(id);
    setExpanded(old=>{const next=new Set(old);if(open)next.delete(id);else next.add(id);return next;});
    if (!open) void state.ensureChats(id);
  }
  return <section className="project-sidebar" aria-label="Dự án">
    <div className="project-sidebar-label">
      <h2 className="sidebar-label"><button type="button" className="project-section-toggle" aria-expanded={sectionOpen} aria-controls="project-sidebar-content" title={sectionOpen ? 'Thu gọn mục Dự án' : 'Mở rộng mục Dự án'} onClick={()=>changeSection(!sectionOpen)}>Dự án<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true"><path d="m4 2 4 4-4 4"/></svg></button></h2>
      <button type="button" className="project-create" aria-label="Tạo dự án" title="Tạo dự án" disabled={disabled} onClick={()=>{changeSection(true);onCreate();}}>+</button>
    </div>
    <div id="project-sidebar-content" hidden={!sectionOpen}>
    {state.loading && !state.projects.length && <ProjectLoading label="Đang tải dự án"/>}
    {state.error && <button className="project-retry" onClick={() => void state.refresh()}>{state.error} Thử lại</button>}
    {!state.loading && !state.error && !state.projects.length && <p className="empty-hint">Chưa có dự án.</p>}
    {state.projects.map(item => {
      const open = expanded.has(item.id), page = state.chats[item.id];
      return <div key={item.id}>
        <div className={`project-row conv${activeId === item.id ? ' active' : ''}`}>
          <button className="project-open" title={item.name} aria-expanded={open} aria-controls={`project-chats-${item.id}`} disabled={disabled} onClick={() => toggle(item.id)}><FolderIcon open={open}/><span>{item.name}</span></button>
          <div className="conv-hover-actions">
            <button aria-label={`Tùy chọn dự án ${item.name}`} title="Tùy chọn dự án" disabled={disabled} onClick={e => onMenu(item, e.currentTarget.getBoundingClientRect())}>⋯</button>
            <button aria-label={`Chat mới trong dự án ${item.name}`} title="Chat mới trong dự án" disabled={disabled} onClick={()=>{setExpanded(old=>new Set(old).add(item.id));onNewChat(item.id);}}><EditIcon/></button>
          </div>
        </div>
        {open && <div className="project-chats" id={`project-chats-${item.id}`}>
          {page?.items.map(chat => <div className={`conv${conversationId === chat.id ? ' active' : ''}`} key={chat.id}><button className="conv-open" disabled={disabled} title={chat.title} onClick={() => onChat(chat.id)}><span className="conv-title">{chat.title || 'Chưa có tiêu đề'}</span></button><div className="conv-hover-actions"><button aria-label={`Tùy chọn ${chat.title}`} disabled={disabled} onClick={e => onConversationMenu(chat,e.currentTarget.getBoundingClientRect())}>⋯</button></div></div>)}
          {page?.error ? <button className="project-retry" onClick={() => void state.refreshChats(item.id)}>{page.error} Thử lại</button> : !page?.items.length && (page?.loading && !page.loaded || !page ? <ProjectLoading label="Đang tải hội thoại dự án"/> : <p className="empty-hint">Chưa có hội thoại.</p>)}
          {page?.more && <button className="project-retry" disabled={disabled || page.loading} onClick={() => void state.refreshChats(item.id,true)}>Xem thêm hội thoại</button>}
        </div>}
      </div>;
    })}
    </div>
  </section>;
}
