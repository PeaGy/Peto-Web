import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react';
import SheetChart from './SheetChart';
import { columnLetter, useSheet } from './SheetPreview';
import type { SheetCell, SheetData } from './documentApi';
import './sheetView.css';

type Position = { r: number; c: number };      // r = 0 là hàng 1 của Excel (tên cột)
const FILLER_WIDTH = 64;                         // cột trống mặc định của Excel, điểm ảnh
const CHART_COLUMNS = 8;                         // số cột trống cần để thấy trọn biểu đồ 480 px

function cellAt(sheet: SheetData, r: number, c: number): SheetCell | null {
  if (r === 0) return c < sheet.columns.length ? { d: sheet.columns[c].header, t: 's' } : null;
  if (r <= sheet.rows.length) return sheet.rows[r - 1][c] ?? null;
  if (r === sheet.rows.length + 1 && sheet.total) return sheet.total[c] ?? null;
  return null;
}

function firstFormula(sheet: SheetData): Position {
  for (const [index, row] of sheet.rows.entries()) {
    const c = row.findIndex(cell => cell?.f);
    if (c >= 0) return { r: index + 1, c };
  }
  return { r: sheet.rows.length ? 1 : 0, c: 0 };
}

/** Lưới xem bảng tính kiểu Excel: thanh công thức, chữ cột, số hàng, hàng tên cột cố định, tab trang tính, biểu đồ. */
export default function SheetView({ id, version, onUnauthorized }: { id: string; version: number; onUnauthorized?: () => void }) {
  const { grid, error, retry } = useSheet(id, version, onUnauthorized);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<Position>({ r: 1, c: 0 });
  const [formulas, setFormulas] = useState(false);
  const [places, setPlaces] = useState<{ left: number; top: number }[]>([]);
  const wrap = useRef<HTMLDivElement>(null);
  const table = useRef<HTMLTableElement>(null);
  // Chỉ cuộn theo ô chọn khi đi bằng phím; lúc mở hay bấm chuột thì giữ nguyên chỗ, để cột đầu (tên) không bị khuất.
  const byKeyboard = useRef(false);
  const sheet = grid?.sheets[Math.min(index, grid.sheets.length - 1)];

  useEffect(() => { setIndex(0); }, [id, version]);
  useEffect(() => {
    if (!sheet) return;
    setSelected(firstFormula(sheet));
    wrap.current?.scrollTo?.(0, 0);
  }, [sheet]);

  const used = sheet ? 1 + sheet.rows.length + (sheet.total ? 1 : 0) : 0;
  const rows = sheet ? Math.max(used + 6, 20, ...sheet.charts.map(chart => chart.row + 16)) : 0;
  const cols = sheet ? Math.max(sheet.columns.length + 3, ...sheet.charts.map(chart => chart.col + CHART_COLUMNS)) : 0;
  const widths = sheet ? Array.from({ length: cols }, (_, c) => sheet.columns[c]?.width ?? FILLER_WIDTH) : [];

  // Biểu đồ nằm đè lên ô như trong Excel: đo vị trí ô neo sau khi vẽ, đo lại khi đổi cỡ (điện thoại có hàng cao hơn).
  const measure = useCallback(() => {
    const element = table.current;
    if (!element || !sheet) return;
    setPlaces(sheet.charts.map(chart => {
      const head = element.querySelector<HTMLElement>(`thead th[data-col="${chart.col}"]`);
      const row = element.querySelector<HTMLElement>(`tbody tr[data-row="${chart.row}"]`);
      return { left: (head?.offsetLeft ?? 0) + 10, top: (row?.offsetTop ?? 0) + 4 };
    }));
  }, [sheet]);
  useLayoutEffect(() => { measure(); }, [measure, formulas]);
  useEffect(() => {
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [measure]);
  useEffect(() => {
    if (!byKeyboard.current) return;
    byKeyboard.current = false;
    wrap.current?.querySelector(`[data-cell="${selected.r}:${selected.c}"]`)?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }, [selected]);

  if (error) return <div className="document-panel-empty" role="alert"><p>{error}</p><button type="button" onClick={retry}>Thử lại</button></div>;
  if (!grid || !sheet) return <div className="document-panel-empty" role="status">Đang mở bảng tính…</div>;

  const current = cellAt(sheet, selected.r, selected.c);
  const move = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === '`' && event.ctrlKey) {
      event.preventDefault();
      setFormulas(value => !value);
      return;
    }
    const step = ({ ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1], Enter: [1, 0] } as Record<string, number[]>)[event.key];
    if (!step || event.altKey || event.metaKey) return;
    event.preventDefault();
    byKeyboard.current = true;
    setSelected(position => ({ r: Math.min(rows - 1, Math.max(0, position.r + step[0])), c: Math.min(cols - 1, Math.max(0, position.c + step[1])) }));
  };

  return <div className="sheet-view">
    <div className="sheet-fx" role="group" aria-label="Thanh công thức">
      <output className="sheet-fx-name" aria-label="Ô đang chọn">{columnLetter(selected.c)}{selected.r + 1}</output>
      <span className="sheet-fx-mark" aria-hidden="true">fx</span>
      <div className="sheet-fx-text" aria-live="polite" aria-label="Nội dung ô">
        {current?.f ?? current?.d ?? ''}{current?.f && <span className="sheet-fx-value">= {current.d}</span>}
      </div>
      <button type="button" className="sheet-fx-toggle" aria-pressed={formulas} title="Hiện công thức trong ô (Ctrl+`)" onClick={() => setFormulas(value => !value)}>Công thức</button>
    </div>
    <div className="sheet-grid-wrap" ref={wrap} tabIndex={0} role="region" aria-label={`Lưới trang tính ${sheet.name}`} onKeyDown={move}>
      <div className="sheet-canvas">
        <table className="sheet-grid" ref={table}>
          <colgroup><col className="sheet-rownum-col" />{widths.map((width, c) => <col key={c} style={{ width }} />)}</colgroup>
          <thead><tr><th className="sheet-corner" aria-hidden="true" />{widths.map((_, c) => <th key={c} data-col={c} className={c === selected.c ? 'on' : undefined}>{columnLetter(c)}</th>)}</tr></thead>
          <tbody>{Array.from({ length: rows }, (_, r) => {
            const kind = r === 0 ? 'head' : sheet.total && r === used - 1 ? 'total' : r < used && r % 2 === 0 ? 'band' : undefined;
            return <tr key={r} data-row={r} className={kind}>
              <th scope="row" className={r === selected.r ? 'on' : undefined}>{r + 1}</th>
              {widths.map((_, c) => {
                const cell = cellAt(sheet, r, c);
                const shown = formulas && cell?.f;
                const align = r === 0 ? '' : shown ? 'formula' : cell?.t === 'n' ? 'n' : cell?.t === 'b' ? 'c' : '';
                const classes = [align, c >= sheet.columns.length ? 'out' : '', r === selected.r && c === selected.c ? 'sel' : ''].filter(Boolean).join(' ');
                return <td key={c} data-cell={`${r}:${c}`} className={classes || undefined}
                  title={cell && cell.d.length > 24 ? cell.d : undefined} onClick={() => setSelected({ r, c })}>
                  {r === 0 && cell && <span className="sheet-filter" aria-hidden="true" />}{shown ? cell.f : cell?.d}
                </td>;
              })}
            </tr>;
          })}</tbody>
        </table>
        {sheet.charts.map((chart, number) => <figure key={number} className="sheet-chart" style={{ left: places[number]?.left ?? 0, top: places[number]?.top ?? 0, width: chart.width, height: chart.height }}>
          <SheetChart chart={chart} />
        </figure>)}
      </div>
    </div>
    <div className="sheet-tabs" role="tablist" aria-label="Trang tính">
      {grid.sheets.map((item, number) => <button key={item.name} type="button" role="tab" aria-selected={item === sheet} className="sheet-tab" onClick={() => setIndex(number)}>
        {item.name}{item.charts.length > 0 && <small> · {item.charts.length} biểu đồ</small>}
      </button>)}
    </div>
  </div>;
}
