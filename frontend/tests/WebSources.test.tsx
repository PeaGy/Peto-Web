import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import WebSources from '../src/features/chat/WebSources';

it('phân biệt trích dẫn, kết quả tìm kiếm và dữ liệu cũ', () => {
  render(<WebSources sources={[
    { url: 'https://example.com/cited', title: 'Cited', kind: 'citation' },
    { url: 'https://example.com/result', title: 'Result', kind: 'result' },
    { url: 'https://example.com/old', title: 'Old' },
    { url: 'javascript:alert(1)', title: 'Unsafe', kind: 'citation' },
  ]} />);
  const panel = screen.getByText('Nguồn · 1').closest('details')!;
  expect(panel.open).toBe(false);
  expect(within(panel).getAllByRole('link', { hidden: true })).toHaveLength(3);
  const others = screen.getByText('Kết quả tìm kiếm khác · 1').closest('details')!;
  expect(others.open).toBe(false);
  expect(within(others).getAllByRole('link', { hidden: true })).toHaveLength(1);
  expect(within(others).getByText('Result')).toBeTruthy();
  expect(within(panel).getByText('Cited')).toBeTruthy();
  expect(within(panel).getByText('Old')).toBeTruthy();
  expect(screen.queryByText('Unsafe')).toBeNull();
});

it('nhận diện nguồn theo hostname thật kể cả link ngắn, không theo tiêu đề hoặc tên miền giả', () => {
  const { container } = render(<WebSources sources={[
    { url: 'https://www.youtube.com/watch?v=abc', title: 'Video' },
    { url: 'https://youtu.be/abc', title: 'Video ngắn' },
    { url: 'https://m.youtube.com/watch?v=abc', title: 'Video trên điện thoại' },
    { url: 'https://github.com/user/repo', title: 'Repo' },
    { url: 'https://gist.github.com/user/abc', title: 'Đoạn code' },
    { url: 'https://youtube.com.example.org/watch', title: 'YouTube' },
    { url: 'https://example.org/youtube.com', title: 'YouTube' },
  ]} />);
  for (const title of ['Video', 'Video ngắn', 'Video trên điện thoại']) {
    expect(screen.getByText(title).closest('a')!.querySelector('.youtube-icon')).toBeTruthy();
  }
  for (const title of ['Repo', 'Đoạn code']) {
    expect(screen.getByText(title).closest('a')!.querySelector('.github-icon')).toBeTruthy();
  }
  for (const title of screen.getAllByText('YouTube')) {
    expect(title.closest('a')!.querySelector('.youtube-icon')).toBeNull();
  }
  expect(container.querySelector('.web-sources > summary .youtube-icon')).toBeNull();
  expect(container.querySelector('img')).toBeNull();
});

it('nút nguồn hiện YouTube khi tất cả nguồn cùng từ YouTube', () => {
  const { container } = render(<WebSources sources={[
    { url: 'https://www.youtube.com/watch?v=abc', title: 'Video', kind: 'citation' },
    { url: 'https://youtu.be/def', title: 'Video khác', kind: 'citation' },
  ]} />);
  expect(container.querySelector('.web-sources > summary .youtube-icon')).toBeTruthy();
  expect(screen.getByText('Nguồn · 2')).toBeTruthy();
});
