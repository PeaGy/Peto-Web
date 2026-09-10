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
