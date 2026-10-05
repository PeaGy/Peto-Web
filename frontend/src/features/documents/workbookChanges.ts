import type { WorkbookChange } from './documentApi';

// Dòng thay đổi máy chủ ghi cho bản Excel đã sửa: 'Trang'!vùng: chữ. Vùng là ô (A9:F9), cả hàng (9:10) hoặc cả cột
// (G:H); không có vùng là thay đổi của cả trang (thêm, đổi tên trang).
const LINE = /^'((?:[^']|'')+)'(?:!([A-Z]{1,3}\d+(?::[A-Z]{1,3}\d+)?|\d+:\d+|[A-Z]{1,3}:[A-Z]{1,3}))?: (.+)$/;
const CELL = /^([A-Z]{1,3})(\d+)$/;

export function parseChange(line: string): WorkbookChange {
  const match = LINE.exec(line.trim());
  if (!match) return { sheet: '', where: '', text: line.trim() };
  return { sheet: match[1].replace(/''/g, "'"), where: match[2] ?? '', text: match[3] };
}

const column = (letters: string) => letters.split('').reduce((sum, char) => sum * 26 + char.charCodeAt(0) - 64, 0) - 1;

/** Nhãn ngắn của vùng: "A9:F9", "Hàng 9", "Hàng 9–10", "Cột G", "Cột G–H"; cả trang thì "Trang". */
export function changeLabel(where: string): string {
  if (!where) return 'Trang';
  const rows = /^(\d+):(\d+)$/.exec(where);
  if (rows) return rows[1] === rows[2] ? `Hàng ${rows[1]}` : `Hàng ${rows[1]}–${rows[2]}`;
  const cols = /^([A-Z]+):([A-Z]+)$/.exec(where);
  if (cols) return cols[1] === cols[2] ? `Cột ${cols[1]}` : `Cột ${cols[1]}–${cols[2]}`;
  return where;
}

/** Vùng [hàng đầu, cột đầu, hàng cuối, cột cuối] (tính từ 0) của một thay đổi; cả hàng/cả cột thì cắt theo vùng có dữ
 * liệu ``used`` (số hàng, số cột). Thay đổi của cả trang không có vùng. */
export function changeArea(where: string, used: [number, number]): number[] | null {
  const lastRow = Math.max(0, used[0] - 1);
  const lastCol = Math.max(0, used[1] - 1);
  const rows = /^(\d+):(\d+)$/.exec(where);
  if (rows) return [Number(rows[1]) - 1, 0, Number(rows[2]) - 1, lastCol];
  const cols = /^([A-Z]+):([A-Z]+)$/.exec(where);
  if (cols) return [0, column(cols[1]), lastRow, column(cols[2])];
  const [first, last = first] = where.split(':');
  const start = CELL.exec(first ?? '');
  const end = CELL.exec(last ?? '');
  if (!start || !end) return null;
  return [Number(start[2]) - 1, column(start[1]), Number(end[2]) - 1, column(end[1])];
}

/** Chữ của dòng thay đổi tách quanh mã màu #RRGGBB, để hiện ô màu nhỏ thay cho mã. */
export function colorParts(text: string): { text: string; color?: string }[] {
  return text.split(/(#[0-9A-Fa-f]{6})/).filter(Boolean).map(part => /^#[0-9A-Fa-f]{6}$/.test(part) ? { text: part, color: part } : { text: part });
}
