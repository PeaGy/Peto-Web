import { useCallback, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import SheetChart from '../../src/features/documents/SheetChart';
import { columnLetter } from '../../src/features/documents/SheetPreview';
import type { SheetChartData } from '../../src/features/documents/documentApi';

export interface WorkbookCell { d?: string; t?: 'n' | 's' | 'b' | 'e'; f?: string; s?: number; p?: 1 }
export interface WorkbookStyle { b?: 1; i?: 1; u?: 1; x?: 1; c?: string; f?: string; z?: number; h?: string; v?: string; w?: 1; in?: number; bd?: Record<'l' | 'r' | 't' | 'b', string> }
export interface WorkbookSheet {
  name: string; kind: 'workbook'; hidden: boolean; cols: { width: number; hidden?: boolean }[]; heights: Record<string, number>;
  hiddenRows: number[]; rowHeight: number; cells: [number, number, WorkbookCell][]; merges: number[][]; freeze: [number, number];
  changed: number[][]; charts: SheetChartData[]; formulas: number; used: [number, number]; truncated: boolean;
}
export interface WorkbookGridData { title: string; kind: 'workbook'; styles: WorkbookStyle[]; sheets: WorkbookSheet[] }
export type Position = { r: number; c: number };

const FILLER = 64;
const luminance = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

/** Kiểu CSS của một ô theo định dạng trong tệp. Ở nền tối (app), chữ tối trên ô không tô nền đổi sang màu chữ của app. */
export function cellCss(style: WorkbookStyle | undefined, cell: WorkbookCell | undefined, paper: boolean): CSSProperties {
  const css: CSSProperties = {};
  if (cell?.t === 'n') css.textAlign = 'right';
  else if (cell?.t === 'b' || cell?.t === 'e') css.textAlign = 'center';
  if (!style) return css;
  if (style.b) css.fontWeight = 700;
  if (style.i) css.fontStyle = 'italic';
  if (style.u || style.x) css.textDecoration = [style.u ? 'underline' : '', style.x ? 'line-through' : ''].join(' ').trim();
  if (style.f) css.backgroundColor = style.f;
  if (style.c && (paper || style.f || luminance(style.c) > 0.35)) css.color = style.c;
  else if (style.f && !paper) css.color = luminance(style.f) > 0.5 ? '#1b1b1b' : '#f2f2f2';
  if (style.z) css.fontSize = `${Math.round(style.z * 4 / 3 * 10) / 10}px`;
  if (style.h) css.textAlign = style.h as CSSProperties['textAlign'];
  if (style.v) css.verticalAlign = style.v === 'center' ? 'middle' : 'top';
  if (style.w) { css.whiteSpace = 'normal'; css.lineHeight = 1.25; }
  if (style.in) css.paddingLeft = 7 + style.in * 9;
  const line = (value?: string) => value && (paper ? value : value.replace(/#000000$/, 'var(--wb-strong-line)'));
  if (style.bd?.l) css.borderLeft = line(style.bd.l);
  if (style.bd?.r) css.borderRight = line(style.bd.r);
  if (style.bd?.t) css.borderTop = line(style.bd.t);
  if (style.bd?.b) css.borderBottom = line(style.bd.b);
  return css;
}

export function inChanged(changed: number[][], r: number, c: number) {
  return changed.some(([r1, c1, r2, c2]) => r >= r1 && r <= r2 && c >= c1 && c <= c2);
}

export function changedCount(changed: number[][]) {
  return changed.reduce((sum, [r1, c1, r2, c2]) => sum + (r2 - r1 + 1) * (c2 - c1 + 1), 0);
}

/** Lưới của một trang tính người dùng: ô thưa theo hàng/cột thật, ô gộp, hàng/cột cố định, biểu đồ đè lên ô. */
export default function WorkbookGrid({ sheet, styles, paper, changes, selected, onSelect, area, formulas, rowsShown, colsShown, compact }: {
  sheet: WorkbookSheet; styles: WorkbookStyle[]; paper: boolean; changes: 'mark' | 'tint' | 'soft' | 'none';
  selected?: Position; onSelect?: (position: Position) => void; area?: number[] | null; formulas?: boolean;
  rowsShown?: number; colsShown?: number; compact?: boolean;
}) {
  const table = useRef<HTMLTableElement>(null);
  const [places, setPlaces] = useState<{ left: number; top: number }[]>([]);
  const cells = useMemo(() => new Map(sheet.cells.map(([r, c, cell]) => [`${r}:${c}`, cell])), [sheet]);
  const covered = useMemo(() => {
    const set = new Set<string>();
    for (const [r1, c1, r2, c2] of sheet.merges) for (let r = r1; r <= r2; r++) for (let c = c1; c <= c2; c++) if (r !== r1 || c !== c1) set.add(`${r}:${c}`);
    return set;
  }, [sheet]);
  const spans = useMemo(() => new Map(sheet.merges.map(([r1, c1, r2, c2]) => [`${r1}:${c1}`, [r2 - r1 + 1, c2 - c1 + 1]])), [sheet]);
  const rows = rowsShown ?? Math.max(sheet.used[0] + 6, 24, ...sheet.charts.map(chart => chart.row + 16));
  const cols = colsShown ?? Math.max(sheet.used[1] + 3, sheet.cols.length, ...sheet.charts.map(chart => chart.col + 8));
  const widths = Array.from({ length: cols }, (_, c) => sheet.cols[c]?.hidden ? 0 : sheet.cols[c]?.width ?? FILLER);
  const heights = Array.from({ length: rows }, (_, r) => sheet.hiddenRows.includes(r) ? 0 : sheet.heights[r] ?? sheet.rowHeight);
  const [frozenRows, frozenCols] = sheet.freeze;
  const head = compact ? 21 : 24;
  const gutter = compact ? 34 : 44;

  const measure = useCallback(() => {
    const element = table.current;
    if (!element) return;
    setPlaces(sheet.charts.map(chart => {
      const column = element.querySelector<HTMLElement>(`thead th[data-col="${chart.col}"]`);
      const row = element.querySelector<HTMLElement>(`tbody tr[data-row="${chart.row}"]`);
      return { left: column?.offsetLeft ?? 0, top: row?.offsetTop ?? 0 };
    }));
  }, [sheet]);
  useLayoutEffect(() => { measure(); }, [measure, formulas]);

  let stickyTop = head;
  const rowTop: number[] = [];
  for (let r = 0; r < rows; r++) { rowTop.push(stickyTop); stickyTop += heights[r]; }
  let stickyLeft = gutter;
  const colLeft: number[] = [];
  for (let c = 0; c < cols; c++) { colLeft.push(stickyLeft); stickyLeft += widths[c]; }

  return <div className={`wb-canvas${paper ? ' paper' : ''}${compact ? ' compact' : ''}`} data-changes={changes}>
    <table className="wb-grid" ref={table}>
      <colgroup><col style={{ width: gutter }} />{widths.map((width, c) => <col key={c} style={{ width }} />)}</colgroup>
      <thead><tr style={{ height: head }}><th className="wb-corner" />{widths.map((width, c) => <th key={c} data-col={c} className={selected?.c === c ? 'on' : undefined} style={width ? undefined : { padding: 0, borderRight: 0 }}>{width ? columnLetter(c) : ''}</th>)}</tr></thead>
      <tbody>{Array.from({ length: rows }, (_, r) => {
        const frozen = r < frozenRows;
        return <tr key={r} data-row={r} style={{ height: heights[r] }} className={frozen ? 'frozen' : undefined}>
          <th scope="row" className={selected?.r === r ? 'on' : undefined} style={frozen && !compact ? { top: rowTop[r], zIndex: 3 } : undefined}>{heights[r] ? r + 1 : ''}</th>
          {widths.map((_, c) => {
            const key = `${r}:${c}`;
            if (covered.has(key)) return null;
            const cell = cells.get(key);
            const span = spans.get(key);
            const style = cell?.s !== undefined ? styles[cell.s] : undefined;
            const css = cellCss(style, cell, paper);
            if (frozen && !compact) Object.assign(css, { position: 'sticky', top: rowTop[r], zIndex: c < frozenCols ? 2 : 1 });
            if (c < frozenCols && !compact) Object.assign(css, { position: 'sticky', left: colLeft[c], zIndex: frozen ? 2 : 1 });
            const changed = changes !== 'none' && inChanged(sheet.changed, r, c);
            const picked = selected && selected.r === r && selected.c === c;
            const inside = area && r >= area[0] && r <= area[2] && c >= area[1] && c <= area[3];
            const shown = formulas && cell?.f;
            const classes = [shown ? 'formula' : '', changed ? 'changed' : '', picked ? 'sel' : '', inside ? 'area' : '', cell?.p ? 'pending' : ''].filter(Boolean).join(' ');
            return <td key={c} data-cell={key} rowSpan={span?.[0]} colSpan={span?.[1]} className={classes || undefined} style={css}
              onClick={onSelect ? () => onSelect({ r, c }) : undefined} title={cell?.d && cell.d.length > 24 ? cell.d : undefined}>
              {shown ? cell.f : cell?.p ? '' : cell?.d}
            </td>;
          })}
        </tr>;
      })}</tbody>
    </table>
    {!compact && sheet.charts.map((chart, index) => <figure key={index} className="wb-chart" style={{ left: places[index]?.left ?? 0, top: places[index]?.top ?? 0, width: chart.width, height: chart.height }}>
      <SheetChart chart={chart} />
    </figure>)}
  </div>;
}
