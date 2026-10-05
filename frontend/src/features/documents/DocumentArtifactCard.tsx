import { useState } from 'react';
import type { DocumentArtifact } from '../../shared/api/api';
import { DocumentIcon } from './DocumentWorkspace';
import ChangeText from './ChangeText';
import { SheetIcon, SheetPreview, useSheet } from './SheetPreview';
import { changeLabel, parseChange } from './workbookChanges';

export function DownloadIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
export function ExpandIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export function SlidesIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2" stroke="currentColor" strokeWidth="1.6" /><path d="M12 16v4M8.5 20h7M7.5 9h6M7.5 12h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>;
}

export function PageImage({ src, page, title }: { src: string; page: number; title: string }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [retry, setRetry] = useState(0);
  return <div className="artifact-page">
    {!loaded && !failed && <div className="artifact-page-loading" role="status">Đang mở trang…</div>}
    {failed ? <div className="artifact-page-error" role="alert"><p>Chưa mở được bản xem trước. Tệp có thể đã bị xóa hoặc phiên đăng nhập đã hết hạn.</p><button type="button" onClick={event => { event.stopPropagation(); setFailed(false); setRetry(value => value + 1); }}>Thử lại</button></div> :
      <img src={`${src}&retry=${retry}`} alt={`${title} — trang ${page}`} loading="lazy" onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />}
  </div>;
}

/** Bảng tính: lưới thu nhỏ dựng từ số liệu máy chủ tính sẵn (không có ảnh xem trước), tải XLSX. */
function SheetArtifactCard({ artifact, onOpen }: { artifact: DocumentArtifact; onOpen: (artifact: DocumentArtifact) => void }) {
  const { grid: loaded, error, retry } = useSheet(artifact.id, artifact.version);
  const grid = loaded && loaded.kind !== 'workbook' ? loaded : null;
  const download = `/api/documents/${encodeURIComponent(artifact.id)}/export/xlsx?version=${artifact.version}`;
  const formulas = grid?.sheets.reduce((sum, sheet) => sum + sheet.formulas, 0) ?? 0;
  const charts = grid?.sheets.reduce((sum, sheet) => sum + sheet.charts.length, 0) ?? 0;
  return <section className="document-artifact sheet" aria-label={`Bảng tính ${artifact.filename}`}>
    <header className="artifact-heading">
      <SheetIcon /><button type="button" className="artifact-name" onClick={() => onOpen(artifact)} title={artifact.filename}>{artifact.filename}</button>
      <a className="artifact-icon" href={download} download={artifact.filename} aria-label={`Tải ${artifact.filename}`} title="Tải XLSX"><DownloadIcon /></a>
      <button type="button" className="artifact-icon" aria-label={`Mở rộng ${artifact.filename}`} title="Mở trong bảng tài liệu" onClick={() => onOpen(artifact)}><ExpandIcon /></button>
    </header>
    <div className="artifact-preview-crop">
      {error ? <div className="artifact-page-error" role="alert"><p>Chưa mở được bản xem trước. Tệp có thể đã bị xóa hoặc phiên đăng nhập đã hết hạn.</p><button type="button" onClick={retry}>Thử lại</button></div>
        : grid?.sheets[0] ? <SheetPreview sheet={grid.sheets[0]} /> : <div className="artifact-page-loading" role="status">Đang mở bảng tính…</div>}
      <button type="button" className="artifact-open-overlay" onClick={() => onOpen(artifact)}>Xem bảng tính <span>· {artifact.pages} trang tính</span><ExpandIcon /></button>
    </div>
    <footer className="artifact-caption"><span>XLSX · {artifact.pages} trang tính{grid ? ` · ${formulas} công thức${charts ? ` · ${charts} biểu đồ` : ''}` : ''}</span></footer>
  </section>;
}

const SHOWN_CHANGES = 4;

/** Tệp Excel người dùng Peto đã sửa (mẫu "Nhật ký thay đổi"): danh sách việc Peto đã làm thay cho lưới thu nhỏ, có sẵn
 * trong thẻ nên không phải tải lưới. */
