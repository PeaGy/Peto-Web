import { useCallback, useEffect, useLayoutEffect, useReducer, useState } from 'react';
import { ChatDraftStore, draftKey, type DraftScope, type DraftSnapshot } from './chatDrafts';
import type { DraftFile } from './files';

export function useChatDrafts(scope: DraftScope | null, authenticated: boolean | undefined) {
  const [store] = useState(() => new ChatDraftStore());
  const [, changed] = useReducer(value => value + 1, 0);
  const key = scope ? draftKey(scope) : null;
  const owner = scope?.ownerId ?? null;
  useLayoutEffect(() => {
    // Chưa biết đăng nhập thì không xóa nháp đang chờ khôi phục sau F5.
    if (authenticated !== undefined) store.setOwner(owner);
  }, [store, owner, authenticated]);
  useLayoutEffect(() => { store.flush(); }, [store, key]);
  useEffect(() => {
    const flush = () => store.flush();
    const hidden = () => { if (document.visibilityState === 'hidden') flush(); };
    window.addEventListener('pagehide', flush);
    window.addEventListener('beforeunload', flush);
    document.addEventListener('visibilitychange', hidden);
    return () => {
      flush(); store.releaseFiles();
      window.removeEventListener('pagehide', flush);
      window.removeEventListener('beforeunload', flush);
      document.removeEventListener('visibilitychange', hidden);
    };
  }, [store]);
  const setDraft = useCallback((text: string) => { if (key) { store.setText(key, text); changed(); } }, [store, key]);
  const setDraftFiles = useCallback((update: DraftFile[] | ((files: DraftFile[]) => DraftFile[])) => {
    if (key) { store.setFiles(key, update); changed(); }
  }, [store, key]);
  const clearDrafts = useCallback(() => { store.clear(); changed(); }, [store]);
  const acceptDraft = useCallback((snapshot: DraftSnapshot) => { store.accept(snapshot); changed(); }, [store]);
  const removeConversationDraft = useCallback((id: string) => { store.removeConversation(id); changed(); }, [store]);
  const removeProjectDraft = useCallback((id: string) => { store.removeProject(id); changed(); }, [store]);
  const draft = key ? store.get(key) : null;
  return { draft: draft?.text ?? '', draftFiles: draft?.files ?? [], setDraft, setDraftFiles,
    snapshotDraft: () => key ? store.snapshot(key) : null,
    clearDrafts, acceptDraft, removeConversationDraft, removeProjectDraft };
}
