import { useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { UnauthorizedError } from './api';
import { deleteDocument, downloadDocument, draftTitle, getDocument, listDocuments, saveDocument, type DocumentDraftRequest, type DocumentSummary, type SavedDocument } from './documentApi';

export function DocumentIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Zm0 0v6h6M8 13h8M8 17h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export default function DocumentWorkspace({ conversationId, request, onUnauthorized, selection, refreshKey = 0 }: {
  conversationId: string | null; request: DocumentDraftRequest | null; onUnauthorized: () => void;
  selection?: { id: string; version: number; key: number } | null; refreshKey?: number;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [listError, setListError] = useState(false);
  const [reload, setReload] = useState(0);
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState<SavedDocument | null>(null);
  const [sourceConversation, setSourceConversation] = useState('');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [closing, setClosing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const alive = useRef(true);
  const dirty = !saved || saved.title !== title || saved.content !== content;

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    setDocuments([]); setListError(false);
    if (conversationId) void listDocuments(conversationId, controller.signal).then(result => {
      if (!controller.signal.aborted) setDocuments(result.documents);
    }).catch(reason => {
      if (controller.signal.aborted) return;
      if (reason instanceof UnauthorizedError) onUnauthorized();
      else setListError(true);
    });
    return () => controller.abort();
  }, [conversationId, reload, refreshKey, onUnauthorized]);
  useEffect(() => {
    if (selection) void load(selection.id, selection.version);
  }, [selection]);
  useEffect(() => {
    if (!request) return;
    setSaved(null); setSourceConversation(request.conversationId);
    setTitle(draftTitle(request.content)); setContent(request.content);
    setError(''); setNotice(''); setEditing(false); setClosing(false); setDeleting(false); setOpen(true);
  }, [request]);
  useEffect(() => {
    if (open) dialog.current?.showModal(); else dialog.current?.close();
  }, [open]);
  useEffect(() => {
    if (body.current) body.current.scrollTop = 0;
  }, [open, editing, request, saved?.id, saved?.version]);
  useEffect(() => {
    if (!open || !dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [open, dirty]);

  function report(reason: unknown) {
    if (!alive.current) return;
    if (reason instanceof UnauthorizedError) onUnauthorized();
    else setError(reason instanceof Error ? reason.message : 'Chưa xử lý được tài liệu.');
  }
  function show(document: SavedDocument) {
    setSaved(document); setTitle(document.title); setContent(document.content); setSourceConversation(document.conversation_id);
    setEditing(false); setClosing(false); setDeleting(false);
  }
  function rename(value: string) {
    setContent(previous => previous.replace(/^(\s*#{1,6}[ \t]+)([^\n]*)(\n|$)/, (match, prefix: string, heading: string, end: string) =>
      heading.trim() === title.trim() ? prefix + value + end : match));
    setTitle(value);
  }
  async function load(id: string, version?: number) {
    setBusy('Đang mở tài liệu…'); setError(''); setNotice(''); setOpen(true);
    if (saved?.id !== id) {
      setSaved(null); setTitle(''); setContent(''); setEditing(false); setClosing(false); setDeleting(false);
    }
    try { const value = await getDocument(id, version); if (alive.current) show(value); }
    catch (reason) { report(reason); }
    finally { if (alive.current) setBusy(''); }
  }
  async function ensureSaved() {
    if (!dirty && saved) return saved;
    const result = await saveDocument({ title: title.trim(), content: content.trim() }, sourceConversation, saved);
    if (alive.current) { show(result); setReload(value => value + 1); }
    return result;
  }
  async function save(close = false) {
    setBusy('Đang lưu…'); setError(''); setNotice('');
    try { await ensureSaved(); if (alive.current) { setNotice('Đã lưu tài liệu.'); if (close) setOpen(false); } }
    catch (reason) { report(reason); }
    finally { if (alive.current) setBusy(''); }
  }
  async function download(format: 'docx' | 'pdf') {
    setBusy(`Đang chuẩn bị ${format.toUpperCase()}…`); setError(''); setNotice('');
    try {
      const document = await ensureSaved();
      const blob = await downloadDocument(document, format);
      if (!alive.current) return;
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement('a');
      link.href = url; link.download = `${document.title.replace(/[<>:"/\\|?*\x00-\x1f]/g, '').slice(0, 90) || 'Tai lieu Peto'}-v${document.version}.${format}`;
      window.document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30000);
      setNotice(`Đã chuẩn bị tệp ${format.toUpperCase()}.`);
    } catch (reason) { report(reason); }
    finally { if (alive.current) setBusy(''); }
  }
  function close() { if (busy) return; if (dirty && content.trim()) setClosing(true); else setOpen(false); }
  async function remove() {
    if (!saved) return;
    setBusy('Đang xóa…'); setError('');
    try { await deleteDocument(saved.id); if (alive.current) { setOpen(false); setReload(value => value + 1); } }
    catch (reason) { report(reason); }
    finally { if (alive.current) setBusy(''); }
  }

  return <>
    {documents.length > 0 && <nav className="document-shelf" aria-label="Tài liệu trong hội thoại">
      <span><DocumentIcon /> Tài liệu</span>
      {documents.map(document => <button key={document.id} aria-label={`${document.title} · Phiên bản ${document.version}`} onClick={() => void load(document.id)}><span>{document.title}</span><small>v{document.version}</small></button>)}
    </nav>}
    {listError && <div className="document-shelf-error">Chưa tải được danh sách tài liệu. <button onClick={() => setReload(value => value + 1)}>Thử lại</button></div>}
    <dialog ref={dialog} className="document-workspace" aria-labelledby="document-workspace-title" onCancel={event => { event.preventDefault(); close(); }}>
      <header className="document-workspace-head">
        <div><span className="document-eyebrow"><DocumentIcon /> TÀI LIỆU CỦA BẠN</span><h2 id="document-workspace-title">{saved ? 'Xem và chỉnh tài liệu' : 'Bản nháp từ Peto'}</h2></div>
        <button className="dialog-close" aria-label="Đóng tài liệu" disabled={!!busy} onClick={close}>×</button>
      </header>
      <div className="document-workspace-toolbar">
        <button className={editing ? 'active' : ''} aria-pressed={editing} disabled={!!busy} onClick={() => setEditing(value => !value)}>{editing ? 'Xem trước' : 'Chỉnh nội dung'}</button>
        {saved && <select aria-label="Phiên bản tài liệu" value={saved.version} disabled={!!busy || dirty} onChange={event => void load(saved.id, Number(event.target.value))}>
          {saved.versions.map(version => <option key={version.version} value={version.version}>Phiên bản {version.version}</option>)}
        </select>}
        <span className="document-save-state">{dirty ? 'Chưa lưu' : 'Đã lưu'}</span>
        <button disabled={!!busy || !dirty || !title.trim() || !content.trim()} onClick={() => void save()}>Lưu</button>
        <button disabled={!!busy || !title.trim() || !content.trim()} onClick={() => void download('docx')}>Tải DOCX</button>
        <button className="document-download-primary" disabled={!!busy || !title.trim() || !content.trim()} onClick={() => void download('pdf')}>Tải PDF</button>
      </div>
      {busy && <p className="document-workspace-status" role="status">{busy}</p>}
      {error && <p className="document-workspace-error" role="alert">{error}</p>}
      {notice && <p className="document-workspace-status" role="status">{notice}</p>}
      {closing && <div className="document-unsaved" role="alert"><p>Bạn có thay đổi chưa lưu.</p><button onClick={() => setClosing(false)}>Tiếp tục sửa</button><button disabled={!!busy} onClick={() => { setClosing(false); setOpen(false); }}>Bỏ thay đổi</button><button disabled={!!busy} onClick={() => void save(true)}>Lưu và đóng</button></div>}
      {deleting && <div className="document-unsaved" role="alert"><p>Xóa tài liệu và toàn bộ phiên bản? Cuộc trò chuyện vẫn được giữ lại.</p><button disabled={!!busy} onClick={() => setDeleting(false)}>Giữ lại</button><button disabled={!!busy} onClick={() => void remove()}>Xóa tài liệu</button></div>}
      <div ref={body} className="document-workspace-body">
        {editing ? <div className="document-editor">
          <label htmlFor="document-name">Tên tài liệu</label><input id="document-name" value={title} maxLength={120} disabled={!!busy} onChange={event => rename(event.target.value)} />
          <label htmlFor="document-content">Nội dung</label><textarea id="document-content" value={content} maxLength={60000} disabled={!!busy} onChange={event => setContent(event.target.value)} />
          <small>{content.length.toLocaleString('vi-VN')} / 60.000 ký tự · Giữ các dấu định dạng của bản nháp để bảo toàn tiêu đề và bảng.</small>
        </div> : <article className="document-paper" aria-label="Nội dung tài liệu">
          <h1>{title}</h1><Markdown remarkPlugins={[remarkGfm]} components={{
            img: ({ alt }) => <span>[Ảnh: {alt || 'không có mô tả'}]</span>,
            a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
          }}>{content.replace(/^\s*#{1,6}\s+([^\n]+)\n?/, (match, heading: string) => heading.trim() === title.trim() ? '' : match)}</Markdown>
        </article>}
      </div>
      <footer className="document-workspace-foot"><p>Bản xem nội dung; cách ngắt trang có thể khác trong tệp tải xuống. Bản đầu chưa xuất ảnh, công thức hay giữ bố cục tài liệu gốc.</p>{saved && <button disabled={!!busy} onClick={() => setDeleting(true)}>Xóa tài liệu…</button>}</footer>
    </dialog>
  </>;
}
