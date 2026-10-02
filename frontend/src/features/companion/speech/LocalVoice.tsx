import { useCallback, useEffect, useRef, useState } from "react";
import { StreamSpeechText, type VoiceStream, type SpeechExpressions } from './streamSpeech';
import type { SpeechQueue } from './speechQueue';
import {
  fallbackOnly,
  LOCAL_VOICE_ENABLED_KEY,
  LOCAL_VOICE_NAME_KEY,
  LocalVoicePlayer,
  OFFICIAL_VOICE_KEY,
  probeVoiceHealth,
  serverSynth,
  speakableText,
  VOICE_FALLBACK_EVENT,
  VOICE_FALLBACK_KEY,
  VOICE_SOURCE_KEY,
  withFallback,
  type SpeakPhase,
  type SpeechTimingHooks,
  type Synthesize,
  type VoiceFallbackDetail,
  type VoiceHealth,
} from "./localSpeech";
import {
  KEY_PROVIDERS,
  keyProvider,
  keyReady,
  speakWithKey,
  updateKeyConfig,
  useKeyConfigs,
  type KeyConfig,
  type KeyConfigs,
  type KeyProviderId,
} from "./voiceProviders";

/** Tên hiển thị của các giọng mẫu đã chọn ở local-tts; giọng lạ thì hiện nguyên mã. */
export const VOICE_LABELS: Record<string, string> = {
  "playful-1": "Sáng & tinh nghịch",
  "gentle-2": "Dịu & vui vẻ",
};

/** Giọng của Giọng Peto (nguồn chính thức); giọng khác hiện "Nhà cung cấp · mã giọng". */
const OFFICIAL_LABELS: Record<string, string> = {
  "stepfun:jilingshaonv": "Jiling, tinh nghịch",
  "stepfun:lively-girl": "Lively Girl",
};
const CLOUD_NAMES: Record<string, string> = { stepfun: "StepFun", openai: "OpenAI", qwen: "Qwen" };

export function voiceLabel(name: string): string {
  if (VOICE_LABELS[name]) return VOICE_LABELS[name];
  if (OFFICIAL_LABELS[name]) return OFFICIAL_LABELS[name];
  const [provider, ...rest] = name.split(":");
  return rest.length ? `${CLOUD_NAMES[provider] ?? provider} · ${rest.join(":")}` : name;
}

/** Giọng của máy chủ Peto kèm tên nguồn, cho câu báo chuyển giọng dự phòng. */
function serverVoiceLabel(name: string): string {
  return VOICE_LABELS[name] ? `Local Voice của Peto (${VOICE_LABELS[name]})` : `Giọng Peto (${voiceLabel(name)})`;
}

export type LocalVoiceStatus = "off" | "checking" | "ready" | "missing";

/** Giọng Peto (chính thức, khóa của chủ web), Local Voice của Peto, hay một nhà cung cấp dùng khóa riêng. */
export type VoiceSourceId = "official" | "home" | KeyProviderId;

/** Nguồn dự phòng: chỉ hai nguồn của máy chủ Peto, vì máy chủ đổi được sang chúng ngay trong một lượt đọc. */
export type FallbackChoice = "" | "home" | "official";

interface Speaking {
  key: string;
  phase: SpeakPhase;
}

