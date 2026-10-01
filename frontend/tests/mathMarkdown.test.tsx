import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Markdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { normalizeMath } from '../src/shared/markdown/mathMarkdown';
import { hasMath } from '../src/shared/markdown/markdownExtras';

function draw(text: string) {
  return render(<Markdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { trust: false, strict: 'ignore' }]]}>{normalizeMath(text)}</Markdown>).container;
}

describe('hiển thị công thức toán', () => {
  it('giữ giá tiền và chữ đậm như đoạn báo lỗi, không dùng font toán cho văn xuôi', () => {
    const text = 'Cached input lúc đó là **$0.40** (Sol) và **$0.20** (6.1 Sol).\n\n'
      + 'Cùng tỷ lệ cache 80%, input hiệu dụng khoảng **$0.56** (Sol) so với **$0.48** (6.1 Sol).\n\n'
      + 'Cost per task khoảng **$1.05** (GPT-6 Sol) và **$0.72** (GPT-6.1 Sol).';
    const el = draw(text);
    expect(el.querySelector('.katex')).toBeNull();
    expect(Array.from(el.querySelectorAll('strong')).map(node => node.textContent))
      .toEqual(['$0.40', '$0.20', '$0.56', '$0.48', '$1.05', '$0.72']);
    expect(el.textContent).not.toContain('*');
    expect(hasMath(normalizeMath(text))).toBe(false);
  });
  it('giữ giá trong bảng và nhận công thức sau giá tiền trong cùng một dòng', () => {
    const el = draw('Giá $5, trước đây $10; công thức $x^2$ hoặc \\(5 + 2 = 7\\).');
    expect(el.textContent).toContain('Giá $5, trước đây $10;');
    expect(el.querySelectorAll('.katex')).toHaveLength(2);
    expect(draw('Input $2.00 | Cached $0.20 | Output $10.00').querySelector('.katex')).toBeNull();
  });
  it('giữ tiền tệ đã escape và không sửa giá hay công thức mẫu trong code', () => {
    const text = 'Giá \\$5 và \\$10. Code: `$5 rồi $x^2$`.';
    expect(draw(text).querySelector('.katex')).toBeNull();
    expect(normalizeMath('```txt\n$5 và $10\n```')).toBe('```txt\n$5 và $10\n```');
  });
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
  it('giữ công thức đơn giản, ký hiệu và hàm bên cạnh giá tiền', () => {
    const el = draw('Giá $5, tính $|x|$, $f(x) g(y)$, $2 sin x$ và $ x + y $.');
    expect(el.textContent).toContain('Giá $5, tính');
    expect(el.querySelectorAll('.katex')).toHaveLength(4);
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
