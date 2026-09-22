import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import MusicVibePicker from '../src/MusicVibePicker';
import { getMusicState } from '../src/musicVibe';

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
