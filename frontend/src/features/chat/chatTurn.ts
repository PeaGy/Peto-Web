import type { Dispatch, RefObject, SetStateAction } from 'react';
import type { NavigateFunction } from 'react-router';
import { chatRoute } from '../../app/routes';
import {
  UnauthorizedError, getMessages, sendMessage, stopChat,
  type ChatAttachment, type ChatSelection, type Message, type OutgoingAttachment, type StopChatResult, type WebSearchMode, type WorkStep,
} from '../../shared/api/api';
import { fileToBase64, isImageFile } from './attachments';
import type { EditDraft } from './chatDrafts';
import { focusComposerIfOwned } from './ChatReplyStatus';
import { messageText } from './draftLinks';
import { normalizeWeb } from './sourceActivity';
import type { useChatDrafts } from './useChatDrafts';
import type { useChatSelection } from './useChatSelection';
import { networkInterrupted, type useReplyRecovery } from './useReplyRecovery';
import { safeSources } from './WebSources';
import { closeWork } from './WorkTimeline';

// Gửi một lượt chat và Dừng nó. Tách khỏi App.tsx (G3.3, 13/11/2026) mà giữ nguyên thân hàm: App dựng `ChatTurnContext`
// ở mỗi lần render rồi gọi hai hàm này, nên chúng thấy đúng các giá trị như closure cũ.

export type ChatRevision = { target: Message; text: string; inlineEdit?: boolean };
export type ActiveReply = { id: string | null; messages: Message[]; projectId: string | null;
  selection: ChatSelection; retry?: ChatRevision; error?: string };
export type StopTicket = { requestId: string; dispatched: boolean; promise?: Promise<StopChatResult | null> };

type Drafts = ReturnType<typeof useChatDrafts>;
type SetState<T> = Dispatch<SetStateAction<T>>;
export type ChatTurnContext = Pick<Drafts, 'draft' | 'draftFiles' | 'editDrafts' | 'snapshotDraft' | 'acceptDraft' | 'resolveEdit' | 'saveEdit'> & {
  abortRef: RefObject<AbortController | null>;
  authVersion: RefObject<number>;
  composerBoxRef: RefObject<HTMLDivElement | null>;
  composerFrom: RefObject<number | null>;
  conversationIdRef: RefObject<string | null>;
  nearBottom: RefObject<boolean>;
  replyRef: RefObject<ActiveReply | null>;
  retryRevision: RefObject<ChatRevision | undefined>;
  stopTicketRef: RefObject<StopTicket | null>;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  viewRef: RefObject<string>;
  activeProjectId: string | null;
  conversationId: string | null;
  messages: Message[];
  chosenModel: string;
  effectiveEffort: ChatSelection['effort'];
  webSearch: WebSearchMode;
  emptyChat: boolean;
  readOnly: boolean;
  loadFailed: boolean;
  loadingConversation: boolean;
  chatSelection: ReturnType<typeof useChatSelection>;
  recovery: ReturnType<typeof useReplyRecovery>;
  navigate: NavigateFunction;
  canResumeEdit: (edit: EditDraft) => boolean;
  isSelectedReply: (reply: ActiveReply) => boolean;
  handleUnauthorized: () => void;
  refreshConversations: () => Promise<void>;
  setConversationId: SetState<string | null>;
  setDocumentRefresh: SetState<number>;
  setEditTarget: SetState<Message | null>;
  setError: SetState<string | null>;
  setMessages: SetState<Message[]>;
  setNotice: SetState<string | null>;
  setRetryAvailable: SetState<boolean>;
  setShowJump: SetState<boolean>;
  setSourcesIndex: SetState<number | null>;
  setStopping: SetState<boolean>;
  setStreaming: SetState<boolean>;
};

