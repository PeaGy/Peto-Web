import { useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { UnauthorizedError } from './api';
import { DocumentIcon } from './DocumentWorkspace';
import { DownloadIcon, ExpandIcon, PageImage } from './DocumentArtifactCard';
import { getDocument, listDocuments, type DocumentSummary, type SavedDocument } from './documentApi';
import './documentPanel.css';

export type DocumentPanelSelection = { id: string; version: number; key: number };
export function RightPanelIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3" stroke="currentColor" strokeWidth="1.6" /><path d="M15 4v16" stroke="currentColor" strokeWidth="1.6" /></svg>;
}
function FileListIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 6h12M9 12h12M9 18h12M3 6h1M3 12h1M3 18h1" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>;
}
const filename = (item: DocumentSummary) => `${item.title}.${item.format || 'docx'}`;
const downloadUrl = (item: DocumentSummary) => `/api/documents/${encodeURIComponent(item.id)}/export/${item.format || 'docx'}?version=${item.version}`;

export default function DocumentPanel({ conversationId, open, expanded, selection, refreshKey, onClose, onExpand, onEdit, onUnauthorized }: {
  conversationId: string | null; open: boolean; expanded: boolean; selection: DocumentPanelSelection | null; refreshKey: number;
  onClose: () => void; onExpand: () => void; onEdit: (item: { id: string; version: number }) => void; onUnauthorized: () => void;
}) {
  const panel = useRef<HTMLDialogElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const [mobile, setMobile] = useState(() => window.matchMedia?.('(max-width: 1100px)')?.matches ?? false);
  const [filesOpen, setFilesOpen] = useState(true);
  const [query, setQuery] = useState('');
  const [files, setFiles] = useState<DocumentSummary[]>([]);
  const [selected, setSelected] = useState<{ id: string; version?: number } | null>(selection);
  const [current, setCurrent] = useState<SavedDocument | null>(null);
  const [listBusy, setListBusy] = useState(false);
  const [listError, setListError] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [page, setPage] = useState(1);

  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 1100px)');
    if (!media) return;
    const update = () => setMobile(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    const element = panel.current;
    if (!element || !open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (mobile) element.showModal(); else element.show();
    return () => { element.close(); if (opener?.isConnected) opener.focus({ preventScroll: true }); };
  }, [open, mobile]);
  useEffect(() => {
    if (selection) { setSelected(selection); if (mobile) setFilesOpen(false); }
  }, [selection]);
  useEffect(() => {
    if (!open) return;
    if (!conversationId) { setFiles([]); setSelected(null); return; }
    const controller = new AbortController();
    setListBusy(true); setListError('');
    void listDocuments(conversationId, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      setFiles(result.documents);
      setSelected(previous => result.documents.some(item => item.id === previous?.id) ? previous : result.documents[0] ? { id: result.documents[0].id } : null);
    }).catch(reason => {
      if (controller.signal.aborted) return;
      if (reason instanceof UnauthorizedError) onUnauthorized();
      else setListError('Chưa tải được danh sách tài liệu.');
    }).finally(() => { if (!controller.signal.aborted) setListBusy(false); });
    return () => controller.abort();
  }, [conversationId, open, refreshKey, retry, onUnauthorized]);
  useEffect(() => {
    setCurrent(null); setError(''); setPage(1);
    if (!selected || !open || !conversationId) { setBusy(false); return; }
    const controller = new AbortController();
    setBusy(true);
    void getDocument(selected.id, selected.version, controller.signal).then(value => {
      if (controller.signal.aborted) return;
      if (value.conversation_id !== conversationId) throw new Error('Tài liệu không thuộc hội thoại này.');
      setCurrent(value);
    }).catch(reason => {
      if (controller.signal.aborted) return;
      if (reason instanceof UnauthorizedError) onUnauthorized();
      else setError(reason instanceof Error ? reason.message : 'Chưa mở được tài liệu.');
    }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [selected, open, conversationId, refreshKey, retry, onUnauthorized]);
  useEffect(() => { if (scroll.current) scroll.current.scrollTop = 0; }, [page, current?.id, current?.version]);

  const filtered = files.filter(item => item.title.toLocaleLowerCase('vi').includes(query.trim().toLocaleLowerCase('vi')));
  const preview = current?.pages && current.format ? `/api/documents/${encodeURIComponent(current.id)}/preview?version=${current.version}&page=${page}` : null;
  return <dialog ref={panel} id="document-panel" className={`document-panel${filesOpen ? ' files-open' : ''}`} role={mobile ? 'dialog' : 'complementary'} aria-label="Tài liệu trong hội thoại" aria-modal={mobile && open ? true : undefined}
    onCancel={event => { event.preventDefault(); onClose(); }} onKeyDown={event => { if (!mobile && event.key === 'Escape') { event.preventDefault(); onClose(); } }}>
    <header className="document-panel-head">
      <DocumentIcon /><h2>Tài liệu</h2><span className="document-panel-count">{files.length}</span>
      <button type="button" className="artifact-icon document-panel-expand" aria-label={expanded ? 'Thu gọn bảng tài liệu' : 'Phóng rộng bảng tài liệu'} title={expanded ? 'Thu gọn' : 'Phóng rộng'} onClick={onExpand}><ExpandIcon /></button>
      <button type="button" className="artifact-icon" aria-label="Đóng bảng tài liệu" title="Đóng bảng tài liệu · Ctrl+Alt+B" onClick={onClose}><RightPanelIcon /></button>
    </header>
    <div className="document-panel-toolbar">
      <button type="button" className="artifact-icon" aria-label={filesOpen ? 'Ẩn danh sách tệp' : 'Hiện danh sách tệp'} aria-expanded={filesOpen} aria-controls="document-file-list" title="Danh sách tệp" onClick={() => setFilesOpen(value => !value)}><FileListIcon /></button>
      <strong title={current ? filename(current) : undefined}>{current ? filename(current) : 'Tài liệu của hội thoại'}</strong>
      {current && <><button type="button" className="document-panel-edit" onClick={() => onEdit(current)}>Sửa nội dung</button><a className="artifact-icon" href={downloadUrl(current)} download={filename(current)} aria-label={`Tải ${filename(current)}`} title="Tải xuống"><DownloadIcon /></a></>}
    </div>
    <div className="document-panel-body">
      <nav id="document-file-list" className="document-file-list" aria-label="Danh sách tài liệu" hidden={!filesOpen}>
        <label className="document-file-search"><span>Tệp trong hội thoại</span><input type="search" aria-label="Tìm tài liệu" placeholder="Tìm tài liệu…" value={query} onChange={event => setQuery(event.target.value)} /></label>
        {listBusy && !files.length && <p role="status">Đang tải danh sách…</p>}
        {listError && <div role="alert"><p>{listError}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Thử lại</button></div>}
        {filtered.map(item => <div key={item.id} className={`document-file-row${selected?.id === item.id ? ' selected' : ''}`}>
          <button type="button" aria-label={`Mở ${filename(item)}`} aria-current={selected?.id === item.id ? 'true' : undefined} title={filename(item)} onClick={() => { setSelected({ id: item.id }); if (mobile) setFilesOpen(false); }}><DocumentIcon /><span><strong>{filename(item)}</strong><small>Phiên bản {item.version}{item.pages ? ` · ${item.pages} trang` : ''}</small></span></button>
          <a className="artifact-icon" href={downloadUrl(item)} download={filename(item)} aria-label={`Tải ${filename(item)} từ danh sách`} title="Tải xuống"><DownloadIcon /></a>
        </div>)}
        {!listBusy && !listError && !filtered.length && <p>{query ? 'Không có tài liệu phù hợp.' : 'Chưa có tài liệu nào.'}</p>}
      </nav>
      <div className="document-panel-preview" inert={mobile && filesOpen}>
        {current && <div className="document-panel-pagination">
          {preview && <><button type="button" aria-label="Trang trước" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>‹</button><span aria-live="polite">Trang {page} / {current.pages}</span><button type="button" aria-label="Trang sau" disabled={page >= (current.pages || 1)} onClick={() => setPage(value => value + 1)}>›</button></>}
          <select aria-label="Phiên bản xem trước" value={current.version} onChange={event => setSelected({ id: current.id, version: Number(event.target.value) })}>{current.versions.map(version => <option key={version.version} value={version.version}>Phiên bản {version.version}</option>)}</select>
        </div>}
        <div className="document-panel-pages" ref={scroll}>
          {busy && <div className="document-panel-empty" role="status">Đang mở tài liệu…</div>}
          {error && <div className="document-panel-empty" role="alert"><p>{error}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Thử lại</button></div>}
          {!busy && !error && !current && <div className="document-panel-empty"><DocumentIcon /><h3>Tài liệu ở ngay đây</h3><p>{listError ? 'Mở danh sách tệp để thử tải lại.' : 'Nhờ Peto tạo một tệp Word hoặc PDF. Các tài liệu của cuộc trò chuyện sẽ được lưu tại đây.'}</p></div>}
          {current && (preview ? <PageImage key={preview} src={preview} page={page} title={current.title} /> : <article className="document-paper" aria-label="Nội dung tài liệu"><Markdown remarkPlugins={[remarkGfm]} components={{ img: ({ alt }) => <span>[Ảnh: {alt || 'không có mô tả'}]</span>, a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> }}>{current.content}</Markdown></article>)}
        </div>
        {current && <p className="document-panel-note">{preview ? current.format === 'docx' ? 'Bản xem PDF cùng nội dung. Font và ngắt trang có thể khác khi mở bằng Word.' : 'Bản xem từ tệp PDF đã lưu.' : 'Bản xem nội dung đã sửa. Tệp tải xuống có thể ngắt trang khác.'}</p>}
      </div>
    </div>
  </dialog>;
}
