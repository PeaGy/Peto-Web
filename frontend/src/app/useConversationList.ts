import { useCallback, useEffect, useRef, useState, type Dispatch, type RefObject, type SetStateAction } from 'react';
import { UnauthorizedError, listConversations, type Conversation } from '../shared/api/api';

// Danh sách hội thoại ở thanh bên (các cuộc không thuộc dự án): tải, tải thêm, và hỏi lại tiêu đề lúc Peto đang đặt tên.
// Tách khỏi App.tsx (G3.3, 13/11/2026); thân các hàm giữ nguyên.

// Tải danh sách hội thoại hỏng thì thử lại một lần sau chừng này mili giây rồi mới báo. Ngày 21/10/2026 một lần tải sau
// lượt chat không tới được máy chủ (log VPS chỉ có 200 OK) mà banner đỏ vẫn hiện, và không tự tắt khi tải lại được.
const LIST_ERROR = "Không tải được danh sách hội thoại. Thử tải lại nhé.";
const LIST_RETRY_MS = 2000;

/** Trạng thái danh sách. `resetList` dùng khi phiên đăng nhập hết hạn. */
export function useConversationList() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const listVersion = useRef(0);
  const listCount = useRef(50);
  const resetList = useCallback(() => {
    listVersion.current += 1;
    setConversations([]);
    setLoadingList(false);
    setHasMore(false);
    listCount.current = 50;
  }, []);
  return { conversations, setConversations, hasMore, loadingList, listCount, listVersion, setHasMore, setLoadingList, resetList };
}

type ListState = ReturnType<typeof useConversationList>;

export function useRefreshConversations(list: ListState, options: {
  handleUnauthorized: () => void;
  refreshProjects: () => Promise<unknown>;
  refreshProjectChats: (id: string) => Promise<unknown>;
  activeProjectRef: RefObject<string | null>;
  setError: Dispatch<SetStateAction<string | null>>;
}) {
  const { listVersion, listCount, setConversations, setHasMore, setLoadingList } = list;
  const { handleUnauthorized, refreshProjects, refreshProjectChats, activeProjectRef, setError } = options;
  const refreshConversations = useCallback(async () => {
    const version = ++listVersion.current;
    setLoadingList(true);
    try {
      const load = async () => {
        const all: Conversation[] = [];
        let more = true;
        while (more && all.length < listCount.current) {
          const page = await listConversations(all.length, 50, '', {unassigned:true});
          if (version !== listVersion.current) return null;
          all.push(...page.conversations);
          more = page.has_more;
          if (!page.conversations.length) break;
        }
        return { all, more };
      };
      let loaded;
      try {
        loaded = await load();
      } catch (err) {
        if (err instanceof UnauthorizedError || version !== listVersion.current) throw err;
        // Trục trặc mạng thoáng qua: thử lại một lần, im lặng, trước khi báo lỗi.
        await new Promise(resolve => window.setTimeout(resolve, LIST_RETRY_MS));
        if (version !== listVersion.current) return;
        loaded = await load();
      }
      if (!loaded) return;
      setConversations(loaded.all);
      setHasMore(loaded.more);
      // Lần tải trước hỏng nhưng lần này được: tắt banner của chính lỗi đó, không đụng lỗi khác.
      setError(previous => previous === LIST_ERROR ? null : previous);
      void refreshProjects();
      if (activeProjectRef.current) void refreshProjectChats(activeProjectRef.current);
    } catch (err) {
      if (version !== listVersion.current) return;
      if (err instanceof UnauthorizedError) handleUnauthorized();
      else setError(LIST_ERROR);
    } finally {
      if (version === listVersion.current) setLoadingList(false);
    }
  }, [handleUnauthorized,refreshProjects,refreshProjectChats]);
  return refreshConversations;
}

/** Tải danh sách lúc đăng nhập, và hỏi lại tiêu đề vài lần khi cuộc đang mở còn chờ Peto đặt tên. */
export function useTitlePolling(list: ListState, options: {
  authenticated: boolean | undefined;
  userId: string | undefined;
  view: string;
  conversationId: string | null;
  streaming: boolean;
  waitingForTitle: boolean;
  activeProjectId: string | null;
  refreshProjectChats: (id: string) => Promise<unknown>;
  refreshConversations: () => Promise<void>;
}) {
  const { setConversations } = list;
  const { authenticated, userId, view, conversationId, streaming, waitingForTitle, activeProjectId, refreshProjectChats,
    refreshConversations } = options;
  useEffect(() => {
    if (!authenticated || view !== 'chat' || streaming || !waitingForTitle) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const poll = async () => {
      try {
        const page = await listConversations(0,50,'',activeProjectId ? {projectId:activeProjectId} : {unassigned:true});
        if (cancelled) return;
        setConversations(current => current.map(item => {
          const fresh = page.conversations.find(row => row.id === item.id);
          return fresh ? { ...item, title: fresh.title, title_state: fresh.title_state, title_attempts: fresh.title_attempts } : item;
        }));
        if (activeProjectId) void refreshProjectChats(activeProjectId);
      } catch { /* A later refresh can recover; do not interrupt typing. */ }
      if (!cancelled && ++attempts < 12) timer = setTimeout(poll, 2500);
    };
    timer = setTimeout(poll, 1500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [userId, authenticated, view, conversationId, streaming, waitingForTitle,activeProjectId,refreshProjectChats]);

  useEffect(() => {
    if (authenticated) void refreshConversations();
  }, [authenticated, refreshConversations]);
}