function WorkbookArtifactCard({ artifact, onOpen }: { artifact: DocumentArtifact; onOpen: (artifact: DocumentArtifact) => void }) {
  const download = `/api/documents/${encodeURIComponent(artifact.id)}/export/xlsx?version=${artifact.version}`;
  const changes = (artifact.changes ?? []).map(parseChange);
  return <section className="document-artifact sheet workbook" aria-label={`Bảng tính ${artifact.filename}`}>
    <header className="artifact-heading">
      <SheetIcon /><button type="button" className="artifact-name" onClick={() => onOpen(artifact)} title={artifact.filename}>{artifact.filename}</button>
      <a className="artifact-icon" href={download} download={artifact.filename} aria-label={`Tải ${artifact.filename}`} title="Tải tệp đã sửa"><DownloadIcon /></a>
      <button type="button" className="artifact-icon" aria-label={`Mở rộng ${artifact.filename}`} title="Mở trong bảng tài liệu" onClick={() => onOpen(artifact)}><ExpandIcon /></button>
    </header>
    {changes.length > 0 ? <ol className="wb-card-log" aria-label="Peto đã sửa">
      {changes.slice(0, SHOWN_CHANGES).map((change, index) => <li key={index}><span className="wb-log-where">{changeLabel(change.where)}</span><ChangeText text={change.text} /></li>)}
    </ol> : <p className="wb-card-empty">Bản Peto đã sửa của tệp bạn gửi.</p>}
    {changes.length > SHOWN_CHANGES && <p className="wb-card-more">và {changes.length - SHOWN_CHANGES} thay đổi khác</p>}
    <footer className="artifact-caption"><span>{artifact.filename.toLowerCase().endsWith('.xlsm') ? 'XLSM' : 'XLSX'} · giữ nguyên định dạng gốc{artifact.version > 1 ? ` · phiên bản ${artifact.version}` : ''}</span>
      <button type="button" onClick={() => onOpen(artifact)}>Xem bảng tính</button></footer>
  </section>;
}

export default function DocumentArtifactCard({ artifact, onEdit, onOpen }: { artifact: DocumentArtifact; onEdit: (artifact: DocumentArtifact) => void; onOpen: (artifact: DocumentArtifact) => void }) {
  if (artifact.format === 'xlsx') return artifact.style === 'workbook'
    ? <WorkbookArtifactCard artifact={artifact} onOpen={onOpen} /> : <SheetArtifactCard artifact={artifact} onOpen={onOpen} />;
  const base = `/api/documents/${encodeURIComponent(artifact.id)}`;
  const download = `${base}/export/${artifact.format}?version=${artifact.version}`;
  const preview = (number: number) => `${base}/preview?version=${artifact.version}&page=${number}`;
  // Bài thuyết trình: hiện trọn slide đầu, tải PPTX hoặc PDF, chưa sửa tay được (nhờ Peto sửa trong chat).
  const slides = artifact.format === 'pptx';
  const pdfName = artifact.filename.replace(/\.pptx$/i, '.pdf');
  return <section className={`document-artifact${slides ? ' slides' : ''}`} aria-label={`${slides ? 'Bài thuyết trình' : 'Tài liệu'} ${artifact.filename}`}>
    <header className="artifact-heading">
      {slides ? <SlidesIcon /> : <DocumentIcon />}<button type="button" className="artifact-name" onClick={() => onOpen(artifact)} title={artifact.filename}>{artifact.filename}</button>
      <a className="artifact-icon" href={download} download={artifact.filename} aria-label={`Tải ${artifact.filename}`} title="Tải xuống"><DownloadIcon /></a>
      <button type="button" className="artifact-icon" aria-label={`Mở rộng ${artifact.filename}`} title="Mở trong bảng tài liệu" onClick={() => onOpen(artifact)}><ExpandIcon /></button>
    </header>
    <div className="artifact-preview-crop"><PageImage key={preview(1)} src={preview(1)} page={1} title={artifact.title} />
      <button type="button" className="artifact-open-overlay" onClick={() => onOpen(artifact)}>{slides ? 'Xem slide' : 'Xem tài liệu'} <span>· {artifact.pages} {slides ? 'slide' : 'trang'}</span><ExpandIcon /></button>
    </div>
    <footer className="artifact-caption">{slides
      ? <><span>PPTX · {artifact.pages} slide · có ghi chú thuyết trình</span><a href={`${base}/export/pdf?version=${artifact.version}`} download={pdfName}>Tải PDF</a></>
      : <><span>{artifact.format.toUpperCase()} · {artifact.pages} trang xem trước</span><button type="button" onClick={() => onEdit(artifact)}>Sửa nội dung</button></>}</footer>
  </section>;
}
