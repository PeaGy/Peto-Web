import { useEffect, useState } from 'react';
import type { SpeakPhase } from '../speech/localSpeech';
import type { HearingState } from '../speech/hearingEngine';

/** Silence/waiting/typing never ducks music; a short release bridges pauses between spoken chunks. */
export function usePlayerDucking(active: boolean, speech: SpeakPhase | null, hearing: Pick<HearingState, 'listening' | 'testing' | 'holding' | 'phase'>) {
  const [visible, setVisible] = useState(() => !document.hidden);
  const [held, setHeld] = useState(false);
  const enabled = active && visible;
  const speaking = speech === 'playing' || (hearing.listening && !hearing.testing && (hearing.holding || hearing.phase === 'speaking'));
  useEffect(() => {
    const visibility = () => setVisible(!document.hidden);
    const hide = () => setVisible(false);
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', hide);
    window.addEventListener('pageshow', visibility);
    return () => {
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', hide);
      window.removeEventListener('pageshow', visibility);
    };
  }, []);
  useEffect(() => {
    if (!enabled || speaking) { setHeld(enabled && speaking); return; }
    const timer = window.setTimeout(() => setHeld(false), 350);
    return () => window.clearTimeout(timer);
  }, [enabled, speaking]);
  return enabled && (speaking || held);
}
