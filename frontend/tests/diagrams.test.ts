import { describe as group, expect, it } from 'vitest';
import { describe, diagramBlocks, hasDiagram, hastText, kindNote, normalizeDiagram, sized, svgSize } from '../src/diagrams';
import { drawioUrl, pdfFromJpeg } from '../src/diagramExport';

group('nhận diện sơ đồ', () => {
  it('lấy tên ở phần đầu và loại theo từ khóa', () => {
    expect(describe('---\ntitle: Quy trình đăng ký\n---\nflowchart TD\n  A --> B')).toEqual({ kind: 'Lưu đồ', title: 'Quy trình đăng ký' });
    expect(describe('---\ntitle: "Có ngoặc kép"\n---\nclassDiagram\n  class A')).toEqual({ kind: 'Sơ đồ lớp', title: 'Có ngoặc kép' });
    expect(describe('%% ghi chú\nsequenceDiagram\n  A->>B: chào')).toEqual({ kind: 'Sơ đồ tuần tự', title: 'Sơ đồ tuần tự' });
    expect(describe('stateDiagram-v2\n  [*] --> A').kind).toBe('Sơ đồ trạng thái');
    expect(describe('erDiagram\n  A ||--o{ B : co').kind).toBe('Sơ đồ quan hệ');
    expect(describe('swimlane-beta\n  subgraph DG["Độc giả"]\n    A(Chọn sách)\n  end').kind).toBe('Sơ đồ phân làn');
    expect(describe('xyz').kind).toBe('Sơ đồ');
  });

  it('sơ đồ hoạt động và use case lấy loại từ tên, không ghi lặp loại khi tên trùng loại', () => {
    const activity = describe('---\ntitle: "Sơ đồ hoạt động: Mượn sách"\n---\nstateDiagram-v2\n  [*] --> A');
    expect(activity).toEqual({ kind: 'Sơ đồ hoạt động', title: 'Sơ đồ hoạt động: Mượn sách' });
    expect(describe('---\ntitle: Sơ đồ use case bán hàng\n---\nflowchart LR\n  A((Khách))').kind).toBe('Sơ đồ use case');
    expect(describe('---\ntitle: Sơ đồ hoạt độngx\n---\nstateDiagram-v2').kind).toBe('Sơ đồ trạng thái');
    expect(kindNote(activity.kind, activity.title)).toBe('');
    expect(kindNote('Sơ đồ tuần tự', 'Sơ đồ tuần tự')).toBe('');
    expect(kindNote('Sơ đồ lớp', 'Thư viện')).toBe('Sơ đồ lớp');
  });

  it('chỉ tính khối mermaid, kể cả ~~~ và khối nằm trong danh sách', () => {
    const text = [
      'Mở đầu', '', '```python', 'print("```mermaid giả")', '```', '',
      '```mermaid', 'flowchart TD', '    A --> B', '```', '',
      '1. Bước một', '', '   ~~~mermaid', '   sequenceDiagram', '       A->>B: chào', '   ~~~', '',
      '````mermaid', 'classDiagram', '  class A', '```', '````',
    ].join('\n');
    expect(hasDiagram(text)).toBe(true);
    expect(diagramBlocks(text)).toEqual([
      'flowchart TD\n    A --> B',
      'sequenceDiagram\n    A->>B: chào',
      'classDiagram\n  class A\n```',
    ]);
    expect(hasDiagram('```python\nprint(1)\n```')).toBe(false);
  });

  it('khối chưa đóng tới cuối tin vẫn tính, như Markdown hiển thị', () => {
    expect(diagramBlocks('Đây:\n```mermaid\npie\n  "A" : 1')).toEqual(['pie\n  "A" : 1']);
  });

  it('cùng một sơ đồ lấy từ cây Markdown hay từ chữ gốc thì ra cùng chuỗi', () => {
    const node = { type: 'element', children: [{ type: 'text', value: '    flowchart TD\n      A --> B\n' }] };
    expect(normalizeDiagram(hastText(node))).toBe('flowchart TD\n  A --> B');
    expect(normalizeDiagram('\r\n  x\r\n')).toBe('x');
  });

  it('đọc cỡ từ viewBox và đặt cỡ cố định cho thẻ svg gốc', () => {
    const svg = '<svg id="d" width="100%" style="max-width: 300px;" viewBox="0 0 300 150"><g><svg width="5"></svg></g></svg>';
    expect(svgSize(svg)).toEqual({ width: 300, height: 150 });
    expect(sized(svg, 120, 60)).toBe('<svg id="d" viewBox="0 0 300 150" width="120" height="60"><g><svg width="5"></svg></g></svg>');
    expect(svgSize('<svg></svg>')).toEqual({ width: 640, height: 400 });
  });
});

group('tải về và mở bằng draw.io', () => {
  it('PDF một trang A4 chứa đúng ảnh JPEG, bảng xref trỏ đúng từng đối tượng', () => {
    const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 0xff, 0xd9]);
    const pdf = pdfFromJpeg(jpeg, 3000, 1500);
    const text = new TextDecoder('latin1').decode(pdf);
    expect(text.startsWith('%PDF-1.4\n')).toBe(true);
    expect(text).toContain('/MediaBox [0 0 841.89 595.28]'); // hình ngang thì trang ngang
    expect(text).toContain('/Width 3000 /Height 1500 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length 9');
    const start = Number(/startxref\n(\d+)\n%%EOF\n$/.exec(text)![1]);
    expect(text.slice(start, start + 4)).toBe('xref');
    const offsets = [...text.slice(start).matchAll(/^(\d{10}) 00000 n $/gm)].map((match) => Number(match[1]));
    expect(offsets).toHaveLength(5);
    offsets.forEach((offset, index) => expect(text.slice(offset).startsWith(`${index + 1} 0 obj`)).toBe(true));
    expect(new TextDecoder('latin1').decode(pdfFromJpeg(jpeg, 400, 900))).toContain('/MediaBox [0 0 595.28 841.89]');
  });

  it('link draw.io mang mã sơ đồ sau dấu # theo đúng cách nén của draw.io', async () => {
    const code = '---\ntitle: Đăng nhập\n---\nsequenceDiagram\n  A->>B: chào';
    const url = await drawioUrl(code);
    // Không có tham số sau dấu ?: có tham số là draw.io hỏi "Tất cả mọi thay đổi sẽ mất!" ngay sau khi mở sơ đồ.
    expect(url.startsWith('https://app.diagrams.net/#create=')).toBe(true);
    const payload = JSON.parse(decodeURIComponent(url.split('#create=')[1]));
    expect(payload.type).toBe('mermaid');
    if (payload.compressed) {
      const bytes = Uint8Array.from(atob(payload.data), (char) => char.charCodeAt(0));
      const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
      expect(decodeURIComponent(await new Response(stream).text())).toBe(code);
    } else {
      expect(payload.data).toBe(code);
    }
  });
});
