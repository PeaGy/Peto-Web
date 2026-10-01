import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  UnauthorizedError,
  clearCompanionMemory,
  deleteCompanionMemory,
  getCompanionMemory,
  setCompanionMemoryEnabled,
  type CompanionMemoryState,
} from "../../shared/api/api";
import { SettingsGroup, SettingsRow, SettingsSwitch } from "./settingsUi";

/**
 * Mục Trí nhớ Companion trong Cài đặt (phương án A chủ web chọn ngày 2026-09-27): công tắc bật/tắt, danh sách những
 * điều Peto tự ghi nhớ từ lời người dùng kể trong Companion, xóa từng dòng hay xóa hết. Máy chủ đọc lại danh sách ở mỗi
 * lượt Companion, nên xóa dòng nào là lượt sau Peto quên dòng đó.
 */
export default function MemorySettings({ open, onUnauthorized }: {
  /** Mục Trí nhớ đang được xem: lúc đó mới tải danh sách. */
  open: boolean;
  onUnauthorized: () => void;
}) {
  const [state, setState] = useState<CompanionMemoryState | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const loadVersion = useRef(0);
  const switchId = useId();

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

  // Mở mục là tải lại: lượt Companion vừa xong có thể vừa ghi thêm.
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setConfirmClear(false);
    load(controller.signal);
    return () => {
      loadVersion.current += 1;
      controller.abort();
    };
  }, [open, load]);

  async function run(action: () => Promise<void>, rollback: CompanionMemoryState | null, failure: string) {
    setError(null);
    setBusy(true);
    try {
      await action();
    } catch (err) {
      if (err instanceof UnauthorizedError) { onUnauthorized(); return; }
      setState(rollback);
      // Lỗi từ máy chủ đã là câu tiếng Việt; mất mạng thì fetch ném TypeError chữ tiếng Anh, nên dùng câu của mình.
      setError(err instanceof Error && !(err instanceof TypeError) ? err.message : failure);
    } finally {
      setBusy(false);
    }
  }

  function toggle(enabled: boolean) {
    if (!state) return;
    const before = state;
    setState({ ...state, enabled });
    void run(() => setCompanionMemoryEnabled(enabled), before, "Chưa đổi được. Thử lại sau nha.");
  }

  function forget(id: number) {
    if (!state) return;
    const before = state;
    setState({ ...state, memories: state.memories.filter((item) => item.id !== id) });
    void run(() => deleteCompanionMemory(id), before, "Chưa xóa được ghi nhớ này.");
  }

  function forgetAll() {
    if (!state) return;
    const before = state;
    setConfirmClear(false);
    setState({ ...state, memories: [] });
    void run(clearCompanionMemory, before, "Chưa xóa được. Thử lại sau nha.");
  }

  const memories = state?.memories ?? [];
  const intro = "Peto ghi lại vài điều bạn kể trong Companion, và tóm tắt phần trò chuyện đã cũ, để lần sau nhớ.";
  const hint = !state ? intro
    : !state.available ? "Chủ web đã tắt trí nhớ Companion trên máy chủ này."
    : state.enabled ? `${intro} Chỉ bạn thấy danh sách này; xóa dòng nào là Peto quên dòng đó.`
    : "Đang tắt: Peto không ghi thêm và không dùng các ghi nhớ bên dưới.";

  return (
    <>
      <SettingsGroup>
        <SettingsRow label="Cho Peto ghi nhớ" htmlFor={state?.available ? switchId : undefined} desc={hint}>
          {state?.available && (
            <SettingsSwitch id={switchId} label="Cho Peto ghi nhớ" checked={state.enabled} disabled={busy} onChange={toggle} />
          )}
        </SettingsRow>
      </SettingsGroup>

      {loadFailed ? (
        <div className="voice-row">
          <p className="settings-hint" role="alert">Chưa tải được danh sách ghi nhớ.</p>
          <button type="button" className="settings-button" onClick={() => load()}>Thử lại</button>
        </div>
      ) : !state && <p className="memory-empty" role="status">Đang tải…</p>}

      {!loadFailed && state && state.available && (
        <SettingsGroup title="Những điều Peto nhớ về bạn">
          {memories.length ? (
            <ul className={state.enabled ? "memory-list" : "memory-list off"} aria-label="Những điều Peto nhớ về bạn">
              {memories.map((item) => (
                <li key={item.id}>
                  <span>{item.text}</span>
                  <button
                    type="button"
                    className="memory-delete"
                    aria-label={`Xóa ghi nhớ: ${item.text}`}
                    title="Xóa ghi nhớ này"
                    disabled={busy}
                    onClick={() => forget(item.id)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="memory-empty">Chưa có ghi nhớ nào. Cứ trò chuyện trong Companion, Peto sẽ tự ghi lại những điều đáng nhớ.</p>
          )}
        </SettingsGroup>
      )}

      {!loadFailed && state && state.available && memories.length > 0 && (
        <div className="memory-foot">
          <span>{memories.length}/{state.limit} ghi nhớ</span>
          {confirmClear ? (
            <span className="memory-confirm" role="group" aria-label="Xác nhận xóa hết">
              Xóa hết {memories.length} ghi nhớ?
              <button type="button" className="settings-button" onClick={() => setConfirmClear(false)}>Giữ lại</button>
              <button type="button" className="settings-button danger" disabled={busy} onClick={forgetAll}>Xóa hết</button>
            </span>
          ) : (
            <button type="button" className="settings-button danger" disabled={busy} onClick={() => setConfirmClear(true)}>Xóa hết</button>
          )}
        </div>
      )}
      {error && <p className="voice-error" role="alert">{error}</p>}
    </>
  );
}
