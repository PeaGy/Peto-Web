import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  UnauthorizedError,
  clearCompanionMemory,
  createCompanionMemory,
  deleteCompanionMemory,
  getCompanionMemory,
  setCompanionMemoryEnabled,
  tellCompanionMemory,
  updateCompanionMemory,
  type CompanionMemory,
  type CompanionMemoryState,
  type MemorySection,
} from "../../shared/api/api";
import { LoadingIndicator } from "../../shared/ui/LoadingIndicator";
import { SettingsGroup, SettingsIcon, SettingsRow, SettingsSwitch } from "./settingsUi";

/*
 * Mục Trí nhớ trong Cài đặt, kiểu "Như Claude" chủ web chọn từ ba bản mẫu ngày 15/10/2026 (theo trang Memory của Claude):
 * các mục chia ba nhóm Bạn, Chủ đề, Lĩnh vực; mỗi hàng có tên, dòng tóm tắt và ngày cập nhật, rê chuột thì hiện Sửa và
 * Xóa. Bấm một hàng là sang trang chi tiết (tóm tắt, các ý, sửa tay, xóa), cuối trang có ô bảo Peto đổi hay bỏ điều gì;
 * cuối danh sách có ô bảo Peto nhớ điều mới. Máy chủ đọc lại trí nhớ ở mỗi lượt Chat và Companion, nên đổi gì ở đây là
 * lượt sau Peto theo đó. Trang Cài đặt Companion (/companion/settings/memory) dùng lại đúng component này.
 */

const SECTIONS: { id: MemorySection; title: string }[] = [
  { id: "you", title: "Bạn" },
  { id: "topic", title: "Chủ đề" },
  { id: "area", title: "Lĩnh vực" },
];
const SECTION_TITLES: Record<MemorySection, string> = { you: "Bạn", topic: "Chủ đề", area: "Lĩnh vực" };
/** Mỗi mục tối đa ngần này ý (mục "Ghi nhớ cũ" giữ được cả danh sách cũ), như máy chủ. */
const MAX_DETAILS = 12;
const MAX_LEGACY_DETAILS = 60;
/** Peto đang xếp ghi nhớ cũ thì hỏi lại sau ngần này mili giây, tối đa SORT_POLLS lần. */
const SORT_POLL_MS = 4000;
const SORT_POLLS = 10;

interface ToastState { text: string; action?: string; onAction?: () => void }

function dayStart(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** "hôm nay", "hôm qua" hay "14 thg 10" theo đồng hồ của trình duyệt. */
function shortDate(seconds: number): string {
  const date = new Date(seconds * 1000);
  const days = Math.round((dayStart(new Date()) - dayStart(date)) / 86_400_000);
  if (days <= 0) return "hôm nay";
  if (days === 1) return "hôm qua";
  return date.toLocaleDateString("vi-VN", { day: "numeric", month: "short" });
}

function longDate(seconds: number): string {
  return new Date(seconds * 1000).toLocaleDateString("vi-VN", { day: "numeric", month: "long", year: "numeric" });
}

/** Lỗi từ máy chủ đã là câu tiếng Việt; mất mạng thì fetch ném TypeError chữ tiếng Anh, nên dùng câu của mình. */
function message(err: unknown, fallback: string): string {
  return err instanceof Error && !(err instanceof TypeError) ? err.message : fallback;
}

const SEND = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
);

/**
 * Ô "bảo Peto" như ô cuối trang Trí nhớ của Claude: Enter gửi, Shift+Enter xuống dòng. Chữ chỉ xóa khi Peto đã làm
 * xong; lỗi thì giữ lại để gửi lại.
 */
