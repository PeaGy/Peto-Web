import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useCompanionActivity } from '../src/features/companion/characters/useCompanionActivity';
import type { SpeakPhase } from '../src/features/companion/speech/localSpeech';

afterEach(() => vi.useRealTimers());

it('chú ý khi gõ rồi trở về nghỉ dù người dùng chưa gửi chữ nháp', () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => useCompanionActivity(true, false, null, false));
  act(() => result.current.noteTyping(true));
  expect(result.current.activity).toBe('listening');
  expect(result.current.typing).toBe(true);
  act(() => vi.advanceTimersByTime(1000));
  act(() => result.current.noteTyping(true));
  act(() => vi.advanceTimersByTime(300));
  expect(result.current.activity).toBe('listening');
  act(() => vi.advanceTimersByTime(900));
  expect(result.current.activity).toBe('idle');
  expect(result.current.typing).toBe(false);
});

it('chờ tiếng thì nghĩ, phát thật thì nói; nối tiếng ngắn không giật về nghỉ', () => {
  vi.useFakeTimers();
  const { result, rerender } = renderHook(({ speech }: { speech: SpeakPhase | null }) =>
    useCompanionActivity(true, false, speech, false), { initialProps: { speech: 'loading' as SpeakPhase | null } });
  expect(result.current.activity).toBe('thinking');
  rerender({ speech: 'playing' });
  expect(result.current.activity).toBe('speaking');
  rerender({ speech: 'buffering' });
  act(() => vi.advanceTimersByTime(300));
  expect(result.current.activity).toBe('speaking');
  act(() => vi.advanceTimersByTime(50));
  expect(result.current.activity).toBe('thinking');
  rerender({ speech: 'playing' });
  expect(result.current.activity).toBe('speaking');
  rerender({ speech: null });
  expect(result.current.activity).toBe('idle');
  act(() => vi.advanceTimersByTime(2000));
  expect(result.current.activity).toBe('idle');
});

it('gõ lượt tiếp theo vẫn thu hút hướng nhìn khi Peto đang nói hoặc viết, không đổi tư thế nói', () => {
  vi.useFakeTimers();
  const { result, rerender } = renderHook(({ speech, streaming }: { speech: SpeakPhase | null; streaming: boolean }) =>
    useCompanionActivity(true, streaming, speech, false),
  { initialProps: { speech: 'playing' as SpeakPhase | null, streaming: true } });
  act(() => result.current.noteTyping(true));
  expect(result.current.typing).toBe(true);
  expect(result.current.activity).toBe('speaking');
  rerender({ speech: 'buffering', streaming: true });
  expect(result.current.typing).toBe(true);
  act(() => vi.advanceTimersByTime(1200));
  expect(result.current.typing).toBe(false);
  act(() => result.current.noteTyping(true));
  rerender({ speech: null, streaming: true });
  expect(result.current.activity).toBe('thinking');
  expect(result.current.typing).toBe(true);
});

it('chú ý khi nghe/chép lời, ưu tiên trả lời và không giữ trạng thái khi rời tab', () => {
  const { result, rerender } = renderHook(({ active, streaming, hearing }) =>
    useCompanionActivity(active, streaming, null, hearing),
  { initialProps: { active: true, streaming: false, hearing: true } });
  expect(result.current.activity).toBe('listening');
  rerender({ active: true, streaming: true, hearing: true });
  expect(result.current.activity).toBe('thinking');
  rerender({ active: false, streaming: true, hearing: true });
  expect(result.current.activity).toBe('idle');
  rerender({ active: true, streaming: false, hearing: false });
  expect(result.current.activity).toBe('idle');
});
