import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import MemorySettings from '../src/features/settings/MemorySettings';
import * as api from '../src/shared/api/api';

vi.mock('../src/shared/api/api', async (original) => ({
  ...await original<typeof import('../src/shared/api/api')>(),
  getCompanionMemory: vi.fn(), setCompanionMemoryEnabled: vi.fn(), deleteCompanionMemory: vi.fn(),
  clearCompanionMemory: vi.fn(), updateCompanionMemory: vi.fn(), createCompanionMemory: vi.fn(),
  tellCompanionMemory: vi.fn(),
}));

const now = Date.now() / 1000;
const entry = (id: number, section: api.MemorySection, title: string, summary: string, details: string[],
  extra: Partial<api.CompanionMemory> = {}): api.CompanionMemory => ({
  id, section, title, summary, details, fixed: false, legacy: false, created_at: now, updated_at: now, ...extra,
});
const profile = entry(3, 'you', 'Hồ sơ', 'Sinh viên năm hai ngành điện',
  ['Đang học năm hai ngành điện', 'Nuôi một con mèo tên Mướp'], { fixed: true });
const project = entry(5, 'area', 'Đồ án vi điều khiển', 'Mạch đo nhiệt độ dùng ESP32', ['Dùng ESP32 và cảm biến DHT22'],
  { updated_at: now - 86_400 });
const hobby = entry(7, 'topic', 'Sở thích', 'Ngoài việc học', ['Chơi đàn guitar']);
const memories = [profile, project, hobby];
const state = (extra: Partial<api.CompanionMemoryState> = {}): api.CompanionMemoryState => ({
  available: true, enabled: true, pending: false, sorting: false, limit: 20, memories, ...extra,
});
const row = (title: string) => screen.getByRole('button', { name: new RegExp(`^${title}`) });

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getCompanionMemory).mockResolvedValue(state());
  vi.mocked(api.setCompanionMemoryEnabled).mockResolvedValue();
  vi.mocked(api.deleteCompanionMemory).mockResolvedValue();
  vi.mocked(api.clearCompanionMemory).mockResolvedValue();
});

afterEach(() => vi.useRealTimers());

it('chia mục theo ba nhóm Bạn, Chủ đề, Lĩnh vực; mỗi hàng có tên, tóm tắt, ngày cập nhật, nút Sửa và Xóa', async () => {
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  await screen.findByText('Sinh viên năm hai ngành điện');
  const lists = screen.getAllByRole('list');
  expect(lists.map((list) => list.getAttribute('aria-label'))).toEqual(['Bạn', 'Chủ đề', 'Lĩnh vực']);
  expect(within(lists[0]).getByText('Cập nhật hôm nay')).toBeTruthy();
  expect(within(lists[2]).getByText('Cập nhật hôm qua')).toBeTruthy();
  expect(within(lists[2]).getByText('Mạch đo nhiệt độ dùng ESP32')).toBeTruthy();
  // Các ý chỉ hiện trong trang chi tiết.
  expect(screen.queryByText('Nuôi một con mèo tên Mướp')).toBeNull();
  expect(screen.getByRole('button', { name: 'Sửa Hồ sơ' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Xóa Sở thích' })).toBeTruthy();
  expect(screen.getByText('3/20 mục · 4 ý')).toBeTruthy();
});

it('bấm một hàng là sang trang chi tiết; nút Trí nhớ hay Esc đưa về danh sách và trả tiêu điểm về hàng đó', async () => {
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: /^Hồ sơ/ }));
  const heading = screen.getByRole('heading', { name: 'Hồ sơ' });
  expect(document.activeElement).toBe(heading);
  expect(screen.getByText('Cập nhật lần cuối')).toBeTruthy();
  expect(screen.getByText('Nuôi một con mèo tên Mướp')).toBeTruthy();
  expect(screen.queryByRole('switch')).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'Trí nhớ' }));
  expect(await screen.findByRole('switch', { name: 'Cho Peto ghi nhớ' })).toBeTruthy();
  expect(document.activeElement).toBe(row('Hồ sơ'));

  fireEvent.click(row('Sở thích'));
  const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
  screen.getByRole('heading', { name: 'Sở thích' }).dispatchEvent(escape);
  expect(escape.defaultPrevented).toBe(true); // hộp Cài đặt không bị đóng theo
  expect(await screen.findByRole('switch')).toBeTruthy();
});

