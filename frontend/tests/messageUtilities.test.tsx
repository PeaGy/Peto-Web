import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatMessage } from '../src/features/chat/ChatMessage';
import CodeBlock from '../src/features/chat/CodeBlock';
import { copyTable, rowsToCsv, rowsToHtml, saveTable, spreadsheetCell, tableRows } from '../src/features/chat/tableExport';
import { printableResponse, printResponse, responseMarkdown } from '../src/features/chat/responseExport';
import type { Message, WebSource } from '../src/shared/api/api';

const sources: WebSource[] = [{ url: 'https://example.com/report', title: 'Báo cáo', citation_ids: ['web:21'], kind: 'citation' }];
const props = { live: false, writing: false, onPreview: () => {}, onEdit: () => {} };
const view = (message: Message, extra: Partial<Parameters<typeof ChatMessage>[0]> = {}) => <ChatMessage {...props} message={message} {...extra} />;
const readBlob = (blob: Blob) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsText(blob);
});

beforeEach(() => {
  vi.stubGlobal('ClipboardItem', undefined);
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  URL.createObjectURL = vi.fn(() => 'blob:peto-export');
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
});
afterEach(() => vi.unstubAllGlobals());

describe('Bảng: dữ liệu và bảo vệ đầu ra', () => {
  it('đọc hàng/ô, xuống dòng và loại citation/controls mà không sửa bảng thật', () => {
    const table = document.createElement('table');
    table.innerHTML = '<thead><tr><th>Tên</th><th>Ghi chú</th></tr></thead><tbody><tr><td>Hà Nội<span class="citation-group"><a>21</a></span></td><td>Một<br>Hai<button>Sao chép</button><script>BAD</script></td></tr></tbody>';
    const original = table.innerHTML;
    expect(tableRows(table)).toEqual([['Tên', 'Ghi chú'], ['Hà Nội', 'Một\nHai']]);
    expect(table.innerHTML).toBe(original);
  });

  it('copy giữ nguyên marker literal trong code/link/user, bỏ badge citation do renderer tạo', () => {
    const content = '| Giá trị | Nguồn |\n| --- | --- |\n| `[web:21]` | Đã kiểm [web:21] |\n| [[web:22]](https://example.com) | Giữ nguyên |';
    const { container, rerender } = render(view({ role: 'assistant', content, sources }));
    expect(tableRows(container.querySelector('table')!)).toEqual([
      ['Giá trị', 'Nguồn'], ['[web:21]', 'Đã kiểm'], ['[web:22]', 'Giữ nguyên'],
    ]);
    rerender(view({ role: 'user', content: '| User |\n| --- |\n| [web:21] |' }));
    expect(tableRows(container.querySelector('table')!)).toEqual([['User'], ['[web:21]']]);
  });

  it('CSV giữ Unicode, dấu phẩy, dấu nháy, xuống dòng và chặn công thức ẩn sau khoảng trắng', () => {
    expect(rowsToCsv([['Tên', 'Mô tả'], ['Tết, 2026', 'Một "hai"\nBa']])).toBe('Tên,Mô tả\r\n"Tết, 2026","Một ""hai""\nBa"');
    for (const value of ['=1+1', '+SUM(A1)', '-2+3', '@SUM(A1)', ' \t=1+1', '\uFEFF=1+1']) expect(spreadsheetCell(value)).toBe(`'${value}`);
    expect(spreadsheetCell('xin chào')).toBe('xin chào');
    expect(rowsToCsv([['=SUM(A1,A2)']])).toBe('"\'=SUM(A1,A2)"');
  });

  it('HTML clipboard chỉ chứa ô text đã escape và bảo vệ spreadsheet formulas', () => {
    const html = rowsToHtml([['Ảnh'], ['<img src=x onerror=alert(1)>'], ['=1+1']]);
    const holder = document.createElement('div'); holder.innerHTML = html;
    expect(holder.querySelector('img,script')).toBeNull();
    expect(holder.querySelectorAll('td')[0].textContent).toBe('<img src=x onerror=alert(1)>');
    expect(holder.querySelectorAll('td')[1].textContent).toBe("'=1+1");
  });

  it('copy cả text/plain và text/html, fallback text khi browser từ chối HTML', async () => {
    const entries: Record<string, Blob>[] = [];
    vi.stubGlobal('ClipboardItem', class { constructor(value: Record<string, Blob>) { entries.push(value); } });
    const write = vi.fn().mockResolvedValue(undefined), writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { write, writeText } });
    const table = document.createElement('table'); table.innerHTML = '<tr><th>Tên</th></tr><tr><td>Peto</td></tr>';
    await copyTable(table);
    expect(write).toHaveBeenCalledTimes(1); expect(writeText).not.toHaveBeenCalled();
    expect(await readBlob(entries[0]['text/plain'])).toBe('Tên\r\nPeto');
    expect(await readBlob(entries[0]['text/html'])).toContain('<th>Tên</th>');
    write.mockRejectedValueOnce(new Error('HTML denied'));
    await copyTable(table); expect(writeText).toHaveBeenCalledWith('Tên\r\nPeto');
  });

  it('lưu CSV có BOM UTF-8 và URL Blob được dọn sau khi tải', async () => {
    vi.useFakeTimers();
    try {
      const table = document.createElement('table'); table.innerHTML = '<tr><td>Tiếng Việt</td></tr>';
      saveTable(table);
      const blob = vi.mocked(URL.createObjectURL).mock.calls[0][0] as Blob;
      expect(blob.type).toBe('text/csv;charset=utf-8');
      // FileReader strips a UTF-8 BOM from its text result; byte count proves it is present.
      expect(blob.size).toBe(new TextEncoder().encode('Tiếng Việt').length + 3);
      expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
      expect(document.querySelector('a[download]')).toBeNull();
      expect(URL.revokeObjectURL).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(1000); expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:peto-export');
    } finally { vi.useRealTimers(); }
  });

  it('table controls nhỏ không có chữ và bị khóa khi bảng đang stream', () => {
    const message: Message = { role: 'assistant', content: '| A | B |\n| --- | --- |\n| Peto | Luna |' };
    const { rerender } = render(view(message, { writing: true, live: true }));
    const copy = screen.getByRole('button', { name: 'Sao chép bảng' }) as HTMLButtonElement;
    expect(copy.disabled).toBe(true); expect(copy.textContent).toBe('');
    expect((screen.getByRole('button', { name: 'Lưu bảng CSV' }) as HTMLButtonElement).disabled).toBe(true);
    rerender(view(message)); expect((screen.getByRole('button', { name: 'Sao chép bảng' }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('Khối code', () => {
  const sevenLines = ['dòng 1', 'dòng 2', 'dòng 3', 'dòng 4', 'dòng 5', 'dòng 6', 'dòng 7'].join('\n') + '\n';
  it('chỉ code hơn 5 dòng có collapse; copy giữ nguyên code khi bị ẩn', async () => {
    const { rerender } = render(<CodeBlock language="text" source="1\n2\n3\n4\n5\n"><code>1\n2\n3\n4\n5</code></CodeBlock>);
    expect(screen.queryByRole('button', { name: 'Thu gọn mã' })).toBeNull();
    rerender(<CodeBlock language="text" source={sevenLines}><code>{sevenLines}</code></CodeBlock>);
    fireEvent.click(screen.getByRole('button', { name: 'Thu gọn mã' }));
    expect(screen.queryByRole('region', { name: 'Mã Văn bản' })).toBeNull();
    expect(screen.getByText('7 dòng đã ẩn')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Sao chép', exact: true }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(sevenLines));
    fireEvent.click(screen.getByRole('button', { name: 'Mở rộng mã' }));
    expect(screen.getByRole('region', { name: 'Mã Văn bản' }).textContent).toBe(sevenLines);
  });

  it('wrap chỉ đổi hiển thị; ngưỡng 90 desktop và 50 trên khung mobile', async () => {
    const listeners = new Set<() => void>();
    const media = { matches: false, addEventListener: (_: string, fn: () => void) => listeners.add(fn), removeEventListener: (_: string, fn: () => void) => listeners.delete(fn) };
    vi.stubGlobal('matchMedia', vi.fn(() => media));
    const line = 'x'.repeat(60);
    const { container } = render(<CodeBlock language="js" source={line}><code>{line}</code></CodeBlock>);
    expect(screen.queryByRole('button', { name: 'Ngắt dòng' })).toBeNull();
    act(() => { media.matches = true; listeners.forEach(fn => fn()); });
    fireEvent.click(screen.getByRole('button', { name: 'Ngắt dòng' }));
    expect(container.querySelector('.message-code.wrapped')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Tắt ngắt dòng' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'Sao chép', exact: true }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(line));
  });

  it('collapse/wrap không reset khi stream kết thúc hoặc source metadata tới', () => {
    const content = `\`\`\`text\n${'x'.repeat(95)}\n${sevenLines}\`\`\``;
    const message: Message = { id: 4, role: 'assistant', content };
    const { container, rerender } = render(view(message, { live: true, writing: true }));
    fireEvent.click(screen.getByRole('button', { name: 'Ngắt dòng' }));
    fireEvent.click(screen.getByRole('button', { name: 'Thu gọn mã' }));
    rerender(view({ ...message, sources }));
    expect(container.querySelector('.message-code.collapsed.wrapped')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Mở rộng mã' })).toBeTruthy();
  });

  it('code đang thu gọn vẫn nhận dòng mới và copy phiên bản hiện tại sau streaming', async () => {
    const start = `\`\`\`text\n${sevenLines}\`\`\``;
    const { rerender } = render(view({ role: 'assistant', content: start }, { live: true, writing: true }));
    fireEvent.click(screen.getByRole('button', { name: 'Thu gọn mã' }));
    rerender(view({ role: 'assistant', content: `\`\`\`text\n${sevenLines}dòng 8\n\`\`\`` }));
    expect(screen.getByText('8 dòng đã ẩn')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Sao chép', exact: true }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(`${sevenLines}dòng 8\n`));
  });
});

describe('Thanh thao tác và xuất phản hồi', () => {
  it('action bar icon-only, copy nguyên Markdown; regen/variants bị khóa nhưng export vẫn mở', async () => {
    const text = '**Xin chào**\n\n$P \\to Q$', regen = vi.fn(), previous = vi.fn(), next = vi.fn();
    render(view({ id: 7, role: 'assistant', status: 'complete', content: text }, { actionsDisabled: true, onRegenerate: regen,
      variants: { index: 1, count: 3, onPrevious: previous, onNext: next } }));
    const copy = screen.getByRole('button', { name: 'Sao chép câu trả lời' });
    expect(copy.textContent).toBe('');
    fireEvent.click(copy); await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(text));
    for (const name of ['Tạo lại câu trả lời', 'Câu trả lời trước', 'Câu trả lời sau']) expect((screen.getByRole('button', { name }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Thêm thao tác' }));
    expect(screen.getByRole('menuitem', { name: 'Lưu Markdown' })).toBeTruthy();
    expect(regen).not.toHaveBeenCalled(); expect(previous).not.toHaveBeenCalled(); expect(next).not.toHaveBeenCalled();
  });

  it('regenerate chỉ hiện cho câu trả lời stored complete; variants dùng index 0-based', () => {
    const regen = vi.fn(), next = vi.fn();
    const message: Message = { id: 7, role: 'assistant', content: 'Peto', status: 'complete' };
    const { rerender } = render(view(message, { onRegenerate: regen, variants: { index: 0, count: 2, onPrevious: () => {}, onNext: next } }));
    expect(screen.getByText('1/2')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Câu trả lời trước' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Câu trả lời sau' })); expect(next).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button', { name: 'Tạo lại câu trả lời' })); expect(regen).toHaveBeenCalledWith(7);
    for (const update of [{ id: undefined }, { status: 'incomplete' as const }, { stopped: true }, { turn_state: 'error' as const }]) {
      rerender(view({ ...message, ...update }, { onRegenerate: regen }));
      expect(screen.queryByRole('button', { name: 'Tạo lại câu trả lời' })).toBeNull();
    }
  });

  it('streaming chỉ khóa request/navigation, không khóa copy hoặc xuất phần chữ đã nhận', async () => {
    render(view({ id: 8, role: 'assistant', content: 'Đoạn đã nhận', status: 'complete' }, { live: true, writing: true, onRegenerate: () => {},
      variants: { index: 0, count: 2, onPrevious: () => {}, onNext: () => {} } }));
    expect((screen.getByRole('button', { name: 'Tạo lại câu trả lời' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Câu trả lời sau' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Sao chép câu trả lời' }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith('Đoạn đã nhận'));
    fireEvent.click(screen.getByRole('button', { name: 'Thêm thao tác' }));
    expect(screen.getByRole('menuitem', { name: 'Lưu Markdown' })).toBeTruthy();
  });

  it('More menu điều khiển bằng Arrow/Home/End/Escape, ngoài click và trả focus', () => {
    render(view({ role: 'assistant', content: 'Peto' }));
    const trigger = screen.getByRole('button', { name: 'Thêm thao tác' });
    fireEvent.keyDown(trigger, { key: 'ArrowUp' });
    const menu = screen.getByRole('menu', { name: 'Thao tác câu trả lời' });
    const save = within(menu).getByRole('menuitem', { name: 'Lưu Markdown' }), print = within(menu).getByRole('menuitem', { name: 'In / lưu PDF' });
    expect(document.activeElement).toBe(print);
    fireEvent.keyDown(print, { key: 'Home' }); expect(document.activeElement).toBe(save);
    fireEvent.keyDown(save, { key: 'ArrowDown' }); expect(document.activeElement).toBe(print);
    fireEvent.keyDown(print, { key: 'Escape' }); expect(screen.queryByRole('menu')).toBeNull(); expect(document.activeElement).toBe(trigger);
    fireEvent.click(trigger); fireEvent.pointerDown(document.body); expect(screen.queryByRole('menu')).toBeNull();
  });

  it('export Markdown giữ đúng phản hồi gốc và thêm URL/ID nguồn thật, không đưa URL nguy hiểm', async () => {
    const text = 'Dữ kiện [web:21]\n\n```js\nconst x = 1;\n```';
    const dangerous = { url: 'javascript:alert(1)', title: 'BAD' };
    expect(responseMarkdown(text)).toBe(text);
    const value = responseMarkdown(text, [...sources, dangerous]);
    expect(value.startsWith(text)).toBe(true); expect(value).toContain('[Báo cáo](<https://example.com/report>) (web:21)'); expect(value).not.toContain('javascript:');
    render(view({ id: 9, role: 'assistant', content: text, sources }));
    fireEvent.click(screen.getByRole('button', { name: 'Thêm thao tác' })); fireEvent.click(screen.getByRole('menuitem', { name: 'Lưu Markdown' }));
    expect(screen.queryByRole('menu')).toBeNull();
    const blob = vi.mocked(URL.createObjectURL).mock.calls[0][0] as Blob;
    expect(await readBlob(blob)).toBe(value);
  });

  it('in xây DOM allowlist, bỏ event/script/URL nguy hiểm và controls, mở toàn bộ code', async () => {
    const root = document.createElement('div');
    root.innerHTML = '<h2 onclick="BAD()">Kết quả</h2><p><a href="javascript:alert(1)">bad</a><a href="https://example.com">safe</a></p><script>BAD()</script><img src="x" onerror="BAD()" alt="Ảnh"><div class="code-block"><div class="code-head">JS<div class="code-actions"><button>Sao chép</button></div></div><pre hidden><code>const a = 1;</code></pre></div><div class="table-actions">Lưu bảng</div>';
    const printable = printableResponse(root);
    expect(printable.querySelector('script,img,button,[onclick],[onerror],[hidden]')).toBeNull();
    expect(printable.querySelector('a')?.getAttribute('href')).toBeNull();
    expect(printable.querySelectorAll('a')[1].getAttribute('href')).toBe('https://example.com');
    expect(printable.textContent).not.toContain('Sao chép'); expect(printable.textContent).toContain('const a = 1;'); expect(root.querySelector('pre')?.hidden).toBe(true);
    const documentCopy = document.implementation.createHTMLDocument();
    const popup = { document: documentCopy, focus: vi.fn(), print: vi.fn(), close: vi.fn(), addEventListener: vi.fn(), closed: false, opener: window };
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);
    await printResponse(root, sources);
    expect(popup.opener).toBeNull(); expect(popup.print).toHaveBeenCalledOnce();
    expect(documentCopy.title).toBe('Peto — Câu trả lời');
    expect(documentCopy.body.querySelectorAll('main')).toHaveLength(1); expect(documentCopy.querySelector('.print-sources')?.textContent).toContain('https://example.com/report');
    expect(documentCopy.querySelector('script,[onclick],img')).toBeNull();
  });

  it('popup bị chặn có thông báo, không cố dùng một API xuất PDF hay LLM', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    render(view({ role: 'assistant', content: '**Nội dung**' }));
    fireEvent.click(screen.getByRole('button', { name: 'Thêm thao tác' })); fireEvent.click(screen.getByRole('menuitem', { name: 'In / lưu PDF' }));
    expect((await screen.findByRole('status')).textContent).toContain('Cho phép cửa sổ bật lên');
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it('quote lịch sử tách khỏi Markdown và article đủ metadata cho selection', () => {
    const jump = vi.fn();
    const { container } = render(view({ id: 22, role: 'user', content: 'Giải thích đoạn này', quoted_source: { message_id: 9, text: 'Đoạn gốc' } }, { onJumpQuote: jump }));
    expect(container.querySelector('article')?.dataset.messageId).toBe('22'); expect(container.querySelector('article')?.dataset.role).toBe('user');
    expect(container.querySelector('[data-message-content]')?.textContent).toBe('Giải thích đoạn này');
    expect(container.querySelector('[data-message-content] .quoted-source')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Về tin nhắn được trích dẫn' })); expect(jump).toHaveBeenCalledWith(9);
  });
});
