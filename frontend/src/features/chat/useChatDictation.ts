import { useCallback, useEffect, useRef, useState } from 'react';
import {
  browserSpeechSupported, startBrowserSpeech, type BrowserSpeechHandlers, type BrowserSpeechSession,
} from '../companion/speech/browserSpeech';
import {
  deviceChoiceSupported, languageOf, loadLanguage, loadMic, resolveMic, saveLanguage, saveMic, type MicChoice,
} from './dictationPrefs';

// Nhập giọng nói ở ô nhắn Chat (G5, chủ web chọn ngày 20/11/2026): nguồn nghe là Web Speech của trình duyệt, miễn phí,
// chữ hiện dần khi đang nói. Ngôn ngữ và micro chọn ở menu cạnh nút micro (DictationMenu.tsx). Trình duyệt không có
// (Firefox) thì không hiện nút micro. Không dùng hearingEngine của Companion: bộ đó có tạm dừng khi Peto nói, tự gửi,
// khóa API riêng, đều không cần ở đây và kéo theo nhiều mã.

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
  /** Nút ✕ lúc đang nghe: thôi nghe và bỏ mọi chữ nghe được lần này, ô nhắn trở lại như lúc bấm micro. */
  cancel(): void;
  /** Luồng micro để vẽ sóng âm lúc đang nghe; null khi không đo được (Safari, điện thoại: không mở micro thứ hai). */
  meterStream: MediaStream | null;
  /** Người dùng gõ tiếp: ẩn lỗi cũ của micro. */
  clearError(): void;
  /** Mã ngôn ngữ nghe ("vi-VN"…), chọn ở menu cạnh micro; đổi khi đang nghe thì lần nghe sau mới theo. */
  language: string;
  setLanguage(code: string): void;
  /** Có chọn được micro không (Chrome/Edge 133+ trên máy tính); không thì luôn dùng micro mặc định. */
  canChooseMic: boolean;
  /** Micro đã chọn (mã và tên); mã rỗng là micro mặc định. */
  mic: MicChoice;
  setMic(choice: MicChoice): void;
}

