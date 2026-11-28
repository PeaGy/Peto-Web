import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ChatMessage } from '../src/features/chat/ChatMessage';
import { opensDisclosure } from '../src/features/chat/disclosure';
import type { WebSource } from '../src/shared/api/api';

// Ba điểm lấy từ assistant-ui (28/11/2026): ngừng bám đáy khi mở một mục trong tin nhắn, aria-busy cho câu trả lời
// đang chạy, và link mở thẻ mới có mô tả cho trình đọc màn hình.

describe('opensDisclosure', () => {
  const article = (html: string) => {
    const root = document.createElement('div');
    root.innerHTML = `<article>${html}</article><div class="outside"><button aria-expanded="false">Ngoài</button></div>`;
    document.body.append(root);
    return root;
  };

  it('nút đang đóng và summary của details đang đóng trong tin nhắn là mở một mục', () => {
    const root = article(`<button class="a" aria-expanded="false"><span class="inner">Đang làm</span></button>
      <button class="b" aria-expanded="true">Thu gọn</button>
      <details><summary class="c">Tóm tắt</summary></details><details open><summary class="d">Đã mở</summary></details>`);
    expect(opensDisclosure(root.querySelector('.inner'))).toBe(true);
    expect(opensDisclosure(root.querySelector('.b'))).toBe(false);
    expect(opensDisclosure(root.querySelector('.c'))).toBe(true);
    expect(opensDisclosure(root.querySelector('.d'))).toBe(false);
    root.remove();
  });

  it('nút mở menu, ô chọn, ô nhập và nút ngoài tin nhắn thì không', () => {
    const root = article(`<button class="menu" aria-expanded="false" aria-haspopup="menu">⋯</button>
      <input class="combo" role="combobox" aria-expanded="false" /><textarea class="text"></textarea>`);
    expect(opensDisclosure(root.querySelector('.menu'))).toBe(false);
    expect(opensDisclosure(root.querySelector('.combo'))).toBe(false);
    expect(opensDisclosure(root.querySelector('.text'))).toBe(false);
    expect(opensDisclosure(root.querySelector('.outside button'))).toBe(false);
    expect(opensDisclosure(null)).toBe(false);
    root.remove();
  });
});

describe('ChatMessage', () => {
  const source: WebSource = { url: 'https://example.com/a', title: 'Nguồn A', citation_ids: ['web:21'], kind: 'citation' };
  const view = (writing: boolean) => <ChatMessage message={{ role: 'assistant', content: 'Xem [trang](https://example.com) [web:21]', sources: [source] }}
    live={writing} writing={writing} onPreview={() => {}} onEdit={() => {}} />;

  it('câu trả lời đang chạy có aria-busy, xong thì bỏ', () => {
    const { container, rerender } = render(view(true));
    expect(container.querySelector('article')?.getAttribute('aria-busy')).toBe('true');
    rerender(view(false));
    expect(container.querySelector('article')?.hasAttribute('aria-busy')).toBe(false);
  });

  it('link trong câu trả lời và trích dẫn nguồn mở thẻ mới, có mô tả cho trình đọc màn hình', () => {
    const { container } = render(view(false));
    const links = [...container.querySelectorAll<HTMLAnchorElement>('a[href^="https://example.com"]')];
    expect(links.length).toBeGreaterThanOrEqual(2);
    for (const link of links) {
      expect(link.target).toBe('_blank');
      expect(link.rel).toBe('noopener noreferrer');
      expect(link.getAttribute('aria-describedby')).toBe('new-tab-hint');
    }
    // Tên link giữ nguyên, chữ mô tả không chen vào nội dung (bản in, chép có định dạng).
    expect(container.textContent).not.toContain('thẻ mới');
  });
});
