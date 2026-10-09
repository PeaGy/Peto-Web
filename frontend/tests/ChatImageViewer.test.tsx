import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import MessageAttachments from '../src/features/chat/MessageAttachments';
import type { ChatAttachment } from '../src/shared/api/api';

const images: ChatAttachment[] = [0, 1].map(i => ({ id: `image-${i}`, name: `Ảnh-${i}.png`, mime: 'image/png', kind: 'image', size: 4096, url: `/api/attachments/image-${i}` }));

function loadImage() {
  const dialog = screen.getByRole('dialog', { name: 'Xem ảnh đính kèm' });
  const stage = dialog.querySelector('.chat-image-stage')!;
  Object.defineProperties(stage, { clientWidth: { configurable: true, value: 832 }, clientHeight: { configurable: true, value: 632 } });
  fireEvent(window, new Event('resize'));
  const image = within(dialog).getByRole('img', { hidden: true });
  Object.defineProperties(image, { naturalWidth: { configurable: true, value: 1600 }, naturalHeight: { configurable: true, value: 1200 } });
  fireEvent.load(image);
  return dialog;
}

describe('khung xem ảnh Chat', () => {
  it('mở tại chỗ, giữ URL/history, đóng bằng nút và trả focus về thumbnail', () => {
    render(<MessageAttachments attachments={images} sent />);
    const thumbnail = screen.getByRole('link', { name: images[0].name });
    thumbnail.focus();
    const url = window.location.href, length = history.length;
    fireEvent.click(thumbnail);
    const dialog = loadImage();
    expect(window.location.href).toBe(url);
    expect(history.length).toBe(length);
    expect(document.activeElement).toBe(within(dialog).getByRole('button', { name: 'Đóng ảnh' }));
    const download = within(dialog).getByRole('link', { name: 'Tải ảnh xuống' });
    expect(download.getAttribute('href')).toBe(images[0].url);
    expect(download.getAttribute('download')).toBe(images[0].name);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Đóng ảnh' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(thumbnail);
  });
  it('đổi mức phóng, vừa khung và đổi ảnh bằng bàn phím mà không đóng modal', () => {
    render(<MessageAttachments attachments={images} sent />);
    fireEvent.click(screen.getByRole('link', { name: images[0].name }));
    const dialog = loadImage();
    const zoom = within(dialog).getByRole('combobox', { name: 'Mức phóng ảnh' }) as HTMLSelectElement;
    expect(zoom.value).toBe('fit');
    fireEvent.change(zoom, { target: { value: '2' } });
    expect(within(dialog).getByRole('img').style.transform).toContain('scale(2)');
    fireEvent.change(zoom, { target: { value: 'fit' } });
    expect(within(dialog).getByRole('img').style.transform).toContain('scale(0.5)');
    fireEvent.keyDown(dialog, { key: 'ArrowRight' });
    loadImage();
    expect(screen.getByRole('dialog')).toBe(dialog);
    expect(within(dialog).getByRole('img').getAttribute('alt')).toBe(images[1].name);
    expect((within(dialog).getByRole('button', { name: 'Ảnh tiếp theo' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent(dialog, new Event('cancel', { bubbles: false, cancelable: true }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
  it('URL tạm chuyển sang URL đã lưu vẫn giữ khung xem và mức zoom', () => {
    const { rerender } = render(<MessageAttachments attachments={images} sent />);
    fireEvent.click(screen.getByRole('link', { name: images[0].name }));
    const dialog = loadImage();
    fireEvent.change(within(dialog).getByRole('combobox'), { target: { value: '2' } });
    rerender(<MessageAttachments attachments={images.map(image => ({ ...image, id: `${image.id}-stored`, url: `${image.url}-stored` }))} sent />);
    expect(screen.getByRole('dialog')).toBe(dialog);
    expect(within(dialog).getByRole('img').getAttribute('src')).toBe(`${images[0].url}-stored`);
    expect(within(dialog).getByRole('img').style.transform).toContain('scale(2)');
  });
  it('ảnh lỗi tải vẫn đóng được và có nút thử lại', () => {
    render(<MessageAttachments attachments={images} sent />);
    fireEvent.click(screen.getByRole('link', { name: images[0].name }));
    const dialog = screen.getByRole('dialog');
    fireEvent.error(within(dialog).getByRole('img', { hidden: true }));
    expect(within(dialog).getByRole('status').textContent).toContain('Không tải được ảnh.');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Thử lại' }));
    expect(within(dialog).getByRole('status').textContent).toBe('Đang tải ảnh…');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Đóng ảnh' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
