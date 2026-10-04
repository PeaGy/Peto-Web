import { UnauthorizedError } from '../../shared/api/api';

export interface Connector {
  id: 'github'; name: string; configured: boolean;
  status: 'connected' | 'not_connected' | 'reconnect'; login: string | null;
  updated_at: number | null; install_url: string | null;
}

async function request<T>(path: string, method = 'GET', signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/connectors${path}`, { method, signal });
  if (response.status === 401) throw new UnauthorizedError();
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Chưa xử lý được kết nối. Hãy thử lại.');
  return body as T;
}

export const listConnectors = (signal?: AbortSignal) => request<{ connectors: Connector[] }>('', 'GET', signal);
export const connectGitHub = (signal?: AbortSignal) => request<{ authorize_url: string }>('/github/connect', 'POST', signal);
export const checkGitHub = (signal?: AbortSignal) => request<Connector>('/github/check', 'POST', signal);
export const disconnectGitHub = (signal?: AbortSignal) => request<{ disconnected: boolean }>('/github', 'DELETE', signal);

/** Chỉ nhận kết quả hiển thị, không nhận khóa hay mã OAuth từ địa chỉ trang. */
export function takeConnectorResult(): string | null {
  const url = new URL(window.location.href);
  const result = url.searchParams.get('connector_result');
  if (!result) return null;
  url.searchParams.delete('connector_result');
  window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash);
  return ['connected', 'cancelled', 'invalid', 'failed'].includes(result) ? result : 'failed';
}
