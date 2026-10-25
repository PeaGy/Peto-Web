import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { ChatMessage } from '../src/features/chat/ChatMessage';
import { citationIndex, safeSources } from '../src/features/chat/sourceData';
import type { Message, WebSource } from '../src/shared/api/api';

const sources: WebSource[] = [
  { url: 'https://example.com/b', title: 'Nguồn B', citation_ids: ['web:26'], kind: 'citation' },
  { url: 'https://example.com/a', title: 'Nguồn A', citation_ids: ['web:21'], kind: 'citation' },
];
function view(content: string, items = sources, writing = false, role: Message['role'] = 'assistant') {
  return <ChatMessage message={{ role, content, sources: items }} live={writing} writing={writing} onPreview={() => {}} onEdit={() => {}} />;
}

it('ánh xạ bằng ID, nhóm citation cạnh nhau và giữ danh sách nguồn mở rộng', () => {
  const { container } = render(view('Còn liên lạc. [web:21] [web:26] [web:21]'));
  expect(container.querySelectorAll('.citation-group')).toHaveLength(1);
  expect(container.querySelectorAll('.citation-badge')).toHaveLength(2);
  const link = screen.getByRole('link', { name: 'Nguồn 21: Nguồn A' });
  expect(link.getAttribute('href')).toBe('https://example.com/a');
  expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  expect(link.getAttribute('data-tip')).toContain('Nguồn A\nhttps://example.com/a');
  expect(container.textContent).not.toContain('[web:');
  const footer = screen.getByText('Nguồn · 2').closest('details')!;
  expect(footer.open).toBe(false);
  expect(within(footer).getAllByRole('link', { hidden: true })).toHaveLength(2);
});

it('mọi điểm chia chunk đều giữ marker kín; metadata về muộn cập nhật đúng nguồn', () => {
  const text = 'Đã xác minh [web:21]';
  const { container, rerender } = render(view('', [], true));
  for (let end = 1; end <= text.length; end++) {
    rerender(view(text.slice(0, end), [], true));
    const visible = container.textContent ?? '';
    expect(visible).not.toMatch(/\[(?:w|we|web|web:|web:[0-9]+)\]?$/);
  }
  expect(container.querySelector('.citation-unavailable')?.textContent).toBe('…');
  rerender(view(text, sources, true));
  expect(screen.getByRole('link', { name: 'Nguồn 21: Nguồn A' })).toBeTruthy();
  rerender(view(text));
  expect(container.querySelector('.citation-unavailable')).toBeNull();
});

it('nguồn thiếu, marker sai, ID trùng URL khác và lượt bị ngắt không bịa liên kết', () => {
  const conflict = [...sources, { url: 'https://other.example/a', title: 'Conflicting', citation_ids: ['web:21'] }];
  const { container, rerender } = render(view('A [web:21] B [web:999] C [web:abc]', conflict));
  expect(container.querySelectorAll('.citation-unavailable')).toHaveLength(3);
  expect(container.querySelectorAll('a.citation-badge')).toHaveLength(0);
  expect(container.textContent).not.toContain('[web:');
  rerender(view('Đã dừng [web:2', []));
  expect(container.textContent).not.toContain('[web:');
  expect(container.querySelector('.citation-unavailable')).toBeTruthy();
});

it('marker sai ID cũng được giữ kín trong lúc đang nhận từng ký tự', () => {
  const text = 'Nguồn [web:abc]';
  const { container, rerender } = render(view('', [], true));
  for (let end = text.indexOf('[') + 1; end <= text.length; end++) {
    rerender(view(text.slice(0, end), [], true));
    expect(container.textContent).not.toContain('[');
  }
  rerender(view(text, []));
  expect(container.querySelector('.citation-unavailable')?.textContent).toBe('?');
});

it('tải lại dữ liệu cũ không có ID vẫn hiện nguồn và không đoán số trong mảng', () => {
  const { container } = render(view('Theo nguồn [web:1]', [{ url: sources[0].url, title: 'Legacy' }]));
  expect(container.querySelector('a.citation-badge')).toBeNull();
  expect(screen.getByText('Legacy')).toBeTruthy();
  expect(container.querySelector('.citation-unavailable')).toBeTruthy();
});

it('giữ nguyên code, inline code, link label và nội dung người dùng', () => {
  const text = '`[web:21]`\n\n```txt\n[web:26]\n```\n\n[nhãn [web:21]](https://example.com)';
  const { container, rerender } = render(view(text));
  expect(container.querySelectorAll('.citation-badge')).toHaveLength(0);
  expect(container.querySelector('code')?.textContent).toBe('[web:21]');
  rerender(view('Tôi gõ [web:21]', sources, false, 'user'));
  expect(container.textContent).toContain('[web:21]');
});

it('nhận native Markdown citation và marker OpenAI có ánh xạ rõ', () => {
  const native = [{ ...sources[0], citation_ids: ['turn0search0'] }];
  const { container, rerender } = render(view('Tin mới citeturn0search0', native));
  expect(container.querySelector('a.citation-badge')?.getAttribute('href')).toBe(sources[0].url);
  expect(container.textContent).not.toContain('');
  rerender(view('Theo nguồn [[2]](https://example.com/b) [[3]](https://example.com/a)'));
  expect(container.querySelectorAll('a.citation-badge')).toHaveLength(2);
  expect(container.querySelectorAll('.citation-group')).toHaveLength(1);
});

it('không lộ native Markdown citation đang nhận từng ký tự', () => {
  const native = 'Kết quả [[2]](https://example.com/b)';
  const { container, rerender } = render(view('', sources, true));
  for (let end = native.indexOf('[[') + 1; end < native.length; end++) {
    rerender(view(native.slice(0, end), sources, true));
    expect(container.textContent).not.toContain('[[');
    expect(container.textContent).not.toContain('https://example.com/b');
  }
  rerender(view(native));
  expect(container.querySelector('a.citation-badge')).toBeTruthy();
});

it('lọc URL/metadata độc hại, escape tiêu đề và bảo toàn alias khi gộp URL', () => {
  const unsafe = ['javascript:alert(1)', 'data:text/html,x', 'https://user:pw@example.com', 'https://example.com/\n', 'https://example.com/\\bad'];
  const items = safeSources([
    ...unsafe.map(url => ({ url, title: 'Unsafe', citation_ids: ['web:1'] })),
    { ...sources[0], title: '<img src=x onerror=alert(1)>' },
    { ...sources[0], citation_ids: ['web:22', 'javascript:alert(1)'] },
  ]);
  expect(items).toHaveLength(1);
  expect(items[0].citation_ids).toEqual(['web:26', 'web:22']);
  expect(citationIndex(items).get('web:22')?.url).toBe(sources[0].url);
  const { container } = render(view('Nguồn [web:22]', items));
  expect(container.querySelector('img')).toBeNull();
  expect(container.querySelector('script')).toBeNull();
  expect(container.querySelector('a.citation-badge')?.getAttribute('data-tip')).toContain('<img');
});

it('nhóm citation rất dài vẫn bị chặn số badge và không rò marker', () => {
  const { container } = render(view(Array.from({ length: 400 }, (_, n) => `[web:${n}]`).join(' '), []));
  expect(container.querySelectorAll('.citation-badge')).toHaveLength(128);
  expect(container.textContent).not.toContain('[web:');
});
