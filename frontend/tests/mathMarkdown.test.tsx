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
  it('giữ dấu phủ định viết kiểu ~p thay vì biến nó thành khoảng trắng', () => {
    // Đúng câu trả lời bị báo lỗi: KaTeX coi ~ là khoảng trắng nên "A → B ≡ ~A ∨ B" hiện thành "A → B ≡ A ∨ B".
    const el = draw(String.raw`Nhớ: $A \to B \equiv ~A \lor B$.

\[P \to (Q \to R) \equiv ~P \lor (~Q \lor R) \equiv ~P \lor ~Q \lor R\]`);
    expect(el.querySelector('.katex-error')).toBeNull();
    const shown = Array.from(el.querySelectorAll('.katex-html')).map((node) => node.textContent).join(' ');
    expect(shown.match(/∼/g)).toHaveLength(5);
  });
  it('chỉ đổi dấu ~ đứng ở chỗ toán hạng', () => {
    // Chuỗi thường chứ không dùng template: "${" trong template là chỗ chèn biến.
    expect(normalizeMath('$~p$')).toBe('${\\sim}p$');
    expect(normalizeMath('\\(p \\land (~q \\lor ~~r)\\)')).toBe('$p \\land ({\\sim}q \\lor {\\sim}{\\sim}r)$');
    // Khoảng trắng thật của LaTeX: giữa hai chữ, sau \text{…}, hay dấu ~ đã escape.
    for (const text of [String.raw`$a~b$`, String.raw`$\text{nếu}~x > 0$`, String.raw`$\~a$`, 'giá ~5 đô']) {
      expect(normalizeMath(text)).toBe(text);
    }
    expect(normalizeMath('`$~p$`')).toBe('`$~p$`');
  });
  it('không tạo hình ảnh từ lệnh LaTeX không đáng tin', () => {
    expect(draw(String.raw`$\includegraphics{https://example.com/test.png}$`).querySelector('img')).toBeNull();
  });
});
