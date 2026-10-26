import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Root, RootContent } from 'mdast';
import { getConversationPreview, listConversations, UnauthorizedError, type Conversation } from '../shared/api/api';
import './historySearch.css';

type PreviewMessage = { role: 'user' | 'assistant'; content: string; id?: number };
type Preview = { messages: PreviewMessage[]; truncated: boolean };
const PREVIEW_CHARACTERS = 24_000, PREVIEW_MESSAGES = 12, PREVIEW_CACHE = 8;

/** Server previews are bounded too; malformed/old responses must not create an unbounded render. */
export function boundedHistoryPreview(value: unknown): Preview {
  if (!value || typeof value !== 'object' || !('messages' in value) || !Array.isArray(value.messages)) return { messages: [], truncated: false };
  const rows = value.messages.filter((row): row is PreviewMessage => Boolean(row) && typeof row === 'object'
    && (row.role === 'user' || row.role === 'assistant') && typeof row.content === 'string');
  const tail = rows.slice(-PREVIEW_MESSAGES);
  let remaining = PREVIEW_CHARACTERS;
  let truncated = ('truncated' in value && value.truncated === true) || rows.length > tail.length;
  const messages: PreviewMessage[] = [];
  for (let index = tail.length - 1; index >= 0; index--) {
    const row = tail[index];
    if (!remaining) { truncated = true; break; }
    let content = row.content.slice(0, remaining);
    if (/[\ud800-\udbff]$/.test(content)) content = content.slice(0, -1);
    truncated ||= content.length < row.content.length;
    remaining -= content.length;
    messages.unshift({ role: row.role, content, ...(typeof row.id === 'number' ? { id: row.id } : {}) });
  }
  return { messages, truncated };
}
function safePreviewUrl(url: string) {
  try { const parsed = new URL(url); return (parsed.protocol === 'https:' || parsed.protocol === 'http:') && !parsed.username && !parsed.password ? url : ''; }
  catch { return ''; }
}
// Previews intentionally have no source metadata. Hide citation controls only in assistant prose;
// code and link labels remain literal, and the underlying message is never changed.
function remarkPreviewCitations() {
  return (tree: Root) => {
    function walk(parent: { children: RootContent[] }) {
      for (const node of parent.children) {
        if (node.type === 'text') {
          node.value = node.value.replace(/\[(?:web|x|src):[^\]\r\n]{0,128}\]|\ue200cite(?:\ue202[^\ue201\r\n]{1,100})+\ue201/g, '')
            .replace(/\[(?:web|x|src):[^\]\r\n]{0,128}$|\ue200cite(?:\ue202[^\ue201\r\n]{0,100})*$/g, '');
        } else if ('children' in node && !['link', 'linkReference'].includes(node.type)) walk(node as { children: RootContent[] });
      }
    }
    walk(tree);
  };
}
function CloseIcon() { return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>; }
function OpenIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" /></svg>; }