function TellBox({ label, placeholder, disabled, onSend }: {
  label: string;
  placeholder: string;
  disabled?: boolean;
  onSend: (text: string) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    const value = text.trim();
    if (!value || busy || disabled) return;
    setBusy(true);
    try {
      if (await onSend(value)) setText("");
    } finally {
      setBusy(false);
    }
  }

  function keydown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  }

  return (
    <div className="memory-tell" data-busy={busy || undefined}>
      <textarea
        rows={1}
        aria-label={label}
        placeholder={busy ? "Peto đang cập nhật trí nhớ…" : placeholder}
        value={busy ? "" : text}
        disabled={disabled || busy}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={keydown}
      />
      <button type="button" className="memory-send" aria-label="Gửi cho Peto" data-tip
        disabled={!text.trim() || busy || disabled} onClick={() => void send()}>
        {busy ? <span className="memory-dots" aria-hidden="true"><i /><i /><i /></span> : SEND}
      </button>
    </div>
  );
}

/** Thông báo ngắn trên ô bảo Peto: "Đã xóa … · Hoàn tác", "Đã thêm vào … · Xem". Tự tắt sau 6 giây. */
function Toast({ toast, onDone }: { toast: ToastState; onDone: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onDone, 6000);
    return () => window.clearTimeout(timer);
  }, [toast, onDone]);
  return (
    <div className="memory-toast" role="status">
      <span>{toast.text}</span>
      {toast.action && <button type="button" onClick={toast.onAction}>{toast.action}</button>}
    </div>
  );
}

