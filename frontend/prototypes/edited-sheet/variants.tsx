import { useEffect, useMemo, useRef, useState } from 'react';
import { DownloadIcon, ExpandIcon } from '../../src/features/documents/DocumentArtifactCard';
import { SheetIcon, columnLetter } from '../../src/features/documents/SheetPreview';
import WorkbookGrid, { changedCount, inChanged, type Position, type WorkbookGridData } from './WorkbookGrid';

export interface Fixture { grid: WorkbookGridData; lines: string[]; results: string[]; notes: string[]; filename: string; version: number }
export interface Variant { name: string; Card: (props: { fixture: Fixture; onOpen: () => void }) => JSX.Element; Panel: (props: { fixture: Fixture }) => JSX.Element }

const address = (position: Position) => `${columnLetter(position.c)}${position.r + 1}`;

function firstChanged(fixture: Fixture): Position {
  const area = fixture.grid.sheets[0].changed[0];
  return area ? { r: area[0], c: area[1] } : { r: 0, c: 0 };
}

function useCell(fixture: Fixture, sheetIndex: number, selected: Position) {
  const sheet = fixture.grid.sheets[sheetIndex];
  return useMemo(() => sheet.cells.find(([r, c]) => r === selected.r && c === selected.c)?.[2], [sheet, selected]);
}

function Toolbar({ fixture }: { fixture: Fixture }) {
  return <div className="document-panel-toolbar">
    <strong title={fixture.filename}>{fixture.filename}</strong>
    <select className="document-panel-version" aria-label="Phiên bản xem trước" defaultValue="1"><option value="1">Phiên bản 1</option></select>
    <a className="artifact-icon" href="#tai" aria-label={`Tải ${fixture.filename}`} title="Tải XLSX" onClick={event => event.preventDefault()}><DownloadIcon /></a>
  </div>;
}

function Tabs({ fixture, index, onPick, extra }: { fixture: Fixture; index: number; onPick: (index: number) => void; extra?: JSX.Element }) {
  return <div className="sheet-tabs" role="tablist" aria-label="Trang tính">
    {fixture.grid.sheets.map((sheet, number) => <button key={sheet.name} type="button" role="tab" aria-selected={number === index} className="sheet-tab" onClick={() => onPick(number)}>
      {sheet.name}{sheet.changed.length > 0 && <small> · đã sửa</small>}
    </button>)}
    {extra}
  </div>;
}

// ---------- 1. Như Excel: giấy trắng như Excel, ô đã sửa có khung và góc xanh, thanh công thức đi qua từng ô đã sửa ----------

function PaperCard({ fixture, onOpen }: { fixture: Fixture; onOpen: () => void }) {
  const sheet = fixture.grid.sheets[0];
  const count = changedCount(sheet.changed);
  return <section className="document-artifact sheet edited" aria-label={`Bảng tính ${fixture.filename}`}>
    <header className="artifact-heading">
      <SheetIcon /><button type="button" className="artifact-name" onClick={onOpen}>{fixture.filename}</button>
      <span className="wb-badge">Bản sửa</span>
      <a className="artifact-icon" href="#tai" aria-label="Tải" onClick={event => event.preventDefault()}><DownloadIcon /></a>
      <button type="button" className="artifact-icon" aria-label="Mở rộng" onClick={onOpen}><ExpandIcon /></button>
    </header>
    <div className="artifact-preview-crop wb-mini-crop">
      <WorkbookGrid sheet={sheet} styles={fixture.grid.styles} paper changes="mark" rowsShown={11} colsShown={8} compact />
      <button type="button" className="artifact-open-overlay" onClick={onOpen}>Xem bảng tính <span>· {count} ô đã sửa</span><ExpandIcon /></button>
    </div>
    <footer className="artifact-caption"><span>XLSX · giữ nguyên định dạng gốc · {count} ô đã sửa</span></footer>
  </section>;
}

