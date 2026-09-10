import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import Imagine from '../src/Imagine';
import * as api from '../src/api';

vi.mock('../src/api', async (original) => ({
  ...await original<typeof import('../src/api')>(),
  listImagineJobs: vi.fn(), createImagineJob: vi.fn(), deleteImagineJob: vi.fn(),
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
});
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
  fireEvent.change(screen.getByLabelText('Tỉ lệ'), { target: { value: '16:9' } });
  fireEvent.change(screen.getByLabelText('Số ảnh'), { target: { value: '2' } });
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
