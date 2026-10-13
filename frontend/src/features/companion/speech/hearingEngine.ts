/**
 * Phần Peto nghe (Ears): nghe micro, chép lời và đưa chữ vào ô nhắn Companion. Một bộ nghe cho cả trang, sống
 * ngoài React như musicVibe, để Companion và Cài đặt dùng chung; âm lượng có kho riêng vì đổi vài chục lần mỗi giây.
 *
 * Hai loại nguồn:
 * - "browser": nhận giọng có sẵn trong trình duyệt (browserSpeech.ts), chữ hiện dần ngay lúc nói.
 * - nguồn dùng khóa (hearingProviders.ts): tự nghe micro, cắt câu theo khoảng im lặng (hearingAudio.Segmenter) rồi
 *   gửi từng câu đi chép.
 *
 * Micro chỉ mở khi người dùng bấm nút micro hay "Bắt đầu nghe thử"; không có gì tự bật.
 *
 * Hai cách nghe (Cài đặt Companion → Nghe, theo Push to Talk của AIRI, PR #2729):
 * - "always" (Luôn nghe, mặc định): bật micro là nghe liên tục, tự cắt câu.
 * - "hold" (Giữ để nói): nút micro chỉ bật chế độ chờ ("ready"), micro vẫn đóng. Micro mở khi giữ phím Space, giữ nút
 *   micro hay nút "Giữ để nói", và đóng khi thả; thả ra là chốt câu. Giữ dưới 300 ms là bấm nhầm, không nghe gì.
 */
import { useSyncExternalStore } from "react";
import { browserSpeechSupported, startBrowserSpeech, type BrowserSpeechSession } from "./browserSpeech";
import { levelOf, rmsOf, Segmenter, thresholdFor, wavFromSamples } from "./hearingAudio";
import { captureSupported, openMicrophone, type MicCapture } from "./hearingCapture";
import {
  HearingError,
  hearingKeyReady,
  hearingProvider,
  transcribeWithKey,
  type HearingLanguage,
  type HearingProviderId,
} from "./hearingProviders";
import { getKeyConfigs } from "./voiceProviders";
import type { HearingTiming } from './companionTiming';
import { audioRequest } from './audioRequest';

export type HearingSource = "browser" | HearingProviderId;
export type HearingMode = "always" | "hold";
/** "ready": đã bật Giữ để nói, micro còn đóng, chờ người dùng giữ phím hay nút. */
export type HearingPhase = "off" | "ready" | "starting" | "waiting" | "speaking" | "transcribing" | "paused";

export interface HearingSettings {
  source: HearingSource;
  deviceId: string;
  language: HearingLanguage;
  /** 0..100: càng cao càng dễ tính là có tiếng nói (chỉ dùng cho nguồn dùng khóa). */
  sensitivity: number;
  autoSend: boolean;
  pauseWhileSpeaking: boolean;
  /** Cho phép lời nói mới dừng câu trả lời và giọng đang phát; mặc định tắt. */
  bargeIn: boolean;
  /** Luôn nghe hay Giữ để nói; mặc định Luôn nghe như AIRI. */
  mode: HearingMode;
}

export interface HearingState extends HearingSettings {
  listening: boolean;
  /** Đang nghe thử trong Cài đặt: chữ nghe được về khung Nghe thử, không vào ô nhắn Companion. */
  testing: boolean;
  phase: HearingPhase;
  /** Chữ đang nghe dở (chỉ nguồn trình duyệt có). */
  interim: string;
  message: string;
  /** Đang giữ để nói (Giữ để nói). */
  holding: boolean;
  /** Mốc performance.now() lúc bắt đầu giữ, cho đồng hồ trên thanh Giữ để nói. */
  holdStartedAt: number;
  /** Lời nhắc ngắn, tự tắt sau vài giây (giữ quá nhanh, giữ quá lâu). */
  hint: string;
}

const SETTING_KEYS: Record<keyof HearingSettings, string> = {
  source: "peto-hearing-source",
  deviceId: "peto-hearing-device",
  language: "peto-hearing-language",
  sensitivity: "peto-hearing-sensitivity",
  autoSend: "peto-hearing-autosend",
  pauseWhileSpeaking: "peto-hearing-pause",
  bargeIn: "peto-hearing-barge-in",
  mode: "peto-hearing-mode",
};

