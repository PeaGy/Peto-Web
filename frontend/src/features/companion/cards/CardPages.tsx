/**
 * Cài đặt Companion → Thẻ nhân vật (chủ web chọn bản "Như AIRI" ngày 25/10/2026), theo Settings → AIRI Card của AIRI
 * (commit 74ddd90): danh sách là lưới thẻ dọc 3:4 (airi-card/index.vue, card-list-item.vue), trang một thẻ có khối lớn và
 * ảnh model bên phải (card-detail.vue), trình sửa có mục bên trái và khối tên/model luôn ở trên (CardEditor.vue).
 *
 * Khác AIRI: thẻ nằm ở máy chủ theo tài khoản; thẻ Peto mặc định không xóa được, chỉ khôi phục bản gốc; trang một thẻ có
 * "Prompt đầy đủ" (máy chủ ghép, gồm phần máy chủ tự thêm và luật cố định) vì chủ web muốn công khai hết. Model hiển thị
 * vẫn nằm trong trình duyệt, nên thẻ trỏ tới một model máy này chưa có thì báo như AIRI (avatar-model-missing).
 */
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore, type CSSProperties, type DragEvent, type MutableRefObject, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useSearchParams } from 'react-router';
import {
  UnauthorizedError, getCompanionCardPrompt, listCompanionConversations, type CompanionCard, type CompanionCardFields,
} from '../../../shared/api/api';
import { Dropdown, type DropdownOption } from '../../../shared/ui/Dropdown';
import { LoadingIndicator } from '../../../shared/ui/LoadingIndicator';
import type { CompanionSettingsPage } from '../../../app/routes';
import { getCharacterAssets, type CharacterModel } from '../characters/characterLibrary';
import type { CharacterLibrary } from '../characters/useCharacters';
import { CHAT_PROVIDERS, chatProvider } from '../providers/catalog';
import { connected, useModels } from '../providers/brain';
import { VOICE_LABELS, voiceLabel, type LocalVoice } from '../speech/LocalVoice';
import { KEY_PROVIDERS, keyProvider, keyReady, suggestedVoices, useKeyConfigs } from '../speech/voiceProviders';
import {
  createCard, loadCompanionCards, pickCompanionCard, removeCard, resetDefaultCard, saveCard, useCompanionCards,
} from './companionCards';
import './cardPages.css';

/** Giới hạn từng trường, khớp LIMITS của backend/features/companion/cards.py. */
const LIMITS = {
  name: 60, nickname: 60, version: 20, description: 20000, notes: 4000, personality: 8000, scenario: 8000,
  system_prompt: 20000, post_history: 4000,
} as const;
const MAX_PROMPT_CHARS = 40000;
const MAX_GREETINGS = 10;

/** Thẻ mới mở sẵn các giá trị mặc định của AIRI (airi-card/new.vue), để người viết thấy mỗi ô dùng làm gì. */
const NEW_CARD = {
  personality: 'You are a regular human, curious about everything.',
  scenario: 'You recently woke up and forgot everything about your previous life.',
  system_prompt: 'You will receive messages, answer to them like a real human.',
  post_history: 'Remember to imitate an human.',
};

type Section = 'identity' | 'behavior' | 'modules' | 'prompt';
const SECTIONS: { id: Section; label: string; icon: ReactNode }[] = [
  { id: 'identity', label: 'Danh tính', icon: <><circle cx="12" cy="8" r="4" /><path d="M4 21v-1a8 8 0 0 1 16 0v1" /></> },
  { id: 'behavior', label: 'Hành vi', icon: <path d="M12 3c.5 4.5 1.5 6 6 6.5-4.5.5-5.5 2-6 6.5-.5-4.5-1.5-6-6-6.5 4.5-.5 5.5-2 6-6.5Z" /> },
  { id: 'modules', label: 'Mô-đun', icon: <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /></> },
  { id: 'prompt', label: 'Prompt', icon: <path d="m9 7-5 5 5 5M15 7l5 5-5 5" /> },
];
const SORTS: DropdownOption[] = [
  { value: 'recent', label: 'Mới thêm' },
  { value: 'az', label: 'Tên A–Z' },
  { value: 'za', label: 'Tên Z–A' },
];

export type CardPage = Extract<CompanionSettingsPage, 'cards' | 'card' | 'card-new' | 'card-edit'>;
/** Rời trang thẻ đang sửa dở: nút quay lại của trang cài đặt hỏi qua đây trước. */
export type LeaveGuard = MutableRefObject<((go: () => void) => void) | null>;

export function isCardPage(page: CompanionSettingsPage): page is CardPage {
  return page === 'cards' || page === 'card' || page === 'card-new' || page === 'card-edit';
}

function Icon({ children, size = 17 }: { children: ReactNode; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>;
}
const ICON = {
  search: <><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  edit: <><path d="M4 20h4L19 9l-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4" /></>,
  trash: <><path d="M4 7h16M10 11v6M14 11v6" /><path d="M6 7l1 13h10l1-13M9 7V4h6v3" /></>,
  restore: <><path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.5" /><path d="M4 4v4.5h4.5" /></>,
  code: <path d="m9 7-5 5 5 5M15 7l5 5-5 5" />,
  lock: <><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></>,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  upload: <><path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" /><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></>,
  download: <><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" /><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></>,
};

/** Tải một tệp trình duyệt đã tạo (gói thẻ), như useDownload của AIRI. */
function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

function fold(text: string) {
  return text.normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/g, 'd').toLowerCase();
}

