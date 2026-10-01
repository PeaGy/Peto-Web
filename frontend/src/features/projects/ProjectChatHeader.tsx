import { FolderIcon } from './ProjectSidebar';

export default function ProjectChatHeader({name}:{name?:string}) {
  const title=name || 'Dự án';
  return <div className="project-chat-name" title={title} aria-label={`Dự án hiện tại: ${title}`}><FolderIcon/><span>{title}</span></div>;
}
