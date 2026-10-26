import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import WebSources from '../src/features/chat/WebSources';
import SourcesPanel from '../src/features/chat/SourcesPanel';
import { faviconUrl, SourceIcon } from '../src/features/chat/SourceIcon';
import { normalizeWeb, type WebActivity } from '../src/features/chat/sourceActivity';
import type { WebSource } from '../src/shared/api/api';

const a = { url: 'https://example.com/a', title: 'Trang A', snippet: 'Đây là một đoạn trích từ kết quả thực.' };
const b = { url: 'https://example.org/b', title: 'Trang B' };
function activity(): WebActivity {
  return normalizeWeb({ version: 1, sources: [a, b], calls: [
    { id: 'xai:1:web-1', kind: 'search', queries: ['màn hình gaming giá 2 triệu'], state: 'done', source_urls: [a.url] },
    { id: 'xai:1:web-2', kind: 'search', queries: ['màn hình IPS'], state: 'done', source_urls: [a.url, b.url] },
  ] })!;
}
function Harness({ sources = [], web }: { sources?: WebSource[]; web?: WebActivity }) {
  const [open, setOpen] = useState(false);
  return <><WebSources sources={sources} web={web} expanded={open} onOpen={() => setOpen(value => !value)} />
    {open && <SourcesPanel sources={sources} web={web} onClose={() => setOpen(false)} />}</>;
}

