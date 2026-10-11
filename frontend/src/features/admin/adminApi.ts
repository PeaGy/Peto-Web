/** Số liệu trang Quản trị (chỉ chủ web). Server trả số đã gộp; thiếu dữ liệu là null, không phải 0. */
import { UnauthorizedError } from '../../shared/api/api';

export type AdminRange = '24h' | '7d' | '30d' | '90d';
export type AdminService = 'xai' | 'openai' | 'anthropic';
export type OutcomeKey = 'complete' | 'stopped' | 'error' | 'timeout' | 'other';

export interface AdminBucket {
  start: number;
  label: string;
  full: string;
  cost: Record<AdminService, number>;
  calls: number;
  empty: boolean;
}

export interface AdminModel {
  key: string;
  label: string;
  service: string;
  slug: string;
  surfaces: string[];
  calls: number;
  side_calls: number;
  turns: number;
  success_rate: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  first_p50_ms: number | null;
  first_p95_ms: number | null;
  input_tokens: number | null;
  cached_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  missing_usage_calls: number;
  cache_unknown_calls: number;
  cost_usd: number | null;
  unpriced_calls: number;
}

export interface AdminOverview {
  range: AdminRange;
  timezone: string;
  generated_at: number;
  data_since: number | null;
  buckets: AdminBucket[];
  bucket_unit: 'hour' | 'day';
  covered_buckets: number;
  calls: number;
  turns: number;
  success_rate: number | null;
  outcomes: { key: OutcomeKey; count: number }[];
  latency: { p50_ms: number | null; p95_ms: number | null; first_p50_ms: number | null; first_p95_ms: number | null };
  cost: {
    total_usd: number | null;
    /** null cho cả khối khi không có giá nào; null cho một dịch vụ có lượt gọi mà chưa tính được giá. */
    by_service: Record<AdminService, number | null> | null;
    rates: 'ok' | 'missing' | 'invalid';
    unpriced_models: string[];
    cache_unknown_models: string[];
    previous_total_usd: number | null;
    not_counted: string[];
  };
  previous_calls: number | null;
  models: AdminModel[];
  searches: number;
  accounts: number | null;
  dropped_events: number;
}

/** 404: tài khoản không phải chủ web (server cố ý không nói rõ hơn). */
export class AdminForbiddenError extends Error {}

export async function getAdminOverview(range: AdminRange, signal?: AbortSignal): Promise<AdminOverview> {
  const response = await fetch(`/api/admin/overview?range=${range}`, { cache: 'no-store', signal });
  if (response.status === 401) throw new UnauthorizedError();
  if (response.status === 404) throw new AdminForbiddenError('Không tìm thấy trang này.');
  if (!response.ok) {
    const value = await response.json().catch(() => ({}));
    throw new Error(typeof value.detail === 'string' ? value.detail : 'Chưa tải được số liệu. Thử lại nhé.');
  }
  return response.json() as Promise<AdminOverview>;
}