it('sửa tay: Lưu gửi mỗi dòng một ý; mục cố định không đổi tên; bỏ hết ý thì báo lỗi và không gọi máy chủ', async () => {
  vi.mocked(api.updateCompanionMemory).mockImplementation(async (id, patch) => ({ ...project, ...patch, id }));
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Sửa Đồ án vi điều khiển' }));
  const name = screen.getByLabelText('Tên mục') as HTMLInputElement;
  expect(document.activeElement).toBe(name);
  fireEvent.change(name, { target: { value: 'Đồ án ESP32' } });
  fireEvent.change(screen.getByLabelText('Chi tiết · mỗi dòng một ý'), {
    target: { value: 'Dùng ESP32\n- Đo nhiệt độ mỗi phút\n\n' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lưu' }));
  await waitFor(() => expect(api.updateCompanionMemory).toHaveBeenCalledWith(5, {
    title: 'Đồ án ESP32', summary: 'Mạch đo nhiệt độ dùng ESP32', details: ['Dùng ESP32', 'Đo nhiệt độ mỗi phút'] }));
  expect(await screen.findByText('Đo nhiệt độ mỗi phút')).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Đồ án ESP32' })).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'Sửa' }));
  fireEvent.change(screen.getByLabelText('Chi tiết · mỗi dòng một ý'), { target: { value: '  \n' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lưu' }));
  expect((await screen.findByRole('alert')).textContent).toBe('Mục cần ít nhất một ý. Muốn bỏ cả mục thì bấm Xóa.');
  expect(api.updateCompanionMemory).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Hủy' }));

  fireEvent.click(screen.getByRole('button', { name: 'Trí nhớ' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Sửa Hồ sơ' }));
  expect(screen.queryByLabelText('Tên mục')).toBeNull();
  expect(document.activeElement).toBe(screen.getByLabelText('Tóm tắt'));

  // Esc thôi sửa, tiêu điểm về tên mục (không rơi ra ngoài), Esc lần nữa về danh sách; hộp Cài đặt không bị đóng.
  fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
  expect(screen.queryByLabelText('Tóm tắt')).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Hồ sơ' }));
  const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
  document.activeElement!.dispatchEvent(escape);
  expect(escape.defaultPrevented).toBe(true);
  expect(await screen.findByRole('switch')).toBeTruthy();
});

it('xóa một mục rồi Hoàn tác thì tạo lại đúng mục đó', async () => {
  vi.mocked(api.createCompanionMemory).mockResolvedValue({ ...hobby, id: 9 });
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa Sở thích' }));
  await waitFor(() => expect(screen.queryByText('Ngoài việc học')).toBeNull());
  expect(api.deleteCompanionMemory).toHaveBeenCalledWith(7);
  expect((await screen.findByRole('status')).textContent).toContain('Đã xóa “Sở thích”.');
  expect(screen.getByText('2/20 mục · 3 ý')).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'Hoàn tác' }));
  expect(await screen.findByText('Ngoài việc học')).toBeTruthy();
  expect(api.createCompanionMemory).toHaveBeenCalledWith(hobby);
});

it('xóa không được thì mục quay lại và báo lỗi của máy chủ, không hiện Hoàn tác', async () => {
  vi.mocked(api.deleteCompanionMemory).mockRejectedValue(new Error('Không tìm thấy mục này. Có thể nó đã được xóa.'));
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: /^Hồ sơ/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Xóa' }));
  expect((await screen.findByRole('alert')).textContent).toBe('Không tìm thấy mục này. Có thể nó đã được xóa.');
  expect(row('Hồ sơ')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Hoàn tác' })).toBeNull();
});

it('Bảo Peto nhớ: cập nhật danh sách và báo; Xem mở đúng mục với ý mới tô sáng; lỗi thì giữ chữ để gửi lại', async () => {
  const updated = { ...profile, details: [...profile.details, 'Mướp đã ba tuổi'] };
  vi.mocked(api.tellCompanionMemory).mockResolvedValueOnce({
    message: 'Đã thêm vào “Hồ sơ”.', changes: [{ id: 3, kind: 'add', fresh: [2] }], memories: [updated, project, hobby] });
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  const box = await screen.findByRole('textbox', { name: 'Bảo Peto nhớ điều gì đó' }) as HTMLTextAreaElement;
  fireEvent.change(box, { target: { value: 'Mướp đã ba tuổi rồi' } });
  fireEvent.keyDown(box, { key: 'Enter' });
  await waitFor(() => expect(api.tellCompanionMemory).toHaveBeenCalledWith('Mướp đã ba tuổi rồi', undefined));
  expect((await screen.findByRole('status')).textContent).toContain('Đã thêm vào “Hồ sơ”.');
  await waitFor(() => expect(box.value).toBe(''));
  expect(screen.getByText('3/20 mục · 5 ý')).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'Xem' }));
  const added = await screen.findByText('Mướp đã ba tuổi');
  expect(added.hasAttribute('data-fresh')).toBe(true);
  expect(screen.getByText('Nuôi một con mèo tên Mướp').hasAttribute('data-fresh')).toBe(false);

  fireEvent.click(screen.getByRole('button', { name: 'Trí nhớ' }));
  vi.mocked(api.tellCompanionMemory).mockRejectedValueOnce(new Error('Peto chưa cập nhật được trí nhớ. Thử lại sau nha.'));
  const again = await screen.findByRole('textbox', { name: 'Bảo Peto nhớ điều gì đó' }) as HTMLTextAreaElement;
  fireEvent.change(again, { target: { value: 'Mình thích mèo' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gửi cho Peto' }));
  expect((await screen.findByRole('alert')).textContent).toBe('Peto chưa cập nhật được trí nhớ. Thử lại sau nha.');
  expect(again.value).toBe('Mình thích mèo');
});

it('Bảo Peto trong trang chi tiết gửi kèm id mục và báo ngay trên ô nhập', async () => {
  vi.mocked(api.tellCompanionMemory).mockResolvedValueOnce({
    message: 'Đã bỏ khỏi “Đồ án vi điều khiển”.', changes: [{ id: 5, kind: 'remove', fresh: [] }],
    memories: [profile, { ...project, details: ['Dùng ESP32'] }, hobby] });
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: /^Đồ án vi điều khiển/ }));
  const box = screen.getByRole('textbox', { name: 'Bảo Peto đổi hay bỏ điều gì trong Đồ án vi điều khiển' });
  fireEvent.change(box, { target: { value: 'bỏ cảm biến DHT22' } });
  fireEvent.keyDown(box, { key: 'Enter' });
  await waitFor(() => expect(api.tellCompanionMemory).toHaveBeenCalledWith('bỏ cảm biến DHT22', 5));
  expect((await screen.findByRole('status')).textContent).toBe('Đã bỏ khỏi “Đồ án vi điều khiển”.');
  expect(screen.getByText('Dùng ESP32')).toBeTruthy();
});

it('tắt công tắc thì lưu lên máy chủ, danh sách mờ đi, ô bảo Peto khóa lại; lỗi thì bật lại', async () => {
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  const toggle = await screen.findByRole('switch', { name: 'Cho Peto ghi nhớ' }) as HTMLInputElement;
  expect(toggle.checked).toBe(true);

  fireEvent.click(toggle);
  expect(api.setCompanionMemoryEnabled).toHaveBeenCalledWith(false);
  expect(screen.getByText('Đang tắt: Peto không ghi thêm và không dùng các ghi nhớ bên dưới.')).toBeTruthy();
  expect(screen.getAllByRole('list').every((list) => list.classList.contains('off'))).toBe(true);
  expect((screen.getByRole('textbox', { name: 'Bảo Peto nhớ điều gì đó' }) as HTMLTextAreaElement).disabled).toBe(true);
  await waitFor(() => expect(toggle.disabled).toBe(false));

  vi.mocked(api.setCompanionMemoryEnabled).mockRejectedValueOnce(new TypeError('Failed to fetch'));
  fireEvent.click(toggle);
  expect((await screen.findByRole('alert')).textContent).toBe('Chưa đổi được. Thử lại sau nha.');
  expect(toggle.checked).toBe(false);
});

it('Xóa hết phải xác nhận; Giữ lại thì thôi, xác nhận thì trí nhớ trống', async () => {
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  await screen.findByText('Sinh viên năm hai ngành điện');

  fireEvent.click(screen.getByRole('button', { name: 'Xóa hết' }));
  const confirm = screen.getByRole('group', { name: 'Xác nhận xóa hết' });
  expect(confirm.textContent).toContain('Xóa hết 3 mục?');
  fireEvent.click(within(confirm).getByRole('button', { name: 'Giữ lại' }));
  expect(screen.queryByRole('group', { name: 'Xác nhận xóa hết' })).toBeNull();
  expect(api.clearCompanionMemory).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Xóa hết' }));
  fireEvent.click(within(screen.getByRole('group', { name: 'Xác nhận xóa hết' })).getByRole('button', { name: 'Xóa hết' }));
  expect(await screen.findByText(/Chưa có ghi nhớ nào/)).toBeTruthy();
  expect(api.clearCompanionMemory).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('list')).toBeNull();
});

it('ghi nhớ cũ đang được xếp thì báo và hỏi lại sau vài giây; mục chưa xếp nằm riêng một nhóm', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const legacy = entry(11, 'topic', 'Ghi nhớ cũ', 'Những điều Peto ghi trước khi trí nhớ chia mục',
    ['Học lớp 12'], { legacy: true });
  vi.mocked(api.getCompanionMemory)
    .mockResolvedValueOnce(state({ sorting: true, memories: [legacy] }))
    .mockResolvedValue(state());
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  expect(await screen.findByText('Peto đang xếp các ghi nhớ cũ vào từng mục…')).toBeTruthy();
  expect(screen.getByRole('list', { name: 'Chưa xếp mục' })).toBeTruthy();
  await vi.advanceTimersByTimeAsync(4000);
  expect(await screen.findByText('Sinh viên năm hai ngành điện')).toBeTruthy();
  expect(screen.queryByText('Peto đang xếp các ghi nhớ cũ vào từng mục…')).toBeNull();
  expect(api.getCompanionMemory).toHaveBeenCalledTimes(2);
});

it('lần tải đầu hiện logo chờ của Peto thay cả mục, không phải một dòng chữ trơn', async () => {
  let finish!: (value: api.CompanionMemoryState) => void;
  vi.mocked(api.getCompanionMemory).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  const { container } = render(<MemorySettings open onUnauthorized={vi.fn()} />);
  expect(screen.getByRole('status', { name: 'Đang tải trí nhớ' })).toBeTruthy();
  expect(container.querySelector('.settings-loading .brand-loading')).toBeTruthy();
  expect(screen.queryByRole('switch')).toBeNull();
  finish(state());
  expect(await screen.findByRole('switch', { name: 'Cho Peto ghi nhớ' })).toBeTruthy();
  expect(screen.queryByRole('status', { name: 'Đang tải trí nhớ' })).toBeNull();
});

it('chủ web tắt trên máy chủ thì chỉ có lời giải thích, không có công tắc, danh sách hay ô bảo Peto', async () => {
  vi.mocked(api.getCompanionMemory).mockResolvedValue(state({ available: false, enabled: false }));
  render(<MemorySettings open onUnauthorized={vi.fn()} />);
  expect(await screen.findByText('Chủ web đã tắt trí nhớ trên máy chủ này.')).toBeTruthy();
  expect(screen.queryByRole('switch')).toBeNull();
  expect(screen.queryByRole('list')).toBeNull();
  expect(screen.queryByRole('textbox')).toBeNull();
});

it('lỗi tải thì cho thử lại; phiên hết hạn thì về màn đăng nhập', async () => {
  vi.mocked(api.getCompanionMemory).mockRejectedValueOnce(new TypeError('Failed to fetch'));
  const { unmount } = render(<MemorySettings open onUnauthorized={vi.fn()} />);
  expect((await screen.findByRole('alert')).textContent).toBe('Chưa tải được trí nhớ.');
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
  expect(await screen.findByText('Ngoài việc học')).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
  unmount();

  vi.mocked(api.getCompanionMemory).mockRejectedValue(new api.UnauthorizedError());
  const onUnauthorized = vi.fn();
  render(<MemorySettings open onUnauthorized={onUnauthorized} />);
  await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
});

it('đóng Cài đặt thì không tải; mở lại thì tải trí nhớ mới', async () => {
  const onUnauthorized = vi.fn();
  const { rerender } = render(<MemorySettings open={false} onUnauthorized={onUnauthorized} />);
  expect(api.getCompanionMemory).not.toHaveBeenCalled();
  rerender(<MemorySettings open onUnauthorized={onUnauthorized} />);
  await screen.findByText('Sinh viên năm hai ngành điện');

  vi.mocked(api.getCompanionMemory).mockResolvedValue(state({ memories: [hobby] }));
  rerender(<MemorySettings open={false} onUnauthorized={onUnauthorized} />);
  rerender(<MemorySettings open onUnauthorized={onUnauthorized} />);
  await waitFor(() => expect(screen.queryByText('Sinh viên năm hai ngành điện')).toBeNull());
  expect(screen.getByText('1/20 mục · 1 ý')).toBeTruthy();
});