export interface LocalVoice {
  notice?: string;
  enabled: boolean;
  setEnabled: (value: boolean) => void;
  /** "ready" khi nguồn đang chọn, hoặc nguồn dự phòng của nó, nói được. */
  status: LocalVoiceStatus;
  /** Vì sao nguồn đang chọn chưa nói được; rỗng khi đã sẵn sàng. */
  problem: string;
  health: VoiceHealth | null;
  checking: boolean;
  source: VoiceSourceId;
  setSource: (value: VoiceSourceId) => void;
  officialVoice: string;
  setOfficialVoice: (value: string) => void;
  homeVoice: string;
  setHomeVoice: (value: string) => void;
  fallback: FallbackChoice;
  setFallback: (value: FallbackChoice) => void;
  keys: KeyConfigs;
  setKeyConfig: (id: KeyProviderId, config: KeyConfig) => void;
  forgetKey: (id: KeyProviderId) => void;
  recheck: () => void;
  speaking: Speaking | null;
  /**
   * Đọc một đoạn. Lỗi thì Promise bị từ chối kèm câu báo tiếng Việt; bị dừng hay bị lượt đọc khác thay
   * chỗ thì kết thúc êm, không báo lỗi. ``fallback: false`` (Nghe thử) chỉ dùng nguồn đang chọn.
   */
  speak: (key: string, text: string, options?: { fallback?: boolean; timing?: SpeechTimingHooks; expressions?: SpeechExpressions }) => Promise<void>;
  stream: (key: string, timing?: SpeechTimingHooks, expressions?: SpeechExpressions) => VoiceStream;
  stop: () => void;
}

function read(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {}
}

const SOURCES = new Set<string>(["official", "home", ...KEY_PROVIDERS.map((provider) => provider.id)]);

/** Nguồn đã chọn; máy đã lưu giọng theo kiểu cũ (một tên giọng chung) thì suy ra nguồn từ tên đó. */
function readSource(): VoiceSourceId {
  const saved = read(VOICE_SOURCE_KEY);
  if (SOURCES.has(saved)) return saved as VoiceSourceId;
  const legacy = read(LOCAL_VOICE_NAME_KEY);
  return legacy && !legacy.includes(":") ? "home" : "official";
}

/**
 * Chưa chọn bao giờ thì dự phòng bằng Máy nhà: Giọng Peto hết lượt hay chưa mở mà máy nhà đang bật thì Peto vẫn nói.
 * Bản cũ lưu mã giọng dự phòng ("playful-1", "openai:nova"); bản này lưu tên nguồn.
 */
function readFallback(): FallbackChoice {
  let saved: string | null = null;
  try {
    saved = localStorage.getItem(VOICE_FALLBACK_KEY);
  } catch {}
  if (saved === null) return "home";
  if (saved === "home" || saved === "official" || !saved) return saved as FallbackChoice;
  return saved.includes(":") ? "official" : "home";
}

function day(resets: string): string {
  const [, month, date] = resets.split("-");
  return date && month ? `${date}/${month}` : "đầu tháng sau";
}

/** Nguồn đã nói được chưa, và nếu chưa thì vì sao (câu hiện cho người dùng). */
export function sourceState(
  source: VoiceSourceId,
  health: VoiceHealth | null,
  keys: KeyConfigs,
): { ready: boolean; problem: string } {
  const provider = keyProvider(source);
  if (provider) {
    return keyReady(provider, keys[provider.id])
      ? { ready: true, problem: "" }
      : { ready: false, problem: `Chưa nhập đủ thông tin ${provider.name} trong Cài đặt → Giọng nói.` };
  }
  if (!health) return { ready: false, problem: "Chưa kết nối được máy chủ giọng nói." };
  if (source === "home") {
    return health.home.online ? { ready: true, problem: "" } : { ready: false, problem: "Máy nhà của Peto đang tắt." };
  }
  const official = health.official;
  if (!official.voices.length) return { ready: false, problem: "Giọng Peto chưa mở trên máy chủ này." };
  if (!official.allowed) return { ready: false, problem: "Giọng Peto dành cho tài khoản Discord và Google." };
  if (official.limit <= official.used) {
    return { ready: false, problem: `Đã hết lượt Giọng Peto tháng này; lượt mới có từ ngày ${day(official.resets)}.` };
  }
  return { ready: true, problem: "" };
}

/** Giọng đã lưu nếu máy chủ còn giọng đó, không thì giọng đầu tiên máy chủ có. */
function pick(saved: string, voices: string[], fallback: string): string {
  if (voices.includes(saved)) return saved;
  return voices[0] ?? (saved || fallback);
}

