import { useState } from 'react';
import type { DocumentArtifact } from './api';
import { DocumentIcon } from './DocumentWorkspace';

export function DownloadIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
export function ExpandIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
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

export default function DocumentArtifactCard({ artifact, onEdit, onOpen }: { artifact: DocumentArtifact; onEdit: (artifact: DocumentArtifact) => void; onOpen: (artifact: DocumentArtifact) => void }) {
  const base = `/api/documents/${encodeURIComponent(artifact.id)}`;
  const download = `${base}/export/${artifact.format}?version=${artifact.version}`;
  const preview = (number: number) => `${base}/preview?version=${artifact.version}&page=${number}`;
  return <section className="document-artifact" aria-label={`Tài liệu ${artifact.filename}`}>
    <header className="artifact-heading">
      <DocumentIcon /><button type="button" className="artifact-name" onClick={() => onOpen(artifact)} title={artifact.filename}>{artifact.filename}</button>
      <a className="artifact-icon" href={download} download={artifact.filename} aria-label={`Tải ${artifact.filename}`} title="Tải xuống"><DownloadIcon /></a>
      <button type="button" className="artifact-icon" aria-label={`Mở rộng ${artifact.filename}`} title="Mở trong bảng tài liệu" onClick={() => onOpen(artifact)}><ExpandIcon /></button>
    </header>
    <div className="artifact-preview-crop"><PageImage key={preview(1)} src={preview(1)} page={1} title={artifact.title} />
      <button type="button" className="artifact-open-overlay" onClick={() => onOpen(artifact)}>Xem tài liệu <span>· {artifact.pages} trang</span><ExpandIcon /></button>
    </div>
    <footer className="artifact-caption"><span>{artifact.format.toUpperCase()} · {artifact.pages} trang xem trước</span><button type="button" onClick={() => onEdit(artifact)}>Sửa nội dung</button></footer>
  </section>;
}
