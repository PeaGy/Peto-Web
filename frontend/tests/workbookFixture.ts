import type { DocumentArtifact } from '../src/shared/api/api';
import type { WorkbookGrid } from '../src/features/documents/documentApi';

/** Bảng lương người dùng gửi mà Peto đã sửa, như backend trả (/api/documents/{id}/sheet, kind 'workbook'). */
export const workbookGrid: WorkbookGrid = {
  kind: 'workbook', title: 'Bảng lương tháng 9',
  styles: [
    { b: 1, z: 14, c: '#1F4E78', h: 'center' },
    { b: 1, f: '#DDEBF7', h: 'center', bd: { l: '1px solid #000000', r: '1px solid #000000', t: '1px solid #000000', b: '1px solid #000000' } },
    { bd: { b: '1px solid #000000' } },
    { f: '#FFF2CC' },
  ],
  changes: [
    { sheet: 'Lương T9', where: '4:4', text: 'chèn 1 hàng trống (theo định dạng hàng 3)' },
    { sheet: 'Lương T9', where: '5:5', text: '2 công thức tổng nới ra để tính cả hàng mới' },
    { sheet: 'Lương T9', where: 'A4:C4', text: 'ghi 3 ô, 1 công thức' },
    { sheet: 'Lương T9', where: 'D2', text: '(trống) → "Thưởng"' },
    { sheet: 'Lương T9', where: 'B3', text: 'nền #FFF2CC' },
    { sheet: 'Ghi chú', where: 'A2', text: '(trống) → "Đã thêm Tùng"' },
  ],
  sheets: [
    {
      name: 'Lương T9', kind: 'workbook', hidden: false, cols: [{ width: 48 }, { width: 160 }, { width: 120 }, { width: 110 }],
      heights: { 0: 37 }, hiddenRows: [], rowHeight: 20, merges: [[0, 0, 0, 3]], freeze: [2, 0], formulas: 4,
      cells: [
        [0, 0, { d: 'BẢNG LƯƠNG THÁNG 9', t: 's', s: 0 }],
        [1, 0, { d: 'Họ và tên', t: 's', s: 1 }], [1, 1, { d: 'Lương', t: 's', s: 1 }], [1, 2, { d: 'Thực lĩnh', t: 's', s: 1 }],
        [1, 3, { d: 'Thưởng', t: 's', s: 1 }],
        [2, 0, { d: 'Lê Thu Hà', t: 's', s: 3 }], [2, 1, { d: '10.800.000 ₫', t: 'n', s: 2 }], [2, 2, { d: '11.600.000 ₫', t: 'n', f: '=B3+800000' }],
        [2, 3, { f: '=_xlfn.XLOOKUP(A3,A:A,B:B)', p: 1 }],
        [3, 0, { d: 'Đỗ Thanh Tùng', t: 's' }], [3, 1, { d: '11.500.000 ₫', t: 'n', s: 2 }], [3, 2, { d: '12.300.000 ₫', t: 'n', f: '=B4+800000' }],
        [4, 0, { d: 'Tổng cộng', t: 's' }], [4, 1, { d: '22.300.000 ₫', t: 'n', f: '=SUM(B3:B4)' }],
      ],
      changed: [[1, 3, 1, 3], [2, 0, 2, 0], [3, 0, 3, 2]], charts: [], used: [5, 4], truncated: false,
    },
    {
      name: 'Ghi chú', kind: 'workbook', hidden: false, cols: [{ width: 200 }], heights: {}, hiddenRows: [], rowHeight: 20, merges: [],
      freeze: [0, 0], formulas: 0, cells: [[0, 0, { d: 'Lập ngày 30/09/2026', t: 's' }], [1, 0, { d: 'Đã thêm Tùng', t: 's' }]],
      changed: [[1, 0, 1, 0]], charts: [], used: [2, 1], truncated: false,
    },
  ],
};

export const workbookArtifact: DocumentArtifact = {
  id: 'W1', title: 'Bảng lương', filename: 'Bảng lương.xlsx', format: 'xlsx', style: 'workbook', pages: 2, version: 2,
  changes: ["'Lương T9'!4:4: chèn 1 hàng trống (theo định dạng hàng 3)", "'Lương T9'!5:5: 2 công thức tổng nới ra để tính cả hàng mới",
    "'Lương T9'!A4:C4: ghi 3 ô, 1 công thức", "'Lương T9'!D2: (trống) → \"Thưởng\"", "'Lương T9'!B3: nền #FFF2CC",
    "'Ghi chú'!A2: (trống) → \"Đã thêm Tùng\""],
};