export async function sendChatTurn(ctx: ChatTurnContext, revision?: ChatRevision) {
  const { abortRef, acceptDraft, activeProjectId, authVersion, canResumeEdit, chatSelection, chosenModel,
    composerBoxRef, composerFrom, conversationId, conversationIdRef, draft, draftFiles, editDrafts, effectiveEffort,
    emptyChat, handleUnauthorized, isSelectedReply, loadFailed, loadingConversation, messages, navigate, nearBottom,
    readOnly, recovery, refreshConversations, replyRef, resolveEdit, retryRevision, saveEdit, setConversationId,
    setDocumentRefresh, setEditTarget, setError, setMessages, setNotice, setRetryAvailable, setShowJump,
    setSourcesIndex, setStopping, setStreaming, snapshotDraft, stopTicketRef, textareaRef, viewRef, webSearch } = ctx;
  const text = revision ? revision.text.trim() : messageText(draft);
  const hasAttachments = revision ? Boolean(revision.target.attachments?.length) : draftFiles.length > 0;
  if ((!text && !hasAttachments) || readOnly || abortRef.current || loadingConversation || loadFailed || !recovery.online || recovery.pending) return;

  const pending = revision ? [] : draftFiles;
  const sentDraft = revision ? null : snapshotDraft();
  const sentQuote = revision ? undefined : sentDraft?.quote;
  const previousMessages = messages;
  const revisionIndex = revision ? messages.findIndex(m => m.id === revision.target.id) : -1;
  if (revision && revisionIndex < 0) {
    setRetryAvailable(false);
    setError("Hãy mở lại cuộc trò chuyện trước khi sửa hoặc tạo lại câu trả lời này.");
    return;
  }
  const previousEdit = revision?.inlineEdit ? editDrafts.find(edit => edit.messageId === revision.target.id) : undefined;
  if (previousEdit && !canResumeEdit(previousEdit)) return;
  const requestId = previousEdit?.requestId ?? crypto.randomUUID();
  const pendingEdit = revision?.inlineEdit && revision.target.id
    ? { messageId: revision.target.id, text: revision.text, requestId } : undefined;
  if (pendingEdit) saveEdit(pendingEdit);
  const prefix = revision ? messages.slice(0, revisionIndex) : messages;
  // A revised reply replaces the selected message; its source panel must not attach to the new reply by index.
  if (revision) setSourcesIndex(null);
  recovery.cancel();
  setRetryAvailable(false);
  retryRevision.current = revision;
  setEditTarget(null);
  setError(null);
  setNotice(null);
  // Tin đầu của cuộc mới: nhớ chỗ ô nhắn đang đứng để trượt nó xuống đáy.
  if (emptyChat) composerFrom.current = composerBoxRef.current?.getBoundingClientRect().top ?? null;
  setStreaming(true);
  setStopping(false);
  nearBottom.current = true;
  setShowJump(false);


  const optimistic: ChatAttachment[] = pending.map((item) => ({
    id: item.id,
    name: item.file.name,
    mime: item.file.type || "application/octet-stream",
    kind: isImageFile(item.file) ? "image" : "file",
    size: item.file.size,
    url: item.previewUrl || "",
  }));

  const startedAt = performance.now();
  const reply: ActiveReply = { id: conversationId, projectId: activeProjectId,
    selection: { model: chosenModel, effort: effectiveEffort }, retry: revision, messages: [
    ...prefix,
    { role: "user", content: text, attachments: revision?.target.attachments || optimistic,
      ...((revision?.target.quoted_source ?? sentQuote) ? { quoted_source: revision?.target.quoted_source ?? sentQuote } : {}) },
    // Bước "chờ" chỉ có ở trình duyệt: bước đầu tiên máy chủ gửi thay nó.
    { role: "assistant", content: "", workStartedAt: startedAt,
      work: { ms: 0, steps: [{ id: 'wait', kind: 'wait', label: 'Đang gửi và chờ máy chủ…', state: 'live', start: 0 }] } },
  ] };
  replyRef.current = reply;
  setMessages(reply.messages);

  const controller = new AbortController();
  abortRef.current = controller;
  const stopTicket = { requestId, dispatched: false } as NonNullable<typeof stopTicketRef.current>;
  stopTicketRef.current = stopTicket;
  let activeId = conversationId;
  let accepted = false;
  let completed = false;
  let interrupted = false;
  let serverStopped = false;
  // Máy chủ đã gửi bản chốt của nhật ký "Đang làm" (sự kiện "work").
  let finalWork = false;
  let storedUserId: number | undefined;
  const session = authVersion.current;

  const writeReply = (change: SetStateAction<Message[]>) => {
    if (session !== authVersion.current) return;
    reply.messages = typeof change === 'function' ? change(reply.messages) : change;
    if (isSelectedReply(reply)) setMessages(reply.messages);
  };

  // Câu trả lời đang viết luôn là tin cuối.
  const updateReply = (change: (last: Message) => Message) => {
    if (session !== authVersion.current) return;
    writeReply((prev) => {
      const last = prev[prev.length - 1];
      return last?.role === "assistant" ? [...prev.slice(0, -1), change(last)] : prev;
    });
  };
  // Bước tới sau khi bấm Dừng thì bỏ: nhật ký đã chốt ở lúc dừng.
  const updateSteps = (change: (steps: WorkStep[]) => WorkStep[]) => {
    if (controller.signal.aborted) return;
    updateReply(last => ({
      ...last, work: { ms: 0, ...last.work, steps: change((last.work?.steps ?? []).filter(step => step.kind !== 'wait')) },
    }));
  };

  const acceptMessage = (id: string, _usedEffort: string, storedMessage?: Message) => {
    if (session !== authVersion.current || (accepted && activeId === id)) return;
    accepted = true;
    storedUserId = storedMessage?.id;
    activeId = id;
    const selected = isSelectedReply(reply);
    reply.id = id;
    if (selected) {
      chatSelection.accepted(id, reply.selection);
      conversationIdRef.current = id;
      setConversationId(id);
      const path = chatRoute(id);
      if (viewRef.current === 'chat' && window.location.pathname !== path) {
        navigate({ pathname: path, search: window.location.search }, { replace: !revision });
      }
    }
    if (sentDraft) acceptDraft(sentDraft, selected ? id : undefined);
    if (pendingEdit && storedMessage?.id && storedMessage.content === text) resolveEdit(pendingEdit);
    if (storedMessage) reply.retry = { target: storedMessage, text: storedMessage.content };
    if (selected) retryRevision.current = reply.retry;
    if (storedMessage) writeReply(prev => [...prev.slice(0, -2), storedMessage, prev[prev.length - 1]]);
    updateReply(last => last.work ? { ...last, work: { ...last.work, steps: last.work.steps.map(step =>
      step.kind === 'wait' ? { ...step, label: 'Đang chuẩn bị câu trả lời…' } : step) } } : last);
  };

  try {
    const attachments: OutgoingAttachment[] = await Promise.all(
      pending.map(async (item) => ({
        name: item.file.name,
        mime: item.file.type,
        data: await fileToBase64(item.file),
      })),
    );

    await chatSelection.waitForSave(conversationId);
    if (session !== authVersion.current || controller.signal.aborted) return;
    stopTicket.dispatched = true;
    await sendMessage(
      {
        requestId: stopTicket.requestId,
        message: text,
        projectId:activeProjectId,
        conversationId,
        branchMessageId: revision?.target.id,
        effort: effectiveEffort,
        webSearch,
        attachments,
        model: chosenModel,
        quotedSource: sentQuote,
      },
      {
        onMeta: acceptMessage,
        onStopped: () => { serverStopped = true; },
        onDelta: (chunk) => updateReply(last => ({ ...last, content: last.content + chunk })),
        onReplace: (rest) => updateReply(last => ({ ...last, content: rest })),
        // Nhật ký "Đang làm" do máy chủ dựng (features/chat/work_log.py): mỗi bước tới là thêm hoặc thay theo id.
        onStep: (step) => updateSteps(steps => {
          const index = steps.findIndex(item => item.id === step.id);
          if (index < 0) return [...steps, step];
          const next = [...steps];
          next[index] = { ...step, summary: step.summary ?? steps[index].summary };
          return next;
        }),
        onThinking: (piece, id) => updateSteps(steps => steps.map(step => step.id === id ? { ...step, summary: (step.summary ?? '') + piece } : step)),
        onWork: (work) => {
          if (controller.signal.aborted) return;
          finalWork = true;
          const { web: rawWeb, ...rest } = work;
          const web = normalizeWeb(rawWeb);
          updateReply(last => ({ ...last, work: { ...rest, ...(web ? { web } : {}) } }));
        },
        onSources: (sources) => {
          if (!controller.signal.aborted) updateReply(last => ({ ...last, sources: safeSources(sources) }));
        },
        onSourceActivity: (web) => {
          if (!controller.signal.aborted) updateReply(last => ({ ...last, work: { ms: 0, steps: [], ...last.work, web } }));
        },
        onArtifact: (artifact) => {
          if (controller.signal.aborted) return;
          // Peto sửa cùng một tệp vài lần trong một lượt: bản mới thay thẻ của bản trước ngay tại chỗ, như máy chủ lưu.
          updateReply(last => {
            const artifacts = [...(last.artifacts || [])];
            const index = artifacts.findIndex(item => item.id === artifact.id);
            if (index >= 0) artifacts[index] = artifact;
            else artifacts.push(artifact);
            return { ...last, artifacts };
          });
          if (isSelectedReply(reply)) setDocumentRefresh(value => value + 1);
        },
        onError: (message, status) => {
          if (session !== authVersion.current) return;
          if (!accepted && status === 404 && pendingEdit) {
            resolveEdit(pendingEdit, { ...pendingEdit, requestId: previousEdit?.requestId, conflict: true });
            return;
          }
          reply.error = message;
          if (!isSelectedReply(reply)) return;
          setError(message);
          setRetryAvailable(accepted || !pendingEdit);
        },
        onDone: (messageId) => {
          completed = true;
          if (Number.isSafeInteger(messageId) && messageId! > 0) updateReply(last => ({ ...last, id: messageId }));
        },
      },
      controller.signal,
    );
  } catch (err) {
    if (err instanceof UnauthorizedError) {
      handleUnauthorized();
    } else if (!controller.signal.aborted) {
      interrupted = true;
      const message = err instanceof Error ? err.message : "Mất kết nối tới máy chủ";
      reply.error = accepted ? message : `${message} Bản nháp được giữ lại; kiểm tra lịch sử trước khi gửi lại nếu kết nối bị ngắt.`;
      if (session === authVersion.current && isSelectedReply(reply)) {
        setError(reply.error);
        setRetryAvailable(accepted || !pendingEdit);
      }
    }
  } finally {
    const stopResult = stopTicket.promise ? await stopTicket.promise : null;
    if (!accepted && stopResult?.conversation_id && stopResult.message) acceptMessage(stopResult.conversation_id, effectiveEffort, stopResult.message);
    if (stopResult?.state === 'complete') completed = true;
    const stoppedByUser = !completed && (serverStopped || stopResult?.stopped === true ||
      (!stopTicket.dispatched && controller.signal.aborted && !networkInterrupted(controller)));
    if (session === authVersion.current) {
      if (!accepted && pendingEdit && !previousEdit?.requestId && (!stopTicket.dispatched || serverStopped || stopResult?.stopped)) {
        resolveEdit(pendingEdit, { messageId: pendingEdit.messageId, text: pendingEdit.text });
      }
      if (stoppedByUser && isSelectedReply(reply)) {
        reply.error = undefined;
        setError(null);
        setRetryAvailable(false);
      }
      if (!accepted) writeReply(previousMessages);
      else {
        const elapsed = Math.round(performance.now() - startedAt);
        writeReply((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role !== "assistant") return prev;
          const work = finalWork ? last.work : closeWork(last.work, completed, elapsed);
          // Lượt hỏng trước khi có chữ giữ nhật ký ở trình duyệt. Lượt chủ động dừng được máy chủ lưu cả khi trống.
          // Lượt hoàn tất có mã tin của máy chủ cũng đã lưu dù rỗng: Peto im lặng có chủ đích (dòng mờ hiện ngay).
          const stored = Boolean(last.content || last.artifacts?.length || (completed && last.id));
          if (!stored && !work?.steps.length && !stoppedByUser) return prev.slice(0, -1);
          return [...prev.slice(0, -1), { ...last, work, workStartedAt: undefined, local: stored || stoppedByUser ? undefined : true,
            status: completed ? "complete" : "incomplete", stopped: stoppedByUser || undefined }];
        });
      }
      // Dừng sau khi máy chủ đã nhận tin thì bong bóng tự ghi "Đã dừng"; chỉ lượt chưa kịp gửi mới cần dòng báo.
      if (stoppedByUser && !accepted && isSelectedReply(reply)) setNotice("Đã dừng gửi. Bản nháp vẫn được giữ lại.");
      if (activeId || !accepted) void refreshConversations();
      if (accepted && activeId && (revision || (completed && !reply.messages.at(-1)?.id))) {
        // Fetch stable IDs for edit/regenerate; preserve the local progress log.
        try {
          const stored = await getMessages(activeId);
          // Bong bóng chỉ có ở trình duyệt (lượt hỏng) không có trong danh sách đã lưu: bỏ qua khi khớp thứ tự.
          if (session === authVersion.current) writeReply(current => {
            let index = 0;
            return current.map(row => {
              if (row.local) return row;
              const saved = stored[index++];
              if (!saved || saved.role !== row.role || saved.content !== row.content) return revision ? { ...row, id: undefined } : row;
              return { ...row, id: saved.id, reply_variants: saved.reply_variants, quoted_source: saved.quoted_source };
            });
          });
        } catch { if (revision) writeReply(current => current.map(row => ({ ...row, id: undefined }))); }
      }
      if (!stoppedByUser && (interrupted || networkInterrupted(controller)) && accepted && activeId && storedUserId !== undefined) {
        recovery.interrupt({ conversationId: activeId, userMessageId: storedUserId });
      }
    }
    if (accepted) for (const item of pending) if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
    setStreaming(false);
    setStopping(false);
    abortRef.current = null;
    if (stopTicketRef.current === stopTicket) stopTicketRef.current = null;
    if (viewRef.current === 'chat' && isSelectedReply(reply)) focusComposerIfOwned(textareaRef.current);
  }
}

export function stopChatTurn(ctx: Pick<ChatTurnContext, 'stopTicketRef' | 'abortRef' | 'setStopping' | 'authVersion' | 'setError'>) {
  const { stopTicketRef, abortRef, setStopping, authVersion, setError } = ctx;
  const ticket = stopTicketRef.current;
  const controller = abortRef.current;
  if (!controller || ticket?.promise) return;
  setStopping(true);
  if (!ticket?.dispatched) { controller.abort(); return; }
  const session = authVersion.current;
  ticket.promise = stopChat(ticket.requestId).then(result => {
    if (result.stopped) controller.abort();
    else if (session === authVersion.current) setStopping(false);
    return result;
  }).catch(() => {
    ticket.promise = undefined;
    if (session === authVersion.current) {
      setStopping(false);
      setError('Chưa xác nhận được Dừng trên máy chủ. Bạn bấm Dừng lại nhé.');
    }
    return null;
  });
}
