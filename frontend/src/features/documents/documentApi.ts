import { UnauthorizedError } from '../../shared/api/api';

export interface DocumentSummary { id: string; conversation_id: string; title: string; version: number; created_at: number; format?: 'docx' | 'pdf' | 'pptx' | 'xlsx' | null; pages?: number | null }
export interface SavedDocument extends DocumentSummary {
  style?: 'report' | 'essay' | 'clean' | 'academic' | 'bold' | 'sheet' | 'workbook';
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
/** Một ô của lưới xem: chữ đã định dạng kiểu Việt Nam, kiểu giá trị (số, chữ, đúng/sai) và công thức nếu có. */
export interface SheetCell { d: string; t: 'n' | 's' | 'b'; f?: string }
export interface SheetChartData {
  type: 'column' | 'bar' | 'line' | 'pie'; title: string; row: number; col: number; width: number; height: number;
  categories: string[]; series: { name: string; values: (number | null)[]; labels: string[] }[];
  axis?: { min: number; max: number; step: number; labels: string[] };
}
export interface SheetData {
  name: string; title: string; columns: { header: string; width: number; wrap: boolean }[];
  rows: (SheetCell | null)[][]; total: (SheetCell | null)[] | null; formulas: number; charts: SheetChartData[];
}
export interface TableGrid { kind?: undefined; title: string; sheets: SheetData[] }

/** Một ô của tệp người dùng Peto đã sửa: chữ đã định dạng, kiểu (số, chữ, đúng/sai, lỗi), công thức, số thứ tự kiểu ô;
 * p là công thức chưa có kết quả (Excel tính khi mở tệp). */
export interface WorkbookCell { d?: string; t?: 'n' | 's' | 'b' | 'e'; f?: string; s?: number; p?: 1 }
/** Kiểu ô rút gọn: đậm, nghiêng, gạch chân, gạch ngang, màu chữ, màu nền, cỡ chữ (pt), căn ngang/dọc, xuống dòng, thụt
 * lề, viền từng cạnh (như "1px solid #000000"). */
export interface WorkbookStyle {
  b?: 1; i?: 1; u?: 1; x?: 1; c?: string; f?: string; z?: number; h?: string; v?: string; w?: 1; in?: number;
  bd?: Partial<Record<'l' | 'r' | 't' | 'b', string>>;
}
export interface WorkbookSheet {
  name: string; kind: 'workbook'; hidden: boolean; cols: { width: number; hidden?: boolean }[]; heights: Record<string, number>;
  hiddenRows: number[]; rowHeight: number; cells: [number, number, WorkbookCell][]; merges: number[][]; freeze: [number, number];
  changed: number[][]; charts: SheetChartData[]; formulas: number; used: [number, number]; truncated: boolean;
}
/** Một dòng thay đổi: trang, vùng (A9:F9, 9:10 là cả hàng, G:H là cả cột, rỗng là cả trang) và chữ. */
export interface WorkbookChange { sheet: string; where: string; text: string }
export interface WorkbookGrid { kind: 'workbook'; title: string; styles: WorkbookStyle[]; sheets: WorkbookSheet[]; changes: WorkbookChange[] }
export type SheetGrid = TableGrid | WorkbookGrid;
/** Lưới bảng tính: bảng Peto tạo (tính lại từ bảng đã lưu) hoặc tệp người dùng Peto đã sửa (đọc từ tệp). Không lưu đệm
 * giữa các tài khoản. */
export const getSheet = (id: string, version: number, signal?: AbortSignal) => json<SheetGrid>(`/api/documents/${encodeURIComponent(id)}/sheet?version=${version}`, { signal });
export const deleteDocument = (id: string) => json(`/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' });
export async function downloadDocument(document: SavedDocument, format: 'docx' | 'pdf') {
  const response = await checked(await fetch(`/api/documents/${encodeURIComponent(document.id)}/export/${format}?version=${document.version}`));
  return response.blob();
}

/** Ghi chú cho người thuyết trình của từng slide, đọc từ bài thuyết trình đã lưu (JSON của create_presentation). */
export function slideNotes(document: SavedDocument): string[] {
  if (document.format !== 'pptx') return [];
  try {
    const deck = JSON.parse(document.content) as { slides?: { notes?: unknown }[] };
    return (deck.slides ?? []).map(slide => typeof slide.notes === 'string' ? slide.notes : '');
  } catch {
    return [];
  }
}

export function draftTitle(content: string) {
  return (content.split('\n').find(line => line.trim()) || 'Tài liệu Peto').replace(/^\s*#{1,6}\s+/, '').replace(/[*_`]/g, '').trim().slice(0, 120) || 'Tài liệu Peto';
}
