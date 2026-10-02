import { useCallback, useEffect, useState } from 'react';
import type { SpeakPhase } from '../speech/localSpeech';
import type { CompanionActivity } from './companionMotion';

/** Tư thế đi theo hành động hiện tại, không đi theo chữ còn nằm trong ô nhắn. */
export function useCompanionActivity(active: boolean, streaming: boolean, speech: SpeakPhase | null, hearing: boolean) {
  const [typingAt, setTypingAt] = useState(0);
  const [waiting, setWaiting] = useState(false);
  const noteTyping = useCallback((hasText: boolean) => setTypingAt(hasText ? Date.now() : 0), []);
  useEffect(() => {
    if (!typingAt) return;
    const timer = window.setTimeout(() => setTypingAt(0), 3000);
    return () => window.clearTimeout(timer);
  }, [typingAt]);
  useEffect(() => {
    if (!active || streaming) setTypingAt(0);
  }, [active, streaming]);
  useEffect(() => {
    setWaiting(false);
    if (speech !== 'buffering') return;
    // Giữ tư thế nói qua khoảng nối tiếng ngắn; chờ lâu mới chuyển sang đang nghĩ.
    const timer = window.setTimeout(() => setWaiting(true), 350);
    return () => window.clearTimeout(timer);
  }, [speech]);
  const activity: CompanionActivity = !active ? 'idle'
    : speech === 'playing' || (speech === 'buffering' && !waiting) ? 'speaking'
      : streaming || speech ? 'thinking'
        : hearing || typingAt ? 'listening' : 'idle';
  return { activity, noteTyping, typing: active && Boolean(typingAt) };
}