const SOURCES = new Set<string>(["browser", "groq", "azure", "openai", "deepgram", "elevenlabs", "gemini", "compat"]);

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {}
}

function readSettings(): HearingSettings {
  const source = read(SETTING_KEYS.source) ?? "";
  const sensitivity = Number(read(SETTING_KEYS.sensitivity));
  return {
    source: SOURCES.has(source) ? source as HearingSource : "browser",
    deviceId: read(SETTING_KEYS.deviceId) ?? "",
    language: read(SETTING_KEYS.language) === "vi" ? "vi" : "en",
    sensitivity: read(SETTING_KEYS.sensitivity) !== null && Number.isFinite(sensitivity)
      ? Math.max(0, Math.min(100, sensitivity)) : 50,
    // Tự gửi mặc định tắt (chủ web chọn ngày 2026-09-24, giống AIRI): chữ chép sai thì người dùng còn sửa được.
    autoSend: read(SETTING_KEYS.autoSend) === "1",
    pauseWhileSpeaking: read(SETTING_KEYS.pauseWhileSpeaking) !== "0",
    bargeIn: read(SETTING_KEYS.bargeIn) === "1",
    mode: read(SETTING_KEYS.mode) === "hold" ? "hold" : "always",
  };
}

let state: HearingState = {
  ...readSettings(), listening: false, testing: false, phase: "off", interim: "", message: "",
  holding: false, holdStartedAt: 0, hint: "",
};
const listeners = new Set<() => void>();

