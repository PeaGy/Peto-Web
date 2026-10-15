import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import GenerationPreview from '../src/features/imagine/GenerationPreview';

const props = { images: [], count: 2, aspect: 'auto', sourceUrl: '/source.png', pending: true, paused: false, prompt: 'Mô tả', status: 'Đang tạo ảnh…' };
const result = { id: 'result', mime: 'image/png', url: '/result.png' };
afterEach(() => vi.restoreAllMocks());

it('tỷ lệ Auto đọc từ ảnh chờ và giữ khung khi hoàn tất, không tải trước nguồn của lượt cũ', () => {
  const { container, rerender } = render(<GenerationPreview {...props} />);
  const source = container.querySelector<HTMLImageElement>('.generation-source')!;
  Object.defineProperties(source, { naturalWidth: { value: 1200 }, naturalHeight: { value: 1800 } });
  fireEvent.load(source);
  expect((container.firstChild as HTMLElement).style.getPropertyValue('--generation-ratio')).toBe(String(2 / 3));
  rerender(<GenerationPreview {...props} pending={false} images={[result]} />);
  expect(container.querySelector('.generation-source')).toBeNull();
  expect((container.firstChild as HTMLElement).style.getPropertyValue('--generation-ratio')).toBe(String(2 / 3));
  // Mở lại lịch sử không dựng ảnh tham chiếu ẩn hay gọi new Image để đo tỷ lệ.
  const probe = vi.spyOn(window, 'Image');
  render(<GenerationPreview {...props} pending={false} images={[result]} />);
  expect(probe).not.toHaveBeenCalled();
});

it('ảnh tham chiếu cực dài vẫn nằm trong khung xem hợp lý', () => {
  const { container } = render(<GenerationPreview {...props} />);
  const source = container.querySelector<HTMLImageElement>('.generation-source')!;
  Object.defineProperties(source, { naturalWidth: { value: 8000 }, naturalHeight: { value: 1 } });
  fireEvent.load(source);
  expect((container.firstChild as HTMLElement).style.getPropertyValue('--generation-ratio')).toBe('2.5');
});

it('ảnh chỉ hiện sau decode và bỏ kết quả decode cũ khi URL thay đổi', async () => {
  let finish!: () => void;
  const { container, rerender } = render(<GenerationPreview {...props} images={[result]} pending={false} />);
  const picture = container.querySelector<HTMLImageElement>('.generation-result img')!;
  Object.defineProperty(picture, 'naturalWidth', { value: 100 });
  picture.decode = () => new Promise<void>(resolve => { finish = resolve; });
  fireEvent.load(picture);
  expect(container.querySelector('.generation-tile')?.getAttribute('data-ready')).toBe('false');
  rerender(<GenerationPreview {...props} images={[{ ...result, url: '/new.png' }]} pending={false} />);
  await act(async () => finish());
  expect(container.querySelector('.generation-tile')?.getAttribute('data-ready')).toBe('false');
  picture.decode = vi.fn().mockResolvedValue(undefined);
  fireEvent.load(picture);
  await waitFor(() => expect(container.querySelector('.generation-tile')?.getAttribute('data-ready')).toBe('true'));
});

it('nút tải lại chỉ thay ảnh bị lỗi và không mở trình xem ngoài ý muốn', () => {
  const open = vi.fn();
  const { container } = render(<GenerationPreview {...props} images={[result]} pending={false} onOpen={open} />);
  const picture = container.querySelector<HTMLImageElement>('.generation-result img')!;
  fireEvent.error(picture);
  fireEvent.click(screen.getByRole('button', { name: 'Tải lại ảnh' }));
  expect(container.querySelector('.generation-result img')).not.toBe(picture);
  expect(open).not.toHaveBeenCalled();
});
