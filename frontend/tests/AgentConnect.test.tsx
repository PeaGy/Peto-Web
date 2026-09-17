import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import AgentConnectDialog, { forgetAgentCode, takeAgentCode } from '../src/AgentConnectDialog';
import * as api from '../src/api';

vi.mock('../src/api', async (original) => ({
  ...await original<typeof import('../src/api')>(),
  getAgentDevice: vi.fn(), answerAgentDevice: vi.fn(),
}));

const pending: api.AgentDevicePending = { user_code: 'KXMT-4P2Q', name: 'DESKTOP-BINH', expires_in: 500 };

beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  window.history.replaceState(null, '', '/');
});

it('lấy mã từ liên kết, xóa khỏi thanh địa chỉ và giữ qua lúc đăng nhập chuyển hướng', () => {
  window.history.replaceState(null, '', '/?agent_code=kxmt-4p2q&x=1#imagine');
  expect(takeAgentCode()).toBe('KXMT-4P2Q');
  expect(window.location.search).toBe('?x=1');
  expect(window.location.hash).toBe('#imagine');
  // Trang tải lại sau khi đăng nhập Discord: URL không còn mã nhưng vẫn nhớ.
  window.history.replaceState(null, '', '/');
  expect(takeAgentCode()).toBe('KXMT-4P2Q');
  forgetAgentCode();
  expect(takeAgentCode()).toBeNull();
  window.history.replaceState(null, '', '/?agent_code=<script>');
  expect(takeAgentCode()).toBeNull();
});

it('cho phép kết nối rồi báo quay lại cửa sổ dòng lệnh', async () => {
  vi.mocked(api.getAgentDevice).mockResolvedValue(pending);
  vi.mocked(api.answerAgentDevice).mockResolvedValue();
  const onClose = vi.fn();
  render(<AgentConnectDialog code="KXMT-4P2Q" isGuest={false} onClose={onClose} onUnauthorized={vi.fn()} />);
  const dialog = screen.getByRole('dialog', { name: 'Kết nối Peto Agent?' });
  expect(await within(dialog).findByText('DESKTOP-BINH')).toBeTruthy();
  expect(within(dialog).getByLabelText('Mã kết nối').textContent).toBe('KXMT-4P2Q');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cho phép' }));
  expect(await within(dialog).findByText(/đã dùng được Peto Agent/)).toBeTruthy();
  expect(api.answerAgentDevice).toHaveBeenCalledWith('KXMT-4P2Q', true);
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xong' }));
  expect(onClose).toHaveBeenCalledTimes(1);
});

it('không cho phép thì báo đã từ chối', async () => {
  vi.mocked(api.getAgentDevice).mockResolvedValue(pending);
  vi.mocked(api.answerAgentDevice).mockResolvedValue();
  render(<AgentConnectDialog code="KXMT-4P2Q" isGuest={false} onClose={vi.fn()} onUnauthorized={vi.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Không cho phép' }));
  expect(await screen.findByRole('dialog', { name: 'Đã từ chối kết nối' })).toBeTruthy();
  expect(api.answerAgentDevice).toHaveBeenCalledWith('KXMT-4P2Q', false);
});

it('mã hết hạn thì hiện lời báo của máy chủ', async () => {
  vi.mocked(api.getAgentDevice).mockRejectedValue(new Error('Mã kết nối không đúng hoặc đã hết hạn.'));
  render(<AgentConnectDialog code="KXMT-4P2Q" isGuest={false} onClose={vi.fn()} onUnauthorized={vi.fn()} />);
  expect((await screen.findByRole('alert')).textContent).toContain('đã hết hạn');
  expect(screen.queryByRole('button', { name: 'Cho phép' })).toBeNull();
});

it('phiên khách không có nút Cho phép và không gọi API', async () => {
  const onClose = vi.fn();
  render(<AgentConnectDialog code="KXMT-4P2Q" isGuest onClose={onClose} onUnauthorized={vi.fn()} />);
  expect(screen.getByText(/chỉ dùng được với tài khoản Discord hoặc Google/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Cho phép' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Đóng' }));
  await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  expect(api.getAgentDevice).not.toHaveBeenCalled();
});