/** `text`: chữ đang có trong ô nhắn; `onText`: ghi chữ mới vào nháp. `resetKey` đổi (sang hội thoại khác) thì dừng nghe. */
export function useChatDictation(text: string, onText: (value: string) => void, resetKey?: string): ChatDictation {
  const [supported] = useState(() => typeof window !== 'undefined' && browserSpeechSupported());
  const [canChooseMic] = useState(() => supported && deviceChoiceSupported());
  const [language, setLanguageState] = useState(loadLanguage);
  const [mic, setMicState] = useState(loadMic);
  const [phase, setPhase] = useState<DictationPhase>('off');
  const [interim, setInterim] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [meterStream, setMeterStream] = useState<MediaStream | null>(null);
  const session = useRef<BrowserSpeechSession | null>(null);
  // Chữ trong ô nhắn lúc bấm micro, để nút ✕ trả lại đúng như cũ.
  const base = useRef('');
  // Micro mở riêng chỉ để vẽ sóng âm khi nghe bằng micro mặc định (Chrome/Edge máy tính).
  const meterOnly = useRef<MediaStream | null>(null);
  // Micro đã chọn được mở riêng rồi đưa track cho trình duyệt nhận giọng; đóng khi thôi nghe.
  const stream = useRef<MediaStream | null>(null);
  // Mỗi lần bấm micro một số mới: mở micro xong mà người dùng đã bấm dừng thì bỏ, không nghe nữa.
  const attempt = useRef(0);
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

  const releaseMic = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    meterOnly.current?.getTracks().forEach((track) => track.stop());
    meterOnly.current = null;
    setMeterStream(null);
  }, []);

  const end = useCallback((keepInterim: boolean) => {
    attempt.current += 1;
    const current = session.current;
    session.current = null;
    current?.stop();
    releaseMic();
    if (keepInterim) commit(interimRef.current);
    interimRef.current = '';
    setInterim('');
    setNotice('');
    setPhase('off');
  }, [commit, releaseMic]);

  const start = useCallback(() => {
    if (!supported || session.current || phase !== 'off') return;
    setError('');
    setNotice('');
    setPhase('starting');
    base.current = textRef.current;
    const id = ++attempt.current;
    const fail = (message: string) => {
      session.current = null;
      releaseMic();
      interimRef.current = '';
      setInterim('');
      setNotice('');
      setPhase('off');
      setError(message);
    };
    const handlers: BrowserSpeechHandlers = {
      onConnecting: () => {},
      onReady: () => setPhase('listening'),
      onSpeechStart: () => {},
      onSpeechEnd: () => {},
      onInterim: (words) => { interimRef.current = words; setInterim(words); },
      onFinal: (words) => commit(words),
      onDraft: (words) => commit(words),
      onNotice: (message) => setNotice(message),
      onError: fail,
    };
    const options = { chat: true, lang: language, languageLabel: languageOf(language).label.toLowerCase() };
    const begin = (track?: MediaStreamTrack) => {
      try {
        session.current = startBrowserSpeech('vi', handlers, { ...options, track });
      } catch (err) {
        fail(err instanceof Error ? err.message : 'Trình duyệt này chưa có tính năng nghe.');
        return;
      }
      if (track && stream.current) {
        setMeterStream(stream.current);
        return;
      }
      // Sóng âm cho micro mặc định: chỉ ở Chrome/Edge máy tính. Safari trên iPhone có thể ngắt nhận giọng khi trang mở
      // thêm micro, nên ở đó chỉ hiện sóng âm chờ.
      if (!canChooseMic) return;
      navigator.mediaDevices.getUserMedia({ audio: true })
        .then((opened) => {
          if (attempt.current !== id) { opened.getTracks().forEach((item) => item.stop()); return; }
          meterOnly.current = opened;
          setMeterStream(opened);
        })
        .catch(() => { /* Không vẽ được sóng âm thì vẫn nghe bình thường. */ });
    };
    if (!canChooseMic || !mic.id) {
      // Micro mặc định: mở ngay trong lần bấm, vì Safari chỉ cho nghe khi còn trong cử chỉ của người dùng.
      begin();
      return;
    }
    navigator.mediaDevices.enumerateDevices()
      .then((listed) => {
        if (attempt.current !== id) return null;
        const deviceId = resolveMic(mic, listed.filter((item) => item.kind === 'audioinput'));
        if (!deviceId) {
          // Micro đã chọn không còn (rút ra, đổi máy): nghe bằng micro mặc định và nói rõ, thay vì báo lỗi.
          begin();
          setNotice(`Không thấy ${mic.label || 'micro đã chọn'}; đang nghe bằng micro mặc định.`);
          return null;
        }
        return navigator.mediaDevices.getUserMedia({
          audio: { deviceId: { exact: deviceId }, echoCancellation: true, noiseSuppression: true },
        });
      })
      .then((opened) => {
        if (!opened) return;
        if (attempt.current !== id) {
          opened.getTracks().forEach((track) => track.stop());
          return;
        }
        stream.current = opened;
        begin(opened.getAudioTracks()[0]);
      })
      .catch((err: unknown) => {
        if (attempt.current !== id) return;
        const name = err instanceof DOMException ? err.name : '';
        fail(name === 'NotAllowedError'
          ? 'Chưa được phép dùng micro. Bấm biểu tượng ổ khóa cạnh địa chỉ trang để cho phép.'
          : 'Không mở được micro đã chọn. Cắm lại micro hoặc chọn micro khác ở mũi tên cạnh nút micro.');
      });
  }, [canChooseMic, commit, language, mic, phase, releaseMic, supported]);

  const stop = useCallback(() => end(true), [end]);

  const cancel = useCallback(() => {
    const before = base.current;
    interimRef.current = '';
    end(false);
    textRef.current = before;
    onTextRef.current(before);
  }, [end]);

  const finishForSend = useCallback(() => {
    const full = appendSpeech(textRef.current, interimRef.current.trim());
    interimRef.current = '';
    end(false);
    return full;
  }, [end]);

  // Sang hội thoại khác, rời tab hay đóng trang: thôi nghe, bỏ phần chưa chốt (nó thuộc ô nhắn cũ).
  useEffect(() => {
    end(false);
    setError('');
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
      stream.current?.getTracks().forEach((track) => track.stop());
      stream.current = null;
      meterOnly.current?.getTracks().forEach((track) => track.stop());
      meterOnly.current = null;
    };
  }, [end]);

  const clearError = useCallback(() => setError(''), []);
  const setLanguage = useCallback((code: string) => { saveLanguage(code); setLanguageState(languageOf(code).code); }, []);
  const setMic = useCallback((choice: MicChoice) => {
    saveMic(choice);
    setMicState(choice.id === 'default' ? { id: '', label: '' } : choice);
  }, []);

  return {
    supported, phase, interim, error, notice, start, stop, finishForSend, cancel, meterStream, clearError, language,
    setLanguage, canChooseMic, mic, setMic,
  };
}
