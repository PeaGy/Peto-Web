import { useCallback, useState, type Dispatch, type RefObject, type SetStateAction } from 'react';
import type { NavigateFunction } from 'react-router';
import { SettingsIcon } from '../settings/settingsUi';
import { UnauthorizedError, updateConversation, type Conversation } from '../../shared/api/api';
import { EditIcon } from '../../shared/ui/EditIcon';
import TextEditDialog from '../../shared/ui/TextEditDialog';
import ConversationMenu from '../../app/ConversationMenu';
import MoveConversationDialog from './MoveConversationDialog';
import { createProject, deleteProject, updateProject, type Project } from './projectApi';
import { ProjectConfirm } from './ProjectControls';
import type { useProjects } from './useProjects';

// Tạo, đổi tên, xóa dự án và chuyển hội thoại vào dự án. Tách khỏi App.tsx (G3.3, 13/11/2026); thân các hàm giữ nguyên.

/** Trạng thái các hộp thoại dự án; `reset` dùng khi phiên đăng nhập hết hạn. */
export function useProjectDialogs() {
  const [projectEdit, setProjectEdit] = useState<Project|'create'|null>(null);
  const [projectName, setProjectName] = useState('');
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectError, setProjectError] = useState('');
  const [projectMenu, setProjectMenu] = useState<{item:Project;left:number;top:number}|null>(null);
  const [projectDelete, setProjectDelete] = useState<Project|null>(null);
  const [moveTarget, setMoveTarget] = useState<Conversation|null>(null);
  const reset = useCallback(() => {
    setProjectEdit(null); setProjectDelete(null); setProjectMenu(null); setMoveTarget(null); setProjectError(''); setProjectBusy(false);
  }, []);
  return { projectEdit, setProjectEdit, projectName, setProjectName, projectBusy, setProjectBusy, projectError, setProjectError,
    projectMenu, setProjectMenu, projectDelete, setProjectDelete, moveTarget, setMoveTarget, reset };
}

export type ProjectActionsContext = {
  dialogs: ReturnType<typeof useProjectDialogs>;
  authVersion: RefObject<number>;
  handleUnauthorized: () => void;
  abortRef: RefObject<AbortController | null>;
  deleting: boolean;
  newConversation: (fromRoute?: boolean, projectId?: string | null) => void;
  setSidebarOpen: Dispatch<SetStateAction<boolean>>;
  refreshProjects: () => Promise<unknown>;
  refreshProjectChats: (id: string) => Promise<unknown>;
  refreshConversations: () => Promise<void>;
  removeProjectDraft: (id: string) => void;
  activeProjectId: string | null;
  setActiveProjectId: Dispatch<SetStateAction<string | null>>;
  conversationId: string | null;
  navigate: NavigateFunction;
  draftContextState: (projectId: string | null) => unknown;
  metadataBusy: boolean;
  setMetadataBusy: Dispatch<SetStateAction<boolean>>;
};

