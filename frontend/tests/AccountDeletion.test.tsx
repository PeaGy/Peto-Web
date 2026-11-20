import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import AccountSettings, { matchesConfirmWord } from '../src/features/settings/AccountDeletion';
import * as api from '../src/shared/api/api';
import type { AccountUser } from '../src/shared/api/api';

vi.mock('../src/shared/api/api', async original => ({
  ...await original<typeof import('../src/shared/api/api')>(),
  deleteAccount: vi.fn(),
}));

const user = { id: 'a1', provider: 'github', username: 'thu', display_name: 'Thử' } as AccountUser;
const unauthorized = vi.fn();
const deleted = vi.fn();
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.deleteAccount).mockResolvedValue(); });

function open(account: AccountUser = user) {
  render(<AccountSettings user={account} disabled={false} onUnauthorized={unauthorized} onDeleted={deleted}>
    <div>Đăng xuất</div>
  </AccountSettings>);
  fireEvent.click(screen.getByRole('button', { name: 'Xóa tài khoản' }));
  return screen.getByRole('textbox', { name: 'Xác nhận để tiếp tục' });
}

it('accepts XÓA in any case and Unicode form, nothing else', () => {
  for (const ok of ['XÓA', 'xóa', ' Xóa ', 'XÓA']) expect(matchesConfirmWord(ok), ok).toBe(true);
  for (const no of ['', 'XOA', 'xóa tài khoản', 'delete']) expect(matchesConfirmWord(no), no).toBe(false);
});

it('keeps the delete button off until XÓA is typed, then deletes and signs out', async () => {
  const input = open();
  expect(screen.getByRole('heading', { name: 'Bạn có chắc chắn muốn xóa tài khoản?' })).toBeTruthy();
  const button = screen.getByRole('button', { name: 'Xóa tài khoản' });
  expect(button).toHaveProperty('disabled', true);
  expect(document.querySelector('.account-delete-art')?.getAttribute('data-mood')).toBe('sad');
  fireEvent.change(input, { target: { value: 'xóa' } });
  expect(button).toHaveProperty('disabled', false);
  expect(document.querySelector('.account-delete-art')?.getAttribute('data-mood')).toBe('down');
  fireEvent.click(button);
  await waitFor(() => expect(api.deleteAccount).toHaveBeenCalledExactlyOnceWith('xóa'));
  await waitFor(() => expect(deleted).toHaveBeenCalledOnce());
});

it('shows the server message and stays open when deletion fails', async () => {
  vi.mocked(api.deleteAccount).mockRejectedValue(new Error('Peto đang trả lời. Dừng lượt đó rồi xóa tài khoản.'));
  const input = open();
  fireEvent.change(input, { target: { value: 'XÓA' } });
  fireEvent.submit(input.closest('form')!);
  expect((await screen.findByRole('alert')).textContent).toContain('Peto đang trả lời');
  expect(deleted).not.toHaveBeenCalled();
  expect(input).toHaveProperty('disabled', false);
});

it('goes back to Unauthorized handling when the session is gone', async () => {
  vi.mocked(api.deleteAccount).mockRejectedValue(new api.UnauthorizedError());
  const input = open();
  fireEvent.change(input, { target: { value: 'XÓA' } });
  fireEvent.submit(input.closest('form')!);
  await waitFor(() => expect(unauthorized).toHaveBeenCalledOnce());
});

it('Hủy returns to the account rows and cheers Peto up on hover', () => {
  open();
  const cancel = screen.getByRole('button', { name: 'Hủy' });
  fireEvent.pointerEnter(cancel);
  expect(document.querySelector('.account-delete-art')?.getAttribute('data-mood')).toBe('happy');
  fireEvent.click(cancel);
  expect(screen.getByText('Đăng xuất')).toBeTruthy();
  expect(document.querySelector('.account-delete')).toBeNull();
});

it('admin accounts get no delete button', () => {
  render(<AccountSettings user={{ ...user, is_owner: true }} disabled={false} onUnauthorized={unauthorized} onDeleted={deleted}>
    <div>Đăng xuất</div>
  </AccountSettings>);
  expect(screen.getByText('Tài khoản quản trị không xóa được ở đây.')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Xóa tài khoản' })).toBeNull();
});

it('Discord accounts are told the bot memory stays', () => {
  open({ ...user, provider: 'discord' });
  expect(screen.getByText(/Trí nhớ của bot Discord không bị xóa ở đây/)).toBeTruthy();
});
