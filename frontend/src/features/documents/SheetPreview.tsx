import { useEffect, useState } from 'react';
import { UnauthorizedError } from '../../shared/api/api';
import { getSheet, type SheetCell, type SheetData, type SheetGrid } from './documentApi';

export function SheetIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3.5" y="4" width="17" height="16" rx="2.5" stroke="currentColor" strokeWidth="1.6" /><path d="M3.5 9.5h17M3.5 14.8h17M9.2 4v16" stroke="currentColor" strokeWidth="1.6" /></svg>;
}

/** Chữ cái của cột thứ ``index`` (0 là A), như Excel. */
export function columnLetter(index: number) {
  let letters = '';
  for (let value = index + 1; value > 0; value = Math.floor((value - 1) / 26)) letters = String.fromCharCode(65 + (value - 1) % 26) + letters;
  return letters;
}

/** Tải số liệu bảng tính cho thẻ và lưới xem; bỏ kết quả đến muộn khi đã đổi sang phiên bản khác. */
export function useSheet(id: string, version: number, onUnauthorized?: () => void) {
  const [grid, setGrid] = useState<SheetGrid | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setGrid(null); setError('');
    getSheet(id, version, controller.signal).then(value => { if (!controller.signal.aborted) setGrid(value); }).catch(reason => {
      if (controller.signal.aborted) return;
      if (reason instanceof UnauthorizedError) onUnauthorized?.();
      setError(reason instanceof Error && !(reason instanceof UnauthorizedError) ? reason.message : 'Chưa mở được bảng tính.');
    });
    return () => controller.abort();
  }, [id, version, retry, onUnauthorized]);
  return { grid, error, retry: () => setRetry(value => value + 1) };
}

const alignOf = (cell: SheetCell | null | undefined) => cell?.t === 'n' ? 'n' : cell?.t === 'b' ? 'c' : '';

/** Thẻ trong chat: vài hàng đầu của trang tính đầu tiên, nền sáng như tệp Excel. */
export function SheetPreview({ sheet }: { sheet: SheetData }) {
  const rows = sheet.rows.slice(0, 7);
  return <table className="sheet-mini" aria-hidden="true">
    <colgroup><col style={{ width: 34 }} />{sheet.columns.map((column, index) => <col key={index} style={{ width: column.width }} />)}</colgroup>
    <thead><tr><th />{sheet.columns.map((_, index) => <th key={index}>{columnLetter(index)}</th>)}</tr></thead>
    <tbody>
      <tr className="head"><th>1</th>{sheet.columns.map((column, index) => <td key={index}>{column.header}</td>)}</tr>
      {rows.map((row, r) => <tr key={r} className={r % 2 ? 'band' : undefined}><th>{r + 2}</th>
        {row.map((cell, c) => <td key={c} className={alignOf(cell)}>{cell?.d}</td>)}</tr>)}
    </tbody>
  </table>;
}
