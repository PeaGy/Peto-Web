// @vitest-environment node
/**
 * Một bản KaTeX cho cả app (G4.2). Chat vẽ công thức bằng rehype-katex nhưng nạp CSS của gói katex ở gốc; hai bản khác
 * nhau thì HTML và CSS lệch tên lớp (0.18 đổi .base thành .katex-base), công thức hiện sai mà không báo lỗi.
 */
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { expect, it } from 'vitest';

const root = createRequire(join(process.cwd(), 'package.json'));
const app = dirname(root.resolve('katex/package.json'));

function katexOf(dependent: string): string {
  // Gói phụ thuộc có thể không xuất package.json; tìm katex từ chính thư mục của gói như Node và Vite vẫn làm.
  const from = createRequire(join(process.cwd(), 'node_modules', dependent, 'package.json'));
  return dirname(from.resolve('katex/package.json'));
}

it('rehype-katex, mermaid và micromark-extension-math dùng đúng gói katex của app', () => {
  for (const dependent of ['rehype-katex', 'mermaid', 'micromark-extension-math']) {
    expect(katexOf(dependent), dependent).toBe(app);
  }
});

it('HTML chat dựng ra có lớp mà CSS đang nạp định nghĩa', () => {
  const katex = createRequire(join(katexOf('rehype-katex'), 'package.json'))('katex') as { renderToString(tex: string): string };
  const css = readFileSync(join(app, 'dist', 'katex.min.css'), 'utf8');
  const html = katex.renderToString('x^2');
  const classes = [...new Set([...html.matchAll(/class="([^"]+)"/g)].flatMap((match) => match[1].split(/\s+/)))];
  // Lớp cấu trúc chính của mỗi dòng công thức; thiếu luật CSS thì phần cao và xuống dòng của công thức sai.
  const structural = classes.filter((name) => /^(katex-)?(base|strut)$/.test(name));
  expect(structural.length).toBeGreaterThan(0);
  for (const name of structural) expect(css, name).toContain(`.${name}{`);
});