function publish(patch: Partial<HearingState>) {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export const getHearingState = () => state;

export function useHearing(): HearingState {
  return useSyncExternalStore(subscribe, getHearingState);
}

let level = 0;
const levelListeners = new Set<() => void>();

function publishLevel(next: number) {
  if (next === level) return;
  level = next;
  levelListeners.forEach((listener) => listener());
}

function subscribeLevel(listener: () => void) {
  levelListeners.add(listener);
  return () => {
    levelListeners.delete(listener);
  };
}

/** Âm lượng micro 0..1, chỉ cho thanh đo và vòng sáng quanh nút micro. */
export function useHearingLevel(): number {
  return useSyncExternalStore(subscribeLevel, () => level);
}

export interface HearingSink {
  onFinal(text: string, finalized?: boolean, timing?: HearingTiming): void;
  onSpeechStart?(): void;
  /** Người dùng bắt đầu giữ để nói: Peto thôi nói và thôi trả lời để nghe, như nói chen nhưng không cần bật. */
  onHoldStart?(): void;
}

let companionSink: HearingSink | null = null;
let testSink: HearingSink | null = null;

/** Companion nhận chữ nghe được vào ô nhắn. */
export function setHearingSink(sink: HearingSink | null) {
  companionSink = sink;
}

/** Khung Nghe thử trong Cài đặt nhận chữ khi đang nghe thử. */
export function setHearingTestSink(sink: HearingSink | null) {
  testSink = sink;
}

/** Nối câu vừa nghe vào chữ đã có trong ô nhắn. */
export function joinSpeech(base: string, text: string): string {
  if (!base.trim()) return text;
  return /\s$/.test(base) ? `${base}${text}` : `${base} ${text}`;
}

function deliver(text: string, finalized = true, timing?: HearingTiming) {
  (state.testing ? testSink : companionSink)?.onFinal(text, finalized, timing);
  publish({ interim: "" });
}

function notifySpeechStart() {
  if (state.listening && !state.testing && state.bargeIn) companionSink?.onSpeechStart?.();
}

interface Engine {
  stop(): void;
  pause(paused: boolean): void;
}

let engine: Engine | null = null;
let generation = 0;
let pauseWanted = false;
let removeLifecycle: (() => void) | null = null;

function stopEngine() {
  removeLifecycle?.();
  removeLifecycle = null;
  engine?.stop();
  engine = null;
}

function fail(error: unknown) {
  generation += 1;
  stopEngine();
  dropHold();
  publish({
    listening: false, testing: false, phase: "off", interim: "",
    message: error instanceof Error ? error.message : "Chưa nghe được.",
  });
  publishLevel(0);
}

const UNSUPPORTED = "Trình duyệt này chưa có tính năng nghe (Firefox chưa hỗ trợ). Dùng Chrome, Edge hoặc Safari, "
  + "hoặc chọn nguồn dùng khóa trong Cài đặt Companion → Nghe.";

async function browserEngine(token: number): Promise<Engine> {
  if (!browserSpeechSupported()) throw new Error(UNSUPPORTED);
  let paused = false;
  let stopped = false;
  let capture: MicCapture | null = null;
  let meterStarted = false;
  let soundMs = 0;
  let recognition: BrowserSpeechSession | null = null;
  const current = () => token === generation && !stopped;
  const startMeter = () => {
    if (meterStarted || !captureSupported()) return;
    meterStarted = true;
    // Web Speech tự dùng micro mặc định. Thanh đo dùng cùng lựa chọn, không dùng micro USB riêng rồi gây hiểu nhầm.
    void openMicrophone("", (chunk) => {
      if (!current() || paused || !capture) return;
      const rms = rmsOf(chunk);
      publishLevel(levelOf(rms));
      soundMs = rms >= 0.01 ? soundMs + chunk.length / capture.sampleRate * 1000 : 0;
      if (soundMs >= 300) recognition?.noteSound();
    }, () => {
      if (current()) publishLevel(0);
    }).then((opened) => {
      if (!current()) opened.stop();
      else capture = opened;
    }).catch(() => {
      if (current()) publish({ message: "Chưa mở được thanh đo âm lượng. Bộ nhận giọng vẫn nghe bằng micro mặc định; bạn thử nói để kiểm tra chữ." });
    });
  };
  const begin = () => {
    let endedAt: number | undefined;
    let lastFinal: HearingTiming | undefined;
    let speechReported = false;
    const speechStart = (resetTiming = true) => {
      if (!current() || paused || speechReported) return;
      speechReported = true;
      if (resetTiming) { endedAt = undefined; lastFinal = undefined; }
      publish({ phase: "speaking" });
      notifySpeechStart();
    };
    recognition = startBrowserSpeech(state.language, {
      onConnecting: () => {
        // Phiên trình duyệt tự mở lại có câu mới; không giữ cờ nói chen của câu dở ở phiên trước.
        speechReported = false;
        endedAt = undefined;
        lastFinal = undefined;
        if (current() && !paused) publish({ phase: "starting" });
      },
      onReady: () => {
        if (!current() || paused) return;
        publish({ phase: "waiting" });
        startMeter();
      },
      onSpeechStart: () => {
        if (endedAt !== undefined) speechReported = false;
        speechStart();
      },
      // Chỉ nghe thấy tiếng ồn thì trình duyệt không trả chữ nào: về lại "đang nghe" thay vì kẹt ở "bạn đang nói".
      onSpeechEnd: () => {
        if (!current() || paused) return;
        endedAt = performance.now();
        // Một số trình duyệt chốt chữ trước khi báo hết tiếng; chỉ giữ mốc thật, không đảo thứ tự.
        if (lastFinal) lastFinal.endedAt = endedAt;
        if (current() && !paused && state.phase === "speaking") {
          publish({ phase: state.interim ? "transcribing" : "waiting" });
        }
      },
      onInterim: (text) => {
        // Một số trình duyệt trả chữ mà không báo speechstart; chữ cũng xác nhận có lời nói.
        if (text.trim()) speechStart(false);
        if (current() && !paused) publish(text ? { interim: text, phase: "speaking" } : { interim: "" });
      },
      onFinal: (text) => {
        if (!current() || paused) return;
        if (text.trim()) speechStart(false);
        lastFinal = { endedAt, finalizedAt: performance.now() };
        deliver(text, true, lastFinal);
        endedAt = undefined;
        speechReported = false;
        publish({ phase: "waiting" });
      },
      onDraft: (text) => {
        if (current() && !paused) deliver(text, false);
      },
      onNotice: (message) => {
        if (current() && !paused) publish({ message });
      },
      onError: (message) => {
        if (current()) fail(new Error(message));
      },
    });
  };
  begin();
  return {
    stop() {
      stopped = true;
      recognition?.stop();
      recognition = null;
      capture?.stop();
    },
    pause(next) {
      if (next === paused) return;
      paused = next;
      soundMs = 0;
      if (next) {
        recognition?.stop();
        recognition = null;
      } else {
        begin();
      }
    },
  };
}

async function keyEngine(token: number, source: HearingProviderId): Promise<Engine> {
  const provider = hearingProvider(source)!;
  if (!hearingKeyReady(provider, getKeyConfigs()[provider.id])) {
    throw new Error(`Chưa nhập đủ khóa ${provider.name} trong Cài đặt Companion → Nghe.`);
  }
  if (!captureSupported()) throw new Error("Trình duyệt này chưa cho ghi âm từ micro.");
  let controller = new AbortController();
  let segmentVersion = 0;
  let paused = false;
  let segmenter: Segmenter | null = null;
  let sampleRate = 0;
  let pending = 0;
  let queue: Promise<void> = Promise.resolve();

  // Chép lần lượt từng câu, để chữ vào ô nhắn đúng thứ tự đã nói.
  const transcribe = (samples: Float32Array) => {
    // Không giữ âm thanh vô hạn khi nguồn chép lời bị chậm: tối đa một câu đang chép và hai câu chờ.
    if (pending >= 3) {
      publish({ phase: 'transcribing', message: 'Nguồn nghe đang chép chậm. Một câu mới chưa được nhận; chờ chữ hiện rồi nói lại nhé.' });
      return;
    }
    const endedAt = performance.now();
    const version = segmentVersion;
    const signal = controller.signal;
    const valid = () => token === generation && version === segmentVersion && !signal.aborted;
    pending += 1;
    const audio = wavFromSamples(samples, sampleRate);
    const language = state.language;
    publish({ phase: "transcribing" });
    queue = queue.then(async () => {
      try {
        if (!valid()) return;
        const words = await audioRequest(abort => transcribeWithKey(provider, getKeyConfigs()[provider.id] ?? {}, audio, language, abort),
          signal, 30000, new HearingError('Nguồn nghe chép lời quá lâu. Bạn có thể nói lại hoặc đổi nguồn nghe.', false));
        if (valid() && !paused && words) deliver(words, true, { endedAt, finalizedAt: performance.now() });
      } catch (error) {
        if (!valid()) return;
        // Khóa sai, hết số dư: nói tiếp cũng hỏng nên thôi nghe. Lỗi mạng, giới hạn lượt: báo rồi nghe tiếp.
        if (error instanceof HearingError && !error.fatal) publish({ message: error.message });
        else fail(error);
      } finally {
        if (!valid()) return;
        pending -= 1;
        if (token === generation && pending === 0 && state.phase === "transcribing") {
          publish({ phase: paused ? "paused" : "waiting" });
        }
      }
    });
  };

  const capture = await openMicrophone(state.deviceId, (chunk) => {
    if (token !== generation || paused || !sampleRate) return;
    publishLevel(levelOf(rmsOf(chunk)));
    segmenter ??= new Segmenter(sampleRate, { threshold: thresholdFor(state.sensitivity) });
    segmenter.setThreshold(thresholdFor(state.sensitivity));
    segmenter.setStartMs(state.bargeIn ? 250 : 90);
    const event = segmenter.push(chunk);
    if (!event) return;
    if (event.type === "start") {
      publish({ phase: "speaking", message: "" });
      notifySpeechStart();
    }
    else if (event.type === "end") transcribe(event.samples);
    else publish({ phase: pending ? "transcribing" : "waiting" });
  }, error => { if (token === generation) fail(error); });
  sampleRate = capture.sampleRate;
  return {
    stop() {
      controller.abort();
      capture.stop();
    },
    pause(next) {
      if (next === paused) return;
      paused = next;
      if (next) {
        // Câu đang chép trước lúc Peto trả lời không được về muộn rồi thành tin nhắn của lượt tiếp theo.
        segmentVersion++;
        controller.abort();
        controller = new AbortController();
        pending = 0;
        queue = Promise.resolve();
      }
      // Câu đang nói dở lúc Peto bắt đầu trả lời thì bỏ: phần đó đã nằm trong tin vừa gửi hoặc là tiếng loa.
      segmenter?.reset();
    },
  };
}

/* ---------- Giữ để nói ---------- */

/** Giữ ngắn hơn chừng này là bấm nhầm (như AIRI): không nghe, không gửi gì. */
export const MIN_HOLD_MS = 300;
/** Giữ lâu hơn chừng này thì tự chốt câu, để không ghi âm vô hạn khi phím bị kẹt. */
export const MAX_HOLD_MS = 60000;
export const HOLD_TOO_SHORT = "Giữ trong lúc nói, thả ra là xong.";

interface HoldEngine {
  /** Thả ra: chốt câu, chép lời rồi gọi holdFinished. */
  finish(endedAt: number): void;
  /** Bỏ: không giao chữ nào. */
  cancel(): void;
}

interface Hold {
  token: number;
  engine: HoldEngine | null;
  ended: "finish" | "cancel" | null;
  endedAt: number;
}

let hold: Hold | null = null;
let holdTimer: ReturnType<typeof setTimeout> | undefined;
let hintTimer: ReturnType<typeof setTimeout> | undefined;

/** Lời nhắc ngắn trên thanh Giữ để nói, tự tắt. */
export function flashHearingHint(text: string) {
  clearTimeout(hintTimer);
  publish({ hint: text });
  hintTimer = setTimeout(() => publish({ hint: "" }), 2600);
}

/** Bỏ lần giữ đang có mà không đổi trạng thái hiển thị (người gọi tự đặt lại). */
function dropHold() {
  clearTimeout(holdTimer);
  const current = hold;
  hold = null;
  if (!current) return;
  current.ended = "cancel";
  current.engine?.cancel();
  if (state.holding) publish({ holding: false });
}

/** Lần giữ đã chép xong (hay không có gì để chép): về lại trạng thái chờ giữ. */
function holdFinished(token: number) {
  if (hold?.token !== token || token !== generation) return;
  hold = null;
  publish({ holding: false, phase: state.listening ? "ready" : "off", interim: "" });
  publishLevel(0);
}

function holdFailed(token: number, error: unknown) {
  if (token !== generation) return;
  // Khóa sai, hết số dư, không có quyền micro: thôi hẳn. Lỗi mạng, giới hạn lượt: báo rồi chờ lần giữ sau.
  if (error instanceof HearingError && !error.fatal) {
    dropHold();
    publish({ holding: false, phase: "ready", interim: "", message: error.message });
    publishLevel(0);
  } else {
    fail(error);
  }
}

/** Bật Giữ để nói: chưa mở micro, chỉ chờ người dùng giữ. Rời trang hay mất tiêu điểm lúc đang giữ thì thôi lần giữ đó. */
function armHold() {
  publish({ listening: true, testing: false, phase: "ready", interim: "", message: "", holding: false });
  publishLevel(0);
  const interrupt = () => {
    if (!hold) return;
    cancelHold({ keepInterim: true });
    flashHearingHint("Đã thôi nghe khi rời trang. Giữ lại để nói tiếp.");
  };
  const hidden = () => {
    if (document.visibilityState === "hidden") interrupt();
  };
  document.addEventListener("visibilitychange", hidden);
  window.addEventListener("pagehide", interrupt);
  window.addEventListener("offline", interrupt);
  window.addEventListener("blur", interrupt);
  removeLifecycle = () => {
    document.removeEventListener("visibilitychange", hidden);
    window.removeEventListener("pagehide", interrupt);
    window.removeEventListener("offline", interrupt);
    window.removeEventListener("blur", interrupt);
  };
}

/** Thanh đo cho nguồn trình duyệt khi giữ: mở sau khi bộ nhận giọng đã chạy, hỏng thì thôi, không ảnh hưởng việc nghe. */
function holdMeter(current: () => boolean) {
  let capture: MicCapture | null = null;
  let stopped = false;
  let started = false;
  return {
    start() {
      if (stopped || started || !captureSupported()) return;
      started = true;
      void openMicrophone("", (chunk) => {
        if (current() && !stopped) publishLevel(levelOf(rmsOf(chunk)));
      }, () => {}).then((opened) => {
        if (stopped || !current()) opened.stop();
        else capture = opened;
      }).catch(() => {});
    },
    stop() {
      stopped = true;
      capture?.stop();
      capture = null;
    },
  };
}

function browserHold(token: number): HoldEngine {
  if (!browserSpeechSupported()) throw new Error(UNSUPPORTED);
  const current = () => token === generation;
  let finishing = false;
  let endedAt = 0;
  let safety: ReturnType<typeof setTimeout> | undefined;
  const meter = holdMeter(current);
  const timing = (): HearingTiming => ({ endedAt, finalizedAt: performance.now() });
  // Câu trình duyệt chốt giữa lúc giữ vào ô nhắn ngay; Tự gửi chờ tới khi thả.
  const recognition = startBrowserSpeech(state.language, {
    onConnecting: () => { if (current() && !finishing) publish({ phase: "starting" }); },
    onReady: () => {
      if (!current() || finishing) return;
      publish({ phase: "waiting" });
      meter.start();
    },
    onSpeechStart: () => { if (current() && !finishing) publish({ phase: "speaking" }); },
    onSpeechEnd: () => {},
    onInterim: (text) => { if (current()) publish({ interim: text }); },
    onFinal: (text) => { if (current()) deliver(text, true, finishing ? timing() : undefined); },
    onDraft: (text) => { if (current()) deliver(text, false); },
    onNotice: (message) => { if (current() && message) publish({ message }); },
    onError: (message) => {
      if (!current()) return;
      if (finishing) {
        clearTimeout(safety);
        holdFinished(token);
      } else {
        holdFailed(token, new Error(message));
      }
    },
  });
  return {
    finish(at) {
      finishing = true;
      endedAt = at;
      meter.stop();
      publishLevel(0);
      // Trình duyệt chốt phần đang nghe dở rồi mới kết thúc; chờ tối đa 3 giây rồi lấy chữ đang có.
      safety = setTimeout(() => {
        if (!current()) return;
        if (state.interim.trim()) deliver(state.interim.trim(), true, timing());
        recognition.stop();
        holdFinished(token);
      }, 3000);
      recognition.finish(() => {
        clearTimeout(safety);
        holdFinished(token);
      });
    },
    cancel() {
      clearTimeout(safety);
      meter.stop();
      recognition.stop();
    },
  };
}

async function keyHold(token: number, source: HearingProviderId): Promise<HoldEngine> {
  const provider = hearingProvider(source)!;
  if (!hearingKeyReady(provider, getKeyConfigs()[provider.id])) {
    throw new Error(`Chưa nhập đủ khóa ${provider.name} trong Cài đặt Companion → Nghe.`);
  }
  if (!captureSupported()) throw new Error("Trình duyệt này chưa cho ghi âm từ micro.");
  const controller = new AbortController();
  const chunks: Float32Array[] = [];
  let length = 0;
  let speechMs = 0;
  let finished = false;
  let sampleRate = 0;
  const capture = await openMicrophone(state.deviceId, (chunk) => {
    if (token !== generation || finished || !sampleRate) return;
    const rms = rmsOf(chunk);
    publishLevel(levelOf(rms));
    if (rms >= thresholdFor(state.sensitivity)) {
      speechMs += chunk.length / sampleRate * 1000;
      if (state.phase !== "speaking") publish({ phase: "speaking" });
    }
    chunks.push(chunk.slice());
    length += chunk.length;
  }, (error) => { if (token === generation) holdFailed(token, error); });
  sampleRate = capture.sampleRate;
  return {
    finish(endedAt) {
      finished = true;
      capture.stop();
      publishLevel(0);
      // Không có đoạn nào đủ to để là tiếng nói: khỏi gửi đi chép, đỡ tốn lượt của người dùng.
      if (speechMs < 150) {
        flashHearingHint("Chưa nghe thấy tiếng nói. Giữ trong lúc nói nhé.");
        holdFinished(token);
        return;
      }
      const samples = new Float32Array(length);
      let offset = 0;
      for (const chunk of chunks) {
        samples.set(chunk, offset);
        offset += chunk.length;
      }
      const audio = wavFromSamples(samples, sampleRate);
      const language = state.language;
      void audioRequest(abort => transcribeWithKey(provider, getKeyConfigs()[provider.id] ?? {}, audio, language, abort),
        controller.signal, 30000, new HearingError("Nguồn nghe chép lời quá lâu. Bạn có thể giữ và nói lại.", false))
        .then((words) => {
          if (token !== generation) return;
          if (words) deliver(words, true, { endedAt, finalizedAt: performance.now() });
          else flashHearingHint("Chưa nghe ra chữ nào. Giữ và nói lại nhé.");
          holdFinished(token);
        })
        .catch((error) => { if (token === generation && !controller.signal.aborted) holdFailed(token, error); });
    },
    cancel() {
      finished = true;
      controller.abort();
      capture.stop();
    },
  };
}

/**
 * Bắt đầu giữ để nói. Trả false khi chưa bật Giữ để nói hay lần giữ trước còn đang chép. Gọi ngay trong sự kiện nhấn
 * phím hay nhấn nút: nguồn trình duyệt cần lượt thao tác của người dùng để mở micro.
 */
export function beginHold(): boolean {
  if (!state.listening || state.testing || state.mode !== "hold" || hold || state.phase !== "ready") return false;
  if (document.visibilityState === "hidden" || !navigator.onLine) return false;
  const token = ++generation;
  const current: Hold = { token, engine: null, ended: null, endedAt: 0 };
  hold = current;
  clearTimeout(hintTimer);
  publish({ holding: true, holdStartedAt: performance.now(), phase: "starting", interim: "", message: "", hint: "" });
  companionSink?.onHoldStart?.();
  holdTimer = setTimeout(() => {
    if (hold !== current || current.ended) return;
    endHold();
    flashHearingHint("Giữ tối đa một phút mỗi lần; câu vừa rồi đã được chốt.");
  }, MAX_HOLD_MS);
  const attach = (engine: HoldEngine) => {
    if (token !== generation || hold !== current) {
      engine.cancel();
      return;
    }
    current.engine = engine;
    if (current.ended === "finish") engine.finish(current.endedAt);
    else if (state.source !== "browser" && state.phase === "starting") publish({ phase: "waiting" });
  };
  try {
    if (state.source === "browser") attach(browserHold(token));
    else void keyHold(token, state.source).then(attach, (error) => holdFailed(token, error));
  } catch (error) {
    holdFailed(token, error);
  }
  return true;
}

/** Thả ra: chốt câu. "short" khi giữ quá ngắn (đã bỏ, không nghe gì). */
export function endHold(): "short" | "done" | null {
  const current = hold;
  if (!current || current.ended) return null;
  if (performance.now() - state.holdStartedAt < MIN_HOLD_MS) {
    cancelHold();
    return "short";
  }
  clearTimeout(holdTimer);
  current.ended = "finish";
  current.endedAt = performance.now();
  publish({ holding: false, phase: "transcribing" });
  publishLevel(0);
  current.engine?.finish(current.endedAt);
  return "done";
}

/** Bỏ lần giữ (Esc, rời trang). `keepInterim`: giữ chữ đang nghe dở làm bản nháp để sửa, không tự gửi. */
export function cancelHold(options: { keepInterim?: boolean } = {}) {
  if (!hold) return;
  if (options.keepInterim && state.interim.trim()) deliver(state.interim.trim(), false);
  generation += 1;
  dropHold();
  publish({ holding: false, phase: state.listening ? "ready" : "off", interim: "" });
  publishLevel(0);
}

/** Bật nghe. `test`: nghe thử trong Cài đặt, chữ về khung Nghe thử và không bị tạm dừng khi Peto nói. */
export async function startListening(mode: "companion" | "test" = "companion"): Promise<void> {
  const token = ++generation;
  stopEngine();
  dropHold();
  if (document.visibilityState === 'hidden' || !navigator.onLine) {
    publish({ listening: false, testing: false, phase: 'off', interim: '', message: 'Mở lại trang và kiểm tra mạng rồi bấm micro để nghe nhé.' });
    publishLevel(0);
    return;
  }
  const testing = mode === "test";
  if (!testing && state.mode === "hold") {
    armHold();
    return;
  }
  publish({ listening: true, testing, phase: "starting", interim: "", message: "" });
  const suspend = (message: string) => {
    if (token !== generation) return;
    stopListening({ keepInterim: true });
    publish({ message });
  };
  const hidden = () => {
    if (document.visibilityState === 'hidden') suspend('Micro đã dừng khi trang xuống nền. Chữ đã nhận được giữ lại; bấm micro để nghe tiếp.');
  };
  const leaving = () => suspend('Micro đã dừng khi rời trang. Bấm micro để nghe tiếp.');
  const offline = () => suspend('Micro đã dừng do mất mạng. Chữ đã nhận được giữ lại; có mạng rồi bấm micro để nghe tiếp.');
  document.addEventListener('visibilitychange', hidden);
  window.addEventListener('pagehide', leaving);
  window.addEventListener('offline', offline);
  removeLifecycle = () => {
    document.removeEventListener('visibilitychange', hidden);
    window.removeEventListener('pagehide', leaving);
    window.removeEventListener('offline', offline);
  };
  try {
    const next = state.source === "browser" ? await browserEngine(token) : await keyEngine(token, state.source);
    if (token !== generation) {
      next.stop();
      return;
    }
    engine = next;
    const paused = pauseWanted && !testing;
    if (paused) next.pause(true);
    if (paused) publish({ phase: "paused" });
    else if (state.source !== "browser") publish({ phase: "waiting" });
  } catch (error) {
    if (token === generation) fail(error);
  }
}

export function stopListening(options: { keepInterim?: boolean } = {}) {
  // Chỉ giữ chữ khi người dùng chủ động tắt: rời tab, đổi nguồn hay Peto đang nói thì bỏ chữ dở.
  if (options.keepInterim && state.interim.trim()) deliver(state.interim.trim(), false);
  generation += 1;
  stopEngine();
  dropHold();
  publish({ listening: false, testing: false, phase: "off", interim: "" });
  publishLevel(0);
}

/** Companion báo Peto đang trả lời hay đang nói: tạm không nghe để Peto khỏi tự nghe giọng mình qua loa. */
export function setHearingPaused(paused: boolean) {
  if (pauseWanted === paused) return;
  pauseWanted = paused;
  if (!engine || state.testing || !state.listening) return;
  engine.pause(paused);
  if (!state.listening) return;
  if (state.phase === "transcribing" && !paused) return;
  // Nguồn trình duyệt tự báo đang kết nối/sẵn sàng qua các sự kiện, không ghi đè kết quả ở đây.
  if (paused) publish({ phase: "paused", interim: "" });
  else if (state.source !== "browser") publish({ phase: "waiting", interim: "" });
  else publish({ interim: "" });
  if (paused) publishLevel(0);
}

export function setHearingSetting<K extends keyof HearingSettings>(key: K, value: HearingSettings[K]) {
  write(SETTING_KEYS[key], typeof value === "boolean" ? (value ? "1" : "0") : String(value));
  publish({ [key]: value } as Partial<HearingState>);
  // Đổi nguồn, micro hay ngôn ngữ lúc đang nghe thì mở lại bộ nghe theo lựa chọn mới; đổi cách nghe cũng vậy.
  if (state.listening && (key === "source" || key === "deviceId" || key === "language" || (key === "mode" && !state.testing))) {
    void startListening(state.testing ? "test" : "companion");
  }
}

export function clearHearingMessage() {
  publish({ message: "" });
}

/** Đọc lại lựa chọn đã lưu (test xóa localStorage giữa các ca). */
export function loadHearingSettings() {
  publish(readSettings());
}
