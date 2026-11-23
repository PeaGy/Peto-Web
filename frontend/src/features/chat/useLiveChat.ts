import { useCallback, useEffect, useRef, useState, type Dispatch, type RefObject, type SetStateAction } from 'react';
import {
  getMessages, stopChat, UnauthorizedError, watchChatLive, type ChatEvent, type LiveEnvelope, type Message,
} from '../../shared/api/api';
import { withArtifact, withSourceActivity, withSources, withStep, withThinking, withWork } from './replyEvents';
import { normalizeWeb } from './sourceActivity';

// Đồng bộ trực tiếp tab Trò chuyện (20/11/2026, kiểu Claude): lượt chat chạy ở tab hay thiết bị khác của cùng tài khoản
// hiện ở đây như lượt tự gửi, chữ chạy dần, "Đang làm", nguồn, tài liệu. Máy chủ: features/chat/live.py.
//
// - Một luồng /api/chat/live cho cả tài khoản, tự kết nối lại. Lượt do chính tab này gửi (ownRequests) bỏ qua.
// - Lượt của hội thoại đang mở: đọc lịch sử đã lưu tới đúng tin hỏi của lượt (máy chủ lưu dần câu trả lời dở, nên
//   phải cắt ở tin hỏi), rồi dựng câu trả lời từ các sự kiện. Xong (done, error, stopped, hay tab gửi ngắt) thì đọc
//   lại bản đã lưu.
// - Lượt của hội thoại khác: chỉ làm mới danh sách hội thoại lúc bắt đầu và lúc xong (hội thoại mới, tiêu đề, thứ tự).

type Turn = {
  requestId: string;
  conversationId: string;
  userMessageId?: number;
  assistant: Message;
  /** Máy chủ không còn giữ đủ lượt này để phát lại (quá dài): chỉ hiện "đang trả lời", đợi xong rồi đọc lại. */
  partial: boolean;
  base: Message[] | null;
  /** Kết nối lại: lượt chưa được phát lại sau live_ready là đã xong trong lúc mất kết nối. */
  stale: boolean;
};

export type RemoteReply = { requestId: string; stopping: boolean };

const TERMINAL = new Set(['done', 'error', 'stopped', 'live_end']);
const BACKOFF_MS = [1_000, 2_000, 5_000, 10_000, 30_000];

function placeholder(partial: boolean): Message {
  return {
    role: 'assistant', content: '', workStartedAt: performance.now(),
    // Bước chờ như ở tab gửi; bước thật đầu tiên của máy chủ thay nó (replyEvents.withSteps bỏ bước 'wait').
    work: { ms: 0, steps: [{ id: 'wait', kind: 'wait', label: partial ? 'Peto đang trả lời trên thiết bị khác…' : 'Đang chuẩn bị câu trả lời…', state: 'live', start: 0 }] },
  };
}

/** Áp một sự kiện SSE vào câu trả lời đang dựng, đúng như tab gửi (replyEvents.ts). Đồng bộ, để hai sự kiện tới sát
 * nhau không ghi đè lên nhau. Sự kiện khác (reading, search, document_status…) chỉ là trạng thái tạm của tab gửi. */
export function applyLiveEvent(message: Message, event: ChatEvent): Message {
  switch (event.type) {
    case 'delta': return { ...message, content: message.content + event.text };
    case 'replace': return { ...message, content: event.text ?? '' };
    case 'step': return withStep(message, event.step);
    case 'thinking': return withThinking(message, event.text, event.step);
    case 'work': return withWork(message, event.work);
    case 'sources': return withSources(message, event.sources);
    case 'source_activity': {
      const web = normalizeWeb(event.web);
      return web ? withSourceActivity(message, web) : message;
    }
    case 'artifact': return withArtifact(message, event.artifact);
    default: return message;
  }
}