/** Trang chi tiết một mục: tóm tắt, các ý, sửa tay, xóa, và ô bảo Peto đổi hay bỏ điều gì trong mục này. */
function EntryDetail({ entry, enabled, startEditing, fresh, onBack, onSave, onDelete, onTell }: {
  entry: CompanionMemory;
  enabled: boolean;
  startEditing: boolean;
  /** Vị trí các ý Peto vừa thêm hay sửa, để tô sáng một lúc. */
  fresh: number[];
  onBack: () => void;
  onSave: (patch: { title?: string; summary?: string; details?: string[] }) => Promise<string | null>;
  onDelete: () => void;
  onTell: (text: string) => Promise<string | null>;
}) {
  const [editing, setEditing] = useState(startEditing);
  const [title, setTitle] = useState(entry.title);
  const [summary, setSummary] = useState(entry.summary);
  const [details, setDetails] = useState(entry.details.join("\n"));
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const headRef = useRef<HTMLHeadingElement>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const summaryId = useId();
  const detailsId = useId();
  const limit = entry.legacy ? MAX_LEGACY_DETAILS : MAX_DETAILS;

  // Mở trang là đưa tiêu điểm vào tên mục, như sang một trang mới; bắt đầu sửa thì vào ô đầu tiên, thôi sửa thì về tên
  // mục. Không để tiêu điểm rơi ra ngoài khi ô nhập biến mất: lúc đó Esc kế tiếp sẽ đóng cả hộp Cài đặt.
  useEffect(() => {
    if (editing) firstFieldRef.current?.focus({ preventScroll: true });
    else headRef.current?.focus({ preventScroll: true });
  }, [editing]);

  function beginEdit() {
    setTitle(entry.title);
    setSummary(entry.summary);
    setDetails(entry.details.join("\n"));
    setEditError(null);
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setEditError(null);
  }

  async function save() {
    const lines = details.split("\n").map((line) => line.replace(/^\s*[-•*]\s*/, "").trim()).filter(Boolean);
    if (!lines.length) { setEditError("Mục cần ít nhất một ý. Muốn bỏ cả mục thì bấm Xóa."); return; }
    if (lines.length > limit) { setEditError(`Mỗi mục tối đa ${limit} ý.`); return; }
    setSaving(true);
    setEditError(null);
    const failure = await onSave({
      ...(entry.fixed ? {} : { title: title.trim() || entry.title }),
      summary: summary.trim() || entry.summary,
      details: lines,
    });
    setSaving(false);
    if (failure) { setEditError(failure); return; }
    cancelEdit();
  }

  async function tell(text: string): Promise<boolean> {
    setNote(null);
    const result = await onTell(text);
    if (result !== null) setNote(result);
    return result !== null;
  }

  function keydown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Escape" || event.defaultPrevented) return;
    // Esc lùi một bước (thôi sửa, rồi về danh sách) thay vì đóng cả hộp Cài đặt.
    event.preventDefault();
    event.stopPropagation();
    if (editing) cancelEdit();
    else onBack();
  }

  return (
    <div className="settings-group memory-detail" onKeyDown={keydown}>
      <button type="button" className="memory-back" onClick={onBack}>
        <SettingsIcon name="chevronLeft" size={16} />Trí nhớ
      </button>
      <div className="memory-detail-head">
        <div className="memory-detail-name">
          <span className="memory-kicker">{entry.legacy ? "Chưa xếp mục" : SECTION_TITLES[entry.section]}</span>
          <h3 ref={headRef} tabIndex={-1}>{entry.title}</h3>
        </div>
        <div className="memory-detail-actions">
          {!editing && (
            <button type="button" className="settings-button" onClick={beginEdit}>
              <SettingsIcon name="pencil" size={16} />Sửa
            </button>
          )}
          <button type="button" className="settings-button danger" onClick={onDelete}>Xóa</button>
        </div>
      </div>

      <dl className={enabled ? "memory-facts" : "memory-facts off"}>
        <dt>Cập nhật lần cuối</dt>
        <dd>{longDate(entry.updated_at)}</dd>
        {editing && !entry.fixed && (
          <>
            <dt><label htmlFor={titleId}>Tên mục</label></dt>
            <dd>
              <input id={titleId} ref={firstFieldRef} className="settings-input memory-input" maxLength={60}
                value={title} onChange={(event) => setTitle(event.target.value)} />
            </dd>
          </>
        )}
        <dt>{editing ? <label htmlFor={summaryId}>Tóm tắt</label> : "Tóm tắt"}</dt>
        <dd>
          {editing ? (
            <input id={summaryId} ref={entry.fixed ? firstFieldRef : undefined} className="settings-input memory-input"
              maxLength={150} value={summary} onChange={(event) => setSummary(event.target.value)} />
          ) : entry.summary}
        </dd>
        <dt>{editing ? <label htmlFor={detailsId}>Chi tiết · mỗi dòng một ý</label> : "Chi tiết"}</dt>
        <dd>
          {editing ? (
            <>
              <textarea id={detailsId} className="settings-input settings-textarea memory-input"
                rows={Math.min(14, Math.max(5, entry.details.length + 1))}
                value={details} onChange={(event) => setDetails(event.target.value)} />
              {editError && <p className="voice-error" role="alert">{editError}</p>}
              <div className="memory-edit-actions">
                <button type="button" className="settings-button" onClick={cancelEdit}>Hủy</button>
                <button type="button" className="settings-button primary" disabled={saving} onClick={() => void save()}>
                  {saving ? "Đang lưu…" : "Lưu"}
                </button>
              </div>
            </>
          ) : (
            <ul className="memory-bullets">
              {entry.details.map((detail, index) => (
                <li key={`${index}-${detail}`} data-fresh={fresh.includes(index) || undefined}>{detail}</li>
              ))}
            </ul>
          )}
        </dd>
      </dl>

      {!editing && (
        <div className="memory-dock">
          {note && <p className="memory-note" role="status">{note}</p>}
          <TellBox
            label={`Bảo Peto đổi hay bỏ điều gì trong ${entry.title}`}
            placeholder="Bảo Peto đổi hay bỏ điều gì"
            disabled={!enabled}
            onSend={tell}
          />
        </div>
      )}
    </div>
  );
}

/**
 * Mục Trí nhớ. `open`: mục đang được xem; lúc đó mới tải danh sách (mở lại là tải lại, vì lượt vừa xong có thể vừa ghi
 * thêm).
 */
