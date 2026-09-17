import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import AgentSettings, { lastUsedLabel } from '../src/AgentSettings';
import * as api from '../src/api';

vi.mock('../src/api', async (original) => ({
  ...await original<typeof import('../src/api')>(),
  listAgentDevices: vi.fn(), revokeAgentDevice: vi.fn(),
}));

const NOW = 1_800_000_000;
const devices: api.AgentDevices = {
  devices: [
    { id: 'd1', name: 'DESKTOP-BINH', created_at: NOW - 9000, last_used_at: NOW - 300 },
    { id: 'd2', name: 'LAPTOP-TRUONG', created_at: NOW - 900000, last_used_at: NOW - 3 * 86400 },
  ],
  steps_used: 16, steps_limit: 200,
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(Date, 'now').mockReturnValue(NOW * 1000);
});

it('liệt kê máy, số bước còn lại và ngắt kết nối từng máy', async () => {
  vi.mocked(api.listAgentDevices).mockResolvedValue(devices);
  vi.mocked(api.revokeAgentDevice).mockResolvedValue();
  render(<AgentSettings open isGuest={false} onUnauthorized={vi.fn()} />);
  expect(await screen.findByText('DESKTOP-BINH')).toBeTruthy();
  expect(screen.getByText(/Hôm nay còn 184\/200 bước/)).toBeTruthy();
  expect(screen.getByText('Dùng 5 phút trước')).toBeTruthy();
  expect(screen.getByText('Dùng 3 ngày trước')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Ngắt kết nối DESKTOP-BINH' }));
  await waitFor(() => expect(screen.queryByText('DESKTOP-BINH')).toBeNull());
  expect(api.revokeAgentDevice).toHaveBeenCalledWith('d1');
  expect(screen.getByText('LAPTOP-TRUONG')).toBeTruthy();
});

it('chưa có máy thì hướng dẫn chạy peto login; lỗi tải thì cho thử lại', async () => {
  vi.mocked(api.listAgentDevices).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ ...devices, devices: [] });
  render(<AgentSettings open isGuest={false} onUnauthorized={vi.fn()} />);
  expect((await screen.findByRole('alert')).textContent).toContain('Chưa tải được danh sách máy');
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
  expect((await screen.findByText(/Chưa có máy nào kết nối/)).textContent).toContain('chạy peto login.');
});

it('tài khoản khách chỉ thấy lời giải thích, không gọi API', () => {
  render(<AgentSettings open isGuest onUnauthorized={vi.fn()} />);
  expect(screen.getByText(/cần đăng nhập bằng Discord hoặc Google/)).toBeTruthy();
  expect(api.listAgentDevices).not.toHaveBeenCalled();
});

it('phiên hết hạn thì về màn đăng nhập', async () => {
  vi.mocked(api.listAgentDevices).mockRejectedValue(new api.UnauthorizedError());
  const onUnauthorized = vi.fn();
  render(<AgentSettings open isGuest={false} onUnauthorized={onUnauthorized} />);
  await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
});

it('nhãn thời gian dùng lần cuối', () => {
  expect(lastUsedLabel(NOW - 10, NOW)).toBe('Vừa dùng xong');
  expect(lastUsedLabel(NOW - 7200, NOW)).toBe('Dùng 2 giờ trước');
});
