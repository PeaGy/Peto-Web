import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import MeasuredImage from '../src/features/imagine/MeasuredImage';

function load(width: number, height: number) {
  const image = screen.getByRole('img', { name: 'Ảnh đang xem' });
  Object.defineProperties(image, { naturalWidth: { value: width }, naturalHeight: { value: height } });
  fireEvent.load(image);
}

it('chỉ đo từ ảnh đã tải và không giữ kích thước ảnh trước khi đổi nguồn', () => {
  const view = render(<MeasuredImage src="/anh-1.png" alt="Ảnh đang xem" />);
  expect(screen.queryByLabelText('Kích thước ảnh thực tế')).toBeNull();
  load(1536, 1024);
  expect(screen.getByLabelText('Kích thước ảnh thực tế').textContent).toBe('1536 × 1024 · 3:2');
  view.rerender(<MeasuredImage src="/anh-2.png" alt="Ảnh đang xem" />);
  expect(screen.queryByLabelText('Kích thước ảnh thực tế')).toBeNull();
  load(1080, 1920);
  expect(screen.getByLabelText('Kích thước ảnh thực tế').textContent).toBe('1080 × 1920 · 9:16');
  fireEvent.error(screen.getByRole('img'));
  expect(screen.queryByLabelText('Kích thước ảnh thực tế')).toBeNull();
});