export default function HistorySearch({ onClose, onSelect, onUnauthorized }: { onClose: () => void; onSelect: (id: string) => void; onUnauthorized: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), input = useRef<HTMLInputElement>(null), previewScroll = useRef<HTMLDivElement>(null);
  const previewOpen = useRef<HTMLButtonElement>(null);
  const resultButtons = useRef(new Map<string, HTMLButtonElement>());
  const opener = useRef(document.activeElement instanceof HTMLElement ? document.activeElement : null);
  const callbacks = useRef({ onClose, onSelect, onUnauthorized });
  callbacks.current = { onClose, onSelect, onUnauthorized };
  const cache = useRef(new Map<string, Preview>());
  const pointer = useRef<{ x: number; y: number } | null>(null);
  const resultsId = useId(), previewId = useId();
  const [query, setQuery] = useState(''), [items, setItems] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true), [error, setError] = useState('');
  const [offset, setOffset] = useState(0), [more, setMore] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null), [preview, setPreview] = useState<Preview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false), [previewError, setPreviewError] = useState('');
  const [previewRetry, setPreviewRetry] = useState(0);
  const [narrow, setNarrow] = useState(() => window.matchMedia?.('(max-width: 760px)').matches ?? false);
  const [mobilePreview, setMobilePreview] = useState(false), previousMobilePreview = useRef(false);
  const selected = items.find(item => item.id === selectedId);

  useEffect(() => {
    const element = dialog.current;
    element?.showModal(); input.current?.focus({ preventScroll: true });
    return () => { cache.current.clear(); element?.close(); if (opener.current?.isConnected) opener.current.focus({ preventScroll: true }); };
  }, []);
  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 760px)');
    if (!media) return;
    const update = () => setNarrow(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (!previousMobilePreview.current && mobilePreview && narrow) previewOpen.current?.focus({ preventScroll: true });
    if (previousMobilePreview.current && !mobilePreview && narrow && selectedId) resultButtons.current.get(selectedId)?.focus({ preventScroll: true });
    previousMobilePreview.current = mobilePreview;
  }, [mobilePreview, narrow, selectedId]);
  function unauthorized() {
    cache.current.clear(); setItems([]); setSelectedId(null); setPreview(null); setPreviewError(''); callbacks.current.onUnauthorized();
  }
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    const timer = setTimeout(async () => {
      try {
        const result = await listConversations(offset, 50, query.trim(), undefined, controller.signal);
        if (controller.signal.aborted) return;
        setItems(previous => [...new Map([...(offset ? previous : []), ...result.conversations].map(item => [item.id, item])).values()]);
        setMore(result.has_more);
      } catch (err) { if (!controller.signal.aborted) { if (err instanceof UnauthorizedError) unauthorized(); else setError('Chưa tìm được lịch sử. Hãy thử lại.'); } }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }, 250);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [query, offset]);
  useEffect(() => {
    const controller = new AbortController();
    setPreview(null); setPreviewError('');
    if (!selectedId) { setPreviewLoading(false); return () => controller.abort(); }
    const existing = cache.current.get(selectedId);
    if (existing) { setPreview(existing); setPreviewLoading(false); return () => controller.abort(); }
    setPreviewLoading(true);
    const timer = setTimeout(async () => {
      try {
        const result = boundedHistoryPreview(await getConversationPreview(selectedId, controller.signal));
        if (controller.signal.aborted) return;
        cache.current.delete(selectedId); cache.current.set(selectedId, result);
        if (cache.current.size > PREVIEW_CACHE) cache.current.delete(cache.current.keys().next().value!);
        setPreview(result);
      } catch (err) { if (!controller.signal.aborted) { if (err instanceof UnauthorizedError) unauthorized(); else setPreviewError('Không thể xem trước hội thoại này.'); } }
      finally { if (!controller.signal.aborted) setPreviewLoading(false); }
    }, 140);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [selectedId, previewRetry]);
  useEffect(() => { if (previewScroll.current && preview) previewScroll.current.scrollTop = previewScroll.current.scrollHeight; }, [preview]);

  function select(id: string) { setSelectedId(id); }
  function navigate(event: KeyboardEvent, fromResult = false) {
    if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229 || !items.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); pointer.current = null;
      const current = items.findIndex(item => item.id === selectedId);
      const index = current < 0 ? event.key === 'ArrowDown' ? 0 : items.length - 1 : (current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      const id = items[index].id;
      select(id); resultButtons.current.get(id)?.scrollIntoView({ block: 'nearest' });
      if (fromResult) resultButtons.current.get(id)?.focus({ preventScroll: true });
    } else if (event.key === 'Enter' && selectedId) { event.preventDefault(); callbacks.current.onSelect(selectedId); }
  }
  function changeQuery(value: string) {
    setQuery(value); setOffset(0); setItems([]); setMore(false); setSelectedId(null); setPreview(null); setPreviewError(''); setMobilePreview(false); cache.current.clear(); pointer.current = null;
  }
  return <dialog ref={dialog} className={`history-dialog history-search-dialog${mobilePreview ? ' showing-preview' : ''}`} aria-label="Tìm kiếm hội thoại"
    onCancel={event => { event.preventDefault(); callbacks.current.onClose(); }}
    onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); callbacks.current.onClose(); } }}
    onClick={event => { if (event.target !== event.currentTarget) return; const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) callbacks.current.onClose(); }}>
    <div className="history-dialog-head"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg>
      <input ref={input} type="search" aria-label="Tìm trong lịch sử chat" aria-controls={resultsId} placeholder="Tìm tiêu đề hoặc nội dung…" maxLength={200} value={query} onChange={event => changeQuery(event.target.value)} onKeyDown={event => navigate(event)} enterKeyHint="search" />
      <button type="button" onClick={() => callbacks.current.onClose()} aria-label="Đóng tìm kiếm"><CloseIcon /></button>
    </div>
    <div className="history-search-body">
      <div id={resultsId} className="history-results" role="region" aria-label="Kết quả hội thoại">
        <p className="history-results-label">{query.trim() ? 'Kết quả tìm kiếm' : 'Hội thoại gần đây'}</p>
        {error && <p className="history-search-state" role="alert">{error}</p>}
        <ul>{items.map(item => <li key={item.id}><button type="button" ref={element => { if (element) resultButtons.current.set(item.id, element); else resultButtons.current.delete(item.id); }}
          className={`history-result${selectedId === item.id ? ' selected' : ''}`} aria-pressed={selectedId === item.id} aria-controls={previewId}
          tabIndex={selectedId === item.id || (!selectedId && item === items[0]) ? 0 : -1} onFocus={() => select(item.id)} onKeyDown={event => navigate(event, true)}
          onPointerMove={event => {
            if (event.pointerType !== 'mouse') return;
            const previous = pointer.current;
            // Listen to actual movement, not enter events emitted when the list scrolls under a stationary pointer.
            if (!previous || Math.abs(previous.x - event.clientX) + Math.abs(previous.y - event.clientY) > 3) {
              pointer.current = { x: event.clientX, y: event.clientY }; select(item.id);
            }
          }}
          onClick={() => { if (narrow) { select(item.id); setMobilePreview(true); } else callbacks.current.onSelect(item.id); }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M21 11a9 9 0 0 1-13 8l-5 2 1-6A9 9 0 1 1 21 11Z" /></svg>
          <span className="history-result-title" title={item.title || 'Chưa có tiêu đề'}>{item.title || 'Chưa có tiêu đề'}</span>
        </button></li>)}</ul>
        {loading && <p className="history-search-state" role="status">Đang tìm…</p>}
        {!loading && !error && !items.length && <p className="history-search-state">Không tìm thấy hội thoại phù hợp.</p>}
        {more && <button type="button" className="load-more" disabled={loading} onClick={() => setOffset(value => value + 50)}>Xem thêm</button>}
      </div>
      <section id={previewId} className="history-preview" aria-label="Xem trước hội thoại" aria-busy={previewLoading}>
        {selected ? <><header className="history-preview-head">
          <button type="button" className="history-preview-back" aria-label="Về kết quả tìm kiếm" onClick={() => setMobilePreview(false)}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m15 5-7 7 7 7" /></svg></button>
          <h2 title={selected.title} aria-live="polite">{selected.title || 'Chưa có tiêu đề'}</h2>
          <button ref={previewOpen} type="button" className="history-preview-open" aria-label="Mở hội thoại đang xem trước" data-tip="Mở hội thoại" onClick={() => callbacks.current.onSelect(selected.id)}><OpenIcon /></button>
        </header><div ref={previewScroll} className="history-preview-scroll" role="region" tabIndex={0} aria-label="Nội dung xem trước">
          {previewLoading ? <p className="history-search-state" role="status">Đang tải hội thoại…</p> : previewError ? <div className="history-preview-error"><p role="alert">{previewError}</p><button type="button" onClick={() => setPreviewRetry(value => value + 1)}>Thử lại xem trước</button></div> : preview && <>
            {selected.archived && <p className="history-preview-note">Hội thoại đã lưu trữ</p>}
            {preview.truncated && <p className="history-preview-note">Đang xem phần cuối hội thoại.</p>}
            {preview.messages.map((message, index) => <article key={message.id ?? index} className={`history-preview-message ${message.role}`} aria-label={message.role === 'user' ? 'Bạn' : 'Peto'}>
              <ReactMarkdown remarkPlugins={message.role === 'assistant' ? [remarkGfm, remarkPreviewCitations] : [remarkGfm]} urlTransform={safePreviewUrl} components={{
                img: ({ alt }) => <span className="history-preview-note">{alt ? `[Ảnh: ${alt}]` : '[Ảnh]'}</span>,
                a: ({ href, children }) => href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>,
                table: ({ children }) => <div className="history-preview-table"><table>{children}</table></div>,
              }}>{message.content || '(Không có nội dung chữ)'}</ReactMarkdown>
            </article>)}
            {!preview.messages.length && <p className="history-search-state">Hội thoại chưa có nội dung chữ để xem trước.</p>}
          </>}
        </div></> : <p className="history-preview-placeholder">Chọn một hội thoại để xem trước.</p>}
      </section>
    </div>
  </dialog>;
}
