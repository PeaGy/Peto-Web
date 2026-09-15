import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Imagine from '../src/Imagine';
import * as api from '../src/api';

vi.mock('../src/api', async (original) => ({
  ...await original<typeof import('../src/api')>(),
  listImagineJobs: vi.fn(), createImagineJob: vi.fn(), deleteImagineJob: vi.fn(),
  deleteImagineImage: vi.fn(), setImagineImageLiked: vi.fn(),
}));
const job: api.ImagineJob = {
  id: 'job-1', prompt: 'Mèo trên mặt trăng', quality: 'medium', resolution: '2k',
  aspect_ratio: '16:9', created_at: 1788990000,
  images: [{ id: 'img-1', mime: 'image/png', url: '/api/imagine/images/img-1' },
    { id: 'img-2', mime: 'image/png', url: '/api/imagine/images/img-2' }],
};
const props = { active: true, onUnauthorized: vi.fn(), onOpenSidebar: vi.fn() };
const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
const sourceFile = () => new File([Uint8Array.from(atob(png), (char) => char.charCodeAt(0))], 'anh-goc.png', { type: 'image/png' });
const editedJob: api.ImagineJob = { ...job, source_image: { id: 'source-1', mime: 'image/png', url: '/api/imagine/images/source-1' } };
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};
beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  Element.prototype.scrollTo = vi.fn();
  vi.mocked(api.listImagineJobs).mockResolvedValue([]);
  vi.mocked(api.createImagineJob).mockResolvedValue(job);
  vi.mocked(api.deleteImagineJob).mockResolvedValue();
  vi.mocked(api.deleteImagineImage).mockResolvedValue({ job_deleted: false });
  vi.mocked(api.setImagineImageLiked).mockImplementation(async (_id, liked) => liked);
});
afterEach(() => vi.unstubAllGlobals());
/** Giả lập điện thoại: CSS đổi bố cục ở mốc 720px, còn JS đọc cùng mốc qua matchMedia. */
function stubPhone() {
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('max-width'), media: query,
    addEventListener: vi.fn(), removeEventListener: vi.fn() }));
}
async function open() {
  const view = render(<Imagine {...props} />);
  await waitFor(() => expect(screen.queryByText('Đang mở bộ ảnh của bạn…')).toBeNull());
  return view;
}