export function projectActions(ctx: ProjectActionsContext) {
  const { authVersion, handleUnauthorized, abortRef, deleting, newConversation, setSidebarOpen, refreshProjects, refreshProjectChats,
    refreshConversations, removeProjectDraft, activeProjectId, setActiveProjectId, conversationId, navigate, draftContextState,
    metadataBusy, setMetadataBusy } = ctx;
  const { projectEdit, setProjectEdit, projectName, projectBusy, setProjectBusy, setProjectError, projectDelete, setProjectDelete,
    moveTarget, setMoveTarget } = ctx.dialogs;
function newProjectChat(id:string) {
  if (abortRef.current || deleting) return;
  newConversation(false, id);setSidebarOpen(false);
  void refreshProjectChats(id);
}
async function saveProject() {
  if (!projectEdit || projectBusy) return;
  const session=authVersion.current;
  setProjectBusy(true);setProjectError('');
  try {
    if (projectName.trim().length>100) throw new Error('Tên dự án tối đa 100 ký tự.');
    if(projectEdit==='create') {const created=await createProject(projectName);if(session!==authVersion.current)return;newProjectChat(created.id);}
    else {await updateProject(projectEdit.id,{name:projectName});if(session!==authVersion.current)return;}
    setProjectEdit(null);await refreshProjects();
  } catch(err) {if(session===authVersion.current) {if(err instanceof UnauthorizedError)handleUnauthorized();else setProjectError(err instanceof Error ? err.message : 'Chưa lưu được dự án.');}}
  finally {if(session===authVersion.current)setProjectBusy(false);}
}
async function removeProject() {
  if(!projectDelete || projectBusy)return;
  const session=authVersion.current, id=projectDelete.id;
  setProjectBusy(true);setProjectError('');
  try {
    await deleteProject(id);
    if(session!==authVersion.current)return;
    removeProjectDraft(id);
    if(activeProjectId===id) {
      setActiveProjectId(null);
      if(!conversationId)navigate({pathname:window.location.pathname,search:window.location.search,hash:window.location.hash},
        {replace:true,state:draftContextState(null)});
    }
    setProjectDelete(null);await refreshConversations();
  }
  catch(err){if(session===authVersion.current){if(err instanceof UnauthorizedError)handleUnauthorized();else setProjectError(err instanceof Error ? err.message : 'Chưa xóa được dự án.');}}
  finally{if(session===authVersion.current)setProjectBusy(false);}
}
async function createProjectForMove(name:string):Promise<Project|null> {
  if (!moveTarget || metadataBusy) return null;
  const session=authVersion.current;
  setMetadataBusy(true);setProjectError('');
  try {
    const project=await createProject(name);
    if (session!==authVersion.current) return null;
    void refreshProjects();
    return project;
  } catch(err) {
    if(session===authVersion.current) {
      if(err instanceof UnauthorizedError)handleUnauthorized();
      else setProjectError(err instanceof Error ? err.message : 'Chưa tạo được dự án.');
    }
    return null;
  } finally {if(session===authVersion.current)setMetadataBusy(false);}
}
async function moveConversation(id:string|null) {
  if(!moveTarget || metadataBusy)return;
  const session=authVersion.current;
  setMetadataBusy(true);setProjectError('');
  try {await updateConversation(moveTarget.id,{project_id:id});if(session!==authVersion.current)return;if(conversationId===moveTarget.id){setActiveProjectId(id);}const old=moveTarget.project_id;setMoveTarget(null);await refreshConversations();if(old)void refreshProjectChats(old);if(id)void refreshProjectChats(id);}
  catch(err){if(session===authVersion.current){if(err instanceof UnauthorizedError)handleUnauthorized();else setProjectError(err instanceof Error ? err.message : 'Chưa chuyển được hội thoại.');}}
  finally{if(session===authVersion.current)setMetadataBusy(false);}
}
  return { newProjectChat, saveProject, removeProject, createProjectForMove, moveConversation };
}

/** Menu, hộp đổi tên, xác nhận xóa dự án và hộp chuyển hội thoại vào dự án. */
export function renderProjectDialogs(ctx: ProjectActionsContext, actions: ReturnType<typeof projectActions>, view: {
  projectState: ReturnType<typeof useProjects>;
}) {
  const { projectMenu, setProjectMenu, projectEdit, setProjectEdit, projectName, setProjectName, projectBusy, projectError, setProjectError,
    projectDelete, setProjectDelete, moveTarget, setMoveTarget } = ctx.dialogs;
  const { metadataBusy, refreshProjects } = ctx;
  const { saveProject, removeProject, createProjectForMove, moveConversation } = actions;
  const { projectState } = view;
  return <>
    {projectMenu && <ConversationMenu label="Tùy chọn dự án" left={projectMenu.left} top={projectMenu.top} onClose={()=>setProjectMenu(null)}>
      <button onClick={()=>{setProjectEdit(projectMenu.item);setProjectName(projectMenu.item.name);setProjectError('');setProjectMenu(null);}}><EditIcon/>Đổi tên dự án</button>
      <div className="popup-menu-sep" role="separator" />
      <button className="danger-button" onClick={()=>{setProjectDelete(projectMenu.item);setProjectError('');setProjectMenu(null);}}><SettingsIcon name="trash"/>Xóa dự án</button>
    </ConversationMenu>}
    {projectEdit && <><TextEditDialog title={projectEdit==='create' ? 'Tạo dự án' : 'Đổi tên dự án'} description={projectError || 'Gom hội thoại cùng một công việc.'} value={projectName} onChange={setProjectName} busy={projectBusy} onClose={()=>setProjectEdit(null)} onSave={()=>void saveProject()}/></>}
    {projectDelete && <ProjectConfirm title="Xóa dự án này?" busy={projectBusy} onClose={()=>setProjectDelete(null)} onConfirm={()=>void removeProject()}><p>“{projectDelete.name}” cùng hướng dẫn và tài liệu chung sẽ bị xóa. Các hội thoại được giữ và trở về Gần đây.</p>{projectError && <p role="alert">{projectError}</p>}</ProjectConfirm>}
    {moveTarget && <MoveConversationDialog item={moveTarget} projects={projectState.projects} busy={metadataBusy} error={projectError} loading={projectState.loading} loadError={projectState.error} onRetry={()=>void refreshProjects()} onCreate={createProjectForMove} onClose={()=>setMoveTarget(null)} onSave={id=>void moveConversation(id)}/>}
  </>;
}