/**
 * Giọng nói dùng chung cho Companion và mục Giọng nói trong Cài đặt: đã bật chưa, nguồn nào, nguồn đó có nói được
 * không, và đoạn nào đang được đọc.
 *
 * Chỉ dò máy chủ khi người dùng đã bật và `active` đúng (Companion hoặc Cài đặt đang mở).
 */
export function useLocalVoice(active: boolean): LocalVoice {
  const [notice, setNotice] = useState('');
  const [enabled, setEnabled] = useState(() => read(LOCAL_VOICE_ENABLED_KEY) === "1");
  const [source, setSourceState] = useState<VoiceSourceId>(readSource);
  const [officialChoice, setOfficialVoice] = useState(() => read(OFFICIAL_VOICE_KEY)
    || (read(LOCAL_VOICE_NAME_KEY).includes(":") ? read(LOCAL_VOICE_NAME_KEY) : ""));
  const [homeChoice, setHomeVoice] = useState(() => {
    const legacy = read(LOCAL_VOICE_NAME_KEY);
    return legacy && !legacy.includes(":") ? legacy : "";
  });
  const [fallback, setFallbackState] = useState<FallbackChoice>(readFallback);
  const keys = useKeyConfigs();
  const [health, setHealth] = useState<VoiceHealth | null>(null);
  const [probing, setProbing] = useState(false);
  const [probe, setProbe] = useState(0);
  const [speaking, setSpeaking] = useState<Speaking | null>(null);
  const player = useRef<LocalVoicePlayer | null>(null);
  const speakVersion = useRef(0);

  const officialVoice = pick(officialChoice, health?.official.voices ?? [], "");
  const homeVoice = pick(homeChoice, health?.home.voices ?? [], "playful-1");
  const state = sourceState(source, health, keys);
  const backupSource: FallbackChoice = fallback !== source ? fallback : "";
  const backupReady = backupSource !== "" && sourceState(backupSource, health, keys).ready;
  const backupVoice = !backupReady ? "" : backupSource === "home" ? homeVoice : officialVoice;
  const status: LocalVoiceStatus = !enabled ? "off"
    : state.ready || backupVoice ? "ready"
    : probing && !health ? "checking" : "missing";

  useEffect(() => {
    const changed = (event: Event) => {
      const detail = (event as CustomEvent<VoiceFallbackDetail | string>).detail;
      const { voice, reason } = typeof detail === "string" ? { voice: detail, reason: undefined } : detail;
      setNotice(`${reason ? `${reason} ` : ""}Đã chuyển sang giọng dự phòng: ${serverVoiceLabel(voice)}.`);
      // Giọng Peto hết lượt giữa chừng thì máy chủ tự đổi giọng mà không báo số lượt: dò lại cho Cài đặt hiện đúng.
      setProbe((count) => count + 1);
    };
    window.addEventListener(VOICE_FALLBACK_EVENT, changed);
    return () => window.removeEventListener(VOICE_FALLBACK_EVENT, changed);
  }, []);

  const stop = useCallback(() => {
    speakVersion.current += 1;
    player.current?.stop();
    setSpeaking(null);
  }, []);

  // Khóa màn hình/đổi tab có thể treo tiếng và các lời hứa phát; dừng cả đoạn đang xin, không tự phát lại.
  useEffect(() => {
    const hidden = () => { if (document.visibilityState === 'hidden') stop(); };
    document.addEventListener('visibilitychange', hidden);
    window.addEventListener('pagehide', stop);
    window.addEventListener('offline', stop);
    return () => {
      document.removeEventListener('visibilitychange', hidden);
      window.removeEventListener('pagehide', stop);
      window.removeEventListener('offline', stop);
    };
  }, [stop]);

  useEffect(() => write(LOCAL_VOICE_ENABLED_KEY, enabled ? "1" : "0"), [enabled]);
  useEffect(() => write(VOICE_SOURCE_KEY, source), [source]);
  useEffect(() => { if (officialChoice) write(OFFICIAL_VOICE_KEY, officialChoice); }, [officialChoice]);
  useEffect(() => { if (homeChoice) write(LOCAL_VOICE_NAME_KEY, homeChoice); }, [homeChoice]);

  useEffect(() => {
    if (!enabled) {
      setHealth(null);
      setNotice('');
      stop();
      return;
    }
    if (!active) return;
    const controller = new AbortController();
    setProbing(true);
    void probeVoiceHealth(controller.signal).then((found) => {
      if (controller.signal.aborted) return;
      setHealth(found);
      setProbing(false);
    });
    return () => {
      controller.abort();
      setProbing(false);
    };
  }, [enabled, active, probe, stop]);

  // Người dùng hay bật máy nhà rồi mới quay lại trang: dò lại khi cửa sổ được chọn lại.
  useEffect(() => {
    if (status !== "missing" || !active || keyProvider(source)) return;
    const again = () => setProbe((count) => count + 1);
    window.addEventListener("focus", again);
    return () => window.removeEventListener("focus", again);
  }, [status, active, source]);

  useEffect(() => () => {
    speakVersion.current += 1;
    player.current?.stop();
  }, []);

  const setSource = useCallback((value: VoiceSourceId) => {
    stop();
    setNotice('');
    setSourceState(value);
  }, [stop]);

  const setFallback = useCallback((value: FallbackChoice) => {
    stop();
    setFallbackState(value);
    write(VOICE_FALLBACK_KEY, value);
  }, [stop]);

  const setKeyConfig = useCallback((id: KeyProviderId, config: KeyConfig) => updateKeyConfig(id, config), []);

  const forgetKey = useCallback((id: KeyProviderId) => {
    stop();
    updateKeyConfig(id, null);
  }, [stop]);

  const synth = useCallback((useBackup: boolean): Synthesize => {
    const backup = useBackup ? backupVoice : "";
    if (!state.ready) {
      if (backup) return fallbackOnly(backup, state.problem);
      throw new Error(state.problem || "Giọng nói chưa sẵn sàng.");
    }
    if (source === "official") {
      return serverSynth(officialVoice, {
        fallback: backup || undefined,
        onUsed: (used) => setHealth((current) => current && { ...current, official: { ...current.official, used } }),
      });
    }
    if (source === "home") return serverSynth(homeVoice, { fallback: backup || undefined });
    const provider = keyProvider(source)!;
    const config = keys[provider.id] ?? {};
    const primary: Synthesize = (text, signal) => speakWithKey(provider, config, text, signal);
    return backup ? withFallback(primary, backup) : primary;
  }, [backupVoice, state.ready, state.problem, source, officialVoice, homeVoice, keys]);

  const speak = useCallback(async (key: string, text: string, options: { fallback?: boolean; timing?: SpeechTimingHooks; expressions?: SpeechExpressions } = {}) => {
    setNotice('');
    if (!player.current) player.current = new LocalVoicePlayer();
    const version = ++speakVersion.current;
    setSpeaking({ key, phase: "loading" });
    try {
      const generate = synth(options.fallback !== false);
      if (speakableText(text)) options.timing?.onTextReady?.();
      const generateChunk: Synthesize = (chunk, signal) => {
        if (version === speakVersion.current) options.timing?.onSynthesisStart?.();
        return generate(chunk, signal);
      };
      const onPhase = (phase: SpeakPhase) => {
        if (version === speakVersion.current) {
          if (phase === 'playing') options.timing?.onPlaying?.();
          setSpeaking({ key, phase });
        }
      };
      let result: 'done' | 'stopped';
      if (options.expressions?.cues?.length) {
        let lastEmotion: string | undefined;
        const speech = new StreamSpeechText(undefined, false);
        for (const cue of options.expressions.cues) speech.markEmotion(cue.emotion, cue.offset);
        speech.push(text); speech.finish();
        result = await player.current.speakQueue(speech.queue, generateChunk, onPhase, chunk => {
          if (version === speakVersion.current && chunk.emotion && chunk.emotion !== lastEmotion) {
            lastEmotion = chunk.emotion; options.expressions?.onEmotion(chunk.emotion);
          }
        });
      } else {
        result = await player.current.speak(text, generateChunk, onPhase);
      }
      if (result === 'stopped') options.timing?.onStopped?.();
    } catch (error) {
      if (version === speakVersion.current) {
        throw error instanceof Error ? error : new Error("Chưa đọc được đoạn này.");
      }
    } finally {
      if (version === speakVersion.current) setSpeaking(null);
    }
  }, [synth]);

  const readQueue = useCallback(async (key: string, queue: SpeechQueue, timing?: SpeechTimingHooks, expressions?: SpeechExpressions) => {
    setNotice('');
    if (!player.current) player.current = new LocalVoicePlayer();
    const version = ++speakVersion.current;
    setSpeaking({ key, phase: 'loading' });
    try {
      const generate = synth(true);
      let lastEmotion: string | undefined;
      const result = await player.current.speakQueue(queue, (chunk, signal) => {
        if (version === speakVersion.current) timing?.onSynthesisStart?.();
        return generate(chunk, signal);
      }, phase => {
        if (version === speakVersion.current) {
          if (phase === 'playing') timing?.onPlaying?.();
          setSpeaking({ key, phase });
        }
      }, chunk => {
        if (version === speakVersion.current && chunk.emotion && chunk.emotion !== lastEmotion) {
          lastEmotion = chunk.emotion; expressions?.onEmotion(chunk.emotion);
        }
      });
      if (result === 'stopped') timing?.onStopped?.();
    } catch (error) {
      if (version === speakVersion.current) throw error instanceof Error ? error : new Error('Chưa đọc được đoạn này.');
    } finally {
      queue.cancel();
      if (version === speakVersion.current) setSpeaking(null);
    }
  }, [synth]);

  const stream = useCallback((key: string, timing?: SpeechTimingHooks, expressions?: SpeechExpressions): VoiceStream => {
    const text = new StreamSpeechText(timing?.onTextReady);
    for (const cue of expressions?.cues ?? []) text.markEmotion(cue.emotion, cue.offset);
    return { push: delta => text.push(delta), markEmotion: (emotion, offset) => text.markEmotion(emotion, offset),
      finish: () => text.finish(), done: readQueue(key, text.queue, timing, expressions) };
  }, [readQueue]);

  const recheck = useCallback(() => setProbe((count) => count + 1), []);

  return {
    enabled, setEnabled, status, problem: enabled && !state.ready ? state.problem : "", health, checking: probing,
    source, setSource, officialVoice, setOfficialVoice, homeVoice, setHomeVoice, fallback, setFallback,
    keys, setKeyConfig, forgetKey, recheck, speaking, speak, stream, stop, notice,
  };
}

