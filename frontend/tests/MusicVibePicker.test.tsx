import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { BeatIndicator, BeatSyncBody } from '../src/features/companion/characters/MusicVibePicker';
import { getMusicState } from '../src/features/companion/characters/musicVibe';

it('lights each beat without depending on CSS animations and clears its timer', () => {
  vi.useFakeTimers();
  try {
    const view = render(<BeatIndicator beats={0} lastBeat={-Infinity} />);
    expect(view.container.querySelector('span')?.dataset.lit).toBe('false');
    view.rerender(<BeatIndicator beats={1} lastBeat={performance.now()} />);
    expect(view.container.querySelector('span')?.dataset.lit).toBe('true');
    act(() => vi.advanceTimersByTime(180));
    expect(view.container.querySelector('span')?.dataset.lit).toBe('false');
    view.rerender(<BeatIndicator beats={2} lastBeat={performance.now()} />);
    expect(view.container.querySelector('span')?.dataset.lit).toBe('true');
    view.unmount(); expect(vi.getTimerCount()).toBe(0);
  } finally { vi.useRealTimers(); }
});

it('adjusts sensitivity separately from strength and restores defaults', () => {
  render(<BeatSyncBody />);
  expect(screen.getByLabelText('Mức âm thanh đầu vào')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Độ nhạy bắt nhịp'), { target: { value: '0.95' } });
  expect(getMusicState().parameters.sensitivity).toBe(0.95);
  expect(getMusicState().strength).toBe(0.5);
  fireEvent.click(screen.getByRole('button', { name: 'Khôi phục mặc định' }));
  expect(getMusicState().parameters.sensitivity).toBe(0.7);
});
