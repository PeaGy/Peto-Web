import { describe as group, expect, it } from 'vitest';
import { describe, quoteTitle } from '../src/features/diagrams/diagrams';

// Mã thật Haiku viết trên app ngày 13/11/2026: Mermaid báo "Mã sơ đồ không hợp lệ" vì dấu ": " thứ hai trong tiêu đề.
const REAL = [
  '---',
  'title: Sơ đồ hoạt động: Quy trình đăng nhập',
  '---',
  'flowchart TD',
  '    S([Bắt đầu]) --> A["Người dùng nhập tài khoản và mật khẩu"]',
  '    A --> B{"Thông tin hợp lệ?"}',
  '    B -- Không --> A',
  '    B -- Có --> H(["Vào hệ thống"])',
].join('\n');

group('tiêu đề sơ đồ có dấu hai chấm', () => {
  it('đặt ngoặc kép cho tiêu đề chưa có ngoặc, giữ nguyên phần còn lại', () => {
    const fixed = quoteTitle(REAL);
    expect(fixed.split('\n')[1]).toBe('title: "Sơ đồ hoạt động: Quy trình đăng nhập"');
    expect(fixed.split('\n').slice(2)).toEqual(REAL.split('\n').slice(2));
    expect(describe(fixed)).toEqual(describe(REAL));
    expect(describe(fixed)).toEqual({ kind: 'Sơ đồ hoạt động', title: 'Sơ đồ hoạt động: Quy trình đăng nhập' });
  });

  it('không đụng tiêu đề đã có ngoặc, khối nhiều dòng, mã không có phần đầu hay dòng title ngoài phần đầu', () => {
    for (const code of [
      '---\ntitle: "Đã có: ngoặc kép"\n---\nflowchart TD\n  A --> B',
      "---\ntitle: 'Ngoặc đơn: cũng được'\n---\nflowchart TD\n  A --> B",
      '---\ntitle: |\n  Nhiều dòng\n---\nflowchart TD\n  A --> B',
      'flowchart TD\n  A["title: không phải phần đầu"] --> B',
      'sequenceDiagram\n  A->>B: title: x',
    ]) expect(quoteTitle(code)).toBe(code);
  });

  it('thoát dấu ngoặc kép và gạch chéo ngược bên trong tiêu đề', () => {
    expect(quoteTitle('---\ntitle: Bài "hay": a\\b\n---\npie\n  "A": 1').split('\n')[1])
      .toBe('title: "Bài \\"hay\\": a\\\\b"');
    expect(quoteTitle('---\nconfig:\n  theme: base\ntitle: Có: hai chấm\n---\nflowchart TD\n  A --> B').split('\n')[3])
      .toBe('title: "Có: hai chấm"');
  });

  it('Mermaid thật từ chối bản gốc và nhận bản đã đặt ngoặc', async () => {
    const mermaid = (await import('mermaid')).default;
    await expect(mermaid.parse(REAL)).rejects.toThrow(/mapping entry/);
    await expect(mermaid.parse(quoteTitle(REAL))).resolves.toBeTruthy();
  });
});
