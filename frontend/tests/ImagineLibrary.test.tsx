import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ImagineLibrary from '../src/features/imagine/ImagineLibrary';
import type { ImagineJob } from '../src/shared/api/api';

const cat: ImagineJob = {
  id: 'job-cat', prompt: 'Mèo trắng đội mũ', quality: 'low', resolution: '1k', aspect_ratio: 'auto', created_at: 2,
  images: [{ id: 'cat-1', mime: 'image/png', url: '/api/imagine/images/cat-1', liked: true },
    { id: 'cat-2', mime: 'image/png', url: '/api/imagine/images/cat-2' }],
};
const lake: ImagineJob = {
  ...cat, id: 'job-lake', prompt: 'Ngôi nhà bên hồ', created_at: 1,
  images: [{ id: 'lake-1', mime: 'image/png', url: '/api/imagine/images/lake-1' }],
};

function setup(overrides: Partial<Parameters<typeof ImagineLibrary>[0]> = {}) {
  const props = {
    open: true, jobs: [cat, lake], onClose: vi.fn(), onOpenImage: vi.fn(),
    onDeleteImages: vi.fn(async (_ids: string[]) => {}), ...overrides,
  };
  const view = render(<ImagineLibrary {...props} />);
  return { ...props, view };
}
const tiles = () => screen.queryAllByRole('button', { name: /^(Xem|Chọn) ảnh: / });
const ids = () => tiles().map((tile) => tile.getAttribute('data-image-id'));
// jsdom chưa chắc có PointerEvent, nên dựng sự kiện chuột mang tên pointer như test Live2DStage.
const pointer = (type: string) => new MouseEvent(type, { button: 0, clientX: 10, clientY: 10, bubbles: true });

beforeEach(() => localStorage.clear());
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('mỗi ảnh một ô, chạm để xem, tìm kiếm không cần gõ dấu', () => {
  const { onOpenImage } = setup();
  expect(ids()).toEqual(['cat-1', 'cat-2', 'lake-1']);
  fireEvent.click(tiles()[1]);
  expect(onOpenImage).toHaveBeenCalledWith(cat, 1);
  fireEvent.click(screen.getByRole('button', { name: 'Tìm trong thư viện' }));
  fireEvent.change(screen.getByLabelText('Tìm ảnh theo mô tả'), { target: { value: 'nha ben HO' } });
  expect(ids()).toEqual(['lake-1']);
  fireEvent.change(screen.getByLabelText('Tìm ảnh theo mô tả'), { target: { value: 'chó' } });
  expect(screen.getByText('Không có ảnh nào khớp')).toBeTruthy();
});

it('bảng lọc đổi sang 3 cột và nhớ lại, còn lọc ảnh đã thích thì không nhớ', () => {
  const { view } = setup();
  fireEvent.click(screen.getByRole('button', { name: 'Bố cục và bộ lọc' }));
  fireEvent.click(screen.getByRole('button', { name: '3 cột' }));
  expect((document.querySelector('.library-grid') as HTMLElement).style.getPropertyValue('--library-columns')).toBe('3');
  fireEvent.click(screen.getByRole('button', { name: 'Chỉ ảnh đã thích' }));
  expect(ids()).toEqual(['cat-1']);
  view.unmount();

  setup();
  expect(ids()).toHaveLength(3);
  fireEvent.click(screen.getByRole('button', { name: 'Bố cục và bộ lọc' }));
  expect(screen.getByRole('button', { name: '3 cột' }).getAttribute('aria-pressed')).toBe('true');
});

