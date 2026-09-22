import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import MusicVibePicker, { BeatIndicator } from '../src/MusicVibePicker';
import { getMusicState } from '../src/musicVibe';

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

it('opens a separate panel, adjusts sensitivity separately from strength and restores defaults', () => {
  render(<MusicVibePicker />);
  fireEvent.click(screen.getByRole('button', { name: 'Mở Beat Sync' }));
  expect(screen.getByRole('dialog', { name: 'Beat Sync' })).toBeTruthy();
  expect(screen.getByLabelText('Mức âm thanh đầu vào')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Độ nhạy bắt nhịp'), { target: { value: '0.95' } });
  expect(getMusicState().parameters.sensitivity).toBe(0.95);
  expect(getMusicState().strength).toBe(0.5);
  fireEvent.click(screen.getByRole('button', { name: 'Khôi phục mặc định' }));
  expect(getMusicState().parameters.sensitivity).toBe(0.7);
  fireEvent.click(screen.getByRole('button', { name: 'Đóng Beat Sync' }));
  expect(screen.queryByRole('dialog')).toBeNull();
});
