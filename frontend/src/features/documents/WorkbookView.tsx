import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import WorkbookGrid, { inArea, type Position } from './WorkbookGrid';
import { columnLetter } from './SheetPreview';
import ChangeText from './ChangeText';
import { changeArea, changeLabel } from './workbookChanges';
import type { WorkbookChange, WorkbookGrid as WorkbookGridData, WorkbookSheet } from './documentApi';

function firstChanged(sheet: WorkbookSheet): Position {
  const area = sheet.changed[0];
  return area ? { r: area[0], c: area[1] } : { r: 0, c: 0 };
}

/** Xem tệp Excel người dùng Peto đã sửa (mẫu "Nhật ký thay đổi" chủ dự án chọn ngày 5/10/2026): danh sách việc Peto đã
 * làm ở trên, bấm một dòng thì tới đúng vùng đó; dưới là thanh công thức và lưới theo đúng định dạng của tệp, ô vừa
 * sửa tô nhạt. */
export default function WorkbookView({ grid }: { grid: WorkbookGridData }) {
  const start = Math.max(0, grid.sheets.findIndex(sheet => sheet.changed.length > 0));
  const [index, setIndex] = useState(start);
  const sheet = grid.sheets[Math.min(index, grid.sheets.length - 1)];
  const [listOpen, setListOpen] = useState(true);
  const [active, setActive] = useState<number | null>(null);
  const [selected, setSelected] = useState<Position>(() => firstChanged(grid.sheets[start]));
  const [formulas, setFormulas] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  // Chỉ cuộn khi đi bằng phím hay bấm một dòng thay đổi; bấm chuột vào ô thì giữ nguyên chỗ đang xem.
  const scroll = useRef(false);
  const cells = useMemo(() => new Map(sheet.cells.map(([r, c, cell]) => [`${r}:${c}`, cell])), [sheet]);
  const current = cells.get(`${selected.r}:${selected.c}`);
  const area = active !== null && grid.changes[active]?.sheet === sheet.name ? changeArea(grid.changes[active].where, sheet.used) : null;

  useEffect(() => {
    if (!scroll.current) return;
    scroll.current = false;
    wrap.current?.querySelector(`[data-cell="${selected.r}:${selected.c}"]`)?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }, [selected, index]);

  const pick = (number: number, change: WorkbookChange) => {
    const target = grid.sheets.findIndex(item => item.name === change.sheet);
    const owner = target >= 0 ? grid.sheets[target] : sheet;
    if (target >= 0) setIndex(target);
    setActive(number);
    const found = changeArea(change.where, owner.used);
    if (found) {
      scroll.current = true;
      setSelected({ r: found[0], c: found[1] });
    }
  };
  const switchSheet = (number: number) => {
    setIndex(number);
    setActive(null);
    setSelected(firstChanged(grid.sheets[number]));
    wrap.current?.scrollTo?.(0, 0);
  };
  const move = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === '`' && event.ctrlKey) {
      event.preventDefault();
      setFormulas(value => !value);
      return;
    }
    const step = ({ ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1], Enter: [1, 0] } as Record<string, number[]>)[event.key];
    if (!step || event.altKey || event.metaKey) return;
    event.preventDefault();
    scroll.current = true;
    setSelected(position => ({ r: Math.max(0, position.r + step[0]), c: Math.max(0, position.c + step[1]) }));
  };
  const changedHere = sheet.changed.some(changed => inArea(changed, selected.r, selected.c));

  return <div className="sheet-view wb-view">
    {grid.changes.length > 0 && <section className={`wb-log-panel${listOpen ? ' open' : ''}`} aria-label="Peto đã sửa">
      <button type="button" className="wb-log-head" aria-expanded={listOpen} onClick={() => setListOpen(value => !value)}>
        <span>Peto đã sửa</span><small>{grid.changes.length} thay đổi</small>
        <svg className="wb-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      {listOpen && <ol className="wb-log">
        {grid.changes.map((change, number) => <li key={number}>
          <button type="button" aria-pressed={active === number} onClick={() => pick(number, change)}>
            <span className="wb-log-where">{changeLabel(change.where)}{grid.sheets.length > 1 && change.sheet && <small>{change.sheet}</small>}</span>
            <ChangeText text={change.text} />
          </button>
        </li>)}
      </ol>}
    </section>}
    <div className="sheet-fx" role="group" aria-label="Thanh công thức">
      <output className="sheet-fx-name" aria-label="Ô đang chọn">{columnLetter(selected.c)}{selected.r + 1}</output>
      <span className="sheet-fx-mark" aria-hidden="true">fx</span>
      <div className="sheet-fx-text" aria-live="polite" aria-label="Nội dung ô">
        {current?.f ?? current?.d ?? ''}
        {current?.f && !current.p && <span className="sheet-fx-value">= {current.d ?? ''}</span>}
        {current?.p && <span className="sheet-fx-value">Excel tính khi mở tệp</span>}
        {changedHere && <span className="wb-fx-changed">Peto vừa sửa</span>}
      </div>
      <button type="button" className="sheet-fx-toggle" aria-pressed={formulas} title="Hiện công thức trong ô (Ctrl+`)" onClick={() => setFormulas(value => !value)}>Công thức</button>
    </div>
    <div className="sheet-grid-wrap" ref={wrap} tabIndex={0} role="region" aria-label={`Lưới trang tính ${sheet.name}`} onKeyDown={move}>
      <WorkbookGrid sheet={sheet} styles={grid.styles} selected={selected} onSelect={setSelected} area={area} formulas={formulas} />
    </div>
    {sheet.truncated && <p className="wb-truncated">Lưới chỉ hiện 500 hàng và 60 cột đầu của trang này; tệp tải về đủ cả.</p>}
    <div className="sheet-tabs" role="tablist" aria-label="Trang tính">
      {grid.sheets.map((item, number) => <button key={item.name} type="button" role="tab" aria-selected={item === sheet} className="sheet-tab" onClick={() => switchSheet(number)}>
        {item.name}{item.hidden && <small> · ẩn</small>}{item.changed.length > 0 && <small> · đã sửa</small>}
      </button>)}
    </div>
  </div>;
}
