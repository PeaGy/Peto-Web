import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import MemorySettings from '../src/MemorySettings';
import * as api from '../src/api';

vi.mock('../src/api', async (original) => ({
  ...await original<typeof import('../src/api')>(),
  getCompanionMemory: vi.fn(), setCompanionMemoryEnabled: vi.fn(), deleteCompanionMemory: vi.fn(),
  clearCompanionMemory: vi.fn(),
}));

const memories: api.CompanionMemory[] = [
  { id: 3, text: 'Đang học năm hai ngành điện', created_at: 100, updated_at: 100 },
  { id: 5, text: 'Nuôi một con mèo tên Mướp', created_at: 200, updated_at: 260 },
];
const state = (extra: Partial<api.CompanionMemoryState> = {}): api.CompanionMemoryState => ({
  available: true, enabled: true, pending: false, limit: 50, memories, ...extra,
});
const list = () => screen.getByRole('list', { name: 'Những điều Peto nhớ về bạn' });

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getCompanionMemory).mockResolvedValue(state());
  vi.mocked(api.setCompanionMemoryEnabled).mockResolvedValue();
  vi.mocked(api.deleteCompanionMemory).mockResolvedValue();
  vi.mocked(api.clearCompanionMemory).mockResolvedValue();
});

it('liệt kê ghi nhớ kèm số lượng, xóa một dòng thì gọi API và dòng đó biến mất', async () => {
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  expect(await screen.findByText('Đang học năm hai ngành điện')).toBeTruthy();
  expect(within(list()).getAllByRole('listitem')).toHaveLength(2);
  expect(screen.getByText('2/50 ghi nhớ')).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'Xóa ghi nhớ: Nuôi một con mèo tên Mướp' }));
  await waitFor(() => expect(screen.queryByText('Nuôi một con mèo tên Mướp')).toBeNull());
  expect(api.deleteCompanionMemory).toHaveBeenCalledWith(5);
  expect(screen.getByText('1/50 ghi nhớ')).toBeTruthy();
});

it('xóa không được thì dòng đó quay lại và báo lỗi của máy chủ', async () => {
  vi.mocked(api.deleteCompanionMemory).mockRejectedValue(new Error('Không tìm thấy ghi nhớ này. Có thể nó đã được xóa.'));
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa ghi nhớ: Đang học năm hai ngành điện' }));
  expect((await screen.findByRole('alert')).textContent).toBe('Không tìm thấy ghi nhớ này. Có thể nó đã được xóa.');
  expect(within(list()).getAllByRole('listitem')).toHaveLength(2);
});

it('tắt công tắc thì lưu lên máy chủ, danh sách mờ đi và lời giải thích đổi theo; lỗi thì bật lại', async () => {
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  const toggle = await screen.findByRole('switch', { name: 'Cho Peto ghi nhớ' });
  expect((toggle as HTMLInputElement).checked).toBe(true);

  fireEvent.click(toggle);
  expect(api.setCompanionMemoryEnabled).toHaveBeenCalledWith(false);
  expect(screen.getByText('Đang tắt: Peto không ghi thêm và không dùng các ghi nhớ bên dưới.')).toBeTruthy();
  expect(list().classList.contains('off')).toBe(true);
  await waitFor(() => expect((toggle as HTMLInputElement).disabled).toBe(false));
  expect((toggle as HTMLInputElement).checked).toBe(false);

  vi.mocked(api.setCompanionMemoryEnabled).mockRejectedValueOnce(new TypeError('Failed to fetch'));
  fireEvent.click(toggle);
  expect((await screen.findByRole('alert')).textContent).toBe('Chưa đổi được. Thử lại sau nha.');
  expect((toggle as HTMLInputElement).checked).toBe(false);
  expect(list().classList.contains('off')).toBe(true);
});

it('Xóa hết phải xác nhận; Giữ lại thì thôi, xác nhận thì danh sách trống', async () => {
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  await screen.findByText('Đang học năm hai ngành điện');

  fireEvent.click(screen.getByRole('button', { name: 'Xóa hết' }));
  const confirm = screen.getByRole('group', { name: 'Xác nhận xóa hết' });
  expect(confirm.textContent).toContain('Xóa hết 2 ghi nhớ?');
  fireEvent.click(within(confirm).getByRole('button', { name: 'Giữ lại' }));
  expect(screen.queryByRole('group', { name: 'Xác nhận xóa hết' })).toBeNull();
  expect(api.clearCompanionMemory).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Xóa hết' }));
  fireEvent.click(within(screen.getByRole('group', { name: 'Xác nhận xóa hết' })).getByRole('button', { name: 'Xóa hết' }));
  expect(await screen.findByText(/Chưa có ghi nhớ nào/)).toBeTruthy();
  expect(api.clearCompanionMemory).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('list')).toBeNull();
});

it('chủ web tắt trên máy chủ thì chỉ có lời giải thích, không có công tắc hay danh sách', async () => {
  vi.mocked(api.getCompanionMemory).mockResolvedValue(state({ available: false, enabled: false }));
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  expect(await screen.findByText('Chủ web đã tắt trí nhớ Companion trên máy chủ này.')).toBeTruthy();
  expect(screen.queryByRole('switch')).toBeNull();
  expect(screen.queryByRole('list')).toBeNull();
});

it('lỗi tải thì cho thử lại; phiên hết hạn thì về màn đăng nhập', async () => {
  vi.mocked(api.getCompanionMemory).mockRejectedValueOnce(new TypeError('Failed to fetch'));
  const { unmount } = render(<MemorySettings open onUnauthorized={vi.fn()} />);
  expect((await screen.findByRole('alert')).textContent).toBe('Chưa tải được danh sách ghi nhớ.');
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
  expect(await screen.findByText('Nuôi một con mèo tên Mướp')).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
  unmount();

  vi.mocked(api.getCompanionMemory).mockRejectedValue(new api.UnauthorizedError());
  const onUnauthorized = vi.fn();
  render(<MemorySettings open onUnauthorized={onUnauthorized} />);
  await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
});

it('đóng Cài đặt thì không tải; mở lại thì tải danh sách mới', async () => {
  const onUnauthorized = vi.fn();
  const { rerender } = render(<MemorySettings open={false} onUnauthorized={onUnauthorized} />);
  expect(api.getCompanionMemory).not.toHaveBeenCalled();
  rerender(<MemorySettings open onUnauthorized={onUnauthorized} />);
  await screen.findByText('Đang học năm hai ngành điện');

  vi.mocked(api.getCompanionMemory).mockResolvedValue(state({ memories: [memories[1]] }));
  rerender(<MemorySettings open={false} onUnauthorized={onUnauthorized} />);
  rerender(<MemorySettings open onUnauthorized={onUnauthorized} />);
  await waitFor(() => expect(screen.queryByText('Đang học năm hai ngành điện')).toBeNull());
  expect(screen.getByText('1/50 ghi nhớ')).toBeTruthy();
});
