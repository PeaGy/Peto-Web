import { UnauthorizedError } from '../../shared/api/api';

export interface Project { id: string; name: string; created_at: number; updated_at: number; conversation_count?: number; file_count?: number }

async function request<T>(path: string, method = 'GET', body?: object): Promise<T> {
  const response = await fetch(`/api/projects${path}`, {method, ...(body ? {headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {})});
  if (response.status === 401) throw new UnauthorizedError();
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Chưa thực hiện được thao tác dự án.');
  return value as T;
}
export const listProjects = async () => (await request<{projects:Project[]}>('')).projects;
export const createProject = (name: string) => request<Project>('', 'POST', {name});
export const updateProject = (id: string, change: {name:string}) => request(`/${id}`, 'PATCH', change);
export const deleteProject = (id: string) => request(`/${id}`, 'DELETE');
