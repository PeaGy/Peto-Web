/**
 * Danh sách hội thoại (AIRI: stage-ui/components/scenarios/chat/components/sessions-list.vue, bản compact trong
 * popover của sessions-dialog.vue) và bộ chọn Profile (AIRI: stage-ui/components/misc/profile-switcher-popover.vue),
 * viết lại bằng React. Máy tính: menu thả xuống neo vào nút; điện thoại (≤720px): tấm kéo từ dưới lên như BottomDrawer
 * của AIRI. Chủ web chọn bản "Như AIRI" ngày 25/10/2026.
 */
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import type { CompanionCard, CompanionConversation } from '../../../shared/api/api';

const COMPACT = '(max-width: 720px)';

function useCompact() {
  const [compact, setCompact] = useState(() => typeof matchMedia === 'function' && matchMedia(COMPACT).matches);
  useEffect(() => {
    if (typeof matchMedia !== 'function') return;
    const media = matchMedia(COMPACT);
    const update = () => setCompact(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  return compact;
}

const relative = typeof Intl.RelativeTimeFormat === 'function' ? new Intl.RelativeTimeFormat('vi', { numeric: 'auto' }) : null;

/** "30 phút trước", "5 ngày trước" như intlFormatDistance AIRI dùng cho danh sách hội thoại. */
export function timeAgo(seconds: number, now = Date.now()): string {
  let value = Math.round(seconds - now / 1000);
  if (!relative) return new Date(seconds * 1000).toLocaleDateString('vi-VN');
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [['second', 60], ['minute', 60], ['hour', 24], ['day', 7], ['week', 4.35], ['month', 12]];
  for (const [unit, size] of steps) {
    if (Math.abs(value) < size) return relative.format(Math.round(value), unit);
    value /= size;
  }
  return relative.format(Math.round(value), 'year');
}

/** Menu neo vào nút (máy tính) hoặc tấm dưới đáy (điện thoại). Esc, bấm ra ngoài đóng; đóng thì trả tiêu điểm về nút. */
export function CompanionPopover({ open, onClose, anchor, align = 'start', title, children }: {
  open: boolean; onClose: () => void; anchor: RefObject<HTMLElement | null>; align?: 'start' | 'end'; title: string;
  children: ReactNode;
}) {
  const compact = useCompact();
  const panel = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{ top: number; left: number } | null>(null);
  useLayoutEffect(() => {
    if (!open || compact || !anchor.current || !panel.current) return;
    const rect = anchor.current.getBoundingClientRect();
    const width = panel.current.offsetWidth;
    const left = align === 'start' ? rect.left : rect.right - width;
    setPlace({ top: rect.bottom + 8, left: Math.max(8, Math.min(left, window.innerWidth - width - 8)) });
  }, [open, compact, anchor, align]);
  const closeRef = useRef(onClose); closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const trigger = anchor.current;
    const key = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.stopPropagation();
      closeRef.current();
    };
    const down = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!panel.current?.contains(target) && !trigger?.contains(target)) closeRef.current();
    };
    window.addEventListener('keydown', key);
    window.addEventListener('pointerdown', down, true);
    const frame = requestAnimationFrame(() => panel.current?.querySelector<HTMLElement>('button, input')?.focus({ preventScroll: true }));
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('keydown', key);
      window.removeEventListener('pointerdown', down, true);
      if (panel.current?.contains(document.activeElement) || document.activeElement === document.body) trigger?.focus({ preventScroll: true });
    };
  }, [open, anchor]);
  if (!open) return null;
  if (compact) {
    return createPortal(
      <div className="companion-sheet-layer">
        <div className="companion-sheet-backdrop" onClick={onClose} />
        <div ref={panel} className="companion-sheet" role="dialog" aria-label={title}>
          <div className="companion-sheet-handle" aria-hidden="true" />
          <h2 className="companion-sheet-title">{title}</h2>
          {children}
        </div>
      </div>,
      document.body,
    );
  }
  return createPortal(
    <div ref={panel} role="dialog" aria-label={title} className="companion-popover" data-align={align}
      style={place ? { top: place.top, left: place.left } : { visibility: 'hidden' }}>
      {children}
    </div>,
    document.body,
  );
}