export function useLiveChat(options: {
  enabled: boolean;
  conversationId: string | null;
  loadingConversation: boolean;
  /** Tab này đang tự gửi một lượt: không vẽ lượt của nơi khác chồng lên. */
  localBusy: boolean;
  ownRequests: RefObject<Set<string>>;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  refreshConversations: () => Promise<void>;
  onUnauthorized: () => void;
  onDocument: () => void;
}) {
  const latest = useRef(options);
  latest.current = options;
  const turns = useRef(new Map<string, Turn>());
  const [remote, setRemote] = useState<RemoteReply | null>(null);
  const remoteRef = useRef(remote);
  remoteRef.current = remote;
  // Lần nạp lịch sử mới nhất của mỗi lượt; kết quả cũ về muộn thì bỏ.
  const loads = useRef(new Map<string, number>());

  const visible = useCallback((turn: Turn) => {
    const { conversationId, loadingConversation, localBusy } = latest.current;
    return turn.conversationId === conversationId && !loadingConversation && !localBusy;
  }, []);

  const render = useCallback((turn: Turn) => {
    if (!visible(turn) || !turn.base) return;
    latest.current.setMessages([...turn.base, turn.assistant]);
    setRemote((prev) => prev?.requestId === turn.requestId ? prev : { requestId: turn.requestId, stopping: false });
  }, [visible]);

  const loadBase = useCallback(async (turn: Turn) => {
    if (!visible(turn)) return;
    const ticket = (loads.current.get(turn.requestId) ?? 0) + 1;
    loads.current.set(turn.requestId, ticket);
    try {
      const stored = await getMessages(turn.conversationId);
      if (loads.current.get(turn.requestId) !== ticket || turns.current.get(turn.requestId) !== turn) return;
      const index = turn.userMessageId === undefined ? -1 : stored.findIndex((row) => row.id === turn.userMessageId);
      turn.base = index >= 0 ? stored.slice(0, index + 1) : stored.filter((row, at) => !(at === stored.length - 1 && row.role === 'assistant'));
      render(turn);
    } catch (err) {
      if (err instanceof UnauthorizedError) latest.current.onUnauthorized();
    }
  }, [render, visible]);

  const finish = useCallback(async (turn: Turn) => {
    turns.current.delete(turn.requestId);
    loads.current.delete(turn.requestId);
    const { conversationId, localBusy } = latest.current;
    if (remoteRef.current?.requestId === turn.requestId) setRemote(null);
    void latest.current.refreshConversations();
    if (turn.conversationId !== conversationId || localBusy) return;
    try {
      const stored = await getMessages(turn.conversationId);
      if (latest.current.conversationId === turn.conversationId && !latest.current.localBusy) latest.current.setMessages(stored);
    } catch (err) {
      if (err instanceof UnauthorizedError) latest.current.onUnauthorized();
    }
  }, []);

  const receive = useCallback((envelope: LiveEnvelope) => {
    if (latest.current.ownRequests.current?.has(envelope.request_id)) return;
    const event = envelope.event;
    let turn = turns.current.get(envelope.request_id);
    if (event.type === 'meta' || event.type === 'live_partial' || !turn) {
      const fresh = !turn;
      const partial = event.type === 'live_partial' || (!turn && event.type !== 'meta');
      turn = {
        requestId: envelope.request_id, conversationId: envelope.conversation_id, partial, base: null, stale: false,
        userMessageId: event.type === 'meta' ? event.message?.id : turn?.userMessageId, assistant: placeholder(partial),
      };
      turns.current.set(envelope.request_id, turn);
      if (fresh) void latest.current.refreshConversations();
      void loadBase(turn);
      if (event.type === 'meta' || event.type === 'live_partial') return;
    }
    turn.stale = false;
    if (TERMINAL.has(event.type)) {
      void finish(turn);
      return;
    }
    if (turn.partial) return;
    turn.assistant = applyLiveEvent(turn.assistant, event as ChatEvent);
    if (event.type === 'artifact' && visible(turn)) latest.current.onDocument();
    render(turn);
  }, [finish, loadBase, render, visible]);

  // Luồng đang mở: resync() đóng nó để kết nối lại ngay, máy chủ phát lại lượt đang chạy từ đầu.
  const connection = useRef<AbortController | null>(null);
  const resynced = useRef(false);
  const resync = useCallback(() => {
    resynced.current = true;
    connection.current?.abort();
  }, []);

  // Một luồng cho cả tài khoản, tự kết nối lại; ngừng khi đăng xuất hay tắt.
  useEffect(() => {
    if (!options.enabled) return;
    const map = turns.current;
    const controller = new AbortController();
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = async () => {
      while (!controller.signal.aborted) {
        const current = new AbortController();
        const stop = () => current.abort();
        controller.signal.addEventListener('abort', stop, { once: true });
        connection.current = current;
        try {
          await watchChatLive({
            onReady: () => {
              attempt = 0;
              // Lượt nào không được phát lại ngay sau đây là đã xong trong lúc mất kết nối: đọc lại bản đã lưu.
              for (const turn of map.values()) turn.stale = true;
              clearTimeout(timer);
              timer = setTimeout(() => {
                // finish xóa khỏi Map trong lúc lặp: chép ra mảng trước.
                for (const turn of Array.from(map.values())) if (turn.stale) void finish(turn);
              }, 800);
            },
            onLive: receive,
          }, current.signal);
        } catch (err) {
          if (controller.signal.aborted) return;
          if (err instanceof UnauthorizedError) {
            latest.current.onUnauthorized();
            return;
          }
        } finally {
          controller.signal.removeEventListener('abort', stop);
          if (connection.current === current) connection.current = null;
        }
        if (controller.signal.aborted) return;
        if (resynced.current) {
          resynced.current = false;
          continue;
        }
        const wait = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
        attempt += 1;
        await new Promise((resolve) => setTimeout(resolve, wait));
      }
    };
    void run();
    return () => {
      controller.abort();
      clearTimeout(timer);
      map.clear();
      setRemote(null);
    };
  }, [options.enabled, finish, receive]);

  // Mở sang hội thoại đang có lượt chạy ở nơi khác (hay vừa tải xong): vẽ lượt đó lên lịch sử vừa tải.
  useEffect(() => {
    const turn = Array.from(turns.current.values()).find((item) => item.conversationId === options.conversationId);
    if (!turn) {
      setRemote(null);
      return;
    }
    if (!options.loadingConversation && !options.localBusy) {
      turn.base = null;
      void loadBase(turn);
    }
  }, [options.conversationId, options.loadingConversation, options.localBusy, loadBase]);

  /** Nút Dừng ở tab này dừng lượt đang chạy ở thiết bị khác (máy chủ ghi "đã dừng" rồi phát cho mọi tab). */
  const stopRemote = useCallback(async () => {
    const current = remoteRef.current;
    if (!current || current.stopping) return;
    setRemote({ ...current, stopping: true });
    try {
      await stopChat(current.requestId);
    } catch (err) {
      if (err instanceof UnauthorizedError) latest.current.onUnauthorized();
      setRemote((prev) => prev?.requestId === current.requestId ? { ...prev, stopping: false } : prev);
    }
  }, []);

  return { remote, stopRemote, resync };
}
