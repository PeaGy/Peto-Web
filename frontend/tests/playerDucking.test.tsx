import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { PlayerVolume } from '../src/features/companion/ytplayer/playerVolume';
import { usePlayerDucking } from '../src/features/companion/ytplayer/usePlayerDucking';
import type { YouTubePlayer } from '../src/features/companion/ytplayer/youtubeApi';
import type { SpeakPhase } from '../src/features/companion/speech/localSpeech';
import type { HearingPhase } from '../src/features/companion/speech/hearingEngine';

function native() {
  const state = { volume: 60, muted: false };
  return { state, api: { getVolume: () => state.volume, isMuted: () => state.muted,
    setVolume: vi.fn((value: number) => { state.volume = value; }),
    mute: () => { state.muted = true; }, unMute: () => { state.muted = false; },
  } as unknown as YouTubePlayer };
}
afterEach(() => { vi.useRealTimers(); delete (document as unknown as Record<string, unknown>).hidden; });

it('native mute/unmute during ducking restores the chosen level, including after duck release', () => {
  const volume = new PlayerVolume(60), player = native(); volume.attach(player.api); volume.duck(true);
  player.state.muted = true; expect(volume.read()).toBe(0); expect(volume.effective).toBe(0);
  volume.duck(false); expect(player.state.muted).toBe(true);
  player.state.muted = false;
  expect(volume.read()).toBe(60); expect(player.state.volume).toBe(60);
  volume.duck(true); volume.set(0); volume.duck(false);
  expect(volume.read()).toBe(0); expect(player.state.muted).toBe(true);
});

it('a native edit just before release becomes the new setting; repeated duck signals never multiply the level twice', () => {
  const volume = new PlayerVolume(60), player = native(); volume.attach(player.api);
  volume.duck(true); volume.duck(true); expect(player.state.volume).toBe(12);
  player.state.volume = 40; volume.duck(false);
  expect(volume.read()).toBe(40); expect(player.state.volume).toBe(40);
  volume.duck(true); volume.set(1); expect(player.state.volume).toBe(1);
  volume.duck(false); expect(volume.read()).toBe(1);
});

it('choosing the same base level in native controls still reapplies the current attenuation', () => {
  vi.useFakeTimers();
  const volume = new PlayerVolume(60), player = native(); volume.attach(player.api); volume.duck(true);
  expect(volume.read()).toBe(60); // acknowledge the duck write
  player.state.volume = 60;
  expect(volume.read()).toBe(60); expect(player.state.volume).toBe(12);
});

it('incomplete YouTube info during cueing is unknown, never a user-selected zero/mute', () => {
  vi.useFakeTimers();
  const volume = new PlayerVolume(50), player = native(); volume.attach(player.api);
  const getVolume = vi.spyOn(player.api, 'getVolume'), isMuted = vi.spyOn(player.api, 'isMuted');
  getVolume.mockReturnValue(undefined as unknown as number); isMuted.mockReturnValue(undefined as unknown as boolean);
  vi.advanceTimersByTime(3000); expect(volume.read()).toBe(50);
  getVolume.mockReturnValue(0); expect(volume.read()).toBe(50);
  getVolume.mockReturnValue(50); isMuted.mockReturnValue(false);
  expect(volume.read()).toBe(50); expect(player.state.muted).toBe(false);
});

it('asynchronous old volume/mute acknowledgements cannot overwrite a newer chosen setting', () => {
  vi.useFakeTimers();
  const volume = new PlayerVolume(60), player = native(); volume.attach(player.api);
  vi.mocked(player.api.setVolume).mockImplementation(() => {});
  volume.duck(true); expect(volume.read()).toBe(60); // still reports the old native 60
  volume.set(40); player.state.volume = 12;
  expect(volume.read()).toBe(40); expect(volume.effective).toBe(8);
  player.state.volume = 8; expect(volume.read()).toBe(40);
  volume.set(0); player.state.muted = false; expect(volume.read()).toBe(0);
  player.state.muted = true; expect(volume.read()).toBe(0);
});

it('detaching cancels all native writes, retains the chosen level, and does not create playback work', () => {
  const volume = new PlayerVolume(73), player = native(); volume.attach(player.api); volume.duck(true);
  volume.detach(); const calls = vi.mocked(player.api.setVolume).mock.calls.length;
  volume.duck(false); volume.set(25);
  expect(player.api.setVolume).toHaveBeenCalledTimes(calls); expect(volume.read()).toBe(25);
  const next = native(); volume.duck(true); volume.attach(next.api);
  expect(next.state.volume).toBe(5);
});

const waiting = { listening: true, testing: false, holding: false, phase: 'waiting' as HearingPhase };
it('waiting, transcription, typing-independent renders and initial TTS loading do not duck', () => {
  const { result, rerender } = renderHook(({ phase, speech }) => usePlayerDucking(true, speech, { ...waiting, phase }), {
    initialProps: { phase: 'waiting' as HearingPhase, speech: 'loading' as SpeakPhase | null },
  });
  expect(result.current).toBe(false);
  rerender({ phase: 'transcribing', speech: null }); expect(result.current).toBe(false);
  rerender({ phase: 'paused', speech: 'buffering' }); expect(result.current).toBe(false);
});

it('release bridges chunk gaps, but a long buffer, cancellation and hearing stop recover volume', () => {
  vi.useFakeTimers();
  const { result, rerender } = renderHook(({ speech, hearing }) => usePlayerDucking(true, speech, hearing), {
    initialProps: { speech: 'playing' as SpeakPhase | null, hearing: waiting },
  });
  expect(result.current).toBe(true);
  rerender({ speech: 'buffering', hearing: waiting }); act(() => vi.advanceTimersByTime(200)); expect(result.current).toBe(true);
  rerender({ speech: 'playing', hearing: waiting }); act(() => vi.advanceTimersByTime(500)); expect(result.current).toBe(true);
  rerender({ speech: 'buffering', hearing: waiting }); act(() => vi.advanceTimersByTime(350)); expect(result.current).toBe(false);
  rerender({ speech: null, hearing: { ...waiting, holding: true } }); expect(result.current).toBe(true);
  rerender({ speech: null, hearing: waiting }); act(() => vi.advanceTimersByTime(350)); expect(result.current).toBe(false);
  rerender({ speech: null, hearing: { ...waiting, phase: 'speaking' } }); expect(result.current).toBe(true);
  rerender({ speech: null, hearing: { ...waiting, listening: false } }); act(() => vi.advanceTimersByTime(350)); expect(result.current).toBe(false);
});

it('test microphone and inactive/hidden Companion do not keep desktop music attenuated; cleanup cancels release', () => {
  vi.useFakeTimers(); Object.defineProperty(document, 'hidden', { configurable: true, value: false, writable: true });
  const { result, rerender, unmount } = renderHook(({ active, testing }) => usePlayerDucking(active, null, { ...waiting, testing, phase: 'speaking' }), {
    initialProps: { active: true, testing: true },
  });
  expect(result.current).toBe(false); rerender({ active: true, testing: false }); expect(result.current).toBe(true);
  act(() => { Object.defineProperty(document, 'hidden', { value: true }); document.dispatchEvent(new Event('visibilitychange')); });
  expect(result.current).toBe(false);
  act(() => { Object.defineProperty(document, 'hidden', { value: false }); document.dispatchEvent(new Event('visibilitychange')); });
  expect(result.current).toBe(true); rerender({ active: false, testing: false }); expect(result.current).toBe(false);
  unmount(); expect(vi.getTimerCount()).toBe(0);
});
