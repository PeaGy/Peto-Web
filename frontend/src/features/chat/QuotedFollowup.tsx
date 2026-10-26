import { useEffect, useState, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import type { QuotedSource } from '../../shared/api/api';
import type { DraftQuote } from './chatDrafts';
import './quotedFollowup.css';

export const MAX_QUOTE_CHARS = 2000;

export function safeQuotedSource(value: unknown): QuotedSource | undefined {
  if (!value || typeof value !== 'object') return;
  const quote = value as Partial<QuotedSource>;
  if (typeof quote.text !== 'string' || !quote.text.trim() || quote.text.length > MAX_QUOTE_CHARS) return;
  if (quote.message_id !== null && (!Number.isSafeInteger(quote.message_id) || quote.message_id! <= 0)) return;
  return { message_id: quote.message_id!, text: quote.text, ...(quote.unavailable || quote.message_id === null ? { unavailable: true } : {}) };
}

/** Only selections fully inside one stored assistant's Markdown can become a contextual quote. */
export function selectedQuote(container: HTMLElement, selection: Selection | null) {
  if (!selection || selection.isCollapsed || !selection.rangeCount) return;
  const range = selection.getRangeAt(0);
  const start = range.startContainer.nodeType === Node.ELEMENT_NODE ? range.startContainer as Element : range.startContainer.parentElement;
  const content = start?.closest<HTMLElement>('[data-message-content]');
  if (!content || !container.contains(content) || !content.contains(range.endContainer)
    || start?.closest('button, [role="button"], .code-head, .table-actions')) return;
  // A range can start in prose and end in an embedded toolbar: never quote UI labels as answer text.
  if ([...content.querySelectorAll('button, [role="button"], .code-head, .table-actions')].some(control => range.intersectsNode(control))) return;
  const article = content.closest<HTMLElement>('article[data-role="assistant"][data-message-id]');
  const id = Number(article?.dataset.messageId), text = selection.toString().trim();
  if (!Number.isSafeInteger(id) || id <= 0 || !text || !article || article.dataset.streaming === 'true' || article.dataset.quoteable === 'false') return;
  const rect = range.getBoundingClientRect();
  return { quote: { message_id: id, text: text.slice(0, MAX_QUOTE_CHARS + 1) }, rect, tooLong: text.length > MAX_QUOTE_CHARS };
}

export function QuoteExcerpt({ quote: value, onJump, onRemove }: {
  quote: QuotedSource; onJump?: (messageId: number) => void; onRemove?: () => void;
}) {
  const quote = safeQuotedSource(value);
  if (!quote) return null;
  const canJump = Boolean(quote.message_id && !quote.unavailable && onJump);
  const text = <><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M5 5v14M9 7h10M9 12h8M9 17h6" /></svg><span>{quote.text}</span></>;
  return <div className="quoted-source">
    {canJump ? <button type="button" className="quoted-source-jump" aria-label="Về tin nhắn được trích dẫn" title={quote.text}
      onClick={() => onJump?.(quote.message_id!)}>{text}</button>
      : <div className="quoted-source-jump unavailable" title={quote.unavailable ? 'Tin nhắn gốc không còn trong hội thoại này' : quote.text}>{text}</div>}
    {onRemove && <button type="button" className="quoted-source-remove" aria-label="Gỡ đoạn trích" onClick={onRemove}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
    </button>}
  </div>;
}

export function QuoteSelection({ containerRef, disabled, onQuote }: {
  containerRef: RefObject<HTMLElement | null>; disabled: boolean; onQuote: (quote: DraftQuote) => void;
}) {
  const [candidate, setCandidate] = useState<ReturnType<typeof selectedQuote>>();
  useEffect(() => {
    setCandidate(undefined);
    if (disabled) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const hide = () => setCandidate(undefined);
    const measure = () => {
      const container = containerRef.current;
      if (!container || document.querySelector('dialog[open][aria-modal="true"], .settings-dialog[open], .history-dialog[open]')) return hide();
      const next = selectedQuote(container, window.getSelection());
      if (!next || next.rect.bottom < 0 || next.rect.top > window.innerHeight) return hide();
      setCandidate(next);
    };
    const changed = () => { clearTimeout(timer); timer = setTimeout(measure, 140); };
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape') { clearTimeout(timer); hide(); } else if (event.shiftKey) changed(); };
    document.addEventListener('selectionchange', changed);
    document.addEventListener('pointerup', changed);
    document.addEventListener('keyup', key);
    window.addEventListener('resize', hide);
    containerRef.current?.addEventListener('scroll', hide, { passive: true });
    const container = containerRef.current;
    return () => {
      clearTimeout(timer);
      document.removeEventListener('selectionchange', changed);
      document.removeEventListener('pointerup', changed);
      document.removeEventListener('keyup', key);
      window.removeEventListener('resize', hide);
      container?.removeEventListener('scroll', hide);
    };
  }, [containerRef, disabled]);
  if (!candidate || disabled) return null;
  const width = Math.min(candidate.tooLong ? 240 : 174, window.innerWidth - 16);
  const left = Math.max(8, Math.min(candidate.rect.left, window.innerWidth - width - 8));
  const top = candidate.rect.top >= 50 ? candidate.rect.top - 42 : Math.min(window.innerHeight - 48, candidate.rect.bottom + 8);
  return createPortal(<button type="button" className="quote-selection-action" style={{ left, top, width }}
    disabled={candidate.tooLong} aria-label={candidate.tooLong ? 'Chọn tối đa 2.000 ký tự' : 'Thêm đoạn trích vào câu hỏi'}
    onPointerDown={event => event.preventDefault()} onClick={() => {
      if (candidate.tooLong) return;
      onQuote(candidate.quote);
      setCandidate(undefined);
      window.getSelection()?.removeAllRanges();
    }}><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M5 5v14M9 7h10M9 12h8M9 17h6" /></svg>
    {candidate.tooLong ? 'Chọn tối đa 2.000 ký tự' : 'Thêm vào câu hỏi'}
  </button>, document.body);
}
