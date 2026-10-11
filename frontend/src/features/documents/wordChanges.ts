// Dòng thay đổi máy chủ ghi cho tệp Word Peto đã sửa (word_edit.ops.describe):
//   "Chèn sau Đoạn 5: 1 bảng", "Xóa Đoạn 2", "Điền Bảng 1, ô hàng 2 cột 1: 0", "Thay chữ Đoạn 1: …".
// Số Đoạn/Bảng là của tệp TRƯỚC lần sửa đó, như Peto đã đọc.

export type WordChangeKind = 'ins' | 'del' | 'fill' | 'edit';
export interface WordChange { where: string; kind: WordChangeKind; text: string }

const PATTERNS: [RegExp, WordChangeKind][] = [
  [/^Chèn sau ((?:Đoạn|Bảng) \d+): (.*)$/, 'ins'],
  [/^Xóa ((?:Đoạn|Bảng) \d+)$/, 'del'],
  [/^Điền (Bảng \d+), (.*)$/, 'fill'],
  [/^Thay chữ (Đoạn \d+): (.*)$/, 'edit'],
];

export const VERBS: Record<WordChangeKind, string> = { ins: 'Chèn', del: 'Xóa', fill: 'Điền', edit: 'Thay' };

export function parseWordChange(line: string): WordChange {
  const text = line.trim();
  for (const [pattern, kind] of PATTERNS) {
    const match = pattern.exec(text);
    if (match) return { where: match[1], kind, text: kind === 'del' ? (match[1].startsWith('Bảng') ? 'bảng' : 'đoạn') : match[2] };
  }
  return { where: '', kind: 'edit', text };
}
