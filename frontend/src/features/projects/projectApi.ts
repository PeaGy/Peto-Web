import { UnauthorizedError, type ChatAttachment, type OutgoingAttachment } from '../../shared/api/api';

export interface Project { id: string; name: string; created_at: number; updated_at: number; conversation_count?: number; file_count?: number }
export interface ProjectFile { id: string; name: string; mime: string; size: number; url: string; document: ChatAttachment['document'] }
export interface ProjectDetail extends Project { instructions: string; files: ProjectFile[] }

async function request<T>(path: string, method = 'GET', body?: object, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/projects${path}`, {method, signal, ...(body ? {headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {})});
  if (response.status === 401) throw new UnauthorizedError();
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Chưa thực hiện được thao tác dự án.');
  return value as T;
}
export const listProjects = async () => (await request<{projects:Project[]}>('')).projects;
export const createProject = (name: string) => request<Project>('', 'POST', {name});
export const getProject = (id: string, signal?: AbortSignal) => request<ProjectDetail>(`/${id}`, 'GET', undefined, signal);
export const updateProject = (id: string, change: {name?:string; instructions?:string}) => request(`/${id}`, 'PATCH', change);
export const deleteProject = (id: string) => request(`/${id}`, 'DELETE');
export const uploadProjectFile = (id: string, file: OutgoingAttachment) => request(`/${id}/files`, 'POST', file);
export const deleteProjectFile = (id: string, fileId: string) => request(`/${id}/files/${fileId}`, 'DELETE');
