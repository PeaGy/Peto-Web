import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import DiscordMemorySettings from '../src/features/settings/DiscordMemorySettings';
import * as api from '../src/shared/api/api';

vi.mock('../src/shared/api/api', async original => ({
  ...await original<typeof import('../src/shared/api/api')>(),
  getDiscordMemorySettings: vi.fn(), setDiscordMemorySettings: vi.fn(),
}));
const deferred = <T,>() => {
  let resolve!: (value: T) => void, reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const unauthorized = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getDiscordMemorySettings).mockResolvedValue({ enabled: true, available: true });
  vi.mocked(api.setDiscordMemorySettings).mockImplementation(async enabled => ({ enabled, available: true }));
});

it('loads only when Account opens and rechecks persisted state when reopened', async () => {
  const { rerender } = render(<DiscordMemorySettings open={false} onUnauthorized={unauthorized} />);
  expect(api.getDiscordMemorySettings).not.toHaveBeenCalled();
  rerender(<DiscordMemorySettings open onUnauthorized={unauthorized} />);
  const toggle = screen.getByRole('switch', { name: 'Trí nhớ từ bot Discord' });
  await waitFor(() => expect(toggle).toHaveProperty('checked', true));
  fireEvent.click(toggle);
  await waitFor(() => expect(api.setDiscordMemorySettings).toHaveBeenCalledExactlyOnceWith(false));
  await waitFor(() => expect(toggle).toHaveProperty('disabled', false));
  expect(toggle).toHaveProperty('checked', false);
  rerender(<DiscordMemorySettings open={false} onUnauthorized={unauthorized} />);
  vi.mocked(api.getDiscordMemorySettings).mockResolvedValue({ enabled: false, available: true });
  rerender(<DiscordMemorySettings open onUnauthorized={unauthorized} />);
  await waitFor(() => expect(api.getDiscordMemorySettings).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(toggle).toHaveProperty('disabled', false));
  expect(toggle).toHaveProperty('checked', false);
});

it('keeps the switch disabled until loaded and rolls back a failed save', async () => {
  const load = deferred<api.DiscordMemorySettings>(), save = deferred<api.DiscordMemorySettings>();
  vi.mocked(api.getDiscordMemorySettings).mockReturnValue(load.promise);
  vi.mocked(api.setDiscordMemorySettings).mockReturnValue(save.promise);
  render(<DiscordMemorySettings open onUnauthorized={unauthorized} />);
  const toggle = screen.getByRole('switch');
  expect(toggle).toHaveProperty('disabled', true);
  await act(async () => load.resolve({ enabled: true, available: true }));
  fireEvent.click(toggle);
  expect(toggle).toHaveProperty('checked', false);
  expect(toggle).toHaveProperty('disabled', true);
  fireEvent.click(toggle);
  expect(api.setDiscordMemorySettings).toHaveBeenCalledOnce();
  await act(async () => save.reject(new TypeError('offline')));
  expect(toggle).toHaveProperty('checked', true);
  expect(toggle).toHaveProperty('disabled', false);
  expect(screen.getByRole('alert').textContent).toContain('Chưa lưu được');
});

it('allows a preference change without an available bot connection', async () => {
  vi.mocked(api.getDiscordMemorySettings).mockResolvedValue({ enabled: true, available: false });
  vi.mocked(api.setDiscordMemorySettings).mockResolvedValue({ enabled: false, available: false });
  render(<DiscordMemorySettings open onUnauthorized={unauthorized} />);
  const toggle = screen.getByRole('switch');
  await waitFor(() => expect(toggle).toHaveProperty('disabled', false));
  expect(screen.getByText(/chưa được cấu hình/)).toBeTruthy();
  fireEvent.click(toggle);
  await waitFor(() => expect(toggle).toHaveProperty('disabled', false));
  expect(toggle).toHaveProperty('checked', false);
});

it('failed reads do not present an editable guessed state and can be retried', async () => {
  vi.mocked(api.getDiscordMemorySettings).mockRejectedValueOnce(new Error('network'));
  render(<DiscordMemorySettings open onUnauthorized={unauthorized} />);
  await screen.findByRole('alert');
  expect(screen.getByRole('switch')).toHaveProperty('disabled', true);
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
  await waitFor(() => expect(screen.getByRole('switch')).toHaveProperty('disabled', false));
  expect(screen.queryByRole('alert')).toBeNull();
});

it('reopening waits for an in-flight save before reading the preference again', async () => {
  const save = deferred<api.DiscordMemorySettings>();
  vi.mocked(api.setDiscordMemorySettings).mockReturnValue(save.promise);
  const { rerender } = render(<DiscordMemorySettings open onUnauthorized={unauthorized} />);
  await waitFor(() => expect(screen.getByRole('switch')).toHaveProperty('disabled', false));
  fireEvent.click(screen.getByRole('switch'));
  rerender(<DiscordMemorySettings open={false} onUnauthorized={unauthorized} />);
  rerender(<DiscordMemorySettings open onUnauthorized={unauthorized} />);
  expect(api.getDiscordMemorySettings).toHaveBeenCalledOnce();
  vi.mocked(api.getDiscordMemorySettings).mockResolvedValue({ enabled: false, available: true });
  await act(async () => save.resolve({ enabled: false, available: true }));
  await waitFor(() => expect(api.getDiscordMemorySettings).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.getByRole('switch')).toHaveProperty('disabled', false));
  expect(screen.getByRole('switch')).toHaveProperty('checked', false);
});

it('ignores stale reads after closing and handles an expired session', async () => {
  const load = deferred<api.DiscordMemorySettings>();
  vi.mocked(api.getDiscordMemorySettings).mockReturnValueOnce(load.promise);
  const { rerender } = render(<DiscordMemorySettings open onUnauthorized={unauthorized} />);
  await waitFor(() => expect(api.getDiscordMemorySettings).toHaveBeenCalledOnce());
  const signal = vi.mocked(api.getDiscordMemorySettings).mock.calls[0][0]!;
  rerender(<DiscordMemorySettings open={false} onUnauthorized={unauthorized} />);
  expect(signal.aborted).toBe(true);
  await act(async () => load.resolve({ enabled: false, available: false }));
  expect(screen.queryByText(/chưa được cấu hình/)).toBeNull();
  vi.mocked(api.getDiscordMemorySettings).mockRejectedValueOnce(new api.UnauthorizedError());
  rerender(<DiscordMemorySettings open onUnauthorized={unauthorized} />);
  await waitFor(() => expect(unauthorized).toHaveBeenCalledOnce());
});
