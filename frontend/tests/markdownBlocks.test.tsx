import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ChatMessage } from '../src/features/chat/ChatMessage';
import { splitMarkdownBlocks } from '../src/shared/markdown/markdownBlocks';

describe('câu trả lời đang chạy chia khối', () => {
  // Chỉ khác chỗ xuống dòng giữa hai thẻ khối (một cây có "\n" ở đó), thứ không hiện ra màn hình.
  it('ra HTML giống hệt khi dựng một cây, trừ khoảng trắng giữa các thẻ khối', () => {
    const content = [
      '## Đề mục', 'Đoạn **đậm** và *nghiêng*,\ncòn tiếp dòng.', '1. Một\n2. Hai', '- a\n\n- b\n\n  ý thêm của b',
      '> trích dẫn\n> dòng hai', '```\nconst x = 1;\n\nconsole.log(x);\n```', 'Đoạn cuối có [liên kết](https://example.com).',
    ].join('\n\n');
    // Một dòng định nghĩa link không dùng tới không hiện ra gì, nhưng buộc cả bài thành một khối: bản đối chứng một cây.
    const html = (single: boolean, writing = false) => {
      const text = single ? `${content}\n\n[khong-dung]: https://example.com` : content;
      const { container, unmount } = render(<ChatMessage message={{ role: 'assistant', content: text }} live={writing}
        writing={writing} onPreview={() => {}} onEdit={() => {}} />);
      const out = container.querySelector('[data-message-content]')!.innerHTML.replace(/>\s+</g, '><')
        .replace(/_r_[a-z0-9]+_/g, 'id'); // useId khác nhau giữa hai lần vẽ riêng
      unmount();
      return out;
    };
    expect(splitMarkdownBlocks(content).length).toBeGreaterThan(4);
    const reference = html(true);
    expect(html(false)).toBe(reference);
    expect(html(false, true)).toBe(reference);
  });
});

// Chia khối cho câu trả lời đang chạy (28/11/2026): ghép lại luôn ra đúng chuỗi gốc, và không bao giờ cắt ở chỗ làm đổi
// nghĩa Markdown.

const check = (text: string) => {
  const blocks = splitMarkdownBlocks(text);
  expect(blocks.join('')).toBe(text);
  return blocks;
};

describe('splitMarkdownBlocks', () => {
  it('cắt ở dòng trống giữa các đoạn và đề mục; ghép lại đúng chuỗi gốc', () => {
    expect(check('## Mở đầu\n\nĐoạn một.\nVẫn đoạn một.\n\nĐoạn hai')).toEqual(['## Mở đầu\n\n', 'Đoạn một.\nVẫn đoạn một.\n\n', 'Đoạn hai']);
    expect(check('Một\n\n\n\nHai\n')).toEqual(['Một\n\n\n\n', 'Hai\n']);
    expect(check('')).toEqual([]);
    expect(check('Chưa xong câu')).toEqual(['Chưa xong câu']);
  });

  it('khối code có dòng trống bên trong, kể cả chưa đóng, là một khối', () => {
    const code = 'Trước\n\n```py\nx = 1\n\ny = 2\n```\n\nSau';
    expect(check(code)).toEqual(['Trước\n\n', '```py\nx = 1\n\ny = 2\n```\n\n', 'Sau']);
    expect(check('```\na\n\nb')).toEqual(['```\na\n\nb']);
    // Rào ~~~ không bị ``` bên trong đóng.
    expect(check('~~~\n```\n\nvẫn code\n~~~\n\nSau')).toEqual(['~~~\n```\n\nvẫn code\n~~~\n\n', 'Sau']);
  });

  it('khối công thức $$ nhiều dòng có dòng trống là một khối', () => {
    expect(check('Ta có\n\n$$\na = b\n\n+ c\n$$\n\nXong')).toEqual(['Ta có\n\n', '$$\na = b\n\n+ c\n$$\n\n', 'Xong']);
    expect(check('Công thức $$x$$ trong dòng.\n\nTiếp')).toEqual(['Công thức $$x$$ trong dòng.\n\n', 'Tiếp']);
  });

  it('không cắt đôi danh sách lỏng hay phần thụt lề của một mục', () => {
    const list = '1. Một\n\n2. Hai\n\n   tiếp ý hai\n\n3. Ba\n\nĐoạn sau';
    expect(check(list)).toEqual(['1. Một\n\n2. Hai\n\n   tiếp ý hai\n\n3. Ba\n\n', 'Đoạn sau']);
    expect(check('- a\n\n- b\n\n    code thụt lề')).toEqual(['- a\n\n- b\n\n    code thụt lề']);
  });

  it('có chú thích cuối trang hay định nghĩa link thì để nguyên một khối', () => {
    expect(check('Câu[^1].\n\nĐoạn.\n\n[^1]: Chú thích')).toHaveLength(1);
    expect(check('Xem [tài liệu][doc].\n\n[doc]: https://example.com')).toHaveLength(1);
  });

  it('bảng, trích dẫn và marker nguồn giữ nguyên trong khối của nó', () => {
    const text = '| A | B |\n| --- | --- |\n| 1 | 2 |\n\n> trích\n> tiếp\n\nNguồn [web:21] ở đây.';
    expect(check(text)).toEqual(['| A | B |\n| --- | --- |\n| 1 | 2 |\n\n', '> trích\n> tiếp\n\n', 'Nguồn [web:21] ở đây.']);
  });
});
