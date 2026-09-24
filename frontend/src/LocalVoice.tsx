import { useCallback, useEffect, useRef, useState } from "react";
import {
  LOCAL_VOICE_ENABLED_KEY,
  LOCAL_VOICE_NAME_KEY,
  LocalVoicePlayer,
  probeLocalVoice,
  type SpeakPhase,
} from "./localSpeech";

/** Tên hiển thị của các giọng mẫu đã chọn ở local-tts; giọng lạ thì hiện nguyên mã. */
export const VOICE_LABELS: Record<string, string> = {
  "playful-1": "Sáng & tinh nghịch",
  "gentle-2": "Dịu & vui vẻ",
};

export type LocalVoiceStatus = "off" | "checking" | "ready" | "missing";

interface Speaking {
  key: string;
  phase: SpeakPhase;
}

export interface LocalVoice {
  notice?: string;
  enabled: boolean;
  setEnabled: (value: boolean) => void;
  status: LocalVoiceStatus;
  voices: string[];
  voice: string;
  setVoice: (value: string) => void;
  recheck: () => void;
  speaking: Speaking | null;
  /**
   * Đọc một đoạn. Lỗi thì Promise bị từ chối kèm câu báo tiếng Việt; bị dừng hay bị lượt đọc khác thay
   * chỗ thì kết thúc êm, không báo lỗi.
   */
  speak: (key: string, text: string) => Promise<void>;
  stop: () => void;
}

function readEnabled(): boolean {
  try {
    return localStorage.getItem(LOCAL_VOICE_ENABLED_KEY) === "1";
  } catch {
    return false;
  }
}

function readVoiceName(): string {
  try {
    return localStorage.getItem(LOCAL_VOICE_NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

/**
 * Trạng thái giọng nói trên máy, dùng chung cho Companion và mục Giọng nói trong Cài đặt: đã bật chưa,
 * máy chủ có đang chạy không, và đoạn nào đang được đọc.
 *
 * Chỉ dò dịch vụ qua VPS khi người dùng đã bật và `active` đúng (Companion hoặc Cài đặt).
 */
export function useLocalVoice(active: boolean): LocalVoice {
  const [notice, setNotice] = useState('');
  useEffect(() => {
    const changed = (event: Event) => setNotice(`Đã chuyển sang giọng dự phòng: ${(event as CustomEvent<string>).detail}.`);
    window.addEventListener('peto-voice-fallback', changed);
    return () => window.removeEventListener('peto-voice-fallback', changed);
  }, []);
  const [enabled, setEnabled] = useState(readEnabled);
  const [voiceName, setVoice] = useState(readVoiceName);
  const [voices, setVoices] = useState<string[]>([]);
  const [status, setStatus] = useState<LocalVoiceStatus>(enabled ? "checking" : "off");
  const [probe, setProbe] = useState(0);
  const [speaking, setSpeaking] = useState<Speaking | null>(null);
  const player = useRef<LocalVoicePlayer | null>(null);
  const speakVersion = useRef(0);

  // Never silently replace a saved voice when its worker goes offline.
  const voice = voiceName || voices[0] || "";

  const stop = useCallback(() => {
    speakVersion.current += 1;
    player.current?.stop();
    setSpeaking(null);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(LOCAL_VOICE_ENABLED_KEY, enabled ? "1" : "0");
    } catch {}
  }, [enabled]);

  useEffect(() => {
    if (!voiceName) return;
    try {
      localStorage.setItem(LOCAL_VOICE_NAME_KEY, voiceName);
    } catch {}
  }, [voiceName]);

  useEffect(() => {
    if (!enabled) {
      setStatus("off");
      setVoices([]);
      stop();
      return;
    }
    if (!active) return;
    const controller = new AbortController();
    setStatus("checking");
    void probeLocalVoice(controller.signal).then((found) => {
      if (controller.signal.aborted) return;
      setVoices(found ?? []);
      setStatus(found ? "ready" : "missing");
    });
    return () => controller.abort();
  }, [enabled, active, probe, stop]);

  // Người dùng hay bật máy chủ rồi mới quay lại trang: dò lại khi cửa sổ được chọn lại.
  useEffect(() => {
    if (status !== "missing" || !active) return;
    const again = () => setProbe((count) => count + 1);
    window.addEventListener("focus", again);
    return () => window.removeEventListener("focus", again);
  }, [status, active]);

  useEffect(() => () => {
    speakVersion.current += 1;
    player.current?.stop();
  }, []);

  const speak = useCallback(async (key: string, text: string) => {
    setNotice('');
    if (!player.current) player.current = new LocalVoicePlayer();
    const version = ++speakVersion.current;
    setSpeaking({ key, phase: "loading" });
    try {
      await player.current.speak(text, voice, (phase) => {
        if (version === speakVersion.current) setSpeaking({ key, phase });
      });
    } catch (error) {
      if (version === speakVersion.current) {
        throw error instanceof Error ? error : new Error("Chưa đọc được đoạn này.");
      }
    } finally {
      if (version === speakVersion.current) setSpeaking(null);
    }
  }, [voice]);

  const recheck = useCallback(() => setProbe((count) => count + 1), []);

  return { enabled, setEnabled, status, voices, voice, setVoice, recheck, speaking, speak, stop, notice };
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
    : phase === "playing" ? "Dừng đọc" : "Nghe Peto đọc tin này";
  return (
    <button
      type="button"
      className={phase ? `message-speak ${phase}` : "message-speak"}
      aria-label={label}
      title={label}
      onClick={phase ? onStop : onSpeak}
    >
      {phase === "playing" ? <StopIcon /> : <SpeakerIcon size={15} />}
    </button>
  );
}
