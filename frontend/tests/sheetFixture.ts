import type { SheetGrid } from '../src/features/documents/documentApi';

/** Bảng điểm hai trang tính như backend trả (/api/documents/{id}/sheet). */
export const sheetGrid: SheetGrid = {
  title: 'Bảng điểm lớp 10A1',
  sheets: [
    {
      name: 'Bảng điểm', title: 'Bảng điểm lớp 10A1', formulas: 3, charts: [],
      columns: [{ header: 'Họ và tên', width: 124, wrap: false }, { header: 'Điểm 1 tiết', width: 111, wrap: false }, { header: 'Điểm TB', width: 80, wrap: false }],
      rows: [
        [{ d: 'Nguyễn Minh Anh', t: 's' }, { d: '7,5', t: 'n' }, { d: '7,8', t: 'n', f: '=ROUND((B2*2+8)/3,1)' }],
        [{ d: 'Trần Gia Bảo', t: 's' }, { d: '8,5', t: 'n' }, { d: '8,7', t: 'n', f: '=ROUND((B3*2+9)/3,1)' }],
      ],
      total: [{ d: 'Trung bình lớp', t: 's' }, null, { d: '8,3', t: 'n', f: '=AVERAGE(C2:C3)' }],
    },
    {
      name: 'Thống kê', title: 'Thống kê', formulas: 2,
      columns: [{ header: 'Xếp loại', width: 89, wrap: false }, { header: 'Số học sinh', width: 111, wrap: false }],
      rows: [
        [{ d: 'Giỏi', t: 's' }, { d: '1', t: 'n', f: "=COUNTIF('Bảng điểm'!C2:C3,\">=8\")" }],
        [{ d: 'Khá', t: 's' }, { d: '1', t: 'n', f: "=COUNTIF('Bảng điểm'!C2:C3,\"<8\")" }],
      ],
      total: null,
      charts: [
        { type: 'column', title: 'Số học sinh theo xếp loại', row: 1, col: 3, width: 480, height: 288, categories: ['Giỏi', 'Khá'],
          series: [{ name: 'Số học sinh', values: [1, 1], labels: ['1', '1'] }], axis: { min: 0, max: 2, step: 1, labels: ['0', '1', '2'] } },
        { type: 'pie', title: 'Tỉ lệ xếp loại', row: 17, col: 3, width: 480, height: 288, categories: ['Giỏi', 'Khá'],
          series: [{ name: 'Số học sinh', values: [1, 1], labels: ['1', '1'] }] },
      ],
    },
  ],
};
