import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { UnauthorizedError, getConversationSettings, updateConversation, type ChatSelection, type ConversationSettings, type Effort, type ModelOption } from '../../shared/api/api';
import { MODEL_KEY, EFFORT_KEY, readStoredModel, readStoredEffort } from '../../app/preferences';

const defaults = (): ChatSelection => ({ model: readStoredModel(), effort: readStoredEffort() });
export const CHAT_SELECTION_ERROR = 'Chưa đồng bộ được model và mức suy nghĩ. Chọn lại hoặc gửi tin để lưu nhé.';
type Pending = { value: ChatSelection; promise: Promise<void>; failed: boolean };

/** Lựa chọn theo hội thoại; chỉ thao tác của người dùng mới ghi lên server, đọc lại không tự ghi đè. */
export function useChatSelection(owner: string | null, models: ModelOption[], onUnauthorized: () => void, onError: (message: string | null) => void, onNotice: (message: string | null) => void, refreshEnabled = true) {
  const [selection, setSelection] = useState(defaults);
  const current = useRef(selection);
  const active = useRef<string | null>(null);
  const pending = useRef(new Map<string, Pending>());
  const scope = useRef(0);
  const revision = useRef(0);
  const options = useRef(models); options.current = models;
  const callbacks = useRef({ onUnauthorized, onError, onNotice }); callbacks.current = { onUnauthorized, onError, onNotice };

  useLayoutEffect(() => {
    scope.current++;
    pending.current.clear(); active.current = null;
    current.current = defaults(); setSelection(current.current);
    return () => { scope.current++; };
  }, [owner]);

  function apply(value: ChatSelection, persona?: string) {
    const model = persona === 'roleplay' || !options.current.some(item => item.key === value.model) ? 'peto' : value.model;
    const efforts = options.current.find(item => item.key === model)?.efforts ?? ['low', 'medium', 'high'];
    const effort = value.effort === 'auto' || efforts.includes(value.effort) ? value.effort : 'auto';
    current.current = { model, effort }; setSelection(current.current);
  }

  function restore(id: string | null, saved?: ConversationSettings) {
    revision.current++;
    active.current = id;
    const unsaved = id ? pending.current.get(id) : undefined;
    apply(unsaved?.value ?? (id ? { model: saved?.model ?? 'peto', effort: saved?.effort ?? 'auto' } : defaults()), saved?.persona);
    if (unsaved?.failed) callbacks.current.onError(CHAT_SELECTION_ERROR);
    if (saved) callbacks.current.onNotice(saved.selection_notice ?? null);
  }

  function change(value: ChatSelection) {
    revision.current++;
    callbacks.current.onNotice(null);
    apply(value);
    // Lựa chọn mặc định cho chat chưa tạo chỉ lưu ở thiết bị; mở chat cũ không đổi mặc định này.
    try { localStorage.setItem(MODEL_KEY, current.current.model); localStorage.setItem(EFFORT_KEY, current.current.effort); } catch {}
    const id = active.current;
    if (!id || !owner) return;
    const epoch = scope.current;
    const previous = pending.current.get(id)?.promise ?? Promise.resolve();
    const entry: Pending = { value: { ...current.current }, promise: Promise.resolve(), failed: false };
    // Gửi tuần tự theo từng chat để phản hồi chậm không lưu đè một lựa chọn mới hơn.
    entry.promise = previous.then(async () => {
      if (epoch !== scope.current) return;
      try {
        await updateConversation(id, entry.value);
        if (epoch === scope.current && pending.current.get(id) === entry) {
          pending.current.delete(id);
          if (active.current === id) callbacks.current.onError(null);
        }
      } catch (err) {
        if (epoch !== scope.current || pending.current.get(id) !== entry) return;
        entry.failed = true;
        if (err instanceof UnauthorizedError) callbacks.current.onUnauthorized();
        else if (active.current === id) callbacks.current.onError(CHAT_SELECTION_ERROR);
      }
    });
    pending.current.set(id, entry);
  }

  useEffect(() => {
    if (!owner || !refreshEnabled) return;
    let controller: AbortController | null = null;
    async function refresh() {
      const id = active.current;
      if (!id || pending.current.has(id) || document.visibilityState === 'hidden') return;
      const epoch = scope.current, version = revision.current;
      controller?.abort();
      const request = new AbortController(); controller = request;
      try {
        const saved = await getConversationSettings(id, request.signal);
        if (request.signal.aborted || epoch !== scope.current || version !== revision.current || active.current !== id) return;
        restore(id, saved);
      } catch (err) {
        if (!request.signal.aborted && epoch === scope.current && err instanceof UnauthorizedError) callbacks.current.onUnauthorized();
      }
    }
    // Trở lại thiết bị/tab đang mở thì đọc riêng cài đặt, không tải lại tin hay mất vị trí cuộn/nháp.
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => { controller?.abort(); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, [owner, refreshEnabled]);

  return {
    ...selection, restore,
    setModel: (model: string) => change({ ...current.current, model }),
    setEffort: (effort: Effort) => change({ ...current.current, effort }),
    waitForSave: async (id: string | null) => { if (id) await pending.current.get(id)?.promise; },
    accepted: (id: string, value: ChatSelection) => {
      revision.current++;
      pending.current.delete(id);
      if (active.current === null || active.current === id) { active.current = id; apply(value); }
    },
  };
}
