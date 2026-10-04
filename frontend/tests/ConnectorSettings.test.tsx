import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import ConnectorSettings from '../src/features/connectors/ConnectorSettings';
import * as api from '../src/features/connectors/connectorApi';
import { UnauthorizedError } from '../src/shared/api/api';

vi.mock('../src/features/connectors/connectorApi', async original => ({
  ...await original<typeof import('../src/features/connectors/connectorApi')>(),
  listConnectors: vi.fn(), connectGitHub: vi.fn(), checkGitHub: vi.fn(), disconnectGitHub: vi.fn(),
}));

const github: api.Connector = { id: 'github', name: 'GitHub', configured: true, status: 'connected', login: 'demo',
  updated_at: 1, install_url: 'https://github.com/apps/peto-test/installations/new' };
const unauthorized = vi.fn();
const mount = (result: string | null = null) => render(<ConnectorSettings open result={result} onUnauthorized={unauthorized} />);

beforeEach(() => {
  vi.mocked(api.listConnectors).mockResolvedValue({ connectors: [github] });
  vi.mocked(api.checkGitHub).mockResolvedValue(github);
  vi.mocked(api.disconnectGitHub).mockResolvedValue({ disconnected: true });
});

it('hiện tài khoản, tìm kiếm và kiểm tra kết nối', async () => {
  mount();
  expect(await screen.findByText('@demo')).toBeTruthy();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'không có' } });
  expect(screen.getByText('Không có kết nối phù hợp.')).toBeTruthy();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'demo' } });
  fireEvent.click(screen.getByRole('button', { name: 'Quản lý', exact: true }));
  expect(screen.getByRole('link', { name: /Quản lý repo/ }).getAttribute('href')).toBe(github.install_url);
  fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra kết nối' }));
  await screen.findByText('Kết nối GitHub đang hoạt động.');
  expect(api.checkGitHub).toHaveBeenCalledTimes(1);
});

it('khám phá chỉ hiện GitHub thực sự có hỗ trợ; chưa cấu hình thì không kết nối được', async () => {
  vi.mocked(api.listConnectors).mockResolvedValue({ connectors: [{ ...github, status: 'not_connected', configured: false, login: null }] });
  mount();
  await screen.findByText('Bạn chưa kết nối ứng dụng nào.');
  fireEvent.click(screen.getByRole('button', { name: 'Khám phá kết nối' }));
  expect(screen.getByRole('button', { name: 'Kết nối', exact: true }).hasAttribute('disabled')).toBe(true);
  expect(screen.getByText(/chưa được quản trị viên bật/)).toBeTruthy();
  expect(screen.queryByText('Google Drive')).toBeNull();
});

it('ngắt kết nối cần xác nhận và giữ nguyên khi hủy', async () => {
  mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Quản lý', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Ngắt kết nối', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Giữ kết nối' }));
  expect(api.disconnectGitHub).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Ngắt kết nối', exact: true }));
  vi.mocked(api.listConnectors).mockResolvedValue({ connectors: [{ ...github, status: 'not_connected', login: null }] });
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận ngắt kết nối' }));
  await screen.findByText('Bạn chưa kết nối ứng dụng nào.');
  expect(api.disconnectGitHub).toHaveBeenCalledTimes(1);
});

it('phiên hết hạn gọi luồng đăng nhập; lỗi tải có thể thử lại', async () => {
  vi.mocked(api.listConnectors).mockRejectedValueOnce(new Error('Lỗi'));
  mount();
  await screen.findByRole('alert');
  vi.mocked(api.listConnectors).mockRejectedValueOnce(new UnauthorizedError());
  fireEvent.click(screen.getByRole('button', { name: 'Tải lại danh sách' }));
  await waitFor(() => expect(unauthorized).toHaveBeenCalled());
});

it('callback chỉ nhận kết quả hiển thị và xóa tham số khỏi URL', () => {
  window.history.replaceState(null, '', '/?connector_result=connected&other=1#companion');
  expect(api.takeConnectorResult()).toBe('connected');
  expect(window.location.search).toBe('?other=1');
  expect(window.location.hash).toBe('#companion');
  window.history.replaceState(null, '', '/');
});

it('kết quả cấp quyền được hiển thị sau khi trở về', async () => {
  mount('connected');
  expect(screen.getByText(/Đã kết nối GitHub\. Bạn có thể/)).toBeTruthy();
  await screen.findByText('@demo');
});