function timeAgo(seconds: number) {
  const minutes = Math.round((Date.now() / 1000 - seconds) / 60);
  if (minutes < 1) return 'vừa xong';
  if (minutes < 60) return `${minutes} phút trước`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} giờ trước`;
  const days = Math.round(minutes / 1440);
  if (days === 1) return 'hôm qua';
  if (days < 30) return `${days} ngày trước`;
  return new Date(seconds * 1000).toLocaleDateString('vi-VN', { day: 'numeric', month: 'numeric', year: 'numeric' });
}

function errorText(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** Hình ma của AIRI (card-model-preview.vue) khi thẻ không có model, hay model chưa có trên máy này. */
function Ghost() {
  return (
    <svg width="56" height="56" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
      <path opacity=".5" d="M21 12v7.2c0 1.1-1.2 1.8-2.2 1.3a2.9 2.9 0 0 0-2.8.2 2.7 2.7 0 0 1-3 0l-.4-.3a1.3 1.3 0 0 0-1.3 0l-.3.3a2.7 2.7 0 0 1-3 0 2.9 2.9 0 0 0-2.8-.2c-1 .5-2.2-.2-2.2-1.3V12a9 9 0 0 1 18 0Z" />
      <circle cx="9" cy="10" r="1.3" /><circle cx="15" cy="10" r="1.3" />
      <path d="M9 14.4c.9.7 1.9 1 3 1s2.1-.3 3-1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/** Ảnh Hiyori đi kèm, cho máy chưa từng vẽ Hiyori (ảnh xem trước chỉ có sau lần hiển thị đầu). */
const BUILTIN_PREVIEW = '/characters/hiyori-preview.webp';

function CardPreview({ model, missing, name, contain, className = '', children }: {
  model?: CharacterModel; missing?: string; name: string; contain?: boolean; className?: string; children?: ReactNode;
}) {
  const image = model?.preview || (model?.builtin ? BUILTIN_PREVIEW : '');
  return (
    <div className={`card-preview ${className}`}>
      {model && image
        ? <img src={image} alt={`${name} · ${model.name}`} className={contain ? 'contain' : undefined} />
        : <div className="card-preview-empty" role="img" aria-label={missing ? `${missing} chưa có trên máy này` : `${name}: chưa có ảnh model`}>
            <Ghost />{missing && <span>Model “{missing}” chưa có trên máy này</span>}
          </div>}
      {children}
    </div>
  );
}

function ActiveBadge() {
  return <span className="card-badge active"><Icon size={13}>{ICON.check}</Icon>Đang dùng</span>;
}

// Thông báo ngắn ("Đã lưu thẻ"): sống ngoài trang, vì lưu xong là chuyển trang và trang cũ bị gỡ.
let toastState: { text: string; key: number } | null = null;
let toastTimer: number | undefined;
const toastListeners = new Set<() => void>();

function showToast(text: string) {
  toastState = { text, key: Date.now() };
  toastListeners.forEach(listener => listener());
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toastState = null; toastListeners.forEach(listener => listener()); }, 2600);
}

function useToast() {
  const toast = useSyncExternalStore(listener => { toastListeners.add(listener); return () => { toastListeners.delete(listener); }; },
    () => toastState);
  return { show: showToast, node: toast ? <div key={toast.key} className="card-toast" role="status">{toast.text}</div> : null };
}

/** Hộp hỏi lại bằng <dialog> như các hộp khác của app; Esc là hủy. */
function Confirm({ open, title, message, confirm, cancel = 'Hủy', danger, busy, onConfirm, onCancel }: {
  open: boolean; title: string; message: string; confirm: string; cancel?: string; danger?: boolean; busy?: boolean;
  onConfirm: () => void; onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (open && !node.open) node.showModal();
    if (!open && node.open) node.close();
  }, [open]);
  return (
    <dialog ref={ref} className="card-dialog" aria-labelledby={titleId} onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
      <h2 id={titleId}>{title}</h2>
      <p>{message}</p>
      <div className="card-dialog-actions">
        <button type="button" className="card-button" disabled={busy} onClick={onCancel}>{cancel}</button>
        <button type="button" className={danger ? 'card-button danger' : 'card-button primary'} disabled={busy} autoFocus onClick={onConfirm}>{confirm}</button>
      </div>
    </dialog>
  );
}

export default function CardPages({ page, cardId, ownerId, library, voice, actions, guard, onNavigate, onUnauthorized }: {
  page: CardPage;
  cardId: string | null;
  ownerId?: string;
  library: CharacterLibrary;
  voice: LocalVoice;
  /** Chỗ trong tiêu đề trang cài đặt cho nút Lưu của trình sửa (như hàng tiêu đề của CardEditor.vue). */
  actions: HTMLElement | null;
  guard: LeaveGuard;
  onNavigate: (page: CompanionSettingsPage, id?: string) => void;
  onUnauthorized: () => void;
}) {
  const cards = useCompanionCards();
  const toast = useToast();
  const failed = useCallback((error: unknown) => {
    if (error instanceof UnauthorizedError) onUnauthorized();
  }, [onUnauthorized]);
  useEffect(() => { loadCompanionCards(ownerId).catch(failed); }, [ownerId, failed]);
  const card = cardId ? cards.cards.find(item => item.id === cardId) : undefined;

  if (cards.status !== 'ready') {
    if (cards.status === 'error') {
      return <div className="card-empty"><strong>Chưa tải được thẻ nhân vật</strong>
        <button type="button" className="card-button" onClick={() => { loadCompanionCards(ownerId, true).catch(failed); }}>Thử lại</button></div>;
    }
    return <div className="card-loading"><LoadingIndicator label="Đang tải thẻ nhân vật" /></div>;
  }
  if ((page === 'card' || page === 'card-edit') && !card) {
    return <div className="card-empty"><strong>Không tìm thấy thẻ</strong><span>Thẻ này đã bị xóa, hay thuộc tài khoản khác.</span>
      <button type="button" className="card-button" onClick={() => onNavigate('cards')}>Về danh sách thẻ</button></div>;
  }
  return <>
    {page === 'cards' && <CardList cards={cards.cards} active={cards.active} library={library} toast={toast.show}
      onNavigate={onNavigate} onFailed={failed} />}
    {page === 'card' && card && <CardDetail key={card.id} card={card} active={cards.active === card.id} library={library}
      toast={toast.show} onNavigate={onNavigate} onFailed={failed} />}
    {(page === 'card-edit' || page === 'card-new') && <CardEditor key={card?.id ?? 'new'} card={card ?? null}
      active={!!card && cards.active === card.id} names={cards.cards} library={library} voice={voice} actions={actions} guard={guard}
      toast={toast.show} onNavigate={onNavigate} onFailed={failed} />}
    {toast.node}
  </>;
}

function modelFor(library: CharacterLibrary, id: string) {
  return library.models.find(model => model.id === id);
}

function CardList({ cards, active, library, toast, onNavigate, onFailed }: {
  cards: CompanionCard[]; active: string; library: CharacterLibrary; toast: (text: string) => void;
  onNavigate: CardPagesNavigate; onFailed: (error: unknown) => void;
}) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('recent');
  const upload = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState<{ error: boolean; lines: string[] } | null>(null);
  const [dragDepth, setDragDepth] = useState(0);
  const fileDrag = (event: DragEvent) => event.dataTransfer?.types.includes('Files') ?? false;

  // Nhập gói thẻ như airi-card/index.vue: đọc gói, nhập model kèm theo vào thư viện (không đổi nhân vật đang hiện), rồi
  // tạo thẻ. Tên trùng thì thêm số; model không nhập được thì vẫn nhập thẻ và báo lý do.
  const importPackage = async (file: File | undefined) => {
    if (!file || importing) return;
    setImporting(true);
    setNotice(null);
    let modelId: string | null = null;
    try {
      const { readCardPackage, uniqueName } = await import('./cardPackage');
      const parsed = await readCardPackage(file);
      const warnings = [...parsed.warnings];
      let displayModel = parsed.fields.display_model ?? '';
      if (parsed.model) {
        try {
          const { importCharacter } = await import('../characters/characterImport');
          const prepared = await importCharacter([parsed.model.file], parsed.model.format);
          await library.addPrepared(prepared, false);
          modelId = prepared.model.id;
          displayModel = modelId;
        } catch (reason) {
          warnings.push(`Không nhập được model kèm thẻ: ${errorText(reason, 'model không hợp lệ.')} Thẻ được nhập không kèm model.`);
        }
      }
      const card = await createCard({ ...parsed.fields, name: uniqueName(parsed.fields.name, cards.map(item => item.name)), display_model: displayModel });
      modelId = null;
      toast(`Đã nhập thẻ ${card.name}.`);
      if (warnings.length) setNotice({ error: false, lines: warnings });
    } catch (reason) {
      onFailed(reason);
      setNotice({ error: true, lines: [errorText(reason, 'Chưa nhập được gói thẻ.')] });
      // Thẻ không tạo được (đủ 50 thẻ, trường quá dài…): bỏ model vừa nhập cho nó, khỏi để model mồ côi trong thư viện.
      if (modelId) await library.remove(modelId).catch(() => {});
    } finally {
      setImporting(false);
    }
  };
  const shown = useMemo(() => {
    const words = fold(query.trim());
    const list = cards.filter(card => !words || fold(`${card.name} ${card.nickname} ${card.description}`).includes(words));
    if (sort === 'az') list.sort((a, b) => a.name.localeCompare(b.name, 'vi'));
    else if (sort === 'za') list.sort((a, b) => b.name.localeCompare(a.name, 'vi'));
    else list.sort((a, b) => (a.is_default ? -1 : b.is_default ? 1 : b.created_at - a.created_at));
    return list;
  }, [cards, query, sort]);
  return <>
    <p className="card-lead">Mỗi thẻ là một nhân vật: tên, tính cách, câu chào, model và prompt riêng. Đổi thẻ ở nút Profile trên
      Companion; mỗi hội thoại giữ thẻ nó được tạo cùng.</p>
    <div className="card-toolbar">
      <label className="card-search">
        <Icon>{ICON.search}</Icon>
        <input type="search" placeholder="Tìm thẻ…" aria-label="Tìm thẻ" value={query} onChange={event => setQuery(event.target.value)} />
      </label>
      <Dropdown id="card-sort" ariaLabel="Sắp xếp thẻ" className="compact card-sort" value={sort} options={SORTS} onChange={setSort} />
      <div className="card-toolbar-actions">
        <button type="button" className="card-button" disabled={importing} onClick={() => upload.current?.click()}>
          <Icon>{ICON.upload}</Icon>{importing ? 'Đang nhập…' : 'Nhập thẻ'}</button>
        <button type="button" className="card-button primary" onClick={() => onNavigate('card-new')}><Icon>{ICON.plus}</Icon>Tạo thẻ mới</button>
      </div>
      <input ref={upload} type="file" accept=".zip,application/zip" hidden aria-hidden="true" tabIndex={-1}
        aria-label="Chọn gói thẻ nhân vật (.zip)"
        onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; void importPackage(file); }} />
    </div>
    {notice && (
      <div className={notice.error ? 'card-notice error' : 'card-notice'} role={notice.error ? 'alert' : 'status'}>
        {notice.lines.map(line => <p key={line}>{line}</p>)}
        <button type="button" className="card-icon-button" aria-label="Đóng thông báo" onClick={() => setNotice(null)}><Icon size={16}>{ICON.close}</Icon></button>
      </div>
    )}
    <div className="card-drop-zone"
      onDragEnter={event => { if (!fileDrag(event)) return; event.preventDefault(); setDragDepth(depth => depth + 1); }}
      onDragOver={event => { if (fileDrag(event)) event.preventDefault(); }}
      onDragLeave={event => { if (fileDrag(event)) setDragDepth(depth => Math.max(0, depth - 1)); }}
      onDrop={event => {
        if (!fileDrag(event)) return;
        event.preventDefault();
        setDragDepth(0);
        void importPackage(event.dataTransfer.files[0]);
      }}>
    {shown.length ? (
      <ul className="card-grid" aria-label="Thẻ nhân vật">
        {shown.map((card, index) => {
          const model = modelFor(library, card.display_model);
          return (
            <li key={card.id} style={{ '--delay': `${Math.min(index, 12) * 40}ms` } as CSSProperties}>
              <button type="button" className="card-grid-item" aria-label={`Xem thẻ: ${card.name}`} onClick={() => onNavigate('card', card.id)}>
                <CardPreview model={model} name={card.name} className={card.id === active ? 'card-grid-preview active' : 'card-grid-preview'}>
                  {card.id === active && <span className="card-preview-badge"><ActiveBadge /></span>}
                </CardPreview>
                <span className="card-grid-name">{card.name}</span>
                <span className="card-grid-meta">
                  <span>v{card.version}</span>
                  {card.is_default && <span className="card-badge">Mặc định</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    ) : (
      <div className="card-empty"><strong>Không có thẻ nào khớp</strong><span>Thử một từ khác.</span></div>
    )}
    {dragDepth > 0 && (
      <div className="card-drop-overlay" aria-hidden="true"><Icon size={36}>{ICON.upload}</Icon><span>Thả gói thẻ (.zip) để nhập</span></div>
    )}
    </div>
  </>;
}
type CardPagesNavigate = (page: CompanionSettingsPage, id?: string) => void;

function CardDetail({ card, active, library, toast, onNavigate, onFailed }: {
  card: CompanionCard; active: boolean; library: CharacterLibrary; toast: (text: string) => void;
  onNavigate: CardPagesNavigate; onFailed: (error: unknown) => void;
}) {
  const [confirm, setConfirm] = useState<'delete' | 'reset' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [prompt, setPrompt] = useState(false);
  const [conversations, setConversations] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const model = modelFor(library, card.display_model);
  const keys = useKeyConfigs();

  useEffect(() => {
    if (confirm !== 'delete') return;
    const controller = new AbortController();
    setConversations(null);
    listCompanionConversations(controller.signal)
      .then(body => setConversations(body.conversations.filter(row => row.card_id === card.id).length))
      .catch(onFailed);
    return () => controller.abort();
  }, [confirm, card.id, onFailed]);

  const run = async (action: () => Promise<void>, failure: string) => {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (err) {
      onFailed(err);
      setError(errorText(err, failure));
    } finally {
      setBusy(false);
    }
  };
  const activate = () => run(async () => {
    await pickCompanionCard(card.id);
    if (model && library.selected.id !== model.id) library.select(model.id);
    toast(`Đã chuyển sang ${card.name}. Companion mở hội thoại của thẻ này.`);
  }, 'Chưa đổi được thẻ.');
  const remove = () => run(async () => {
    const deleted = await removeCard(card.id);
    setConfirm(null);
    onNavigate('cards');
    toast(deleted ? `Đã xóa thẻ ${card.name} và ${deleted} hội thoại.` : `Đã xóa thẻ ${card.name}.`);
  }, 'Chưa xóa được thẻ.');
  const reset = () => run(async () => {
    await resetDefaultCard();
    setConfirm(null);
    toast('Thẻ Peto đã về bản gốc.');
  }, 'Chưa khôi phục được thẻ.');
  // Xuất gói như card-detail.vue của AIRI: thẻ cùng model tự nhập của máy này; model có sẵn (Hiyori) chỉ ghi tên.
  const exportPackage = () => run(async () => {
    setExporting(true);
    try {
      const { buildCardPackage, packageFileName } = await import('./cardPackage');
      let missing = false;
      let source: import('./cardPackage').PackageModel = { kind: 'none' };
      if (model?.builtin) source = { kind: 'builtin', id: model.id };
      else if (model) {
        const assets = await getCharacterAssets(model.id);
        if (assets) source = { kind: 'file', name: model.name, format: model.format, assets };
        else missing = true;
      } else missing = !!card.display_model;
      download(await buildCardPackage(card, source), packageFileName(card.name));
      toast(missing ? `Đã xuất thẻ ${card.name}, không kèm model vì trình duyệt này chưa có model đó.` : `Đã xuất thẻ ${card.name}.`);
    } finally {
      setExporting(false);
    }
  }, 'Chưa xuất được thẻ.');

  const brain = card.modules.brain;
  const voiceChoice = card.modules.voice;
  return (
    <div className="card-detail">
      <section className="card-hero">
        <div className="card-hero-text">
          <div className="card-hero-badges">
            {active && <ActiveBadge />}
            {card.is_default && <span className="card-badge">Mặc định</span>}
            <span className="card-muted">v{card.version} · sửa {timeAgo(card.updated_at)}</span>
          </div>
          <p className="card-hero-desc">{card.description || (card.is_default
            ? 'Nhân vật mặc định của Peto Web. Prompt công khai để bạn xem cách viết thẻ biểu cảm và luật trò chuyện.'
            : 'Thẻ chưa có mô tả.')}</p>
          <div className="card-actions">
            <button type="button" className="card-button primary" disabled={active || busy} onClick={() => void activate()}>
              {active ? <><Icon size={16}>{ICON.check}</Icon>Đang dùng</> : 'Dùng thẻ này'}
            </button>
            <button type="button" className="card-button" onClick={() => onNavigate('card-edit', card.id)}><Icon size={16}>{ICON.edit}</Icon>Sửa thẻ</button>
            <button type="button" className="card-button" disabled={busy} onClick={() => void exportPackage()}>
              <Icon size={16}>{ICON.download}</Icon>{exporting ? 'Đang xuất…' : 'Xuất thẻ'}</button>
            <button type="button" className="card-button" onClick={() => setPrompt(true)}><Icon size={16}>{ICON.code}</Icon>Prompt đầy đủ</button>
            {card.is_default
              ? card.modified && <button type="button" className="card-button" disabled={busy} onClick={() => setConfirm('reset')}>
                  <Icon size={16}>{ICON.restore}</Icon>Khôi phục bản gốc</button>
              : <button type="button" className="card-button danger-text" disabled={busy} onClick={() => setConfirm('delete')}>
                  <Icon size={16}>{ICON.trash}</Icon>Xóa</button>}
          </div>
          {error && <p className="card-error" role="alert">{error}</p>}
        </div>
        <CardPreview model={model} missing={model ? undefined : card.display_model || undefined} name={card.name} contain className="card-hero-preview" />
      </section>
      <div className="card-detail-body">
        <div className="card-detail-main">
          {card.description && <Block title="Mô tả"><p>{card.description}</p></Block>}
          {card.notes && <Block title="Ghi chú của người tạo"><p>{card.notes}</p></Block>}
          <Block title="Nhân vật">
            <dl className="card-dl">
              <Row label="Tính cách" value={card.personality} />
              <Row label="Tình huống" value={card.scenario} />
              <Row label="Câu chào" value={card.greetings.join('\n')} />
              <Row label="System prompt" value={card.system_prompt} long />
              <Row label="Chỉ dẫn sau lịch sử" value={card.post_history} />
            </dl>
          </Block>
        </div>
        <aside className="card-detail-aside">
          <Block title="Mô-đun">
            <dl className="card-dl compact">
              <Row label="Model hiển thị" value={model ? `${model.name} · ${model.format === 'vrm' ? 'VRM' : 'Live2D'}`
                : card.display_model ? `${card.display_model} (chưa có trên máy này)` : 'Không có model'} />
              <Row label="Bộ não" value={brainText(brain, keys)} />
              <Row label="Giọng nói" value={voiceText(voiceChoice, keys)} />
              <Row label="Trí nhớ" value={card.is_default ? 'Dùng chung với Trò chuyện' : 'Chưa có (chỉ thẻ Peto dùng trí nhớ)'} />
            </dl>
          </Block>
        </aside>
      </div>
      <Confirm open={confirm === 'delete'} danger busy={busy} title={`Xóa thẻ ${card.name}?`} confirm="Xóa thẻ"
        message={conversations === null ? 'Xóa luôn các hội thoại của thẻ này. Không hoàn tác được.'
          : conversations ? `Xóa luôn ${conversations} hội thoại của thẻ này. Không hoàn tác được.` : 'Thẻ chưa có hội thoại nào. Không hoàn tác được.'}
        onCancel={() => setConfirm(null)} onConfirm={() => void remove()} />
      <Confirm open={confirm === 'reset'} busy={busy} title="Khôi phục thẻ Peto?" confirm="Khôi phục"
        message="Mọi chỗ bạn sửa trên thẻ Peto quay về bản gốc của Peto Web. Hội thoại và trí nhớ vẫn giữ."
        onCancel={() => setConfirm(null)} onConfirm={() => void reset()} />
      {prompt && <PromptDialog card={card} onClose={() => setPrompt(false)} onFailed={onFailed} />}
    </div>
  );
}

function brainText(brain: Record<string, string> | undefined, keys: ReturnType<typeof useKeyConfigs>) {
  if (!brain?.provider) return 'Theo cài đặt chung';
  if (brain.provider === 'peto') return 'Peto';
  const info = chatProvider(brain.provider);
  const name = info?.name ?? brain.provider;
  const here = info && keys[info.id]?.key?.trim() ? '' : ' (máy này chưa có khóa, dùng cài đặt chung)';
  return `${name}${brain.model ? ` · ${brain.model}` : ''}${here}`;
}

function voiceText(choice: Record<string, string> | undefined, keys: ReturnType<typeof useKeyConfigs>) {
  if (!choice?.source) return 'Theo cài đặt chung';
  const voiceName = choice.voice ? ` · ${choice.source === 'official' || choice.source === 'home' ? voiceLabel(choice.voice) : choice.voice}` : '';
  if (choice.source === 'official') return `Giọng Peto${voiceName}`;
  if (choice.source === 'home') return `Máy nhà của Peto${voiceName}`;
  const provider = keyProvider(choice.source);
  const here = provider && keyReady(provider, keys[provider.id]) ? '' : ' (máy này chưa có khóa, dùng cài đặt chung)';
  return `${provider?.name ?? choice.source}${choice.model ? ` · ${choice.model}` : ''}${voiceName}${here}`;
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return <section className="card-block"><h2>{title}</h2>{children}</section>;
}

function Row({ label, value, long }: { label: string; value: string; long?: boolean }) {
  const [open, setOpen] = useState(false);
  const text = value.trim();
  const clipped = long && text.length > 600 && !open;
  return (
    <div className="card-dl-row">
      <dt>{label}</dt>
      <dd className={text ? undefined : 'card-muted'}>
        {text ? <span className={long ? 'card-mono' : undefined}>{clipped ? `${text.slice(0, 600)}…` : text}</span> : 'Để trống'}
        {long && text.length > 600 && <button type="button" className="card-link" onClick={() => setOpen(value => !value)}>
          {open ? 'Thu gọn' : 'Xem hết'}</button>}
      </dd>
    </div>
  );
}

function PromptDialog({ card, onClose, onFailed }: { card: CompanionCard; onClose: () => void; onFailed: (error: unknown) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [state, setState] = useState<{ prompt: string; memory: boolean } | 'loading' | 'error'>('loading');
  const [copied, setCopied] = useState(false);
  useLayoutEffect(() => { ref.current?.showModal(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    getCompanionCardPrompt(card.id, controller.signal).then(setState).catch(error => {
      if (controller.signal.aborted) return;
      onFailed(error);
      setState('error');
    });
    return () => controller.abort();
  }, [card.id, onFailed]);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2200);
    return () => window.clearTimeout(timer);
  }, [copied]);
  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text).then(() => setCopied(true)).catch(() => {});
  };
  return (
    <dialog ref={ref} className="card-dialog wide" aria-labelledby={titleId} onClose={onClose}>
      <div className="card-dialog-head">
        <h2 id={titleId}>Prompt đầy đủ · {card.name}</h2>
        <button type="button" className="card-icon-button" aria-label="Đóng" onClick={() => ref.current?.close()}><Icon size={18}>{ICON.close}</Icon></button>
      </div>
      <p className="card-note">Đúng những gì máy chủ gửi cho AI ở lượt kế tiếp của thẻ, theo thứ tự: phần của thẻ, phần máy chủ tự thêm
        (giờ, hồ sơ{card.is_default ? ', trí nhớ' : ''}), chỉ dẫn sau lịch sử, rồi luật cố định. Lượt có Player hay tra web thì máy chủ
        gắn thêm hướng dẫn công cụ; phần đó không có ở đây.</p>
      {state === 'loading' && <div className="card-loading small"><LoadingIndicator label="Đang ghép prompt" /></div>}
      {state === 'error' && <p className="card-error" role="alert">Chưa tải được prompt. Đóng rồi mở lại thử nhé.</p>}
      {typeof state === 'object' && <>
        <div className="card-prompt-bar">
          <span>{state.prompt.length.toLocaleString('vi-VN')} ký tự · {state.memory ? 'có trí nhớ chung' : 'không dùng trí nhớ chung'}</span>
          <button type="button" className="card-button small" onClick={() => copy(state.prompt)}>
            <Icon size={15}>{copied ? ICON.check : ICON.copy}</Icon>{copied ? 'Đã chép' : 'Chép'}</button>
        </div>
        <pre className="card-prompt" tabIndex={0}>{state.prompt}</pre>
      </>}
    </dialog>
  );
}

interface Draft {
  name: string; nickname: string; version: string; description: string; notes: string; personality: string; scenario: string;
  system_prompt: string; post_history: string; display_model: string; greetings: string;
  brain: { provider: string; model: string };
  voice: { source: string; model: string; voice: string };
}

function toDraft(card: CompanionCard | null, model: string): Draft {
  const brain = card?.modules.brain;
  const voice = card?.modules.voice;
  return {
    name: card?.name ?? '', nickname: card?.nickname ?? '', version: card?.version ?? '1.0.0',
    description: card?.description ?? '', notes: card?.notes ?? '',
    personality: card?.personality ?? NEW_CARD.personality, scenario: card?.scenario ?? NEW_CARD.scenario,
    system_prompt: card?.system_prompt ?? NEW_CARD.system_prompt, post_history: card?.post_history ?? NEW_CARD.post_history,
    display_model: card?.display_model ?? model, greetings: (card?.greetings ?? []).join('\n'),
    brain: { provider: brain?.provider ?? '', model: brain?.model ?? '' },
    voice: { source: voice?.source ?? '', model: voice?.model ?? '', voice: voice?.voice ?? '' },
  };
}

function fields(draft: Draft): CompanionCardFields {
  const modules: CompanionCardFields['modules'] = {};
  if (draft.brain.provider) modules.brain = draft.brain.provider === 'peto' ? { provider: 'peto' }
    : { provider: draft.brain.provider, ...(draft.brain.model ? { model: draft.brain.model } : {}) };
  if (draft.voice.source) modules.voice = { source: draft.voice.source,
    ...(draft.voice.model ? { model: draft.voice.model } : {}), ...(draft.voice.voice ? { voice: draft.voice.voice } : {}) };
  return {
    name: draft.name.trim(), nickname: draft.nickname.trim(), version: draft.version.trim(), description: draft.description,
    notes: draft.notes, personality: draft.personality, scenario: draft.scenario, system_prompt: draft.system_prompt,
    post_history: draft.post_history, display_model: draft.display_model,
    greetings: draft.greetings.split('\n').map(line => line.trim()).filter(Boolean), modules,
  };
}

/** Chỉ các trường khác bản đang lưu, để thẻ Peto còn theo bản gốc ở những ô người dùng không đụng tới. */
function changed(next: CompanionCardFields, current: CompanionCard | null): CompanionCardFields {
  if (!current) return next;
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(next)) {
    if (JSON.stringify(value) !== JSON.stringify(current[key as keyof CompanionCard])) result[key] = value;
  }
  return result as CompanionCardFields;
}

function CardEditor({ card, active, names, library, voice, actions, guard, toast, onNavigate, onFailed }: {
  card: CompanionCard | null; active: boolean; names: CompanionCard[]; library: CharacterLibrary; voice: LocalVoice;
  actions: HTMLElement | null; guard: LeaveGuard; toast: (text: string) => void; onNavigate: CardPagesNavigate;
  onFailed: (error: unknown) => void;
}) {
  const [params, setParams] = useSearchParams();
  const requested = params.get('section');
  const section: Section = SECTIONS.some(item => item.id === requested) ? requested as Section : 'identity';
  const [initial] = useState(() => toDraft(card, library.selected.id));
  const [draft, setDraft] = useState(initial);
  const [tried, setTried] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [leaving, setLeaving] = useState<(() => void) | null>(null);
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft(current => ({ ...current, [key]: value }));
  const setSection = (next: Section) => setParams(value => {
    const copy = new URLSearchParams(value);
    if (next === 'identity') copy.delete('section'); else copy.set('section', next);
    return copy;
  }, { replace: true });

  const name = draft.name.trim();
  const nameError = !name ? 'Cần đặt tên cho thẻ.'
    : names.some(item => item.id !== card?.id && item.name.toLocaleLowerCase('vi') === name.toLocaleLowerCase('vi')) ? `Đã có thẻ tên "${name}".` : '';
  const versionError = draft.version.trim() ? '' : 'Cần có phiên bản, ví dụ 1.0.0.';
  const greetings = draft.greetings.split('\n').filter(line => line.trim());
  const greetingError = greetings.length > MAX_GREETINGS ? `Mỗi thẻ có tối đa ${MAX_GREETINGS} câu chào.` : '';
  const promptChars = draft.system_prompt.length + draft.description.length + draft.personality.length + draft.scenario.length
    + draft.post_history.length;
  const promptError = promptChars > MAX_PROMPT_CHARS ? `Phần prompt dài quá ${MAX_PROMPT_CHARS.toLocaleString('vi-VN')} ký tự cộng lại.` : '';

  // Nút quay lại của trang cài đặt và tải lại trang: hỏi trước khi bỏ chỗ đang sửa (như hộp "Discard changes?" của AIRI).
  useEffect(() => {
    guard.current = dirty ? go => setLeaving(() => go) : null;
    return () => { guard.current = null; };
  }, [dirty, guard]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const save = async (activate: boolean) => {
    setTried(true);
    setError('');
    if (nameError || versionError) { setSection('identity'); return; }
    if (greetingError) { setSection('behavior'); return; }
    if (promptError) { setSection('prompt'); return; }
    setSaving(true);
    try {
      const next = fields(draft);
      const saved = card ? await saveCard(card.id, changed(next, card)) : await createCard(next);
      const shown = modelFor(library, saved.display_model);
      if (activate) await pickCompanionCard(saved.id);
      // Thẻ đang dùng đổi model hiển thị: sân khấu đổi theo, nếu máy này có model đó.
      if ((activate || active) && shown && library.selected.id !== shown.id) library.select(shown.id);
      guard.current = null;
      toast(activate ? `Đã lưu và chuyển sang ${saved.name}.` : 'Đã lưu thẻ.');
      onNavigate('card', saved.id);
    } catch (err) {
      onFailed(err);
      setError(errorText(err, 'Chưa lưu được thẻ.'));
    } finally {
      setSaving(false);
    }
  };

  const model = modelFor(library, draft.display_model);
  const modelOptions: DropdownOption[] = library.models.map(item => ({ value: item.id, label: item.name,
    hint: item.format === 'vrm' ? 'VRM · 3D' : 'Live2D · 2D' }));
  if (draft.display_model && !model) modelOptions.push({ value: draft.display_model, label: draft.display_model, hint: 'Chưa có trên máy này' });

  const buttons = (
    <>
      {dirty && <span className="card-badge warn">Chưa lưu</span>}
      <button type="button" className={active ? 'card-button primary' : 'card-button'} disabled={saving} onClick={() => void save(false)}>
        {card ? 'Lưu' : 'Tạo thẻ'}</button>
      {!active && <button type="button" className="card-button primary" disabled={saving} onClick={() => void save(true)}>
        {card ? 'Lưu và dùng' : 'Tạo và dùng'}</button>}
    </>
  );

  return (
    <div className="card-editor">
      {actions && createPortal(buttons, actions)}
      {error && <p className="card-error banner" role="alert">{error}</p>}
      <section className="card-editor-hero">
        <div className="card-editor-hero-fields">
          <div className="card-field-row">
            <TextField id="card-name" label="Tên" required value={draft.name} max={LIMITS.name} onChange={value => set('name', value)}
              error={tried ? nameError : ''} placeholder="Ví dụ: Mika" />
            <TextField id="card-nickname" label="Biệt danh" value={draft.nickname} max={LIMITS.nickname}
              onChange={value => set('nickname', value)} hint="Có biệt danh thì nhân vật xưng bằng tên này ({{char}})." />
          </div>
          <div className="card-field-row">
            <div className="card-field">
              <label id="card-model-label" htmlFor="card-model">Model hiển thị</label>
              <Dropdown id="card-model" value={draft.display_model} options={modelOptions} onChange={value => set('display_model', value)} />
              <small>Nhập model mới ở trang Nhân vật. Model nằm trong trình duyệt này, thẻ chỉ ghi tên model.</small>
            </div>
            <TextField id="card-version" label="Phiên bản" required value={draft.version} max={LIMITS.version}
              onChange={value => set('version', value)} error={tried ? versionError : ''} hint="Tăng lên khi sửa từ một thẻ cũ." />
          </div>
        </div>
        <CardPreview model={model} missing={model ? undefined : draft.display_model || undefined} name={name || 'Thẻ mới'} contain
          className="card-editor-preview" />
      </section>
      <div className="card-editor-body">
        <nav className="card-editor-nav" aria-label="Mục của thẻ">
          {SECTIONS.map(item => (
            <button key={item.id} type="button" className={item.id === section ? 'on' : undefined}
              aria-current={item.id === section ? 'page' : undefined} onClick={() => setSection(item.id)}>
              <Icon>{item.icon}</Icon>{item.label}
            </button>
          ))}
        </nav>
        <div key={section} className="card-editor-section">
          {section === 'identity' && <>
            <p className="card-note">Nhân vật là ai, câu chuyện và hoàn cảnh của họ. Mô tả được gửi cho AI; ghi chú thì không.</p>
            <TextField id="card-description" label="Mô tả" rows={4} value={draft.description} max={LIMITS.description}
              onChange={value => set('description', value)} />
            <TextField id="card-notes" label="Ghi chú của người tạo" rows={2} value={draft.notes} max={LIMITS.notes}
              onChange={value => set('notes', value)} hint="Chỉ để bạn đọc." />
          </>}
          {section === 'behavior' && <>
            <p className="card-note">Cách nhân vật cư xử và mở đầu cuộc trò chuyện.</p>
            <TextField id="card-personality" label="Tính cách" rows={3} value={draft.personality} max={LIMITS.personality}
              onChange={value => set('personality', value)} hint="Rụt rè? Tò mò? Nói nhanh hay chậm?" />
            <TextField id="card-scenario" label="Tình huống" rows={3} value={draft.scenario} max={LIMITS.scenario}
              onChange={value => set('scenario', value)} hint="Xung quanh có gì, chuyện gì đang diễn ra lúc bắt đầu." />
            <TextField id="card-greetings" label="Câu chào" rows={3} value={draft.greetings} error={tried ? greetingError : ''}
              onChange={value => set('greetings', value)} hint={`Mỗi dòng một câu, tối đa ${MAX_GREETINGS} câu. Hội thoại mới mở bằng câu đầu tiên.`} />
          </>}
          {section === 'modules' && <ModuleFields draft={draft} voice={voice} onChange={set} />}
          {section === 'prompt' && <>
            <TextField id="card-system" label="System prompt" rows={10} mono value={draft.system_prompt} max={LIMITS.system_prompt}
              onChange={value => set('system_prompt', value)}
              hint="Dặn AI cách trả lời. {{char}} là tên nhân vật, {{user}} là tên bạn. Cách dùng thẻ biểu cảm <|EMOTE_…|> xem trong thẻ Peto." />
            <TextField id="card-post" label="Chỉ dẫn sau lịch sử" rows={2} mono value={draft.post_history} max={LIMITS.post_history}
              onChange={value => set('post_history', value)} hint="AI đọc phần này sau mọi phần khác của prompt, ngay trước khi trả lời." />
            <p className={promptError ? 'card-count over' : 'card-count'}>
              {promptChars.toLocaleString('vi-VN')} / {MAX_PROMPT_CHARS.toLocaleString('vi-VN')} ký tự prompt (system prompt, mô tả,
              tính cách, tình huống, chỉ dẫn sau lịch sử){tried && promptError ? `. ${promptError}` : ''}</p>
            <div className="card-rule">
              <strong><Icon size={16}>{ICON.lock}</Icon> Luật cố định của Peto Web</strong>
              <span>Luôn gắn vào cuối prompt của mọi thẻ, không sửa được: không viết nội dung tình dục liên quan tới người dưới 18 tuổi,
                kể cả nhân vật được tả là hay trông như trẻ vị thành niên.</span>
            </div>
          </>}
        </div>
      </div>
      <Confirm open={!!leaving} danger title="Bỏ thay đổi?" message="Thay đổi chưa được lưu. Rời trang này thì mất." cancel="Sửa tiếp"
        confirm="Bỏ thay đổi" onCancel={() => setLeaving(null)}
        onConfirm={() => { const go = leaving; setLeaving(null); guard.current = null; go?.(); }} />
    </div>
  );
}

function TextField({ id, label, hint, value, onChange, error, required, rows, max, placeholder, mono }: {
  id: string; label: string; hint?: string; value: string; onChange: (value: string) => void; error?: string;
  required?: boolean; rows?: number; max?: number; placeholder?: string; mono?: boolean;
}) {
  const area = useRef<HTMLTextAreaElement>(null);
  // Ô nhiều dòng cao theo nội dung (tới 60% màn hình), để đọc trọn prompt dài mà không cuộn hai lớp.
  useLayoutEffect(() => {
    const node = area.current;
    if (!node) return;
    node.style.height = 'auto';
    node.style.height = `${Math.min(node.scrollHeight + 2, window.innerHeight * 0.6)}px`;
  }, [value]);
  const describedBy = [hint ? `${id}-hint` : '', error ? `${id}-error` : ''].filter(Boolean).join(' ') || undefined;
  return (
    <div className={error ? 'card-field invalid' : 'card-field'}>
      <label htmlFor={id}>{label}{required && <span className="card-required" aria-hidden="true"> *</span>}</label>
      {hint && <small id={`${id}-hint`}>{hint}</small>}
      {rows
        ? <textarea ref={area} id={id} className={mono ? 'text-field mono' : 'text-field'} rows={rows} value={value} maxLength={max}
            placeholder={placeholder} aria-invalid={!!error || undefined} aria-describedby={describedBy}
            onChange={event => onChange(event.target.value)} />
        : <input id={id} className="text-field" value={value} maxLength={max} placeholder={placeholder} aria-invalid={!!error || undefined}
            aria-required={required || undefined} aria-describedby={describedBy} onChange={event => onChange(event.target.value)} />}
      {error && <span id={`${id}-error`} className="card-error-text">{error}</span>}
    </div>
  );
}

/**
 * Mô-đun của thẻ (Modules của CardEditor.vue): bộ não và giọng riêng; để trống là theo cài đặt chung. Chỉ liệt kê nhà cung
 * cấp đã có khóa trên máy này; thẻ đồng bộ từ máy khác mà chọn nhà máy này chưa có thì vẫn giữ lựa chọn, máy này dùng cài
 * đặt chung.
 */
function ModuleFields({ draft, voice, onChange }: {
  draft: Draft; voice: LocalVoice; onChange: <K extends keyof Draft>(key: K, value: Draft[K]) => void;
}) {
  const keys = useKeyConfigs();
  const models = useModels();
  const brainProviders = CHAT_PROVIDERS.filter(item => connected(item.id, keys[item.id], models));
  const brainOptions: DropdownOption[] = [
    { value: '', label: 'Theo cài đặt chung', hint: 'Bộ não chọn ở Mô-đun → Bộ não' },
    { value: 'peto', label: 'Peto', hint: 'Grok qua tài khoản Peto' },
    ...brainProviders.map(item => ({ value: item.id, label: item.name, hint: 'Khóa của bạn', group: 'Khóa của bạn' })),
  ];
  if (draft.brain.provider && !brainOptions.some(option => option.value === draft.brain.provider)) {
    brainOptions.push({ value: draft.brain.provider, label: chatProvider(draft.brain.provider)?.name ?? draft.brain.provider,
      hint: 'Máy này chưa kết nối; dùng cài đặt chung', group: 'Khóa của bạn' });
  }
  const brainInfo = chatProvider(draft.brain.provider);
  const brainModels = brainInfo ? brainInfo.id === 'azure-openai' ? [] : models[brainInfo.id] ?? [] : [];
  const brainModelOptions: DropdownOption[] = [{ value: '', label: 'Model đầu tiên của nhà cung cấp' },
    ...brainModels.map(item => ({ value: item, label: item }))];
  if (draft.brain.model && !brainModels.includes(draft.brain.model)) brainModelOptions.push({ value: draft.brain.model, label: draft.brain.model });

  const sourceOptions: DropdownOption[] = [
    { value: '', label: 'Theo cài đặt chung', hint: 'Giọng chọn ở Mô-đun → Giọng nói' },
    { value: 'official', label: 'Giọng Peto', group: 'Của Peto' },
    { value: 'home', label: 'Máy nhà của Peto', group: 'Của Peto' },
    ...KEY_PROVIDERS.filter(item => keyReady(item, keys[item.id])).map(item => ({ value: item.id, label: item.name, group: 'Khóa của bạn' })),
  ];
  if (draft.voice.source && !sourceOptions.some(option => option.value === draft.voice.source)) {
    sourceOptions.push({ value: draft.voice.source, label: keyProvider(draft.voice.source)?.name ?? draft.voice.source,
      hint: 'Máy này chưa có khóa; dùng cài đặt chung', group: 'Khóa của bạn' });
  }
  const provider = keyProvider(draft.voice.source);
  const voiceModel = provider ? draft.voice.model || provider.models?.[0] || '' : '';
  const voiceList: DropdownOption[] = draft.voice.source === 'official'
    ? (voice.health?.official.voices ?? []).map(id => ({ value: id, label: voiceLabel(id) }))
    : draft.voice.source === 'home'
      ? (voice.health?.home.voices ?? Object.keys(VOICE_LABELS)).map(id => ({ value: id, label: voiceLabel(id) }))
      : provider ? suggestedVoices(provider, voiceModel).map(item => ({ value: item.id, label: item.label, hint: item.hint, group: item.group })) : [];
  if (draft.voice.voice && !voiceList.some(option => option.value === draft.voice.voice)) {
    voiceList.unshift({ value: draft.voice.voice, label: provider ? draft.voice.voice : voiceLabel(draft.voice.voice) });
  }
  const voiceOptions: DropdownOption[] = [{ value: '', label: 'Giọng đang chọn ở trang Giọng nói' }, ...voiceList];
  const modelOptions: DropdownOption[] = provider?.models?.length
    ? [{ value: '', label: 'Model đang chọn ở trang Giọng nói' },
        ...provider.models.map(item => ({ value: item, label: provider.modelInfo?.[item]?.label ?? item, hint: provider.modelInfo?.[item]?.hint }))]
    : [];

  return <>
    <p className="card-note">Để trống thì thẻ theo cài đặt chung ở Mô-đun. Khóa API vẫn nằm trong trình duyệt (Nhà cung cấp); thẻ chỉ
      ghi nhớ lựa chọn, nên máy chưa có khóa đó dùng cài đặt chung.</p>
    <h3 className="card-subhead">Bộ não</h3>
    <div className="card-field-row">
      <div className="card-field">
        <label id="card-brain-label" htmlFor="card-brain">Nhà cung cấp</label>
        <Dropdown id="card-brain" value={draft.brain.provider} options={brainOptions}
          onChange={value => onChange('brain', { provider: value, model: '' })} />
      </div>
      {brainInfo && brainInfo.id !== 'azure-openai' && (
        <div className="card-field">
          <label id="card-brain-model-label" htmlFor="card-brain-model">Model</label>
          <Dropdown id="card-brain-model" value={draft.brain.model} options={brainModelOptions}
            onChange={value => onChange('brain', { ...draft.brain, model: value })} />
        </div>
      )}
    </div>
    <h3 className="card-subhead">Giọng nói</h3>
    <div className="card-field-row">
      <div className="card-field">
        <label id="card-voice-source-label" htmlFor="card-voice-source">Nguồn giọng</label>
        <Dropdown id="card-voice-source" value={draft.voice.source} options={sourceOptions}
          onChange={value => onChange('voice', { source: value, model: '', voice: '' })} />
      </div>
      {provider && modelOptions.length > 0 && (
        <div className="card-field">
          <label id="card-voice-model-label" htmlFor="card-voice-model">Model giọng</label>
          <Dropdown id="card-voice-model" value={draft.voice.model} options={modelOptions}
            onChange={value => onChange('voice', { ...draft.voice, model: value, voice: '' })} />
        </div>
      )}
    </div>
    {draft.voice.source && (
      <div className="card-field">
        <label id="card-voice-label" htmlFor="card-voice">Giọng</label>
        <Dropdown id="card-voice" value={draft.voice.voice} options={voiceOptions} editable={!!provider} emptyValue=""
          placeholder="Giọng đang chọn ở trang Giọng nói" onChange={value => onChange('voice', { ...draft.voice, voice: value })} />
        {!provider && !voice.health && <small>Bật giọng nói ở Mô-đun → Giọng nói để thấy danh sách giọng của máy chủ.</small>}
      </div>
    )}
  </>;
}
