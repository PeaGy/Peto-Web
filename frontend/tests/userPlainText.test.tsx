import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ChatMessage } from '../src/features/chat/ChatMessage';
import { linkParts, splitUserText } from '../src/features/chat/UserPlainText';

const props = { live: false, writing: false, onPreview: () => {}, onEdit: () => {} };

describe('tin người dùng là chữ thuần (G4.1)', () => {
  it('giữ ký tự Markdown, xuống dòng và khoảng trắng đúng như đã gõ', () => {
    const typed = '# Không phải tiêu đề\n* không phải danh sách\n1. vẫn là chữ\n  thụt hai dấu cách\n$x^2$ và **đậm**';
    const { container } = render(<ChatMessage {...props} message={{ id: 1, role: 'user', content: typed }} />);
    const bubble = container.querySelector('.bubble.user')!;
    expect(bubble.querySelector('h1, ul, ol, strong, em, .katex, table')).toBeNull();
    expect(bubble.querySelector('.user-plain-text')?.textContent).toBe(typed);
  });

  it('khối code rào bằng ``` hoặc ~~~ thành khối code, chưa đóng thì tới cuối tin', () => {
    expect(splitUserText('Xem nè:\n```python\nprint("*hi*")\n```\nCảm ơn')).toEqual([
      { kind: 'text', text: 'Xem nè:' },
      { kind: 'code', language: 'python', source: 'print("*hi*")' },
      { kind: 'text', text: 'Cảm ơn' },
    ]);
    expect(splitUserText('~~~\na\n\nb')).toEqual([{ kind: 'code', language: '', source: 'a\n\nb' }]);
    expect(splitUserText('````md\n```\nbên trong\n```\n````')).toEqual([
      { kind: 'code', language: 'md', source: '```\nbên trong\n```' }]);
    const { container } = render(<ChatMessage {...props} message={{ id: 2, role: 'user', content: 'a\n```js\nlet x = 1;\n```' }} />);
    expect(container.querySelector('.bubble.user .code-block code')?.textContent).toBe('let x = 1;');
    expect(container.querySelector('.bubble.user .code-lang')?.textContent).toBeTruthy();
  });

  it('link thành chip, bỏ dấu câu và dấu đóng ngoặc thừa ở cuối', () => {
    expect(linkParts('Đọc https://example.com/a. Rồi (https://vi.wikipedia.org/wiki/Mèo_(định_hướng)).')).toEqual([
      { text: 'Đọc ' }, { text: 'https://example.com/a', href: 'https://example.com/a' }, { text: '. Rồi (' },
      { text: 'https://vi.wikipedia.org/wiki/Mèo_(định_hướng)', href: 'https://vi.wikipedia.org/wiki/Mèo_(định_hướng)' },
      { text: ').' },
    ]);
    expect(linkParts('không có link, chỉ http:// chữ')).toEqual([{ text: 'không có link, chỉ http:// chữ' }]);
    const { container } = render(<ChatMessage {...props} message={{ id: 3, role: 'user', content: 'Xem https://example.com/x nhé' }} />);
    const link = container.querySelector('.bubble.user a.message-link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('https://example.com/x');
    expect(link.getAttribute('rel')).toContain('noopener');
  });

  it('chỉ đổi tin người dùng; câu trả lời của Peto vẫn là Markdown', () => {
    const { container } = render(<ChatMessage {...props} message={{ id: 4, role: 'assistant', content: '**đậm**' }} />);
    expect(container.querySelector('.bubble.assistant strong')?.textContent).toBe('đậm');
  });
});
