import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Markdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { normalizeMath } from '../src/mathMarkdown';

function draw(text: string) {
  return render(<Markdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { trust: false, strict: 'ignore' }]]}>{normalizeMath(text)}</Markdown>).container;
}

describe('hiển thị công thức toán', () => {
  it('hiển thị hệ thức và công thức trong dòng giống ảnh báo lỗi', () => {
    const el = draw(String.raw`\[a_n = c_1 a_{n-1} + c_2 a_{n-2} + \dots + c_k a_{n-k}\]
với \(c_k \neq 0\).`);
    expect(el.querySelectorAll('.katex')).toHaveLength(2);
    expect(el.querySelectorAll('.katex-display')).toHaveLength(1);
    expect(el.querySelector('.katex-error')).toBeNull();
  });
  it('hỗ trợ dấu đô la, phân số và ma trận', () => {
    const el = draw('$x^2$\n\n$$\n\\frac{1}{2}+\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}\n$$');
    expect(el.querySelectorAll('.katex')).toHaveLength(2);
    expect(el.querySelector('.katex-error')).toBeNull();
  });
  it('không thay đổi công thức mẫu trong code', () => {
    const text = '```python\n' + String.raw`print("\(x\)")` + '\n```\n`' + String.raw`\[x\]` + '`';
    expect(normalizeMath(text)).toBe(text);
    expect(draw(text).querySelector('.katex')).toBeNull();
  });
  it('giữ công thức chưa hoàn tất khi đang nhận câu trả lời', () => {
    expect(normalizeMath(String.raw`Đang viết \(x_`)).toBe(String.raw`Đang viết \(x_`);
    expect(draw('$\\khongtontai{x}$').textContent).toContain('\\khongtontai');
  });
  it('không tạo hình ảnh từ lệnh LaTeX không đáng tin', () => {
    expect(draw(String.raw`$\includegraphics{https://example.com/test.png}$`).querySelector('img')).toBeNull();
  });
});