it('nút gọn có favicon, nguồn không bung vào câu trả lời; đóng trả focus về nút nguồn', () => {
  render(<Harness sources={[a, a, b, { url: 'javascript:alert(1)', title: 'Unsafe' }]} />);
  const button = screen.getByRole('button', { name: 'Mở 2 nguồn tham khảo' });
  expect(button.getAttribute('aria-expanded')).toBe('false');
  expect(button.querySelectorAll('.source-favicon')).toHaveLength(2);
  expect(screen.queryByRole('link')).toBeNull();
  button.focus(); fireEvent.click(button);
  const panel = screen.getByRole('complementary', { name: 'Nguồn tham khảo' });
  expect(within(panel).getAllByRole('link')).toHaveLength(2);
  expect(button.getAttribute('aria-controls')).toBe(panel.id);
  expect(screen.queryByText('Unsafe')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Đóng bảng nguồn' }));
  expect(screen.queryByRole('complementary')).toBeNull();
  expect(document.activeElement).toBe(button);
});

it('nhóm query đóng mặc định, bấm mới hiện nguồn và giữ nguồn chung trong hai nhóm', () => {
  render(<Harness web={activity()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Mở 2 nguồn tham khảo' }));
  const first = screen.getByRole('button', { name: /màn hình gaming giá 2 triệu/ });
  const second = screen.getByRole('button', { name: /màn hình IPS/ });
  expect(first.getAttribute('aria-expanded')).toBe('false');
  expect(screen.queryByRole('link')).toBeNull();
  fireEvent.click(first);
  expect(first.getAttribute('aria-expanded')).toBe('true');
  expect(screen.getByRole('link', { name: /Trang A/ }).getAttribute('href')).toBe(a.url);
  expect(screen.getByText(a.snippet)).toBeTruthy();
  fireEvent.click(second);
  expect(screen.getAllByRole('link', { name: /Trang A/ })).toHaveLength(2);
  expect(screen.getByRole('link', { name: /Trang B/ })).toBeTruthy();
});

it('metadata đến muộn giữ nguyên nhóm đang mở và vị trí cuộn', () => {
  const initial = activity();
  initial.calls[0].state = 'live';
  const { rerender } = render(<SourcesPanel web={initial} onClose={() => {}} />);
  const query = screen.getByRole('button', { name: /màn hình gaming giá 2 triệu/ });
  fireEvent.click(query);
  const scroll = screen.getByRole('region', { name: 'Danh sách nguồn' });
  scroll.scrollTop = 40;
  const next = activity();
  next.sources.push({ url: 'https://example.net/c', title: 'Trang C' });
  next.calls[0].source_urls.push('https://example.net/c');
  rerender(<SourcesPanel web={next} onClose={() => {}} />);
  expect(query.getAttribute('aria-expanded')).toBe('true');
  expect(screen.getByRole('link', { name: /Trang C/ })).toBeTruthy();
  expect(scroll.scrollTop).toBe(40);
});

it('query thiếu chỉ dùng nhãn chung; page call và lỗi có trạng thái riêng', () => {
  const web = normalizeWeb({ version: 1, sources: [a], calls: [
    { id: 'web-1', kind: 'search', queries: [], state: 'failed', source_urls: [] },
    { id: 'page-1', kind: 'page', operation: 'fetch', url: a.url, queries: [], state: 'done', source_urls: [a.url] },
  ] })!;
  render(<SourcesPanel web={web} onClose={() => {}} />);
  const failed = screen.getByRole('button', { name: /Tìm kiếm bị lỗi: Lượt tra cứu/ });
  fireEvent.click(failed);
  expect(screen.getByText('Lượt này chưa có nguồn dùng được.')).toBeTruthy();
  expect(screen.getByRole('button', { name: /Đã mở trang: example.com/ })).toBeTruthy();
  expect(screen.queryByRole('button', { name: /Trang A/ })).toBeNull();
});

it('nguồn cũ vẫn giữ mức bằng chứng và lọc liên kết không an toàn', () => {
  render(<SourcesPanel sources={[
    { ...a, kind: 'citation', access: 'search' },
    { ...b, kind: 'result', access: 'page' },
    { url: 'https://github.com/test/repo', title: 'Repo', kind: 'result', access: 'tool', partial: true },
    { url: 'data:text/html,x', title: 'Unsafe' },
  ]} onClose={() => {}} />);
  expect(screen.getByText('Trang A').closest('a')?.textContent).toContain('Kết quả tìm kiếm');
  expect(screen.getByText('Trang B').closest('section')?.querySelector('h3')?.textContent).toContain('Trang đã mở');
  expect(screen.getByText('Repo').closest('a')?.textContent).toContain('Công cụ · một phần');
  expect(screen.queryByText('Unsafe')).toBeNull();
});

it('không lặp mức bằng chứng trên từng card khi tiêu đề nhóm đã nói rõ', () => {
  const { container } = render(<SourcesPanel sources={[
    { ...a, kind: 'result', access: 'search' },
    { ...b, kind: 'result', access: 'search' },
  ]} onClose={() => {}} />);
  expect(screen.getByRole('heading', { name: /Kết quả tìm kiếm/ })).toBeTruthy();
  expect(container.querySelectorAll('.web-source-evidence')).toHaveLength(0);
});

it.each(['done', 'failed', 'stopped'] as const)('không báo đang tra mãi khi lượt %s không có nguồn', state => {
  const web: WebActivity = { version: 1, sources: [], calls: [
    { id: 'xai:1:empty', kind: 'search', queries: [], state: 'live', source_urls: [] },
  ] };
  const { rerender } = render(<WebSources web={web} />);
  expect(screen.getByRole('button', { name: 'Mở chi tiết tra cứu' }).textContent).toBe('Đang tra cứu');
  rerender(<WebSources web={{ ...web, calls: [{ ...web.calls[0], state }] }} />);
  expect(screen.getByRole('button', { name: 'Mở chi tiết tra cứu' }).textContent).toBe('Tra cứu');
});

it('title/query chỉ là text React, không thực thi HTML và nguồn vẫn mở an toàn', () => {
  const web = normalizeWeb({ version: 1, sources: [{ ...a, title: '<img src=x onerror=alert(1)>' }], calls: [
    { id: 'web-1', kind: 'search', queries: ['<script>evil()</script>'], state: 'done', source_urls: [a.url] },
  ] })!;
  const { container } = render(<SourcesPanel web={web} onClose={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: /<script>evil\(\)<\/script>/ }));
  const link = screen.getByText('<img src=x onerror=alert(1)>').closest('a')!;
  expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  expect(container.querySelector('script, img[src="x"], img[onerror]')).toBeNull();
});

it('nhận diện logo theo hostname thật và favicon chỉ gửi domain, không path/query/referrer', () => {
  expect(faviconUrl('https://www.example.com/private?token=secret#person')).toBe('https://www.google.com/s2/favicons?domain=example.com&sz=32');
  for (const url of ['http://localhost/a', 'http://127.0.0.1/a', 'http://[::1]/a', 'http://portal.local/a', 'http://files.internal/a', 'javascript:alert(1)']) expect(faviconUrl(url)).toBeUndefined();
  const { container, rerender } = render(<SourceIcon url="https://youtube.com.example.org/watch" />);
  expect(container.querySelector('.youtube-icon')).toBeNull();
  const image = container.querySelector('img')!;
  expect(image.getAttribute('referrerpolicy')).toBe('no-referrer');
  fireEvent.error(image);
  expect(container.querySelector('img')).toBeNull();
  expect(container.querySelector('svg')).toBeTruthy();
  rerender(<SourceIcon url="https://m.youtube.com/watch?v=abc" />);
  expect(container.querySelector('.youtube-icon')).toBeTruthy();
  rerender(<SourceIcon url="https://gist.github.com/user/abc" />);
  expect(container.querySelector('.github-icon')).toBeTruthy();
});

it('sheet điện thoại giữ Tab trong bảng, Escape đóng và trả focus', () => {
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  try {
    render(<Harness web={activity()} />);
    const trigger = screen.getByRole('button', { name: /Mở 2 nguồn/ });
    trigger.focus(); fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Nguồn tham khảo' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    const close = screen.getByRole('button', { name: 'Đóng bảng nguồn' });
    close.focus(); fireEvent.keyDown(close, { key: 'Tab', shiftKey: true });
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).toBe(screen.getByRole('button', { name: /màn hình IPS/ }));
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  } finally { vi.unstubAllGlobals(); }
});

it('chỉ cảnh báo giới hạn khi envelope bị cắt, không thêm hướng dẫn dài mặc định', () => {
  const { rerender } = render(<SourcesPanel web={activity()} onClose={() => {}} />);
  expect(screen.queryByText(/giới hạn của lượt này/)).toBeNull();
  rerender(<SourcesPanel web={{ ...activity(), truncated: true }} onClose={() => {}} />);
  expect(screen.getByText(/giới hạn của lượt này/)).toBeTruthy();
});
