import { useState } from 'react';
import type { ChatAttachment } from '../../shared/api/api';
import { FileGlyph, formatSize } from './files';
import ChatImageViewer from './ChatImageViewer';

function filePresentation(file: ChatAttachment) {
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (file.kind === 'image') return { kind: 'image', label: 'Ảnh' };
  if (extension === 'pdf' || file.mime === 'application/pdf') return { kind: 'pdf', label: 'PDF' };
  if (['xls', 'xlsx', 'xlsm', 'csv', 'tsv', 'ods'].includes(extension ?? '')) return { kind: 'sheet', label: 'Bảng tính' };
  if (['ppt', 'pptx', 'odp'].includes(extension ?? '')) return { kind: 'slides', label: 'Bài trình chiếu' };
  if (['py', 'js', 'jsx', 'ts', 'tsx', 'html', 'css', 'json', 'yml', 'yaml', 'sh', 'sql', 'java', 'c', 'cpp', 'rs', 'go'].includes(extension ?? '')) return { kind: 'code', label: 'Mã nguồn' };
  if (['doc', 'docx', 'md', 'markdown', 'rtf', 'odt'].includes(extension ?? '')) return { kind: 'document', label: 'Tài liệu' };
  if (['txt', 'log'].includes(extension ?? '') || file.mime.startsWith('text/')) return { kind: 'text', label: 'Văn bản' };
  return { kind: 'file', label: 'Tệp' };
}

function AttachmentIcon({ kind }: { kind: string }) {
  return <span className={`message-file-icon ${kind}`} aria-hidden="true">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      {kind === 'code' ? <><path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-12-2 14" /></>
        : kind === 'sheet' ? <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M4 9h16M4 15h16M10 9v12" /></>
        : kind === 'image' ? <><rect x="3" y="3" width="18" height="18" rx="3" /><circle cx="8" cy="8" r="1.5" /><path d="m3 17 5-5 4 4 4-6 5 7" /></>
        : <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6M8 13h8m-8 4h5" /></>}
    </svg>
  </span>;
}

function DocumentReading({ document }: { document: NonNullable<ChatAttachment['document']> }) {
  // Tệp đã đọc đủ không cần thêm dòng xác nhận dưới thẻ; OCR vẫn có lưu ý về độ chính xác.
  if (document.status === 'ready' && !document.ocr_pages) return null;
  return <details className={`document-details ${document.status === 'ready' ? 'ready' : 'limited'}`}>
    <summary>
      {document.status === 'ready' ? 'Đã đọc bằng OCR' : document.status === 'partial' ? 'Đọc được một phần' : 'Chưa đọc được'}
      {document.pages != null && ` · ${document.pages_read != null ? `${document.pages_read}/` : ''}${document.pages} trang`}
      {document.sheets != null && ` · ${document.sheets_read != null && document.sheets_read !== document.sheets ? `${document.sheets_read}/` : ''}${document.sheets} trang tính`}
      {document.status === 'partial' && !!document.ocr_pages && ' · có OCR'}
      {!!document.formulas && ` · ${document.formulas} công thức`}
      {!!document.formulas_unread && ` · ${document.formulas_unread} công thức MathType chưa đọc`}
    </summary>
    <p>{document.notice}</p>
  </details>;
}

function FileAttachment({ file, sent }: { file: ChatAttachment; sent: boolean }) {
  const presentation = filePresentation(file);
  const description = `${presentation.label} · ${formatSize(file.size)}`;
  return <div className={sent ? 'message-file-entry' : 'document-card'}>
    <a href={file.url || undefined} className={`file-chip${sent ? ' message-file-card' : ''}`} download={file.name}
      title={sent ? `${file.name} · ${description}` : undefined} aria-label={sent ? `${file.name}, ${description}` : undefined}>
      {sent ? <AttachmentIcon kind={presentation.kind} /> : <FileGlyph name={file.name} kind="file" />}
      <span className={sent ? 'message-file-copy' : undefined}>
        <strong>{file.name}</strong>
        <em>{sent ? description : formatSize(file.size)}</em>
      </span>
    </a>
    {file.document && <DocumentReading document={file.document} />}
  </div>;
}

function ImageAttachment({ file, sent, onOpen }: { file: ChatAttachment; sent: boolean; onOpen: () => void }) {
  return <a href={file.url} target="_blank" rel="noopener noreferrer" title={file.name}
    aria-haspopup="dialog" onClick={event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); onOpen();
    }}
    className={sent ? 'message-image-link' : 'bubble-image-link'}>
    {/* Giữ chỗ trước khi ảnh tải, kể cả khi URL tạm được thay bằng URL máy chủ. */}
    <img src={file.url} alt={file.name} className={sent ? 'message-image' : 'bubble-image'}
      width={sent ? 112 : undefined} height={sent ? 112 : undefined} />
  </a>;
}

export default function MessageAttachments({ attachments, sent }: { attachments: ChatAttachment[]; sent: boolean }) {
  const [selectedImage, setSelectedImage] = useState<number | null>(null);
  const images = attachments.filter(file => file.kind === 'image' && file.url);
  const files = attachments.filter(file => file.kind !== 'image' || !file.url);
  return <>{!sent ? <div className="bubble-files">
    {attachments.map(file => file.kind === 'image' && file.url
      ? <ImageAttachment key={file.id} file={file} sent={false} onOpen={() => setSelectedImage(images.indexOf(file))} />
      : <FileAttachment key={file.id} file={file} sent={false} />)}
  </div> : <div className="message-attachments" role="group" aria-label="Đính kèm trong tin nhắn">
    {images.length > 0 && <div className="message-image-grid">
      {images.map((file, index) => <ImageAttachment key={file.id} file={file} sent onOpen={() => setSelectedImage(index)} />)}
    </div>}
    {files.length > 0 && <div className="message-file-list">
      {files.map(file => <FileAttachment key={file.id} file={file} sent />)}
    </div>}
  </div>}
    {selectedImage !== null && images[selectedImage] && <ChatImageViewer images={images} index={selectedImage}
      onIndexChange={setSelectedImage} onClose={() => setSelectedImage(null)} />}
  </>;
}