/** Danh sách mọi hội thoại Companion: "Hội thoại mới" ở đầu, xóa phải bấm hai lần (như AIRI). */
export function ConversationList({ rows, loading, failed, currentId, busy, onSelect, onNew, onDelete, onRetry }: {
  rows: CompanionConversation[]; loading: boolean; failed: boolean; currentId: string | null; busy?: boolean;
  onSelect: (row: CompanionConversation) => void; onNew: () => void; onDelete: (row: CompanionConversation) => void; onRetry: () => void;
}) {
  const [pending, setPending] = useState<string | null>(null);
  return (
    <div className="companion-sessions">
      <button type="button" className="companion-menu-new" disabled={busy} onClick={onNew}>
        <PlusIcon /> Hội thoại mới
      </button>
      <div className="companion-menu-divider" />
      {failed ? (
        <div className="companion-menu-empty" role="alert">
          Chưa tải được danh sách. <button type="button" onClick={onRetry}>Thử lại</button>
        </div>
      ) : loading && rows.length === 0 ? (
        <p className="companion-menu-empty">Đang tải…</p>
      ) : rows.length === 0 ? (
        <p className="companion-menu-empty"><ConversationIcon /> Chưa có hội thoại nào</p>
      ) : (
        <ul className="companion-session-list">
          {rows.map(row => {
            const current = row.id === currentId;
            const label = row.preview || 'Hội thoại mới';
            return (
              <li key={row.id} className={`companion-session${current ? ' current' : ''}`} onMouseLeave={() => setPending(null)}>
                <button type="button" className="companion-session-select" aria-current={current ? 'true' : undefined} disabled={busy}
                  onClick={() => { setPending(null); onSelect(row); }}>
                  <span className="companion-session-bar" aria-hidden="true" />
                  <span className="companion-session-text">
                    <strong>{label}</strong>
                    <small>{timeAgo(row.updated_at)} · {row.card_name}</small>
                  </span>
                </button>
                <button type="button" className={`companion-session-delete${pending === row.id ? ' confirm' : ''}`} disabled={busy}
                  aria-label={pending === row.id ? `Xác nhận xóa: ${label}` : `Xóa hội thoại: ${label}`}
                  onKeyDown={event => {
                    if (event.key === 'Escape' && pending) { event.stopPropagation(); setPending(null); }
                  }}
                  onClick={() => {
                    if (pending !== row.id) { setPending(row.id); return; }
                    setPending(null);
                    onDelete(row);
                  }}>
                  <TrashIcon />{pending === row.id && <span>Xóa?</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Danh sách thẻ (Profile), "Lưu thành Profile mới" với ô nhập tên ngay tại chỗ, và "Quản lý Profile". */
export function ProfileList({ cards, activeId, busy, onPick, onSaveAs, onManage }: {
  cards: CompanionCard[]; activeId: string; busy?: boolean;
  onPick: (card: CompanionCard) => void; onSaveAs: (name: string) => Promise<void>; onManage?: () => void;
}) {
  const active = cards.find(card => card.id === activeId);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const trimmed = name.trim();
  const duplicate = Boolean(trimmed) && cards.some(card => card.name === trimmed);
  useEffect(() => { if (creating) { input.current?.focus(); input.current?.select(); } }, [creating]);
  async function confirm() {
    if (!trimmed || duplicate || saving) return;
    setSaving(true);
    setError('');
    try {
      await onSaveAs(trimmed);
      setCreating(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chưa lưu được Profile mới.');
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="companion-profiles">
      <ul className="companion-profile-list">
        {cards.map(card => (
          <li key={card.id}>
            <button type="button" className={`companion-profile${card.id === activeId ? ' current' : ''}`}
              aria-current={card.id === activeId ? 'true' : undefined} disabled={busy} onClick={() => onPick(card)}>
              {card.id === activeId ? <CheckIcon /> : <FaceIcon />}
              <span>{card.name}</span>
              {card.is_default && <small>Mặc định</small>}
            </button>
          </li>
        ))}
      </ul>
      <div className="companion-menu-divider" />
      {creating ? (
        <div className="companion-profile-create">
          <input ref={input} value={name} placeholder="Tên Profile" aria-label="Tên Profile mới" aria-invalid={duplicate || undefined}
            maxLength={60} disabled={saving}
            onChange={event => { setName(event.target.value); setError(''); }}
            onKeyDown={event => {
              if (event.key === 'Enter') { event.preventDefault(); void confirm(); }
              if (event.key === 'Escape') { event.stopPropagation(); setCreating(false); }
            }} />
          <button type="button" className="companion-profile-ok" aria-label="Lưu thành Profile mới"
            disabled={!trimmed || duplicate || saving} onClick={() => void confirm()}><CheckIcon /></button>
          <button type="button" className="companion-profile-cancel" aria-label="Hủy" onClick={() => setCreating(false)}><CloseIcon /></button>
          {(duplicate || error) && <p className="companion-profile-error" role="alert">{duplicate ? 'Đã có Profile tên này.' : error}</p>}
        </div>
      ) : (
        <button type="button" className="companion-menu-action" disabled={busy || !active}
          onClick={() => { setName(active?.name ?? ''); setError(''); setCreating(true); }}>
          <PlusIcon /> Lưu thành Profile mới
        </button>
      )}
      {onManage && <button type="button" className="companion-menu-action" onClick={onManage}><GearIcon /> Quản lý Profile</button>}
    </div>
  );
}

export function CardAvatar({ name }: { name: string }) {
  return <span className="companion-card-avatar" aria-hidden="true">{(name.trim()[0] ?? 'P').toUpperCase()}</span>;
}

export const ChevronIcon = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>;
export const ConversationIcon = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /><path d="M8 9.5h8M8 12.5h5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>;
const PlusIcon = () => <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" /><path d="M12 8v8M8 12h8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>;
const TrashIcon = () => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>;
const CheckIcon = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="currentColor" opacity=".18" /><path d="m8 12 3 3 5-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>;
const FaceIcon = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="5" stroke="currentColor" strokeWidth="1.6" /><circle cx="9" cy="10" r="1" fill="currentColor" /><circle cx="15" cy="10" r="1" fill="currentColor" /><path d="M8.5 14.5c1.8 1.6 5.2 1.6 7 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>;
const CloseIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>;
const GearIcon = () => <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.7" /><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>;
