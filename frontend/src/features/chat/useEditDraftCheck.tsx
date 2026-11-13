import { useEffect, useState, type Dispatch, type RefObject, type SetStateAction } from 'react';
import type { NavigateFunction } from 'react-router';
import { chatRoute } from '../../app/routes';
import { UnauthorizedError, getChatTurnReceipt, getMessages, type AuthState, type Message } from '../../shared/api/api';
import type { EditDraft } from './chatDrafts';
import { EditDraftNotice } from './ReplyRecoveryNotice';
import type { useChatDrafts } from './useChatDrafts';
import type { useReplyRecovery } from './useReplyRecovery';

// Bản sửa tin nhắn đã gửi đi mà chưa rõ máy chủ lưu chưa: hỏi biên nhận của lượt đó rồi quyết định giữ, mở lại hay bỏ.
// Tách khỏi App.tsx (G3.3, 13/11/2026); thân hiệu ứng giữ nguyên.

type SetState<T> = Dispatch<SetStateAction<T>>;
type Recovery = ReturnType<typeof useReplyRecovery>;
export type EditDraftCheckOptions = {
  latestEdit: EditDraft | undefined;
  routedConversationId: string | null;
  conversationId: string | null;
  view: string;
  auth: AuthState | null;
  recovery: Recovery;
  streaming: boolean;
  loadingConversation: boolean;
  editTarget: Message | null;
  resolveEdit: ReturnType<typeof useChatDrafts>['resolveEdit'];
  navigate: NavigateFunction;
  refreshConversations: () => Promise<void>;
  handleUnauthorized: () => void;
  authVersion: RefObject<number>;
  conversationIdRef: RefObject<string | null>;
  viewRef: RefObject<string>;
  setArchived: SetState<boolean>;
  setActiveProjectId: SetState<string | null>;
  setLegacyRoleplay: SetState<boolean>;
  setMessages: SetState<Message[]>;
  setLoadFailed: SetState<boolean>;
  setError: SetState<string | null>;
};

export type EditDraftNoticeContext = {
  messages: Message[];
  loadingConversation: boolean;
  deleting: boolean;
  recovery: Recovery;
  loadFailed: boolean;
  readOnly: boolean;
  loadConversation: (id: string) => Promise<void>;
  openEditor: (target: Message) => void;
  resolveEdit: ReturnType<typeof useChatDrafts>['resolveEdit'];
  canResumeEdit: (edit: EditDraft) => boolean;
  editCheck: { edit: EditDraft; state: 'checking' | 'ready' | 'unconfirmed' } | null;
  checkAgain: () => void;
};

