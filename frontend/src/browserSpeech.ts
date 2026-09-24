/**
 * Nhận giọng có sẵn trong trình duyệt (Web Speech API). Chrome và Edge gửi âm thanh lên máy chủ của Google hay
 * Microsoft để chép lời, Safari chép ngay trên máy, Firefox chưa có (kiểm ngày 2026-09-24).
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
  onSpeechStart(): void;
  onSpeechEnd(): void;
  onInterim(text: string): void;
  onFinal(text: string): void;
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

/**
 * Nghe liên tục tới khi gọi `stop()`. Chrome tự kết thúc phiên nghe sau một lúc im lặng dù đã bật `continuous`,
 * nên phiên hết thì mở phiên mới.
 */
export function startBrowserSpeech(language: HearingLanguage, handlers: BrowserSpeechHandlers): { stop(): void } {
  const Klass = speechRecognitionClass();
  if (!Klass) throw new Error("Trình duyệt này chưa có tính năng nghe.");
  let stopped = false;
  let recognition: Recognition | null = null;
  let quickEnds = 0;

  const begin = () => {
    const startedAt = Date.now();
    const next = new Klass();
    next.lang = language === "vi" ? "vi-VN" : "en-US";
    next.continuous = true;
    next.interimResults = true;
    next.onspeechstart = () => handlers.onSpeechStart();
    next.onspeechend = () => handlers.onSpeechEnd();
    next.onresult = (event) => {
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const words = result[0]?.transcript ?? "";
        if (result.isFinal) {
          if (words.trim()) handlers.onFinal(words.trim());
        } else {
          interim += words;
        }
      }
      handlers.onInterim(interim.trim());
    };
    next.onerror = (event) => {
      // Không nghe thấy gì hay bị hủy chủ động là chuyện thường; phiên sau mở lại ở onend.
      if (event.error === "no-speech" || event.error === "aborted") return;
      stopped = true;
      handlers.onError(errorMessage(event.error, language));
    };
    next.onend = () => {
      if (stopped || recognition !== next) return;
      // Im lặng lâu thì phiên hết là thường, mở lại. Phiên vừa mở đã hết, nhiều lần liền, là trình duyệt từ chối
      // ngầm: dừng hẳn, không mở lại vô hạn.
      quickEnds = Date.now() - startedAt < 1000 ? quickEnds + 1 : 0;
      if (quickEnds > 5) {
        stopped = true;
        handlers.onError(errorMessage("", language));
        return;
      }
      begin();
    };
    recognition = next;
    try {
      next.start();
    } catch {
      stopped = true;
      handlers.onError(errorMessage("", language));
    }
  };

  begin();
  return {
    stop() {
      stopped = true;
      const current = recognition;
      recognition = null;
      try {
        current?.abort();
      } catch {}
    },
  };
}
