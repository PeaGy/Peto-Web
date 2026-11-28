import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ResponseActions from '../src/features/chat/ResponseActions';
import {
  clipboardHtml, conversationFilename, conversationMarkdown, printableConversation,
} from '../src/features/chat/responseExport';
import type { Message, WebSource } from '../src/shared/api/api';

// Xuất cả hội thoại (Markdown, bản in) và chép câu trả lời có định dạng (28/11/2026).

const source: WebSource = { url: 'https://example.com/a', title: 'Nguồn A', citation_ids: ['web:21'], kind: 'citation' };
const day = new Date(2026, 10, 28);

afterEach(() => { vi.unstubAllGlobals(); });

describe('conversationMarkdown', () => {
  it('tiêu đề, ngày xuất, từng tin Bạn/Peto; tệp, tài liệu và nguồn đi theo tin của nó', () => {
    const messages: Message[] = [
      { role: 'user', content: 'Tóm tắt giúp mình', attachments: [{ id: 'f', name: 'bao_cao`q3.pdf', mime: 'application/pdf', kind: 'file', size: 1, url: '' }] },
      { role: 'assistant', content: 'Đây là **tóm tắt** [web:21].', sources: [source],
        artifacts: [{ id: 'd', title: 'Tóm tắt', filename: 'tom-tat.docx', version: 1, format: 'docx', style: 'report', pages: 1 }] },
      { role: 'assistant', content: '   ' },
      { role: 'user', content: 'Cảm ơn' },
    ];
    expect(conversationMarkdown('Báo cáo\nquý 3', messages, day)).toBe([
      '# Báo cáo quý 3\n\n_Xuất từ Peto ngày 28/11/2026_',
      "## Bạn\n\nTóm tắt giúp mình\n\nTệp đính kèm: `bao_cao'q3.pdf`",
      '## Peto\n\nĐây là **tóm tắt** [web:21].\n\nTài liệu Peto tạo: `tom-tat.docx`\n\n### Nguồn\n\n- [Nguồn A](<https://example.com/a>) (web:21)',
      '## Bạn\n\nCảm ơn',
    ].join('\n\n---\n\n') + '\n');
  });

  it('tên tệp không dấu, không ký tự lạ', () => {
    expect(conversationFilename('Đặt lịch học Xác suất — tuần 1!')).toBe('peto-dat-lich-hoc-xac-suat-tuan-1.md');
    expect(conversationFilename('???')).toBe('peto-hoi-thoai.md');
  });
});

describe('printableConversation', () => {
  it('mỗi tin một mục có nhãn; bỏ nhật ký, nút Xem thêm và thao tác; nguồn sau câu trả lời', () => {
    const container = document.createElement('div');
    container.innerHTML = `
      <article data-role="user"><div data-message-content><div class="user-fold"><p class="user-plain-text">Hỏi\nhai dòng</p></div>
        <button class="user-fold-toggle">Xem thêm</button></div></article>
      <article data-role="assistant"><div class="work-log">Đã làm trong 3 giây</div>
        <div data-message-content><h2>Kết quả</h2><p>Trả lời</p></div>
        <div class="message-actions" data-export-exclude><button>Sao chép</button></div></article>`;
    const messages: Message[] = [{ role: 'user', content: 'Hỏi\nhai dòng' }, { role: 'assistant', content: 'Trả lời', sources: [source] }];
    const main = printableConversation(container, messages, 'Hội thoại thử', document, day);
    expect(main.querySelector('h1')?.textContent).toBe('Hội thoại thử');
    expect(main.querySelector('.print-meta')?.textContent).toBe('Xuất từ Peto ngày 28/11/2026');
    expect([...main.querySelectorAll('.print-role')].map(node => node.textContent)).toEqual(['Bạn', 'Peto']);
    expect(main.textContent).not.toMatch(/Xem thêm|Đã làm trong|Sao chép/);
    expect(main.querySelector('.print-turn.assistant .print-sources a')?.getAttribute('href')).toBe('https://example.com/a');
    expect(main.querySelector('button')).toBeNull();
  });
});

describe('clipboardHtml', () => {
  const root = () => {
    const node = document.createElement('div');
    node.innerHTML = `<p>Công thức <span class="katex"><span class="katex-mathml"><math><semantics><mi>x</mi>
      <annotation encoding="application/x-tex">x^2</annotation></semantics></math></span><span class="katex-html">x2</span></span>
      và nguồn <span class="citation-group"><a class="citation-badge" href="https://example.com/a">21</a></span>.</p>
      <span class="katex-display"><span class="katex"><span class="katex-mathml"><math><semantics><mi>a</mi>
      <annotation encoding="application/x-tex">\\frac{a}{b}</annotation></semantics></math></span></span></span>
      <table><thead><tr><th>A</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>
      <div class="code-block"><div class="code-head"><span>python</span></div><pre><code>print(1)</code></pre></div>
      <img src="x" onerror="alert(1)" alt="ảnh"><script>alert(1)</script>`;
    return node;
  };

  it('công thức thành TeX, nguồn thành [n], bảng và code có style trên thẻ, không lớp và không mã độc', () => {
    const html = clipboardHtml(root());
    expect(html).toContain('$x^2$');
    expect(html).toContain('<p>$$\\frac{a}{b}$$</p>');
    expect(html).toContain('[21]');
    expect(html).toContain('<table style="border-collapse:collapse">');
    expect(html).toMatch(/<td style="border:1px solid #bbb[^"]*">1<\/td>/);
    expect(html).toContain('<pre style="font-family:Consolas,monospace;white-space:pre-wrap"><code>print(1)</code></pre>');
    expect(html).not.toMatch(/class=|python|<script|onerror|<img|x2/);
  });

  it('nút chép câu trả lời ghi cả chữ thường lẫn HTML; trình duyệt không có ClipboardItem thì chép chữ thường', async () => {
    const entries: Record<string, Blob>[] = [];
    const write = vi.fn().mockResolvedValue(undefined);
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('ClipboardItem', class { constructor(value: Record<string, Blob>) { entries.push(value); } });
    Object.assign(navigator, { clipboard: { write, writeText } });
    const contentRef = { current: root() };
    const view = render(<ResponseActions text="Công thức $x^2$" contentRef={contentRef} />);
    fireEvent.click(screen.getByRole('button', { name: 'Sao chép câu trả lời' }));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    expect(await entries[0]['text/plain'].text()).toBe('Công thức $x^2$');
    expect(await entries[0]['text/html'].text()).toContain('$x^2$');
    expect(writeText).not.toHaveBeenCalled();
    view.unmount();

    vi.stubGlobal('ClipboardItem', undefined);
    render(<ResponseActions text="Chỉ chữ" contentRef={contentRef} />);
    fireEvent.click(screen.getByRole('button', { name: 'Sao chép câu trả lời' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('Chỉ chữ'));
  });
});