export default function MemorySettings({ open, onUnauthorized }: {
  open: boolean;
  onUnauthorized: () => void;
}) {
  const [state, setState] = useState<CompanionMemoryState | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [view, setView] = useState<{ id: number; editing: boolean } | null>(null);
  const [fresh, setFresh] = useState<{ id: number; indices: number[] } | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const loadVersion = useRef(0);
  const polls = useRef(0);
  const returnTo = useRef<number | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const switchId = useId();
  const latest = useRef(state);
  latest.current = state;

  const load = useCallback((signal?: AbortSignal) => {
    const version = ++loadVersion.current;
    setLoadFailed(false);
    getCompanionMemory(signal).then(
      (result) => { if (version === loadVersion.current) setState(result); },
      (err: unknown) => {
        if (version !== loadVersion.current || signal?.aborted) return;
        if (err instanceof UnauthorizedError) { onUnauthorized(); return; }
        setLoadFailed(true);
      },
    );
  }, [onUnauthorized]);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setConfirmClear(false);
    polls.current = 0;
    load(controller.signal);
    return () => {
      loadVersion.current += 1;
      controller.abort();
    };
  }, [open, load]);

  // Peto đang xếp ghi nhớ cũ vào từng mục: hỏi lại sau vài giây cho tới khi xong.
  useEffect(() => {
    if (!open || !state?.sorting || polls.current >= SORT_POLLS) return;
    const timer = window.setTimeout(() => { polls.current += 1; load(); }, SORT_POLL_MS);
    return () => window.clearTimeout(timer);
  }, [open, state, load]);

  const entry = view ? state?.memories.find((item) => item.id === view.id) : undefined;
  // Mục đang xem không còn (vừa xóa, hay tải lại thấy đã mất) thì về danh sách.
  useEffect(() => { if (view && state && !entry) setView(null); }, [view, state, entry]);

  // Về danh sách thì tiêu điểm trở lại đúng hàng vừa mở.
  useLayoutEffect(() => {
    if (view || returnTo.current === null) return;
    rootRef.current?.querySelector<HTMLElement>(`[data-entry="${returnTo.current}"] .memory-row-main`)
      ?.focus({ preventScroll: true });
    returnTo.current = null;
  }, [view]);

  const unauthorized = useCallback((err: unknown) => {
    if (err instanceof UnauthorizedError) { onUnauthorized(); return true; }
    return false;
  }, [onUnauthorized]);

  async function run(action: () => Promise<void>, rollback: CompanionMemoryState | null, failure: string) {
    setError(null);
    setBusy(true);
    try {
      await action();
    } catch (err) {
      if (unauthorized(err)) return;
      setState(rollback);
      setError(message(err, failure));
    } finally {
      setBusy(false);
    }
  }

  function show(id: number, editing = false) {
    returnTo.current = id;
    setToast(null);
    setError(null);
    setFresh(null);
    setView({ id, editing });
  }

  function back() {
    setFresh(null);
    setView(null);
  }

  function toggle(enabled: boolean) {
    if (!state) return;
    const before = state;
    setState({ ...state, enabled });
    void run(() => setCompanionMemoryEnabled(enabled), before, "Chưa đổi được. Thử lại sau nha.");
  }

  function forgetAll() {
    if (!state) return;
    const before = state;
    setConfirmClear(false);
    setToast(null);
    setState({ ...state, memories: [] });
    void run(clearCompanionMemory, before, "Chưa xóa được. Thử lại sau nha.");
  }

  async function restore(item: CompanionMemory) {
    setToast(null);
    try {
      const created = await createCompanionMemory(item);
      const current = latest.current;
      if (current) setState({ ...current, memories: [...current.memories, created] });
    } catch (err) {
      if (!unauthorized(err)) setError(message(err, "Chưa hoàn tác được. Thử lại sau nha."));
    }
  }

  function remove(item: CompanionMemory) {
    if (!state) return;
    const before = state;
    setView(null);
    setToast(null);
    setState({ ...state, memories: state.memories.filter((other) => other.id !== item.id) });
    void run(async () => {
      await deleteCompanionMemory(item.id);
      setToast({ text: `Đã xóa “${item.title}”.`, action: "Hoàn tác", onAction: () => void restore(item) });
    }, before, "Chưa xóa được mục này.");
  }

  async function save(item: CompanionMemory, patch: { title?: string; summary?: string; details?: string[] }) {
    try {
      const updated = await updateCompanionMemory(item.id, patch);
      const current = latest.current;
      if (current) setState({ ...current, memories: current.memories.map((other) => other.id === item.id ? updated : other) });
      return null;
    } catch (err) {
      if (unauthorized(err)) return null;
      return message(err, "Chưa lưu được. Thử lại sau nha.");
    }
  }

  /** Bảo Peto: trả về câu báo của Peto, hay null khi không làm được (lỗi đã hiện). */
  async function tell(text: string, entryId?: number): Promise<string | null> {
    setError(null);
    try {
      const result = await tellCompanionMemory(text, entryId);
      const current = latest.current;
      if (current) setState({ ...current, memories: result.memories });
      const target = result.changes.find((change) => change.kind !== "delete");
      if (entryId !== undefined) {
        const own = result.changes.find((change) => change.id === entryId);
        if (own?.kind === "delete") {
          setView(null);
          setToast({ text: result.message });
        } else {
          setFresh(own ? { id: entryId, indices: own.fresh } : null);
        }
      } else {
        setToast({
          text: result.message,
          ...(target ? {
            action: "Xem",
            onAction: () => { show(target.id); setFresh({ id: target.id, indices: target.fresh }); },
          } : {}),
        });
      }
      return result.message;
    } catch (err) {
      if (unauthorized(err)) return null;
      setError(message(err, "Peto chưa cập nhật được trí nhớ. Thử lại sau nha."));
      return null;
    }
  }

  const dismissToast = useCallback(() => setToast(null), []);
  const memories = state?.memories ?? [];
  const ideas = memories.reduce((sum, item) => sum + item.details.length, 0);
  const intro = "Peto ghi lại điều bạn kể trong Chat và Companion, kể cả cách bạn muốn được xưng hô, để lần sau nhớ.";
  const hint = !state ? intro
    : !state.available ? "Chủ web đã tắt trí nhớ trên máy chủ này."
    : state.enabled ? `${intro} Chỉ bạn thấy trang này; xóa điều gì là Peto quên điều đó.`
    : "Đang tắt: Peto không ghi thêm và không dùng các ghi nhớ bên dưới.";

  if (state?.available && entry && view) {
    return (
      <div className="memory-page" ref={rootRef}>
        <EntryDetail
          key={entry.id}
          entry={entry}
          enabled={state.enabled}
          startEditing={view.editing}
          fresh={fresh?.id === entry.id ? fresh.indices : []}
          onBack={back}
          onSave={(patch) => save(entry, patch)}
          onDelete={() => remove(entry)}
          onTell={(text) => tell(text, entry.id)}
        />
        {error && <p className="voice-error" role="alert">{error}</p>}
      </div>
    );
  }

  const groups = [
    ...SECTIONS.map((section) => ({
      key: section.id,
      title: section.title,
      items: memories.filter((item) => item.section === section.id && !item.legacy),
    })),
    { key: "legacy", title: "Chưa xếp mục", items: memories.filter((item) => item.legacy) },
  ].filter((group) => group.items.length);

  // Lần tải đầu: logo chờ của Peto thay cả mục (DESIGN.md, "Notices, errors, loading"), như mục Kết nối.
  if (!state && !loadFailed) {
    return <div className="memory-page"><div className="settings-loading"><LoadingIndicator label="Đang tải trí nhớ" /></div></div>;
  }

  return (
    <div className="memory-page" ref={rootRef}>
      <SettingsGroup>
        <SettingsRow label="Cho Peto ghi nhớ" htmlFor={state?.available ? switchId : undefined} desc={hint}>
          {state?.available && (
            <SettingsSwitch id={switchId} label="Cho Peto ghi nhớ" checked={state.enabled} disabled={busy} onChange={toggle} />
          )}
        </SettingsRow>
      </SettingsGroup>

      {loadFailed ? (
        <div className="voice-row">
          <p className="settings-hint" role="alert">Chưa tải được trí nhớ.</p>
          <button type="button" className="settings-button" onClick={() => load()}>Thử lại</button>
        </div>
      ) : null}

      {!loadFailed && state?.available && (
        <>
          {state.sorting && (
            <div className="memory-sorting">
              <LoadingIndicator variant="icon" label="Peto đang xếp các ghi nhớ cũ vào từng mục" />
              <span aria-hidden="true">Peto đang xếp các ghi nhớ cũ vào từng mục…</span>
            </div>
          )}
          {groups.length ? groups.map((group) => (
            <SettingsGroup key={group.key} title={group.title} className="memory-group">
              <ul className={state.enabled ? "memory-rows" : "memory-rows off"} aria-label={group.title}>
                {[...group.items].sort((a, b) => a.title.localeCompare(b.title, "vi")).map((item) => (
                  <li key={item.id} className="memory-row" data-entry={item.id}>
                    <button type="button" className="memory-row-main" onClick={() => show(item.id)}>
                      <span className="memory-row-title">{item.title}</span>
                      <span className="memory-row-summary">{item.summary}</span>
                      <span className="memory-row-date">Cập nhật {shortDate(item.updated_at)}</span>
                      <span className="memory-row-chevron"><SettingsIcon name="chevronRight" size={16} /></span>
                    </button>
                    <span className="memory-row-actions">
                      <button type="button" className="memory-icon" aria-label={`Sửa ${item.title}`} data-tip
                        onClick={() => show(item.id, true)}>
                        <SettingsIcon name="pencil" size={16} />
                      </button>
                      <button type="button" className="memory-icon danger" aria-label={`Xóa ${item.title}`} data-tip
                        disabled={busy} onClick={() => remove(item)}>
                        <SettingsIcon name="trash" size={16} />
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            </SettingsGroup>
          )) : (
            <p className="memory-empty">Chưa có ghi nhớ nào. Cứ trò chuyện, Peto sẽ tự ghi lại những điều đáng nhớ.</p>
          )}

          {memories.length > 0 && (
            <div className="memory-foot">
              <span>{memories.length}/{state.limit} mục · {ideas} ý</span>
              {confirmClear ? (
                <span className="memory-confirm" role="group" aria-label="Xác nhận xóa hết">
                  Xóa hết {memories.length} mục?
                  <button type="button" className="settings-button" onClick={() => setConfirmClear(false)}>Giữ lại</button>
                  <button type="button" className="settings-button danger" disabled={busy} onClick={forgetAll}>Xóa hết</button>
                </span>
              ) : (
                <button type="button" className="settings-button danger" disabled={busy} onClick={() => setConfirmClear(true)}>Xóa hết</button>
              )}
            </div>
          )}
          {error && <p className="voice-error" role="alert">{error}</p>}

          <div className="memory-dock">
            {toast && <Toast toast={toast} onDone={dismissToast} />}
            <TellBox
              label="Bảo Peto nhớ điều gì đó"
              placeholder="Ví dụ: Con mèo của mình tên Mơ"
              disabled={!state.enabled}
              onSend={async (text) => (await tell(text)) !== null}
            />
          </div>
        </>
      )}
      {!loadFailed && state && !state.available && error && <p className="voice-error" role="alert">{error}</p>}
    </div>
  );
}
