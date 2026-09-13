import { useCallback, useEffect, useRef, useState } from "react";
import {
  LOCAL_VOICE_ENABLED_KEY,
  LOCAL_VOICE_NAME_KEY,
  LocalVoicePlayer,
  probeLocalVoice,
  type SpeakPhase,
} from "./localSpeech";

/** Tên hiển thị của các giọng mẫu đã chọn ở local-tts; giọng lạ thì hiện nguyên mã. */
const VOICE_LABELS: Record<string, string> = {
  "playful-1": "Sáng & tinh nghịch",
  "gentle-2": "Dịu & vui vẻ",
};

export type LocalVoiceStatus = "off" | "checking" | "ready" | "missing";

const STATUS_TEXT: Record<LocalVoiceStatus, string> = {
  off: "",
  checking: "Đang tìm máy chủ giọng nói trên máy này…",
  ready: "Giọng nói đã sẵn sàng: Peto sẽ nói khi trả lời xong.",
  missing: "Chưa thấy máy chủ giọng nói trên máy này. Bật máy chủ rồi bấm Kiểm tra lại, hoặc tắt giọng nói "
    + "để chỉ chat bằng chữ.",
};

interface Speaking {
  key: string;
  phase: SpeakPhase;
}

export interface LocalVoice {
  enabled: boolean;
  setEnabled: (value: boolean) => void;
  status: LocalVoiceStatus;
  voices: string[];
  voice: string;
  setVoice: (value: string) => void;
  recheck: () => void;
  speaking: Speaking | null;
  speak: (key: string, text: string) => void;
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
 * Trạng thái giọng nói trên máy: đã bật chưa, máy chủ có đang chạy không, và tin nào đang được
 * đọc. Chỉ dò 127.0.0.1 khi người dùng đã bật.
 */
export function useLocalVoice(onError: (message: string) => void): LocalVoice {
  const [enabled, setEnabled] = useState(readEnabled);
  const [voiceName, setVoice] = useState(readVoiceName);
  const [voices, setVoices] = useState<string[]>([]);
  const [status, setStatus] = useState<LocalVoiceStatus>(enabled ? "checking" : "off");
  const [probe, setProbe] = useState(0);
  const [speaking, setSpeaking] = useState<Speaking | null>(null);
  const player = useRef<LocalVoicePlayer | null>(null);
  const speakVersion = useRef(0);
  const reportError = useRef(onError);

  useEffect(() => {
    reportError.current = onError;
  }, [onError]);

  const voice = voices.includes(voiceName) ? voiceName : (voices[0] ?? "");

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
    const controller = new AbortController();
    setStatus("checking");
    void probeLocalVoice(controller.signal).then((found) => {
      if (controller.signal.aborted) return;
      setVoices(found ?? []);
      setStatus(found ? "ready" : "missing");
    });
    return () => controller.abort();
  }, [enabled, probe, stop]);

  // Người dùng hay bật máy chủ rồi mới quay lại trang: dò lại khi tab được chọn lại.
  useEffect(() => {
    if (status !== "missing") return;
    const again = () => setProbe((count) => count + 1);
    window.addEventListener("focus", again);
    return () => window.removeEventListener("focus", again);
  }, [status]);

  useEffect(() => () => {
    speakVersion.current += 1;
    player.current?.stop();
  }, []);

  const speak = useCallback((key: string, text: string) => {
    if (!player.current) player.current = new LocalVoicePlayer();
    const version = ++speakVersion.current;
    setSpeaking({ key, phase: "loading" });
    player.current.speak(text, voice, (phase) => {
      if (version === speakVersion.current) setSpeaking({ key, phase });
    }).then(
      () => {
        if (version === speakVersion.current) setSpeaking(null);
      },
      (error: unknown) => {
        if (version !== speakVersion.current) return;
        setSpeaking(null);
        reportError.current(error instanceof Error ? error.message : "Chưa đọc được tin này.");
      },
    );
  }, [voice]);

  const recheck = useCallback(() => setProbe((count) => count + 1), []);

  return { enabled, setEnabled, status, voices, voice, setVoice, recheck, speaking, speak, stop };
}

function SpeakerIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 9h4l5-4v14l-5-4H4z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M17 9a4 4 0 0 1 0 6M19.5 6.5a8 8 0 0 1 0 11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

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
      className={phase ? "message-speak active" : "message-speak"}
      aria-label={label}
      onClick={phase ? onStop : onSpeak}
    >
      <SpeakerIcon />
      {phase === "loading" ? "Đang chuẩn bị…" : phase === "playing" ? "Dừng" : "Nghe"}
    </button>
  );
}

/** Nút bật giọng nói, trạng thái máy chủ, chọn giọng và tắt tiếng, đặt dưới ảnh Peto trong Companion. */
export function VoiceControls({ voice, muted, onToggleMute }: {
  voice: LocalVoice;
  muted: boolean;
  onToggleMute: () => void;
}) {
  if (!voice.enabled) {
    return (
      <div className="companion-voice">
        <button type="button" className="companion-button" onClick={() => voice.setEnabled(true)}>
          Bật giọng nói trên máy này
        </button>
        <p>
          Giọng nói chỉ dùng được trên máy đã cài máy chủ giọng nói của Peto; không có thì vẫn chat bằng chữ
          bình thường. Nếu Chrome hỏi quyền truy cập thiết bị trong mạng cục bộ, chọn Cho phép.
        </p>
      </div>
    );
  }
  return (
    <div className="companion-voice">
      <p role="status">{STATUS_TEXT[voice.status]}</p>
      <div className="companion-voice-actions">
        {voice.status === "missing" && (
          <button type="button" className="companion-button" onClick={voice.recheck}>Kiểm tra lại</button>
        )}
        {voice.status === "ready" && voice.voices.length > 1 && (
          <select aria-label="Giọng" value={voice.voice} onChange={(event) => voice.setVoice(event.target.value)}>
            {voice.voices.map((name) => (
              <option key={name} value={name}>{VOICE_LABELS[name] ?? name}</option>
            ))}
          </select>
        )}
        {voice.status === "ready" && (
          <button type="button" className="companion-button" aria-pressed={muted} onClick={onToggleMute}>
            Tắt tiếng
          </button>
        )}
        <button type="button" className="companion-button" onClick={() => voice.setEnabled(false)}>
          Tắt giọng nói
        </button>
      </div>
    </div>
  );
}