it('chọn nhiều ảnh để tải xuống, rồi xóa sau khi xác nhận', async () => {
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const { onDeleteImages } = setup();
  fireEvent.click(screen.getByRole('button', { name: 'Chọn' }));
  expect((screen.getByRole('button', { name: 'Xóa' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(tiles()[0]);
  fireEvent.click(tiles()[2]);
  expect(tiles()[0].getAttribute('aria-pressed')).toBe('true');
  expect(tiles()[1].getAttribute('aria-pressed')).toBe('false');

  fireEvent.click(screen.getByRole('button', { name: 'Tải xuống' }));
  expect(click.mock.contexts.map((link) => (link as HTMLAnchorElement).getAttribute('href')))
    .toEqual(['/api/imagine/images/cat-1?download=1', '/api/imagine/images/lake-1?download=1']);

  fireEvent.click(screen.getByRole('button', { name: 'Xóa' }));
  expect(onDeleteImages).not.toHaveBeenCalled();
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Xóa 2 ảnh?' })).getByRole('button', { name: 'Xóa ảnh' }));
  await waitFor(() => expect(onDeleteImages).toHaveBeenCalledWith(['cat-1', 'lake-1']));
  expect(await screen.findByRole('button', { name: 'Chọn' })).toBeTruthy();
});

it('giữ lâu chọn ảnh, không mở menu hay bỏ chọn khi nhấc tay; xóa lỗi thì báo', async () => {
  vi.useFakeTimers();
  const onDeleteImages = vi.fn(async (_ids: string[]) => { throw new Error('Chưa xóa được 1 ảnh. Thử lại nhé.'); });
  setup({ onDeleteImages });
  const tile = tiles()[1];
  act(() => { tile.dispatchEvent(pointer('pointerdown')); });
  act(() => { vi.advanceTimersByTime(500); });
  expect(screen.queryByRole('menu')).toBeNull();
  act(() => { tile.dispatchEvent(pointer('pointerup')); });
  // Cú nhấc tay sau khi giữ lâu không được bỏ chọn ngay ảnh vừa chọn.
  fireEvent.click(tile, { detail: 1 });
  expect(tiles()[1].getAttribute('aria-pressed')).toBe('true');
  vi.useRealTimers();

  fireEvent.click(screen.getByRole('button', { name: 'Xóa', exact: true }));
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Xóa ảnh này?' })).getByRole('button', { name: 'Xóa ảnh' }));
  expect((await screen.findByRole('alert')).textContent).toContain('Chưa xóa được 1 ảnh');
  expect(onDeleteImages).toHaveBeenCalledWith(['cat-2']);
});

it('trình duyệt chia sẻ được tệp thì gửi đúng các ảnh đã chọn', async () => {
  const share = vi.fn(async (_data: { files: File[] }) => {});
  Object.defineProperty(navigator, 'share', { value: share, configurable: true });
  Object.defineProperty(navigator, 'canShare', { value: () => true, configurable: true });
  const fetchImage = vi.fn(async (_url: string) => ({ ok: true, blob: async () => new Blob(['png'], { type: 'image/png' }) }));
  vi.stubGlobal('fetch', fetchImage);
  try {
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Chọn' }));
    fireEvent.click(tiles()[2]);
    fireEvent.click(screen.getByRole('button', { name: 'Chia sẻ' }));
    await waitFor(() => expect(share).toHaveBeenCalledTimes(1));
    expect(fetchImage).toHaveBeenCalledWith('/api/imagine/images/lake-1');
    expect(share.mock.calls[0][0].files.map((file) => [file.name, file.type])).toEqual([['peto-1.png', 'image/png']]);
  } finally {
    Reflect.deleteProperty(navigator, 'share');
    Reflect.deleteProperty(navigator, 'canShare');
  }
});

it('Escape đóng từng lớp: thoát chế độ chọn trước rồi mới đóng thư viện', () => {
  const { onClose } = setup();
  const dialog = screen.getByRole('dialog', { name: 'Thư viện ảnh' });
  fireEvent.click(screen.getByRole('button', { name: 'Chọn' }));
  fireEvent(dialog, new Event('cancel', { cancelable: true }));
  expect(screen.getByRole('button', { name: 'Chọn' })).toBeTruthy();
  expect(onClose).not.toHaveBeenCalled();
  fireEvent(dialog, new Event('cancel', { cancelable: true }));
  expect(onClose).toHaveBeenCalledTimes(1);
});


it('bấm nhanh mở ảnh, không tự chuyển sang chọn sau khi chờ lâu hơn ngưỡng giữ', () => {
  vi.useFakeTimers();
  const { onOpenImage } = setup();
  const tile = tiles()[0];
  act(() => { tile.dispatchEvent(pointer('pointerdown')); vi.advanceTimersByTime(100); tile.dispatchEvent(pointer('pointerup')); });
  fireEvent.click(tile, { detail: 1 });
  act(() => { vi.advanceTimersByTime(1000); });
  expect(onOpenImage).toHaveBeenCalledWith(cat, 0);
  expect(screen.queryByRole('button', { name: 'Hủy', exact: true })).toBeNull();
});

it('trượt để cuộn hoặc hủy cử chỉ không chọn ảnh', () => {
  vi.useFakeTimers();
  setup();
  const tile = tiles()[0];
  act(() => {
    tile.dispatchEvent(pointer('pointerdown'));
    vi.advanceTimersByTime(200);
    tile.dispatchEvent(new MouseEvent('pointermove', { clientX: 10, clientY: 70, bubbles: true }));
    vi.advanceTimersByTime(1000);
  });
  expect(screen.queryByRole('button', { name: 'Hủy', exact: true })).toBeNull();
  act(() => { tile.dispatchEvent(pointer('pointerdown')); tile.dispatchEvent(pointer('pointercancel')); vi.advanceTimersByTime(1000); });
  expect(screen.queryByRole('button', { name: 'Hủy', exact: true })).toBeNull();
});

it('chuột phải mở menu riêng, đóng menu rồi bấm ảnh vẫn xem được', () => {
  const { onOpenImage } = setup();
  fireEvent.contextMenu(tiles()[0]);
  expect(screen.getByRole('menu', { name: 'Thao tác với ảnh' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Hủy', exact: true })).toBeNull();
  fireEvent(screen.getByRole('dialog', { name: 'Thư viện ảnh' }), new Event('cancel', { cancelable: true }));
  fireEvent.click(tiles()[0]);
  expect(onOpenImage).toHaveBeenCalledWith(cat, 0);
});

it('đóng/mở thư viện thoát chế độ chọn và không chặn lần xem tiếp theo', () => {
  vi.useFakeTimers();
  const { view, onOpenImage, onClose, onDeleteImages } = setup({ onUseSources: vi.fn() });
  act(() => { tiles()[0].dispatchEvent(pointer('pointerdown')); vi.advanceTimersByTime(500); });
  expect(screen.queryByText(/Chọn theo thứ tự mong muốn/)).toBeNull();
  expect(document.querySelector('.image-nav-rail')).toBeNull();
  const props = { jobs: [cat, lake], onOpenImage, onClose, onDeleteImages };
  view.rerender(<ImagineLibrary {...props} open={false} />);
  view.rerender(<ImagineLibrary {...props} open />);
  fireEvent.click(tiles()[0]);
  expect(onOpenImage).toHaveBeenCalledWith(cat, 0);
  expect(screen.queryByRole('button', { name: 'Hủy', exact: true })).toBeNull();
});
