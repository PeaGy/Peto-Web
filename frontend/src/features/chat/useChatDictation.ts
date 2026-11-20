import { useCallback, useEffect, useRef, useState } from 'react';
import { browserSpeechSupported, startBrowserSpeech, type BrowserSpeechSession } from '../companion/speech/browserSpeech';

// Nhập giọng nói ở ô nhắn Chat (G5, chủ web chọn ngày 20/11/2026): nguồn nghe là Web Speech của trình duyệt, miễn phí,
// chữ hiện dần khi đang nói. Trình duyệt không có (Firefox) thì không hiện nút micro. Không dùng hearingEngine của
// Companion: bộ đó có tạm dừng khi Peto nói, tự gửi, khóa API riêng, đều không cần ở đây và kéo theo nhiều mã.

/** Nối câu vừa nghe vào chữ đã có trong ô nhắn (như `joinSpeech` của Companion). */
export function appendSpeech(base: string, text: string): string {
  if (!text) return base;
  if (!base.trim()) return text;
  return /\s$/.test(base) ? `${base}${text}` : `${base} ${text}`;
}

export type DictationPhase = 'off' | 'starting' | 'listening';

export interface ChatDictation {
  supported: boolean;
  phase: DictationPhase;
  /** Phần trình duyệt còn đang nghe, chưa chốt; ô nhắn hiện nó sau chữ đã có và tạm không cho sửa. */
  interim: string;
  error: string;
  notice: string;
  start(): void;
  /** Dừng nghe; phần chưa chốt vẫn vào ô nhắn để người dùng sửa. */
  stop(): void;
  /** Dừng nghe và trả về chữ đầy đủ (cả phần chưa chốt) để gửi ngay. */
  finishForSend(): string;
  /** Người dùng gõ tiếp: ẩn lỗi cũ của micro. */
  clearError(): void;
}

/** `text`: chữ đang có trong ô nhắn; `onText`: ghi chữ mới vào nháp. `resetKey` đổi (sang hội thoại khác) thì dừng nghe. */
export function useChatDictation(text: string, onText: (value: string) => void, resetKey?: string): ChatDictation {
  const [supported] = useState(() => typeof window !== 'undefined' && browserSpeechSupported());
  const [phase, setPhase] = useState<DictationPhase>('off');
  const [interim, setInterim] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const session = useRef<BrowserSpeechSession | null>(null);
  const textRef = useRef(text);
  const interimRef = useRef('');
  const onTextRef = useRef(onText);
  textRef.current = text;
  onTextRef.current = onText;

  const commit = useCallback((words: string) => {
    if (!words.trim()) return;
    const next = appendSpeech(textRef.current, words.trim());
    textRef.current = next;
    onTextRef.current(next);
  }, []);

  const end = useCallback((keepInterim: boolean) => {
    const current = session.current;
    session.current = null;
    current?.stop();
    if (keepInterim) commit(interimRef.current);
    interimRef.current = '';
    setInterim('');
    setNotice('');
    setPhase('off');
  }, [commit]);

  const start = useCallback(() => {
    if (!supported || session.current) return;
    setError('');
    setNotice('');
    setPhase('starting');
    try {
      // Mở ngay trong lần bấm: Safari chỉ cho nghe khi còn trong cử chỉ của người dùng.
      session.current = startBrowserSpeech('vi', {
        onConnecting: () => {},
        onReady: () => setPhase('listening'),
        onSpeechStart: () => {},
        onSpeechEnd: () => {},
        onInterim: (words) => { interimRef.current = words; setInterim(words); },
        onFinal: (words) => commit(words),
        onDraft: (words) => commit(words),
        onNotice: (message) => setNotice(message),
        onError: (message) => {
          session.current = null;
          interimRef.current = '';
          setInterim('');
          setNotice('');
          setPhase('off');
          setError(message);
        },
      }, { chat: true });
    } catch (err) {
      session.current = null;
      setPhase('off');
      setError(err instanceof Error ? err.message : 'Trình duyệt này chưa có tính năng nghe.');
    }
  }, [commit, supported]);

  const stop = useCallback(() => end(true), [end]);

  const finishForSend = useCallback(() => {
    const full = appendSpeech(textRef.current, interimRef.current.trim());
    interimRef.current = '';
    end(false);
    return full;
  }, [end]);

  // Sang hội thoại khác, rời tab hay đóng trang: thôi nghe, bỏ phần chưa chốt (nó thuộc ô nhắn cũ).
  useEffect(() => {
    end(false);
  }, [resetKey, end]);
  useEffect(() => {
    const hide = () => { if (document.visibilityState === 'hidden') end(false); };
    const leave = () => end(false);
    document.addEventListener('visibilitychange', hide);
    window.addEventListener('pagehide', leave);
    return () => {
      document.removeEventListener('visibilitychange', hide);
      window.removeEventListener('pagehide', leave);
      session.current?.stop();
      session.current = null;
    };
  }, [end]);

  const clearError = useCallback(() => setError(''), []);

  return { supported, phase, interim, error, notice, start, stop, finishForSend, clearError };
}
