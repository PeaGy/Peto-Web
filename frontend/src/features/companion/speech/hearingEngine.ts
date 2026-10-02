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

export type HearingSource = "browser" | HearingProviderId;
export type HearingPhase = "off" | "starting" | "waiting" | "speaking" | "transcribing" | "paused";

export interface HearingSettings {
  source: HearingSource;
  deviceId: string;
  language: HearingLanguage;
  /** 0..100: càng cao càng dễ tính là có tiếng nói (chỉ dùng cho nguồn dùng khóa). */
  sensitivity: number;
  autoSend: boolean;
  pauseWhileSpeaking: boolean;
}

export interface HearingState extends HearingSettings {
  listening: boolean;
  /** Đang nghe thử trong Cài đặt: chữ nghe được về khung Nghe thử, không vào ô nhắn Companion. */
  testing: boolean;
  phase: HearingPhase;
  /** Chữ đang nghe dở (chỉ nguồn trình duyệt có). */
  interim: string;
  message: string;
}

const SETTING_KEYS: Record<keyof HearingSettings, string> = {
  source: "peto-hearing-source",
  deviceId: "peto-hearing-device",
  language: "peto-hearing-language",
  sensitivity: "peto-hearing-sensitivity",
  autoSend: "peto-hearing-autosend",
  pauseWhileSpeaking: "peto-hearing-pause",
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
  };
}

let state: HearingState = {
  ...readSettings(), listening: false, testing: false, phase: "off", interim: "", message: "",
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

interface Engine {
  stop(): void;
  pause(paused: boolean): void;
}

let engine: Engine | null = null;
let generation = 0;
let pauseWanted = false;

function stopEngine() {
  engine?.stop();
  engine = null;
}

function fail(error: unknown) {
  generation += 1;
  stopEngine();
  publish({
    listening: false, testing: false, phase: "off", interim: "",
    message: error instanceof Error ? error.message : "Chưa nghe được.",
  });
  publishLevel(0);
}

const UNSUPPORTED = "Trình duyệt này chưa có tính năng nghe (Firefox chưa hỗ trợ). Dùng Chrome, Edge hoặc Safari, "
  + "hoặc chọn nguồn dùng khóa trong Cài đặt → Giọng nói → Peto nghe.";

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
    recognition = startBrowserSpeech(state.language, {
      onConnecting: () => {
        if (current() && !paused) publish({ phase: "starting" });
      },
      onReady: () => {
        if (!current() || paused) return;
        publish({ phase: "waiting" });
        startMeter();
      },
      onSpeechStart: () => {
        if (current() && !paused) {
          endedAt = undefined; lastFinal = undefined;
          publish({ phase: "speaking" });
        }
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
        if (current() && !paused) publish(text ? { interim: text, phase: "speaking" } : { interim: "" });
      },
      onFinal: (text) => {
        if (!current() || paused) return;
        lastFinal = { endedAt, finalizedAt: performance.now() };
        deliver(text, true, lastFinal);
        endedAt = undefined;
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
    throw new Error(`Chưa nhập đủ khóa ${provider.name} trong Cài đặt → Giọng nói → Peto nghe.`);
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
        const words = await transcribeWithKey(provider, getKeyConfigs()[provider.id] ?? {}, audio, language, signal);
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
    const event = segmenter.push(chunk);
    if (!event) return;
    if (event.type === "start") publish({ phase: "speaking", message: "" });
    else if (event.type === "end") transcribe(event.samples);
    else publish({ phase: pending ? "transcribing" : "waiting" });
  });
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

/** Bật nghe. `test`: nghe thử trong Cài đặt, chữ về khung Nghe thử và không bị tạm dừng khi Peto nói. */
export async function startListening(mode: "companion" | "test" = "companion"): Promise<void> {
  stopEngine();
  const token = ++generation;
  const testing = mode === "test";
  publish({ listening: true, testing, phase: "starting", interim: "", message: "" });
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
  // Đổi nguồn, micro hay ngôn ngữ lúc đang nghe thì mở lại bộ nghe theo lựa chọn mới.
  if (state.listening && (key === "source" || key === "deviceId" || key === "language")) {
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
