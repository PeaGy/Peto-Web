import { useCallback, useEffect, useRef, useState } from 'react';
import { getMessages, UnauthorizedError, type Message } from '../../shared/api/api';

export interface InterruptedReply { conversationId: string; userMessageId: number }
type Status = 'idle' | 'waiting' | 'syncing' | 'recovered' | 'partial' | 'failed';
interface Options {
  scope: string | null;
  conversationId: string | null;
  enabled: boolean;
  busy: boolean;
  onRecovered: (messages: Message[], complete: boolean) => void;
  onUnauthorized: () => void;
  onDisconnect: () => void;
}

/** Chỉ đọc lịch sử của lượt đã được máy chủ xác nhận; không gửi lại tin hay gọi AI. */
export function useReplyRecovery(options: Options) {
  const latest = useRef(options);
  latest.current = options;
  const generation = useRef(0);
  const [ticket, setTicket] = useState<(InterruptedReply & { scope: string | null }) | null>(null);
  const [status, setStatus] = useState<Status>('idle');
  const [online, setOnline] = useState(navigator.onLine);
  const [visible, setVisible] = useState(document.visibilityState !== 'hidden');
  const [revision, setRevision] = useState(0);
  const cancel = useCallback(() => {
    generation.current++;
    setTicket(null);
    setStatus('idle');
  }, []);
  const interrupt = useCallback((reply: InterruptedReply) => {
    generation.current++;
    setTicket({ ...reply, scope: latest.current.scope });
    setStatus('waiting');
  }, []);

  useEffect(() => {
    const offline = () => {
      setOnline(false);
      latest.current.onDisconnect();
    };
    const connected = () => setOnline(true);
    const visibility = () => setVisible(document.visibilityState !== 'hidden');
    window.addEventListener('offline', offline);
    window.addEventListener('online', connected);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      generation.current++;
      window.removeEventListener('offline', offline);
      window.removeEventListener('online', connected);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, []);

  // navigator.onLine có lúc báo sai: Chrome Android giữ "ngoại tuyến" cả khi trang vừa tải từ mạng (F5 cũng không hết,
  // 6/10/2026). Báo ngoại tuyến thì hỏi máy chủ ngay rồi cứ 10 giây một lần; có phản hồi bất kỳ là có mạng.
  useEffect(() => {
    if (online) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const probe = async () => {
      try {
        await fetch('/api/auth/me', { cache: 'no-store', credentials: 'same-origin' });
        if (!stopped) setOnline(true);
        return;
      } catch {
        // Thật sự mất mạng: thử lại sau.
      }
      if (!stopped) timer = setTimeout(probe, 10_000);
    };
    void probe();
    return () => { stopped = true; clearTimeout(timer); };
  }, [online]);

  useEffect(() => {
    if (!ticket) return;
    if (ticket.scope !== options.scope || ticket.conversationId !== options.conversationId) {
      cancel();
      return;
    }
    if (!options.enabled || options.busy || !online || !visible) {
      setStatus('waiting');
      return;
    }
    const version = generation.current;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let timeout: ReturnType<typeof setTimeout>;
    const valid = () => !controller.signal.aborted && version === generation.current
      && latest.current.scope === ticket.scope && latest.current.conversationId === ticket.conversationId
      && latest.current.enabled && !latest.current.busy;
    const recover = async () => {
      setStatus('syncing');
      // Chờ thao tác lưu của luồng vừa bị ngắt; đọc có giới hạn để không tạo vòng lặp nền.
      for (const delay of [250, 1000, 2500]) {
        await new Promise<void>(resolve => { timer = setTimeout(resolve, delay); });
        if (!valid()) return;
        const read = new AbortController();
        const abortRead = () => read.abort();
        controller.signal.addEventListener('abort', abortRead, { once: true });
        timeout = setTimeout(abortRead, 5000);
        try {
          const stored = await getMessages(ticket.conversationId, read.signal);
          if (!valid()) return;
          const userIndex = stored.findIndex(row => row.id === ticket.userMessageId && row.role === 'user');
          const reply = userIndex < 0 ? undefined : stored[userIndex + 1];
          // Chưa có câu trả lời được lưu thì giữ phần chữ trên máy, không thay bằng lịch sử thiếu tin.
          if (reply?.role === 'assistant') {
            const complete = reply.status !== 'incomplete';
            setTicket(null);
            setStatus(complete ? 'recovered' : 'partial');
            latest.current.onRecovered(stored, complete);
            return;
          }
        } catch (err) {
          if (!valid()) return;
          if (err instanceof UnauthorizedError) {
            cancel();
            latest.current.onUnauthorized();
            return;
          }
        } finally {
          clearTimeout(timeout);
          controller.signal.removeEventListener('abort', abortRead);
        }
      }
      if (valid()) setStatus('failed');
    };
    void recover();
    return () => { controller.abort(); clearTimeout(timer); clearTimeout(timeout); };
  }, [ticket, options.scope, options.conversationId, options.enabled, options.busy, online, visible, revision, cancel]);

  // Đổi hội thoại/tài khoản thì bỏ cả thông báo thành công của hội thoại trước.
  useEffect(() => { if (!ticket) setStatus('idle'); }, [options.scope, options.conversationId]);
  return {
    status, online, pending: status === 'waiting' || status === 'syncing', interrupt, cancel,
    retry: () => setRevision(value => value + 1),
  };
}

/** Ngắt do mất mạng khác với người dùng chủ động bấm Dừng. */
export function disconnectStream(controller: AbortController | null) {
  controller?.abort(new DOMException('Mất kết nối tới máy chủ.', 'NetworkError'));
}
export function networkInterrupted(controller: AbortController) {
  return controller.signal.aborted && controller.signal.reason?.name === 'NetworkError';
}
