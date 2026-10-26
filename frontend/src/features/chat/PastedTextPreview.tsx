import { useEffect, useRef, useState } from 'react';
import './pastedText.css';

const PREVIEW_BYTES = 512 * 1024;
const PREVIEW_CHARS = 100_000;

export default function PastedTextPreview({ file, onClose }: { file: File; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const [text, setText] = useState('');
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [truncated, setTruncated] = useState(false);
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const element = dialog.current;
    element?.showModal(); close.current?.focus();
    return () => { element?.close(); if (opener?.isConnected) opener.focus({ preventScroll: true }); };
  }, []);
  useEffect(() => {
    const reader = new FileReader();
    setText(''); setLoading(true); setError(false);
    reader.onload = () => { const result = String(reader.result ?? ''); setText(result.slice(0, PREVIEW_CHARS));
      setTruncated(file.size > PREVIEW_BYTES || result.length > PREVIEW_CHARS); setLoading(false); };
    reader.onerror = () => { setError(true); setLoading(false); };
    reader.readAsText(file.slice(0, PREVIEW_BYTES), 'utf-8');
    return () => { reader.onload = null; reader.onerror = null; if (reader.readyState === FileReader.LOADING) reader.abort(); };
  }, [file]);
  return <dialog ref={dialog} className="pasted-text-preview" aria-label={`Xem ${file.name}`} aria-modal="true"
    onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => {
      if (event.target !== event.currentTarget) return;
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
    }}>
    <header><strong>{file.name}</strong><button ref={close} type="button" aria-label="Đóng xem tệp" onClick={onClose}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
    </button></header>
    {loading ? <p role="status">Đang mở tệp…</p> : error ? <p role="alert">Chưa mở được bản xem trước. Tệp vẫn được giữ nguyên.</p>
      : <pre tabIndex={0} aria-label="Nội dung tệp đã dán">{text}</pre>}
    {truncated && <p className="pasted-preview-note">Bản xem trước được giới hạn; tệp đính kèm vẫn giữ toàn bộ nội dung.</p>}
  </dialog>;
}
