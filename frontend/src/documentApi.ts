import { UnauthorizedError } from './api';

export interface DocumentSummary { id: string; conversation_id: string; title: string; version: number; created_at: number; format?: 'docx' | 'pdf' | null; pages?: number | null }
export interface SavedDocument extends DocumentSummary {
  style?: 'report' | 'essay';
  content: string;
  versions: { version: number; title: string; created_at: number }[];
}
export interface DocumentDraftRequest { conversationId: string; content: string; key: number }

async function checked(response: Response) {
  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(typeof error?.detail === 'string' ? error.detail : 'Chưa xử lý được tài liệu. Bạn thử lại nhé.');
  }
  return response;
}
async function json<T>(url: string, init?: RequestInit): Promise<T> {
  return (await checked(await fetch(url, init))).json();
}
export const listDocuments = (id: string, signal?: AbortSignal) => json<{ documents: DocumentSummary[] }>(`/api/documents?conversation_id=${encodeURIComponent(id)}`, { signal });
export const getDocument = (id: string, version?: number, signal?: AbortSignal) => json<SavedDocument>(`/api/documents/${encodeURIComponent(id)}${version ? `?version=${version}` : ''}`, { signal });
export const saveDocument = (draft: { title: string; content: string }, conversationId: string, previous: SavedDocument | null) => json<SavedDocument>(
  previous ? `/api/documents/${encodeURIComponent(previous.id)}/versions` : '/api/documents',
  { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...draft, style: previous?.style || 'report', ...(previous ? { base_version: previous.versions[0].version } : { conversation_id: conversationId }) }) },
);
export const deleteDocument = (id: string) => json(`/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' });
export async function downloadDocument(document: SavedDocument, format: 'docx' | 'pdf') {
  const response = await checked(await fetch(`/api/documents/${encodeURIComponent(document.id)}/export/${format}?version=${document.version}`));
  return response.blob();
}

export function draftTitle(content: string) {
  return (content.split('\n').find(line => line.trim()) || 'Tài liệu Peto').replace(/^\s*#{1,6}\s+/, '').replace(/[*_`]/g, '').trim().slice(0, 120) || 'Tài liệu Peto';
}
