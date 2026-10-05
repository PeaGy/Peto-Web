import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import SheetChart from './SheetChart';
import { columnLetter } from './SheetPreview';
import type { WorkbookCell, WorkbookSheet, WorkbookStyle } from './documentApi';

export type Position = { r: number; c: number };
const FILLER = 64;          // cột trống mặc định của Excel, điểm ảnh
const HEAD = 24;
const GUTTER = 44;

const luminance = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

/** Kiểu CSS của một ô theo định dạng trong tệp. Lưới theo nền của app: ở nền tối, chữ tối trên ô không tô màu đổi sang
 * màu chữ của app, ô có màu nền giữ màu và lấy chữ tương phản; viền đen đổi sang màu đường kẻ đậm của lưới. */
export function cellCss(style: WorkbookStyle | undefined, cell: WorkbookCell | undefined, dark: boolean): CSSProperties {
  const css: CSSProperties = {};
  if (cell?.t === 'n') css.textAlign = 'right';
  else if (cell?.t === 'b' || cell?.t === 'e') css.textAlign = 'center';
  if (!style) return css;
  if (style.b) css.fontWeight = 700;
  if (style.i) css.fontStyle = 'italic';
  if (style.u || style.x) css.textDecoration = [style.u ? 'underline' : '', style.x ? 'line-through' : ''].join(' ').trim();
  if (style.f) css.backgroundColor = style.f;
  if (style.c && (!dark || style.f || luminance(style.c) > 0.35)) css.color = style.c;
  else if (style.f) css.color = luminance(style.f) > 0.5 ? '#1b1b1b' : '#f2f2f2';
  if (style.z) css.fontSize = `${Math.round(style.z * 4 / 3 * 10) / 10}px`;
  if (style.h) css.textAlign = style.h as CSSProperties['textAlign'];
  if (style.v) css.verticalAlign = style.v === 'center' ? 'middle' : 'top';
  if (style.w) { css.whiteSpace = 'normal'; css.lineHeight = 1.25; }
  if (style.in) css.paddingLeft = 7 + style.in * 9;
  const line = (value?: string) => value && value.replace(/#000000$/, 'var(--wb-strong-line)');
  if (style.bd?.l) css.borderLeft = line(style.bd.l);
  if (style.bd?.r) css.borderRight = line(style.bd.r);
  if (style.bd?.t) css.borderTop = line(style.bd.t);
  if (style.bd?.b) css.borderBottom = line(style.bd.b);
  return css;
}

export const inArea = (area: number[], r: number, c: number) => r >= area[0] && r <= area[2] && c >= area[1] && c <= area[3];

/** Có đang ở nền tối không (data-theme của app, mặc định tối). */
function useDark() {
  const read = () => document.documentElement.dataset.theme !== 'light';
  const [dark, setDark] = useState(read);
  useEffect(() => {
    const observer = new MutationObserver(() => setDark(read()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, []);
  return dark;
}

/** Lưới một trang tính của tệp người dùng: ô thưa theo hàng/cột thật, ô gộp, hàng/cột cố định như tệp, biểu đồ đè lên ô,
 * ô Peto vừa sửa tô nhạt, vùng đang chọn trong danh sách thay đổi có khung. */
export default function WorkbookGrid({ sheet, styles, selected, onSelect, area, formulas }: {
  sheet: WorkbookSheet; styles: WorkbookStyle[]; selected: Position; onSelect: (position: Position) => void;
  area: number[] | null; formulas: boolean;
}) {
  const dark = useDark();
  const table = useRef<HTMLTableElement>(null);
  const [places, setPlaces] = useState<{ left: number; top: number }[]>([]);
  const cells = useMemo(() => new Map(sheet.cells.map(([r, c, cell]) => [`${r}:${c}`, cell])), [sheet]);
  const covered = useMemo(() => {
    const set = new Set<string>();
    for (const [r1, c1, r2, c2] of sheet.merges) for (let r = r1; r <= r2; r++) for (let c = c1; c <= c2; c++) if (r !== r1 || c !== c1) set.add(`${r}:${c}`);
    return set;
  }, [sheet]);
  const spans = useMemo(() => new Map(sheet.merges.map(([r1, c1, r2, c2]) => [`${r1}:${c1}`, [r2 - r1 + 1, c2 - c1 + 1]])), [sheet]);
  const rows = Math.max(sheet.used[0] + 6, 24, ...sheet.charts.map(chart => chart.row + 16));
  const cols = Math.max(sheet.used[1] + 3, sheet.cols.length, ...sheet.charts.map(chart => chart.col + 8));
  const widths = Array.from({ length: cols }, (_, c) => sheet.cols[c]?.hidden ? 0 : sheet.cols[c]?.width ?? FILLER);
  const hidden = useMemo(() => new Set(sheet.hiddenRows), [sheet]);
  const heights = Array.from({ length: rows }, (_, r) => hidden.has(r) ? 0 : sheet.heights[r] ?? sheet.rowHeight);
  const [frozenRows, frozenCols] = sheet.freeze;
  const rowTop: number[] = [];
  heights.reduce((top, height) => { rowTop.push(top); return top + height; }, HEAD);
  const colLeft: number[] = [];
  widths.reduce((left, width) => { colLeft.push(left); return left + width; }, GUTTER);

  // Biểu đồ nằm đè lên ô như trong Excel: đo vị trí ô neo sau khi vẽ, đo lại khi đổi cỡ.
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
  useEffect(() => {
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [measure]);

  return <div className="wb-canvas">
    <table className="wb-grid" ref={table}>
      <colgroup><col style={{ width: GUTTER }} />{widths.map((width, c) => <col key={c} style={{ width }} />)}</colgroup>
      <thead><tr style={{ height: HEAD }}><th className="wb-corner" aria-hidden="true" />{widths.map((width, c) => <th key={c} data-col={c}
        className={selected.c === c ? 'on' : undefined} style={width ? undefined : { padding: 0, borderRight: 0 }}>{width ? columnLetter(c) : ''}</th>)}</tr></thead>
      <tbody>{heights.map((height, r) => {
        const frozen = r < frozenRows;
        return <tr key={r} data-row={r} style={{ height }} className={frozen ? 'frozen' : undefined}>
          <th scope="row" className={selected.r === r ? 'on' : undefined} style={frozen ? { top: rowTop[r], zIndex: 3 } : undefined}>{height ? r + 1 : ''}</th>
          {widths.map((_, c) => {
            const key = `${r}:${c}`;
            if (covered.has(key)) return null;
            const cell = cells.get(key);
            const span = spans.get(key);
            const css = cellCss(cell?.s !== undefined ? styles[cell.s] : undefined, cell, dark);
            if (frozen) Object.assign(css, { position: 'sticky', top: rowTop[r], zIndex: c < frozenCols ? 2 : 1 });
            if (c < frozenCols) Object.assign(css, { position: 'sticky', left: colLeft[c], zIndex: frozen ? 2 : 1 });
            const shown = formulas && cell?.f;
            const classes = [shown ? 'formula' : '', sheet.changed.some(changed => inArea(changed, r, c)) ? 'changed' : '',
              selected.r === r && selected.c === c ? 'sel' : '', area && inArea(area, r, c) ? 'area' : '', cell?.p ? 'pending' : '']
              .filter(Boolean).join(' ');
            return <td key={c} data-cell={key} rowSpan={span?.[0]} colSpan={span?.[1]} className={classes || undefined} style={css}
              onClick={() => onSelect({ r, c })} title={cell?.p ? 'Excel tính khi mở tệp' : cell?.d && cell.d.length > 24 ? cell.d : undefined}>
              {shown ? cell.f : cell?.p ? '…' : cell?.d}
            </td>;
          })}
        </tr>;
      })}</tbody>
    </table>
    {sheet.charts.map((chart, index) => <figure key={index} className="wb-chart" style={{ left: places[index]?.left ?? 0, top: places[index]?.top ?? 0, width: chart.width, height: chart.height }}>
      <SheetChart chart={chart} />
    </figure>)}
  </div>;
}