export function useEditDraftCheck(options: EditDraftCheckOptions) {
  const { latestEdit, routedConversationId, conversationId, view, auth, recovery, streaming, loadingConversation, editTarget, resolveEdit, navigate,
    refreshConversations, handleUnauthorized, authVersion, conversationIdRef, viewRef, setArchived, setActiveProjectId, setLegacyRoleplay, setMessages, setLoadFailed, setError } = options;
  const [editCheck, setEditCheck] = useState<{ edit: EditDraft; state: 'checking' | 'ready' | 'unconfirmed' } | null>(null);
  const [editCheckAttempt, setEditCheckAttempt] = useState(0);
  useEffect(() => {
    const requestId = latestEdit?.requestId;
    if (!requestId || !latestEdit || !routedConversationId || routedConversationId !== conversationId
      || view !== 'chat' || !auth?.authenticated || !recovery.online || recovery.pending || streaming || loadingConversation || editTarget) return;
    const edit = latestEdit;
    const controller = new AbortController();
    const session = authVersion.current;
    const current = () => !controller.signal.aborted && session === authVersion.current
      && conversationIdRef.current === routedConversationId && viewRef.current === 'chat';
    setEditCheck({ edit, state: 'checking' });
    const timeout = window.setTimeout(() => {
      if (!current()) return;
      controller.abort();
      setEditCheck({ edit, state: 'unconfirmed' });
    }, 8000);
    void (async () => {
      try {
        const receipt = await getChatTurnReceipt(requestId, controller.signal);
        if (!current()) return;
        if (receipt.state === 'saved' && receipt.content === edit.text.trim()) {
          if (receipt.conversation_id !== conversationId) {
            if (!resolveEdit(edit)) return;
            navigate({ pathname: chatRoute(receipt.conversation_id), search: window.location.search });
          } else {
            const stored = await getMessages(conversationId, controller.signal, settings => {
              if (!current()) return;
              setArchived(Boolean(settings.archived));
              setActiveProjectId(settings.project_id ?? null);
              setLegacyRoleplay(settings.persona === 'roleplay');
            });
            if (!current()) return;
            const found = stored.some(row => row.id === receipt.message_id && row.role === 'user' && row.content === receipt.content);
            if (!resolveEdit(edit, found ? undefined : { messageId: edit.messageId, text: edit.text, conflict: true })) return;
            setMessages(stored);
            setLoadFailed(false);
            setError(null);
          }
          void refreshConversations();
        } else if (receipt.state === 'unsaved' || receipt.state === 'unavailable' || receipt.state === 'saved'
          || (receipt.state === 'missing' && edit.conflict)) {
          resolveEdit(edit, { messageId: edit.messageId, text: edit.text,
            conflict: edit.conflict || receipt.state === 'saved' || receipt.state === 'unavailable' ? true : undefined });
        } else {
          setEditCheck({ edit, state: receipt.state === 'missing' ? 'ready' : 'unconfirmed' });
        }
      } catch (err) {
        if (!current()) return;
        if (err instanceof UnauthorizedError) handleUnauthorized();
        else setEditCheck({ edit, state: 'unconfirmed' });
      } finally {
        window.clearTimeout(timeout);
      }
    })();
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [latestEdit, editCheckAttempt, routedConversationId, conversationId, view, auth?.authenticated, recovery.online,
    recovery.pending, streaming, loadingConversation, editTarget, resolveEdit, navigate, refreshConversations, handleUnauthorized]);
  const canResumeEdit = (edit: EditDraft) =>
    !edit.conflict && (!edit.requestId || (editCheck?.edit === edit && editCheck.state === 'ready'));
  const checkAgain = () => setEditCheckAttempt(attempt => attempt + 1);
  return { editCheck, canResumeEdit, checkAgain };
}

/** Dòng báo về một bản sửa tin chưa gửi xong, kèm nút làm tiếp khi được. */
export function editDraftNotice(edit: EditDraft, id: string, ctx: EditDraftNoticeContext) {
  const { messages, loadingConversation, deleting, recovery, loadFailed, readOnly, loadConversation, openEditor, resolveEdit, canResumeEdit, editCheck, checkAgain } = ctx;
  const target = messages.find(row => row.id === edit.messageId && row.role === 'user');
  const busy = loadingConversation || deleting || !recovery.online;
  let message = 'Phần chỉnh sửa này chưa được gửi.';
  let action: { label: string; run: () => void; disabled?: boolean } | undefined;
  if (edit.conflict) {
    if (target || loadingConversation || loadFailed) {
      message = 'Tin nhắn gốc đã thay đổi. Hãy tải bản mới nhất. Phần bạn vừa sửa được giữ bên dưới.';
      action = { label: 'Tải bản mới nhất', run: () => void loadConversation(id), disabled: busy };
    }
  } else if (!recovery.online) {
    message = 'Bản sửa được giữ trong tab này. Peto sẽ đối chiếu khi có mạng.';
  } else if (canResumeEdit(edit)) {
    if (target && !readOnly) action = { label: 'Mở lại bản sửa', run: () => openEditor(target), disabled: busy };
    else if (loadFailed) action = { label: 'Tải bản mới nhất', run: () => void loadConversation(id), disabled: busy };
  } else if (editCheck?.edit === edit && editCheck.state === 'unconfirmed') {
    message = 'Chưa xác nhận được bản sửa đã lưu hay chưa. Phần bạn vừa sửa được giữ bên dưới.';
    action = { label: 'Kiểm tra lại', run: checkAgain, disabled: busy };
  } else {
    message = 'Đang đối chiếu bản sửa với lịch sử…';
  }
  return <EditDraftNotice key={JSON.stringify([id, edit.messageId])} text={edit.text}
    message={message} action={action} onDiscard={() => resolveEdit(edit)} />;
}
