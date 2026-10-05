import { StrictMode, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../../src/shared/styles/styles.css';
import '../../src/features/documents/documentPanel.css';
import '../../src/features/documents/sheetView.css';
import './prototype.css';
import fixture from './fixture.json';
import { SheetIcon } from '../../src/features/documents/SheetPreview';
import { VARIANTS, type Fixture } from './variants';

const data = fixture as unknown as Fixture;

function Shell({ index }: { index: number }) {
  const { Card, Panel } = VARIANTS[index];
  const [shown, setShown] = useState(() => new URLSearchParams(location.search).get('panel') === '1');
  const open = () => setShown(true);
  return <div className="proto-shell">
    <main className="proto-chat">
      <div className="proto-messages">
        <article className="bubble user"><p>Thêm Đỗ Thanh Tùng (nhân viên, lương 11.500.000, phụ cấp 800.000) vào bảng lương, thêm cột thưởng 10% lương cơ bản, và tô vàng ô của chị Hà để mình kiểm tra lại.</p>
          <div className="proto-attachment"><SheetIcon />Bảng lương tháng 9.xlsx<small>XLSX · 14 KB</small></div></article>
        <article className="bubble assistant">
          <p>Mình đã sửa thẳng trên tệp của bạn, định dạng và biểu đồ giữ nguyên:</p>
          <ul><li>Thêm hàng 9 cho <strong>Đỗ Thanh Tùng</strong>, thực lĩnh 12.300.000 ₫; hàng Tổng cộng đã tính cả hàng mới.</li>
            <li>Thêm cột <strong>Thưởng (10%)</strong>, làm tròn đến nghìn; tổng thưởng 6.950.000 ₫.</li>
            <li>Tô vàng ô B6 (Lê Thu Hà).</li></ul>
          <Card fixture={data} onOpen={open} />
        </article>
      </div>
    </main>
    <aside className={`document-panel proto-panel${shown ? ' open' : ''}`} aria-label="Tài liệu trong hội thoại">
      <header className="document-panel-head"><h2>Tài liệu</h2><span className="document-panel-count">1</span>
        <button type="button" className="artifact-icon proto-close" aria-label="Đóng bảng tài liệu" onClick={() => setShown(false)}>×</button></header>
      <div className="document-panel-toolbar">
        <strong title={data.filename}>{data.filename}</strong>
        <select className="document-panel-version" aria-label="Phiên bản xem trước" defaultValue="1"><option value="1">Phiên bản 1</option></select>
      </div>
      <div className="document-panel-body"><div className="document-panel-preview"><Panel fixture={data} />
        <p className="document-panel-note">Bản sửa giữ nguyên định dạng, công thức khác và biểu đồ của tệp gốc. Số liệu do Peto tính sẵn; Excel tính lại khi mở tệp.</p>
      </div></div>
    </aside>
  </div>;
}

function Harness() {
  const initial = Math.min(VARIANTS.length, Math.max(1, Number(new URLSearchParams(location.search).get('v')) || 1)) - 1;
  const [current, setCurrent] = useState(initial);
  const [ready, setReady] = useState(false);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const highlight = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const element = items.current[current];
    if (element && highlight.current) {
      highlight.current.style.width = `${element.offsetWidth}px`;
      highlight.current.style.transform = `translateX(${element.offsetLeft}px)`;
    }
    const url = new URL(location.href);
    url.searchParams.set('v', String(current + 1));
    history.replaceState(null, '', url);
  }, [current]);
  useEffect(() => { requestAnimationFrame(() => requestAnimationFrame(() => setReady(true))); }, []);
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable || event.metaKey || event.ctrlKey || event.altKey) return;
      const number = parseInt(event.key, 10);
      if (number >= 1 && number <= VARIANTS.length) setCurrent(number - 1);
      else if (event.key === 'ArrowRight' && target.tagName !== 'TD' && !target.closest('.wb-wrap')) setCurrent(value => (value + 1) % VARIANTS.length);
      else if (event.key === 'ArrowLeft' && !target.closest('.wb-wrap')) setCurrent(value => (value - 1 + VARIANTS.length) % VARIANTS.length);
    };
    document.addEventListener('keydown', keydown);
    return () => document.removeEventListener('keydown', keydown);
  }, []);
  return <>
    <Shell key={current} index={current} />
    <nav className="proto-picker" aria-label="Prototype variants" data-position="top" data-ready={ready ? '' : undefined}>
      <span className="proto-picker-highlight" aria-hidden="true" ref={highlight} />
      {VARIANTS.map((variant, number) => <button key={variant.name} ref={element => { items.current[number] = element; }} className="proto-picker-item"
        data-active={number === current ? '' : undefined} aria-current={number === current ? 'true' : undefined} onClick={() => setCurrent(number)}>{variant.name}</button>)}
    </nav>
  </>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><Harness /></StrictMode>);
