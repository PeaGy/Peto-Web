import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import type { WebSource } from '../../shared/api/api';
import { CheckIcon, ChevronIcon, CopyIcon, MarkdownIcon, MoreIcon, PrintIcon, RetryIcon } from './messageUtilityIcons';
import { printResponse, saveResponseMarkdown } from './responseExport';
import { useMessageCopy } from './useMessageCopy';
import './messageUtilities.css';

/** Zero-based selection within the sibling responses of the same user turn. */
export interface ResponseVariants {
  index: number;
  count: number;
  onPrevious: () => void;
  onNext: () => void;
  loading?: boolean;
}

function ResponseMore({ text, sources, contentRef, messageId }: {
  text: string; sources?: WebSource[]; contentRef: RefObject<HTMLDivElement | null>; messageId?: number;
}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const [position, setPosition] = useState<{ top: number; left: number }>();
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const initialLast = useRef(false);

  function close(restore = true) {
    setOpen(false);
    if (restore) trigger.current?.focus({ preventScroll: true });
  }
  useLayoutEffect(() => {
    if (!open || !menu.current || !trigger.current) return;
    const anchor = trigger.current.getBoundingClientRect();
    const box = menu.current.getBoundingClientRect();
    const top = anchor.top >= box.height + 16 ? anchor.top - box.height - 6 : anchor.bottom + 6;
    setPosition({ top: Math.max(8, Math.min(top, window.innerHeight - box.height - 8)),
      left: Math.max(8, Math.min(anchor.left, window.innerWidth - box.width - 8)) });
  }, [open]);

  useLayoutEffect(() => {
    // Browsers cannot focus the initial visibility:hidden measuring pass.
    if (!open || !position || !menu.current) return;
    const items = menu.current.querySelectorAll<HTMLButtonElement>('[role="menuitem"]');
    items[initialLast.current ? items.length - 1 : 0]?.focus({ preventScroll: true });
  }, [open, position]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) close(false);
    };
    const moved = (event: Event) => { if (!menu.current?.contains(event.target as Node)) close(false); };
    document.addEventListener('pointerdown', outside);
    window.addEventListener('resize', moved);
    window.addEventListener('scroll', moved, true);
    return () => {
      document.removeEventListener('pointerdown', outside);
      window.removeEventListener('resize', moved);
      window.removeEventListener('scroll', moved, true);
    };
  }, [open]);

  function onMenuKey(event: KeyboardEvent<HTMLDivElement>) {
    const items = [...(menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])];
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    const move = (index: number) => { event.preventDefault(); items[(index + items.length) % items.length]?.focus(); };
    if (event.key === 'ArrowDown') move(at + 1);
    else if (event.key === 'ArrowUp') move(at - 1);
    else if (event.key === 'Home') move(0);
    else if (event.key === 'End') move(items.length - 1);
    else if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
    // Restore the trigger before the browser's normal Tab navigation leaves this menu.
    else if (event.key === 'Tab') close();
  }

  return <>
    <button ref={trigger} type="button" className="message-utility-button" aria-label="Thêm thao tác" data-tip
      aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
      onClick={() => { initialLast.current = false; setPosition(undefined); setOpen(value => !value); }}
      onKeyDown={event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault(); initialLast.current = event.key === 'ArrowUp'; setPosition(undefined); setOpen(true);
        }
      }}><MoreIcon /></button>
    {open && createPortal(<div ref={menu} id={menuId} role="menu" aria-label="Thao tác câu trả lời" className="response-more-menu"
      style={position ?? { visibility: 'hidden' }} onKeyDown={onMenuKey} onBlur={event => {
        if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node) && event.relatedTarget !== trigger.current) close(false);
      }}>
      <button type="button" role="menuitem" tabIndex={-1} onClick={() => {
        close();
        try { saveResponseMarkdown(text, sources, messageId); setError(''); }
        catch { setError('Chưa lưu được tệp Markdown. Bạn thử lại nhé.'); }
      }}><MarkdownIcon /><span>Lưu Markdown</span></button>
      <button type="button" role="menuitem" tabIndex={-1} onClick={() => {
        close();
        if (!contentRef.current) { setError('Chưa có nội dung để in.'); return; }
        setError('');
        void printResponse(contentRef.current, sources).catch(reason => setError(reason instanceof Error ? reason.message : 'Chưa mở được bản in.'));
      }}><PrintIcon /><span>In / lưu PDF</span></button>
    </div>, document.body)}
    {error && <span className="message-utility-error" role="status">{error}</span>}
  </>;
}

export default function ResponseActions({ text, sources, messageId, contentRef, stopped, onRetry, onRegenerate, variants, disabled }: {
  text: string;
  sources?: WebSource[];
  messageId?: number;
  contentRef: RefObject<HTMLDivElement | null>;
  stopped?: boolean;
  onRetry?: () => void;
  onRegenerate?: (messageId: number) => void;
  variants?: ResponseVariants;
  disabled?: boolean;
}) {
  const { state, label, copy } = useMessageCopy();
  const canExport = Boolean(text.trim());
  const busy = disabled || variants?.loading;
  return <div className="message-actions response-actions" data-export-exclude>
    {canExport && <button type="button" className={`message-utility-button message-copy${state === 'done' ? ' done' : ''}`}
      aria-label={`${label} câu trả lời`} data-tip onClick={() => void copy(text)}>{state === 'done' ? <CheckIcon /> : <CopyIcon />}</button>}
    {onRetry && <button type="button" className="message-utility-button" aria-label="Thử lại" data-tip onClick={onRetry} disabled={busy}><RetryIcon /></button>}
    {onRegenerate && messageId !== undefined && <button type="button" className="message-utility-button" aria-label="Tạo lại câu trả lời" data-tip
      onClick={() => onRegenerate(messageId)} disabled={busy}><RetryIcon /></button>}
    {variants && variants.count > 1 && <div className="response-variants" role="group" aria-label="Phiên bản câu trả lời" aria-busy={variants.loading || undefined}>
      <button type="button" className="message-utility-button" aria-label="Câu trả lời trước" data-tip onClick={variants.onPrevious}
        disabled={busy || variants.index <= 0}><ChevronIcon /></button>
      <span className="response-variant-count" aria-live="polite">{variants.index + 1}/{variants.count}</span>
      <button type="button" className="message-utility-button" aria-label="Câu trả lời sau" data-tip onClick={variants.onNext}
        disabled={busy || variants.index >= variants.count - 1}><ChevronIcon next /></button>
    </div>}
    {canExport && <ResponseMore text={text} sources={sources} contentRef={contentRef} messageId={messageId} />}
    {stopped && <span className="message-stopped-tag">Đã dừng</span>}
  </div>;
}