export function SpeakerIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 9h4l5-4v14l-5-4H4z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M17 9a4 4 0 0 1 0 6M19.5 6.5a8 8 0 0 1 0 11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function SpeakerOffIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 9h4l5-4v14l-5-4H4z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M17 9.5l5 5M22 9.5l-5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" />
    </svg>
  );
}

/** Nút nghe lại dưới tin của Peto: chỉ một icon nhỏ, còn nhãn đọc màn hình nói rõ đang ở bước nào. */
export function SpeakButton({ phase, onSpeak, onStop }: {
  phase: SpeakPhase | null;
  onSpeak: () => void;
  onStop: () => void;
}) {
  const label = phase === "loading" ? "Đang chuẩn bị giọng đọc, bấm để dừng"
    : phase === "buffering" ? "Đang chờ đoạn tiếng tiếp theo, bấm để dừng"
      : phase === "playing" ? "Dừng đọc" : "Nghe Peto đọc tin này";
  return (
    <button
      type="button"
      className={phase ? `message-speak ${phase}` : "message-speak"}
      aria-label={label}
      title={label}
      onClick={phase ? onStop : onSpeak}
    >
      {phase === "playing" || phase === "buffering" ? <StopIcon /> : <SpeakerIcon size={15} />}
    </button>
  );
}