function PaperPanel({ fixture }: { fixture: Fixture }) {
  const [index, setIndex] = useState(0);
  const sheet = fixture.grid.sheets[index];
  const [selected, setSelected] = useState<Position>(firstChanged(fixture));
  const [formulas, setFormulas] = useState(false);
  const cell = useCell(fixture, index, selected);
  const stops = useMemo(() => sheet.changed.map(([r, c]) => ({ r, c })), [sheet]);
  const at = sheet.changed.findIndex(area => inChanged([area], selected.r, selected.c));
  const wrap = useRef<HTMLDivElement>(null);
  const jump = (step: number) => {
    const count = stops.length;
    if (!count) return;
    const next = stops[at < 0 ? (step > 0 ? 0 : count - 1) : (at + step + count) % count];
    setSelected(next);
    requestAnimationFrame(() => wrap.current?.querySelector(`[data-cell="${next.r}:${next.c}"]`)?.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
  };
  const changed = inChanged(sheet.changed, selected.r, selected.c);
  return <div className="sheet-view wb-view paper-view">
    <div className="sheet-fx" role="group" aria-label="Thanh công thức">
      <output className="sheet-fx-name">{address(selected)}</output>
      <span className="sheet-fx-mark" aria-hidden="true">fx</span>
      <div className="sheet-fx-text">{cell?.f ?? cell?.d ?? ''}{cell?.f && <span className="sheet-fx-value">= {cell.d}</span>}{changed && <span className="wb-fx-changed">Đã sửa</span>}</div>
      {stops.length > 0 && <div className="wb-stepper" aria-label="Đi qua các ô đã sửa">
        <button type="button" aria-label="Vùng sửa trước" onClick={() => jump(-1)}>‹</button>
        <span>{changedCount(sheet.changed)} ô đã sửa</span>
        <button type="button" aria-label="Vùng sửa sau" onClick={() => jump(1)}>›</button>
      </div>}
      <button type="button" className="sheet-fx-toggle" aria-pressed={formulas} onClick={() => setFormulas(value => !value)}>Công thức</button>
    </div>
    <div className="sheet-grid-wrap wb-wrap" ref={wrap} tabIndex={0}>
      <WorkbookGrid sheet={sheet} styles={fixture.grid.styles} paper changes="mark" selected={selected} onSelect={setSelected} formulas={formulas} />
    </div>
    <Tabs fixture={fixture} index={index} onPick={setIndex} />
  </div>;
}

// ---------- 2. Nhật ký thay đổi: danh sách việc Peto đã làm đứng đầu, bấm một dòng để tới vùng đó ----------

const LINE = /^\s*'?(.+?)'?!([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?:\s*(.*)$/;
const column = (letters: string) => letters.split('').reduce((sum, char) => sum * 26 + char.charCodeAt(0) - 64, 0) - 1;

function parseLine(line: string): { label: string; detail: string; area: number[] | null } {
  const match = LINE.exec(line);
  if (match) {
    const [, , c1, r1, c2, r2, detail] = match;
    const area = [Number(r1) - 1, column(c1), Number(r2 ?? r1) - 1, column(c2 ?? c1)];
    return { label: c2 ? `${c1}${r1}:${c2}${r2}` : `${c1}${r1}`, detail, area };
  }
  const row = /hàng (\d+)/.exec(line);
  return { label: row ? `Hàng ${row[1]}` : '', detail: line.trim(), area: row ? [Number(row[1]) - 1, 0, Number(row[1]) - 1, 6] : null };
}

/** Dòng thay đổi: mã màu #RRGGBB hiện thành ô màu nhỏ thay cho mã. */
function Detail({ text }: { text: string }) {
  const parts = text.split(/(#[0-9A-Fa-f]{6})/);
  return <span>{parts.map((part, index) => index % 2 ? <i key={index} className="wb-swatch" style={{ background: part }} title={part} /> : part)}</span>;
}

function LogCard({ fixture, onOpen }: { fixture: Fixture; onOpen: () => void }) {
  const items = fixture.lines.map(parseLine);
  return <section className="document-artifact sheet edited log" aria-label={`Bảng tính ${fixture.filename}`}>
    <header className="artifact-heading">
      <SheetIcon /><button type="button" className="artifact-name" onClick={onOpen}>{fixture.filename}</button>
      <a className="artifact-icon" href="#tai" aria-label="Tải" onClick={event => event.preventDefault()}><DownloadIcon /></a>
      <button type="button" className="artifact-icon" aria-label="Mở rộng" onClick={onOpen}><ExpandIcon /></button>
    </header>
    <ol className="wb-log compact">
      {items.slice(0, 4).map((item, index) => <li key={index}><span className="wb-log-where">{item.label}</span><Detail text={item.detail} /></li>)}
    </ol>
    {items.length > 4 && <p className="wb-log-more">và {items.length - 4} thay đổi khác</p>}
    <footer className="artifact-caption"><span>XLSX · giữ nguyên định dạng gốc</span><button type="button" onClick={onOpen}>Xem bảng tính</button></footer>
  </section>;
}

function LogPanel({ fixture }: { fixture: Fixture }) {
  const [index, setIndex] = useState(0);
  const sheet = fixture.grid.sheets[index];
  const items = useMemo(() => fixture.lines.map(parseLine), [fixture]);
  const [open, setOpen] = useState(true);
  const [active, setActive] = useState<number | null>(null);
  const [selected, setSelected] = useState<Position>(firstChanged(fixture));
  const cell = useCell(fixture, index, selected);
  const wrap = useRef<HTMLDivElement>(null);
  const area = active !== null ? items[active].area : null;
  useEffect(() => {
    if (!area) return;
    wrap.current?.querySelector(`[data-cell="${area[0]}:${area[1]}"]`)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [area]);
  return <div className="sheet-view wb-view">
    <section className={`wb-log-panel${open ? ' open' : ''}`} aria-label="Thay đổi lượt này">
      <button type="button" className="wb-log-head" aria-expanded={open} onClick={() => setOpen(value => !value)}>
        <span>Peto đã sửa</span><small>{items.length} thay đổi</small><span className="wb-chevron" aria-hidden="true">⌄</span>
      </button>
      {open && <ol className="wb-log">
        {items.map((item, number) => <li key={number}>
          <button type="button" aria-pressed={active === number} onClick={() => { setActive(number); if (item.area) setSelected({ r: item.area[0], c: item.area[1] }); }}>
            <span className="wb-log-where">{item.label || '—'}</span><Detail text={item.detail} />
          </button>
        </li>)}
      </ol>}
    </section>
    <div className="sheet-fx" role="group" aria-label="Thanh công thức">
      <output className="sheet-fx-name">{address(selected)}</output>
      <span className="sheet-fx-mark" aria-hidden="true">fx</span>
      <div className="sheet-fx-text">{cell?.f ?? cell?.d ?? ''}{cell?.f && <span className="sheet-fx-value">= {cell.d}</span>}</div>
    </div>
    <div className="sheet-grid-wrap wb-wrap" ref={wrap} tabIndex={0}>
      <WorkbookGrid sheet={sheet} styles={fixture.grid.styles} paper={false} changes="soft" selected={selected} onSelect={setSelected} area={area} />
    </div>
    <Tabs fixture={fixture} index={index} onPick={setIndex} />
  </div>;
}

// ---------- 3. Tô nhẹ: giữ nguyên lưới hiện có, chỉ phủ màu vàng nhạt lên ô vừa sửa ----------

function TintCard({ fixture, onOpen }: { fixture: Fixture; onOpen: () => void }) {
  const sheet = fixture.grid.sheets[0];
  return <section className="document-artifact sheet edited" aria-label={`Bảng tính ${fixture.filename}`}>
    <header className="artifact-heading">
      <SheetIcon /><button type="button" className="artifact-name" onClick={onOpen}>{fixture.filename}</button>
      <a className="artifact-icon" href="#tai" aria-label="Tải" onClick={event => event.preventDefault()}><DownloadIcon /></a>
      <button type="button" className="artifact-icon" aria-label="Mở rộng" onClick={onOpen}><ExpandIcon /></button>
    </header>
    <div className="artifact-preview-crop wb-mini-crop">
      <WorkbookGrid sheet={sheet} styles={fixture.grid.styles} paper changes="tint" rowsShown={11} colsShown={8} compact />
      <button type="button" className="artifact-open-overlay" onClick={onOpen}>Xem bảng tính <span>· {fixture.grid.sheets.length} trang tính</span><ExpandIcon /></button>
    </div>
    <footer className="artifact-caption"><span>XLSX · bản Peto đã sửa · {fixture.grid.sheets.length} trang tính</span></footer>
  </section>;
}

function TintPanel({ fixture }: { fixture: Fixture }) {
  const [index, setIndex] = useState(0);
  const sheet = fixture.grid.sheets[index];
  const [selected, setSelected] = useState<Position>(firstChanged(fixture));
  const [formulas, setFormulas] = useState(false);
  const cell = useCell(fixture, index, selected);
  return <div className="sheet-view wb-view">
    <div className="sheet-fx" role="group" aria-label="Thanh công thức">
      <output className="sheet-fx-name">{address(selected)}</output>
      <span className="sheet-fx-mark" aria-hidden="true">fx</span>
      <div className="sheet-fx-text">{cell?.f ?? cell?.d ?? ''}{cell?.f && <span className="sheet-fx-value">= {cell.d}</span>}</div>
      <button type="button" className="sheet-fx-toggle" aria-pressed={formulas} onClick={() => setFormulas(value => !value)}>Công thức</button>
    </div>
    <div className="sheet-grid-wrap wb-wrap" tabIndex={0}>
      <WorkbookGrid sheet={sheet} styles={fixture.grid.styles} paper={false} changes="tint" selected={selected} onSelect={setSelected} formulas={formulas} />
    </div>
    <Tabs fixture={fixture} index={index} onPick={setIndex} extra={<span className="wb-legend"><i aria-hidden="true" />Ô Peto vừa sửa</span>} />
  </div>;
}

export const VARIANTS: Variant[] = [
  { name: 'Như Excel', Card: PaperCard, Panel: PaperPanel },
  { name: 'Nhật ký thay đổi', Card: LogCard, Panel: LogPanel },
  { name: 'Tô nhẹ', Card: TintCard, Panel: TintPanel },
];
