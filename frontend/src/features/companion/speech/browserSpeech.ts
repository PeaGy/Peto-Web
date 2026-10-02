/**
 * Nhận giọng có sẵn trong trình duyệt (Web Speech API). Dịch vụ và khả năng nghe phụ thuộc trình duyệt;
 * có lớp SpeechRecognition chưa đảm bảo dịch vụ thực sự khởi động hay chép được lời.
 */
import type { HearingLanguage } from "./hearingProviders";

interface RecognitionAlternative {
  transcript: string;
}

interface RecognitionResult {
  isFinal: boolean;
  0: RecognitionAlternative;
}

interface RecognitionEvent {
  resultIndex: number;
  results: ArrayLike<RecognitionResult>;
}

interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  onspeechstart: (() => void) | null;
  onspeechend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type RecognitionClass = new () => Recognition;

export function speechRecognitionClass(): RecognitionClass | null {
  const scope = window as unknown as { SpeechRecognition?: RecognitionClass; webkitSpeechRecognition?: RecognitionClass };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

export function browserSpeechSupported(): boolean {
  return speechRecognitionClass() !== null;
}

export interface BrowserSpeechHandlers {
  onConnecting(): void;
  onReady(): void;
  onSpeechStart(): void;
  onSpeechEnd(): void;
  onInterim(text: string): void;
  onFinal(text: string): void;
  /** Chữ chưa được trình duyệt chốt: giữ để người dùng sửa, không tự gửi. */
  onDraft(text: string): void;
  onNotice(message: string): void;
  onError(message: string): void;
}

function errorMessage(code: string, language: HearingLanguage): string {
  if (code === "not-allowed" || code === "service-not-allowed") {
    return "Chưa được phép dùng micro hoặc dịch vụ nhận giọng của trình duyệt. Bấm biểu tượng ổ khóa cạnh địa chỉ trang để cho phép.";
  }
  if (code === "network") return "Trình duyệt không kết nối được dịch vụ nhận giọng. Kiểm tra mạng hoặc chọn nguồn nghe khác trong Cài đặt.";
  if (code === "audio-capture") return "Không mở được micro. Kiểm tra micro rồi thử lại.";
  if (code === "language-not-supported") {
    return `Trình duyệt này chưa nghe được ${language === "vi" ? "tiếng Việt" : "tiếng Anh"}. Đổi ngôn ngữ hoặc nguồn nghe trong Cài đặt.`;
  }
  return "Trình duyệt ngừng nghe giữa chừng. Bấm micro để nghe lại.";
}

export interface BrowserSpeechSession {
  stop(): void;
  /** Thanh đo chỉ xác nhận có âm thanh, không coi đó là chữ đã nhận được. */
  noteSound(): void;
}

/** Nghe tới khi gọi `stop()`. Phiên hết sau im lặng thì mở lại, nhưng không lặp vô hạn nếu khởi động thất bại. */
export function startBrowserSpeech(language: HearingLanguage, handlers: BrowserSpeechHandlers): BrowserSpeechSession {
  const Klass = speechRecognitionClass();
  if (!Klass) throw new Error("Trình duyệt này chưa có tính năng nghe.");
  let stopped = false;
  let recognition: Recognition | null = null;
  let quickEnds = 0;
  let interim = "";
  let startTimer: ReturnType<typeof setTimeout> | undefined;
  let restartTimer: ReturnType<typeof setTimeout> | undefined;
  let resultTimer: ReturnType<typeof setTimeout> | undefined;
  let soundNoticed = false;
  let warned = false;
  const clearTimers = () => {
    clearTimeout(startTimer);
    clearTimeout(restartTimer);
    clearTimeout(resultTimer);
  };
  const stop = () => {
    stopped = true;
    clearTimers();
    const current = recognition;
    recognition = null;
    try { current?.abort(); } catch {}
  };
  const noteSound = () => {
    if (stopped || warned || resultTimer) return;
    soundNoticed = true;
    resultTimer = setTimeout(() => {
      resultTimer = undefined;
      if (stopped) return;
      warned = true;
      handlers.onNotice("Micro có âm thanh nhưng dịch vụ nhận giọng chưa trả chữ. Kiểm tra micro mặc định, mạng và ngôn ngữ trong Cài đặt → Giọng nói → Peto nghe; thử nguồn nghe khác nếu vẫn lỗi.");
    }, 8000);
  };

  const begin = () => {
    if (stopped) return;
    const startedAt = Date.now();
    const next = new Klass();
    next.lang = language === "vi" ? "vi-VN" : "en-US";
    next.continuous = true;
    next.interimResults = true;
    const current = () => !stopped && recognition === next;
    next.onstart = () => {
      if (!current()) return;
      clearTimeout(startTimer);
      handlers.onReady();
    };
    next.onspeechstart = () => {
      if (!current()) return;
      noteSound();
      handlers.onSpeechStart();
    };
    next.onspeechend = () => { if (current()) handlers.onSpeechEnd(); };
    next.onresult = (event) => {
      if (!current()) return;
      clearTimeout(startTimer);
      interim = "";
      let hasWords = false;
      for (let index = 0; index < event.results.length; index += 1) {
        const result = event.results[index];
        const words = result[0]?.transcript ?? "";
        hasWords ||= Boolean(words.trim());
        if (result.isFinal) {
          if (index >= event.resultIndex && words.trim()) handlers.onFinal(words.trim());
        } else {
          interim += words;
        }
      }
      if (hasWords) {
        clearTimeout(resultTimer);
        resultTimer = undefined;
        warned = false;
        soundNoticed = false;
        handlers.onNotice("");
      }
      handlers.onInterim(interim.trim());
    };
    next.onerror = (event) => {
      if (!current()) return;
      if (event.error === "no-speech") {
        if (soundNoticed) handlers.onNotice("Trình duyệt chưa nhận ra lời. Kiểm tra micro mặc định và ngôn ngữ bạn nói, rồi thử lại.");
        return;
      }
      if (event.error === "aborted") return;
      if (interim.trim()) {
        handlers.onDraft(interim.trim());
        interim = "";
      }
      stop();
      handlers.onError(errorMessage(event.error, language));
    };
    next.onend = () => {
      if (!current()) return;
      clearTimeout(startTimer);
      recognition = null;
      if (interim.trim()) {
        handlers.onDraft(interim.trim());
        interim = "";
        handlers.onInterim("");
        handlers.onNotice("Phiên nghe kết thúc khi câu chưa được chốt. Phần chữ đang nghe đã được giữ để bạn kiểm tra.");
      }
      // Im lặng lâu thì phiên hết là thường, mở lại. Phiên vừa mở đã hết, nhiều lần liền, là trình duyệt từ chối
      // ngầm: dừng hẳn, không mở lại vô hạn.
      quickEnds = Date.now() - startedAt < 1000 ? quickEnds + 1 : 0;
      if (quickEnds > 5) {
        stop();
        handlers.onError(errorMessage("", language));
        return;
      }
      restartTimer = setTimeout(begin, 300);
    };
    recognition = next;
    handlers.onConnecting();
    startTimer = setTimeout(() => {
      if (!current()) return;
      stop();
      handlers.onError("Dịch vụ nhận giọng của trình duyệt chưa khởi động. Kiểm tra quyền micro và mạng, hoặc chọn nguồn nghe khác trong Cài đặt → Giọng nói → Peto nghe.");
    }, 10000);
    try {
      next.start();
    } catch {
      stop();
      handlers.onError(errorMessage("", language));
    }
  };

  begin();
  return { stop, noteSound };
}