it('fills an idea without generating, then sends the chosen options', async () => {
  await open();
  fireEvent.click(screen.getByRole('button', { name: /Một nhân vật/ }));
  expect(api.createImagineJob).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Chi tiết', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: '2K', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Tỉ lệ: Tự động' }));
  fireEvent.click(screen.getByRole('menuitemradio', { name: '16:9' }));
  fireEvent.click(screen.getByRole('button', { name: 'Số ảnh: 1 ảnh' }));
  fireEvent.click(screen.getByRole('menuitemradio', { name: '2 ảnh' }));
  expect(screen.getByRole('button', { name: 'Tỉ lệ: 16:9' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  await screen.findByRole('button', { name: /Xem ảnh 1:/ });
  expect(api.createImagineJob).toHaveBeenCalledWith({
    prompt: expect.stringContaining('Mèo trắng'), quality: 'medium', resolution: '2k', aspect_ratio: '16:9', n: 2,
  });
});

it('keeps the request and draft across tab switches, without stealing chat focus', async () => {
  const request = deferred<api.ImagineJob>();
  vi.mocked(api.createImagineJob).mockReturnValue(request.promise);
  const view = await open();
  fireEvent.change(screen.getByLabelText('Bức ảnh bạn muốn tạo'), { target: { value: job.prompt } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  fireEvent.submit(screen.getByLabelText('Bức ảnh bạn muốn tạo').closest('form')!);
  expect(api.createImagineJob).toHaveBeenCalledTimes(1);
  view.rerender(<><Imagine {...props} active={false} /><input aria-label="Trò chuyện" /></>);
  screen.getByLabelText('Trò chuyện').focus();
  await act(async () => request.resolve(job));
  expect(document.activeElement).toBe(screen.getByLabelText('Trò chuyện'));
  view.rerender(<Imagine {...props} />);
  await screen.findByRole('button', { name: /Xem ảnh 1:/ });
  expect((screen.getByLabelText('Bức ảnh bạn muốn tạo') as HTMLTextAreaElement).value).toBe(job.prompt);
  expect(api.listImagineJobs).toHaveBeenCalledTimes(1);
});

it('waits for gallery loading before accepting a generation request', async () => {
  const loading = deferred<api.ImagineJob[]>();
  vi.mocked(api.listImagineJobs).mockReturnValueOnce(loading.promise);
  render(<Imagine {...props} />);
  fireEvent.change(screen.getByLabelText('Bức ảnh bạn muốn tạo'), { target: { value: 'Ý tưởng mới' } });
  fireEvent.submit(screen.getByLabelText('Bức ảnh bạn muốn tạo').closest('form')!);
  expect(api.createImagineJob).not.toHaveBeenCalled();
  await act(async () => loading.resolve([job]));
  expect(screen.getByRole('button', { name: /Xem ảnh 1:/ })).toBeTruthy();
});

it('keeps the prompt when generation fails, then allows another attempt', async () => {
  vi.mocked(api.createImagineJob).mockRejectedValueOnce(new Error('Peto đang bận.'));
  await open();
  fireEvent.change(screen.getByLabelText('Bức ảnh bạn muốn tạo'), { target: { value: job.prompt } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  expect((await screen.findByRole('alert')).textContent).toContain('Peto đang bận.');
  expect((screen.getByLabelText('Bức ảnh bạn muốn tạo') as HTMLTextAreaElement).value).toBe(job.prompt);
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  await screen.findByRole('button', { name: /Xem ảnh 1:/ });
});

it('retries loading without losing the draft', async () => {
  vi.mocked(api.listImagineJobs).mockRejectedValueOnce(new Error('offline')).mockResolvedValue([job]);
  await open();
  fireEvent.change(screen.getByLabelText('Bức ảnh bạn muốn tạo'), { target: { value: 'Đang viết' } });
  fireEvent.click(screen.getByRole('button', { name: 'Thử tải lại' }));
  await screen.findByRole('button', { name: /Xem ảnh 1:/ });
  expect((screen.getByLabelText('Bức ảnh bạn muốn tạo') as HTMLTextAreaElement).value).toBe('Đang viết');
});

it('requires confirmation before deletion and keeps the job if deletion fails', async () => {
  vi.mocked(api.listImagineJobs).mockResolvedValue([job]);
  vi.mocked(api.deleteImagineJob).mockRejectedValueOnce(new Error('Chưa xóa được')).mockResolvedValue();
  await open();
  fireEvent.click(screen.getByRole('button', { name: /Xóa lượt ảnh:/ }));
  expect(api.deleteImagineJob).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Giữ lại' }));
  expect(api.deleteImagineJob).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: /Xóa lượt ảnh:/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Xóa ảnh', exact: true }));
  const dialog = screen.getByRole('dialog', { name: 'Xóa lượt ảnh này?' });
  await within(dialog).findByRole('alert');
  expect(screen.getByRole('button', { name: /Xem ảnh 1:/ })).toBeTruthy();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Xóa ảnh', exact: true }));
  await waitFor(() => expect(screen.queryByRole('button', { name: /Xem ảnh 1:/ })).toBeNull());
});

it('opens the correct image, navigates the set, downloads it and closes with Escape', async () => {
  vi.mocked(api.listImagineJobs).mockResolvedValue([job]);
  await open();
  fireEvent.click(screen.getByRole('button', { name: /Xem ảnh 1:/ }));
  const dialog = screen.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  expect(within(dialog).getByRole('img').getAttribute('src')).toBe(job.images[0].url);
  fireEvent.click(within(dialog).getByRole('button', { name: 'Sau →' }));
  expect(within(dialog).getByRole('link', { name: /Tải ảnh xuống/ }).getAttribute('href')).toBe(job.images[1].url + '?download=1');
  fireEvent(dialog, new Event('cancel', { bubbles: false, cancelable: true }));
  expect(screen.queryByRole('dialog')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Dùng lại mô tả' }));
  expect((screen.getByLabelText('Bức ảnh bạn muốn tạo') as HTMLTextAreaElement).value).toBe(job.prompt);
  expect(screen.getByRole('button', { name: 'Chi tiết' }).getAttribute('aria-pressed')).toBe('true');
  expect(api.createImagineJob).not.toHaveBeenCalled();
});

it('returns to login when the image request is unauthorized', async () => {
  vi.mocked(api.createImagineJob).mockRejectedValue(new api.UnauthorizedError());
  await open();
  fireEvent.change(screen.getByLabelText('Bức ảnh bạn muốn tạo'), { target: { value: job.prompt } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  await waitFor(() => expect(props.onUnauthorized).toHaveBeenCalledTimes(1));
});

it('xem trước ảnh đính kèm, giữ ảnh khi lỗi rồi gửi lại đúng nội dung', async () => {
  vi.mocked(api.createImagineJob).mockRejectedValueOnce(new Error('Peto đang bận.')).mockResolvedValue(editedJob);
  await open();
  fireEvent.change(screen.getByLabelText('Chọn ảnh để sửa'), { target: { files: [sourceFile()] } });
  const preview = await screen.findByRole('img', { name: 'Ảnh gốc để chỉnh sửa' });
  expect(preview.getAttribute('src')).toBe('data:image/png;base64,' + png);
  expect(api.createImagineJob).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Bạn muốn sửa gì trong ảnh?'), { target: { value: 'Thêm mũ tím' } });
  fireEvent.click(screen.getByRole('button', { name: 'Sửa ảnh', exact: true }));
  await screen.findByText('Peto đang bận.');
  expect(screen.getByRole('img', { name: 'Ảnh gốc để chỉnh sửa' })).toBe(preview);
  expect((screen.getByLabelText('Bạn muốn sửa gì trong ảnh?') as HTMLTextAreaElement).value).toBe('Thêm mũ tím');
  fireEvent.click(screen.getByRole('button', { name: 'Sửa ảnh', exact: true }));
  await screen.findByText('Đã chỉnh sửa');
  expect(api.createImagineJob).toHaveBeenLastCalledWith(expect.objectContaining({ prompt: 'Thêm mũ tím', source_image: { data: png } }));
  expect(vi.mocked(api.createImagineJob).mock.calls[1][0]).not.toHaveProperty('source_image_id');
  expect(screen.getAllByRole('button', { name: /Xem ảnh \d:/ })).toHaveLength(2);
});

it('gỡ ảnh trở về tạo ảnh mới, không gửi lại ảnh đã gỡ', async () => {
  await open();
  fireEvent.change(screen.getByLabelText('Chọn ảnh để sửa'), { target: { files: [sourceFile()] } });
  fireEvent.click(await screen.findByRole('button', { name: 'Gỡ ảnh gốc' }));
  fireEvent.change(screen.getByLabelText('Bức ảnh bạn muốn tạo'), { target: { value: 'Mèo trắng' } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  await screen.findByRole('button', { name: /Xem ảnh 1:/ });
  expect(vi.mocked(api.createImagineJob).mock.calls[0][0]).not.toHaveProperty('source_image');
  expect(vi.mocked(api.createImagineJob).mock.calls[0][0]).not.toHaveProperty('source_image_id');
});

it.each([
  [new File(['ghi chú'], 'ghi-chu.txt', { type: 'text/plain' })],
  [new File([new Uint8Array(8 * 1024 * 1024 + 1)], 'qua-lon.png', { type: 'image/png' })],
  [sourceFile(), sourceFile()],
])('từ chối tệp sai loại, quá lớn hoặc nhiều ảnh trước khi gọi dịch vụ: %#', async (...files) => {
  await open();
  fireEvent.change(screen.getByLabelText('Chọn ảnh để sửa'), { target: { files } });
  await screen.findByRole('alert');
  expect(screen.queryByRole('img', { name: 'Ảnh gốc để chỉnh sửa' })).toBeNull();
  expect(api.createImagineJob).not.toHaveBeenCalled();
});

it('sửa đúng ảnh đã chọn trong bộ ảnh mà không tải lên lần nữa', async () => {
  vi.mocked(api.listImagineJobs).mockResolvedValue([job]);
  vi.mocked(api.createImagineJob).mockResolvedValue({ ...editedJob, id: 'edited-2' });
  await open();
  fireEvent.click(screen.getByRole('button', { name: /Xem ảnh 2:/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Sửa ảnh này' }));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.getByRole('img', { name: 'Ảnh gốc để chỉnh sửa' }).getAttribute('src')).toBe(job.images[1].url);
  expect(document.activeElement).toBe(screen.getByLabelText('Bạn muốn sửa gì trong ảnh?'));
  fireEvent.change(screen.getByLabelText('Bạn muốn sửa gì trong ảnh?'), { target: { value: 'Đổi nền' } });
  fireEvent.click(screen.getByRole('button', { name: 'Sửa ảnh', exact: true }));
  await screen.findByText('Đã chỉnh sửa');
  expect(api.createImagineJob).toHaveBeenCalledWith(expect.objectContaining({ source_image_id: 'img-2', aspect_ratio: 'auto' }));
  expect(vi.mocked(api.createImagineJob).mock.calls[0][0]).not.toHaveProperty('source_image');
});

it('xem và dùng lại đúng ảnh gốc của lượt sửa', async () => {
  vi.mocked(api.listImagineJobs).mockResolvedValue([editedJob]);
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Xem ảnh gốc' }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByRole('img').getAttribute('src')).toBe(editedJob.source_image!.url);
  expect(within(dialog).queryByRole('button', { name: 'Sau →' })).toBeNull();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Đóng ảnh' }));
  fireEvent.click(screen.getByRole('button', { name: 'Dùng lại mô tả' }));
  expect((screen.getByLabelText('Bạn muốn sửa gì trong ảnh?') as HTMLTextAreaElement).value).toBe(job.prompt);
  fireEvent.click(screen.getByRole('button', { name: 'Sửa ảnh', exact: true }));
  await waitFor(() => expect(api.createImagineJob).toHaveBeenCalledWith(expect.objectContaining({ source_image_id: 'source-1' })));
});

it('nhận ảnh kéo thả và ảnh dán vào ô nhập', async () => {
  await open();
  const form = screen.getByLabelText('Bức ảnh bạn muốn tạo').closest('form')!;
  fireEvent.drop(form, { dataTransfer: { files: [sourceFile()] } });
  fireEvent.click(await screen.findByRole('button', { name: 'Gỡ ảnh gốc' }));
  fireEvent.paste(screen.getByLabelText('Bức ảnh bạn muốn tạo'), { clipboardData: { files: [sourceFile()] } });
  await screen.findByRole('button', { name: 'Gỡ ảnh gốc' });
  expect(api.createImagineJob).not.toHaveBeenCalled();
});

it('menu tỉ lệ mở ở mục đang chọn, đi bằng phím, Escape trả về nút, chạm ngoài thì đóng', async () => {
  const request = deferred<api.ImagineJob>();
  vi.mocked(api.createImagineJob).mockReturnValue(request.promise);
  await open();
  const ratio = screen.getByRole('button', { name: 'Tỉ lệ: Tự động' });
  fireEvent.click(ratio);
  expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: 'Tự động' }));
  // Hai cột: mũi tên xuống nhảy cả hàng.
  fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' });
  expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: '16:9' }));
  fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
  expect(screen.queryByRole('menu')).toBeNull();
  expect(document.activeElement).toBe(ratio);
  fireEvent.click(ratio);
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole('menu')).toBeNull();
  fireEvent.change(screen.getByLabelText('Bức ảnh bạn muốn tạo'), { target: { value: job.prompt } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  expect((screen.getByRole('button', { name: 'Tỉ lệ: Tự động' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button', { name: 'Số ảnh: 1 ảnh' }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => request.resolve(job));
});

it('điện thoại: thanh thu gọn mở khi bấm vào ô nhập hoặc nút tùy chọn, chạm ra ngoài thì thu lại', async () => {
  stubPhone();
  render(<Imagine {...props} />);
  await waitFor(() => expect(screen.queryByText('Đang mở bộ ảnh của bạn…')).toBeNull());
  const dock = document.querySelector('.studio-dock')!;
  const input = screen.getByLabelText('Bức ảnh bạn muốn tạo') as HTMLTextAreaElement;
  expect(dock.classList.contains('expanded')).toBe(false);
  expect(input.placeholder).toBe('Gõ để tưởng tượng');
  act(() => { input.focus(); });
  expect(dock.classList.contains('expanded')).toBe(true);
  expect(input.placeholder).toBe('Nhập để tạo hình ảnh');
  // Chạm vào bộ ảnh: thanh thu lại và bàn phím ẩn theo.
  fireEvent.pointerDown(document.body);
  expect(dock.classList.contains('expanded')).toBe(false);
  expect(document.activeElement).not.toBe(input);
  fireEvent.click(screen.getByRole('button', { name: 'Mở tùy chọn tạo ảnh' }));
  expect(dock.classList.contains('expanded')).toBe(true);
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Nhanh', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Mở thư viện ảnh' }));
  expect(screen.getByRole('dialog', { name: 'Thư viện ảnh' })).toBeTruthy();
});

it('xóa từng ảnh trong thư viện: lượt còn ảnh thì ở lại, xóa ảnh cuối thì lượt biến mất', async () => {
  vi.mocked(api.listImagineJobs).mockResolvedValue([job]);
  vi.mocked(api.deleteImagineImage).mockResolvedValueOnce({ job_deleted: false }).mockResolvedValueOnce({ job_deleted: true });
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Mở thư viện ảnh' }));
  const library = screen.getByRole('dialog', { name: 'Thư viện ảnh' });
  const removeFirstTile = async () => {
    fireEvent.click(within(library).getByRole('button', { name: 'Chọn' }));
    fireEvent.click(within(library).getAllByRole('button', { name: /^Chọn ảnh: / })[0]);
    fireEvent.click(within(library).getByRole('button', { name: 'Xóa' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Xóa ảnh này?' })).getByRole('button', { name: 'Xóa ảnh' }));
    await within(library).findByRole('button', { name: 'Chọn' });
  };

  await removeFirstTile();
  expect(api.deleteImagineImage).toHaveBeenLastCalledWith('img-1');
  expect(document.querySelectorAll('.imagine-job')).toHaveLength(1);
  expect(screen.getAllByRole('button', { name: /^Xem ảnh \d: / })).toHaveLength(1);
  expect(within(library).getAllByRole('button', { name: /^Xem ảnh: / })).toHaveLength(1);

  await removeFirstTile();
  expect(api.deleteImagineImage).toHaveBeenLastCalledWith('img-2');
  expect(document.querySelectorAll('.imagine-job')).toHaveLength(0);
  expect(within(library).getByText('Chưa có ảnh nào. Ảnh bạn tạo sẽ hiện ở đây.')).toBeTruthy();
});

it('nút thư viện hiện ảnh mới nhất; nút thích trong khung xem ảnh lưu lên máy chủ, lỗi thì trả lại', async () => {
  vi.mocked(api.listImagineJobs).mockResolvedValue([job]);
  vi.mocked(api.setImagineImageLiked).mockRejectedValueOnce(new Error('Chưa lưu được, thử lại nhé.'));
  await open();
  expect(screen.getByRole('button', { name: 'Mở thư viện ảnh' }).querySelector('img')!.getAttribute('src')).toBe(job.images[0].url);
  fireEvent.click(screen.getByRole('button', { name: /Xem ảnh 2:/ }));
  const dialog = screen.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  const like = () => within(dialog).getByRole('button', { name: 'Thích' });
  expect(like().getAttribute('aria-pressed')).toBe('false');
  fireEvent.click(like());
  expect(like().getAttribute('aria-pressed')).toBe('true');
  expect((await within(dialog).findByRole('alert')).textContent).toContain('Chưa lưu được');
  expect(like().getAttribute('aria-pressed')).toBe('false');
  fireEvent.click(like());
  await waitFor(() => expect(api.setImagineImageLiked).toHaveBeenLastCalledWith('img-2', true));
  expect(like().getAttribute('aria-pressed')).toBe('true');
  expect(within(dialog).queryByRole('alert')).toBeNull();
});

it('điện thoại: bấm tạo ảnh thì thanh thu lại, ô nhập bỏ focus và vẫn giữ mô tả', async () => {
  stubPhone();
  const request = deferred<api.ImagineJob>();
  vi.mocked(api.createImagineJob).mockReturnValue(request.promise);
  await open();
  const input = screen.getByLabelText('Bức ảnh bạn muốn tạo') as HTMLTextAreaElement;
  act(() => { input.focus(); });
  fireEvent.change(input, { target: { value: job.prompt } });
  fireEvent.click(screen.getByRole('button', { name: 'Tạo ảnh', exact: true }));
  expect(document.querySelector('.studio-dock')!.classList.contains('expanded')).toBe(false);
  expect(document.activeElement).not.toBe(input);
  await act(async () => request.resolve(job));
  expect(document.activeElement).not.toBe(input);
  expect(input.value).toBe(job.prompt);
});
