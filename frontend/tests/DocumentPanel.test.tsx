import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, beforeEach, expect, it, vi } from 'vitest';
import DocumentPanel from '../src/features/documents/DocumentPanel';
import * as api from '../src/features/documents/documentApi';
vi.mock('../src/features/documents/documentApi', async original => ({ ...await original<typeof import('../src/features/documents/documentApi')>(), listDocuments: vi.fn(), getDocument: vi.fn(), getSheet: vi.fn(), getWordPreview: vi.fn() }));
import { sheetGrid } from './sheetFixture';
import { preloadLazyParts } from './lazyParts';
beforeAll(preloadLazyParts);
const one: api.SavedDocument = { id: 'D1', conversation_id: 'C1', title: 'Bài văn', version: 1, created_at: 1, content: '# Bài văn\nNội dung', format: 'docx', pages: 3, versions: [{ version: 2, title: 'Bản mới', created_at: 2 }, { version: 1, title: 'Bài văn', created_at: 1 }] };
const two: api.SavedDocument = { ...one, id: 'D2', title: 'Kế hoạch', format: 'pdf', pages: 1 };
const props = { conversationId: 'C1', open: true, expanded: false, selection: null, refreshKey: 0, onClose: vi.fn(), onExpand: vi.fn(), onEdit: vi.fn(), onUnauthorized: vi.fn() };
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [one, two] });
  vi.mocked(api.getDocument).mockImplementation(async id => id === 'D1' ? one : two);
});
it('liệt kê tệp, chuyển tệp, tìm tên và tải đúng phiên bản đang xem', async () => {
  render(<DocumentPanel {...props} />);
  const panel = within(screen.getByRole('complementary', { name: 'Tài liệu trong hội thoại' }));
  expect(await panel.findByRole('img', { name: 'Bài văn — trang 1' })).toBeTruthy();
  fireEvent.click(panel.getByRole('button', { name: 'Trang sau' }));
  expect(panel.getByRole('img').getAttribute('src')).toContain('version=1&page=2');
  expect(panel.getByRole('link', { name: 'Tải Bài văn.docx', exact: true }).getAttribute('href')).toContain('/D1/export/docx?version=1');
  fireEvent.click(panel.getByRole('button', { name: 'Mở Kế hoạch.pdf' }));
  expect(await panel.findByRole('img', { name: 'Kế hoạch — trang 1' })).toBeTruthy();
  expect(panel.getByRole('button', { name: 'Trang sau' })).toHaveProperty('disabled', true);
  fireEvent.change(panel.getByRole('searchbox', { name: 'Tìm tài liệu' }), { target: { value: 'kế hoạch' } });
  expect(panel.queryByRole('button', { name: 'Mở Bài văn.docx' })).toBeNull();
  fireEvent.click(panel.getByRole('button', { name: 'Sửa nội dung' }));
  expect(props.onEdit).toHaveBeenCalledWith(two);
});
it('thẻ trong chat mở bản cũ, có thể chọn lại bản mới đã sửa', async () => {
  vi.mocked(api.getDocument).mockResolvedValueOnce(one).mockResolvedValueOnce({ ...one, version: 2, content: '# Bản sửa\nNội dung đã sửa', format: null, pages: null });
  render(<DocumentPanel {...props} selection={{ id: 'D1', version: 1, key: 1 }} />);
  await screen.findByRole('img');
  expect(api.getDocument).toHaveBeenCalledWith('D1', 1, expect.any(AbortSignal));
  fireEvent.click(screen.getByRole('combobox', { name: 'Phiên bản xem trước' }));
  fireEvent.click(screen.getByRole('option', { name: 'Phiên bản 2' }));
  expect((await screen.findByRole('article', { name: 'Nội dung tài liệu' })).textContent).toContain('Nội dung đã sửa');
  expect(screen.getByRole('link', { name: 'Tải Bài văn.docx', exact: true }).getAttribute('href')).toContain('version=2');
});
it('không hiển thị phản hồi đến muộn của tệp trước khi đã chọn tệp khác', async () => {
  let resolve!: (value: api.SavedDocument) => void;
  vi.mocked(api.getDocument).mockImplementation(id => id === 'D1' ? new Promise(done => { resolve = done; }) : Promise.resolve(two));
  render(<DocumentPanel {...props} />);
  await waitFor(() => expect(api.getDocument).toHaveBeenCalled());
  fireEvent.click(await screen.findByRole('button', { name: 'Mở Kế hoạch.pdf' }));
  await screen.findByRole('img', { name: 'Kế hoạch — trang 1' });
  await act(async () => resolve(one));
  expect(screen.queryByRole('img', { name: 'Bài văn — trang 1' })).toBeNull();
});
it('danh sách lỗi có thể thử lại, không làm mất lối đóng panel', async () => {
  vi.mocked(api.listDocuments).mockRejectedValueOnce(new Error('Offline'));
  render(<DocumentPanel {...props} />);
  const error = await screen.findByRole('alert');
  fireEvent.click(within(error).getByRole('button', { name: 'Thử lại' }));
  expect(await screen.findByRole('button', { name: 'Mở Bài văn.docx' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Đóng bảng tài liệu' }));
  expect(props.onClose).toHaveBeenCalled();
});
it('giao diện điện thoại dùng hộp thoại, chọn tệp xong nhường màn hình cho trang xem', async () => {
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  try {
    render(<DocumentPanel {...props} />);
    expect(screen.getByRole('dialog', { name: 'Tài liệu trong hội thoại' }).getAttribute('aria-modal')).toBe('true');
    fireEvent.click(await screen.findByRole('button', { name: 'Mở Kế hoạch.pdf' }));
    await screen.findByRole('img', { name: 'Kế hoạch — trang 1' });
    expect(screen.queryByRole('navigation', { name: 'Danh sách tài liệu' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Hiện danh sách tệp' }));
    expect(screen.getByRole('navigation', { name: 'Danh sách tài liệu' })).toBeTruthy();
  } finally { vi.unstubAllGlobals(); }
});

it('bài thuyết trình lật theo slide và hiện ghi chú cho người thuyết trình của đúng slide', async () => {
  const deck: api.SavedDocument = { ...one, id: 'P1', title: 'Thư viện số', format: 'pptx', pages: 2, style: 'clean',
    content: JSON.stringify({ title: 'Thư viện số', theme: 'clean', slides: [{ layout: 'cover', title: 'Bìa', notes: 'Chào thầy cô.' }, { layout: 'bullets', title: 'Bài toán', bullets: ['a'] }] }) };
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [deck] });
  vi.mocked(api.getDocument).mockResolvedValue(deck);
  render(<DocumentPanel {...props} />);
  const panel = within(screen.getByRole('complementary', { name: 'Tài liệu trong hội thoại' }));
  const notes = await panel.findByRole('region', { name: 'Ghi chú cho người thuyết trình' });
  expect(notes.textContent).toContain('Chào thầy cô.');
  expect(panel.getByText('Slide 1 / 2')).toBeTruthy();
  fireEvent.click(panel.getByRole('button', { name: 'Slide sau' }));
  expect(panel.getByRole('img').getAttribute('src')).toContain('page=2');
  expect(panel.getByRole('region', { name: 'Ghi chú cho người thuyết trình' }).textContent).toContain('Slide này không có ghi chú.');
  expect(panel.getByRole('link', { name: 'Tải PDF' }).getAttribute('href')).toContain('/P1/export/pdf?version=1');
  expect(panel.getByRole('link', { name: 'Tải Thư viện số.pptx', exact: true }).getAttribute('href')).toContain('/P1/export/pptx?version=1');
  expect(panel.queryByRole('button', { name: 'Sửa nội dung' })).toBeNull();
  expect(panel.getByRole('button', { name: 'Mở Thư viện số.pptx' }).textContent).toContain('2 slide');
});

it('bảng tính mở lưới kiểu Excel: thanh công thức theo ô chọn, phím mũi tên, hiện công thức, tab trang tính và biểu đồ', async () => {
  const book: api.SavedDocument = { ...one, id: 'X1', title: 'Bảng điểm', format: 'xlsx', pages: 2, style: 'sheet', content: '{}',
    versions: [{ version: 1, title: 'Bảng điểm', created_at: 1 }] };
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [book] });
  vi.mocked(api.getDocument).mockResolvedValue(book);
  vi.mocked(api.getSheet).mockResolvedValue(sheetGrid);
  render(<DocumentPanel {...props} />);
  const panel = within(screen.getByRole('complementary', { name: 'Tài liệu trong hội thoại' }));
  const grid = await panel.findByRole('region', { name: 'Lưới trang tính Bảng điểm' });
  expect(api.getSheet).toHaveBeenCalledWith('X1', 1, expect.any(AbortSignal));
  // Mở ra là chọn ô công thức đầu tiên, để thấy ngay công thức.
  expect(panel.getByLabelText('Ô đang chọn').textContent).toBe('C2');
  expect(panel.getByLabelText('Nội dung ô').textContent).toBe('=ROUND((B2*2+8)/3,1)= 7,8');
  fireEvent.keyDown(grid, { key: 'ArrowDown' });
  expect(panel.getByLabelText('Ô đang chọn').textContent).toBe('C3');
  fireEvent.click(panel.getByText('Trung bình lớp'));
  expect(panel.getByLabelText('Ô đang chọn').textContent).toBe('A4');
  expect(panel.getByLabelText('Nội dung ô').textContent).toBe('Trung bình lớp');
  fireEvent.keyDown(grid, { key: '`', ctrlKey: true });
  expect(panel.getByRole('button', { name: 'Công thức' }).getAttribute('aria-pressed')).toBe('true');
  expect(panel.getByText('=AVERAGE(C2:C3)')).toBeTruthy();
  expect(panel.queryByRole('combobox', { name: 'Phiên bản xem trước' })).toBeNull();
  expect(panel.getByRole('link', { name: 'Tải Bảng điểm.xlsx', exact: true }).getAttribute('href')).toContain('/X1/export/xlsx?version=1');
  expect(panel.queryByRole('link', { name: 'Tải PDF' })).toBeNull();
  fireEvent.click(panel.getByRole('tab', { name: /Thống kê/ }));
  expect(await panel.findByRole('region', { name: 'Lưới trang tính Thống kê' })).toBeTruthy();
  expect(panel.getByRole('img', { name: 'Biểu đồ: Số học sinh theo xếp loại' })).toBeTruthy();
  expect(panel.getByRole('img', { name: 'Biểu đồ: Tỉ lệ xếp loại' }).textContent).toContain('50%');
  expect(panel.getByLabelText('Nội dung ô').textContent).toContain("=COUNTIF('Bảng điểm'!C2:C3");
  expect(panel.getByText(/Bấm một ô để xem công thức/)).toBeTruthy();
});

it('mở bảng tính từ thẻ trong chat thì thu danh sách tệp để lưới đủ chỗ', async () => {
  const book: api.SavedDocument = { ...one, id: 'X1', title: 'Bảng điểm', format: 'xlsx', pages: 2, style: 'sheet', content: '{}',
    versions: [{ version: 1, title: 'Bảng điểm', created_at: 1 }] };
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [book, one] });
  vi.mocked(api.getDocument).mockImplementation(async id => id === 'X1' ? book : one);
  vi.mocked(api.getSheet).mockResolvedValue(sheetGrid);
  render(<DocumentPanel {...props} selection={{ id: 'X1', version: 1, key: 7 }} />);
  await screen.findByRole('region', { name: 'Lưới trang tính Bảng điểm' });
  expect(screen.queryByRole('navigation', { name: 'Danh sách tài liệu' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Hiện danh sách tệp' }));
  expect(screen.getByRole('navigation', { name: 'Danh sách tài liệu' })).toBeTruthy();
});

it('tệp Word Peto đã sửa: danh sách thay đổi trỏ đúng chỗ theo mã dấu sửa, phần chèn và xóa được tô, chỉ tải DOCX', async () => {
  const edited: api.SavedDocument = { ...one, id: 'W1', title: 'Bài tập 05', format: 'docx', pages: 0, style: 'wordedit', version: 2,
    content: 'x', versions: [{ version: 2, title: 'Bài tập 05', created_at: 2 }, { version: 1, title: 'Bài tập 05', created_at: 1 }] };
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [edited, one] });
  vi.mocked(api.getDocument).mockImplementation(async id => id === 'W1' ? edited : one);
  const scrolled: string[] = [];
  Element.prototype.scrollIntoView = function (this: Element) { scrolled.push(this.textContent ?? ''); };
  vi.mocked(api.getWordPreview).mockResolvedValue({ kind: 'word', title: 'Bài tập 05', truncated: false, blocks: [
    { type: 'p', number: 1, parts: [{ text: 'Ghi chú cũ', state: 'del' }], state: 'del', revs: [3] },
    { type: 'p', number: 2, label: 'a)', parts: [{ text: 'Lập bảng giá trị của F.' }] },
    // Lời giải của lần sửa trước (mã 1–2) và của lần này (mã 4–6): dòng thay đổi của lần này phải tới khối sau.
    { type: 'p', number: 3, parts: [{ text: 'Lời giải cũ', state: 'ins' }], state: 'ins', revs: [1, 2] },
    { type: 'p', number: 4, parts: [{ text: 'Ta có ', state: 'ins' }, { math: '\overline{x}', display: false, state: 'ins' }], state: 'ins', revs: [4, 5] },
    { type: 'table', rows: [{ state: 'ins', cells: [{ parts: [{ text: 'x', state: 'ins' }] }, { parts: [{ text: 'F', state: 'ins' }] }] }], revs: [6] },
  ], changes: [{ text: 'Xóa Đoạn 1', revs: [3, 3] }, { text: 'Chèn sau Đoạn 2: 1 đoạn, 1 bảng', revs: [4, 6] }, { text: 'Xóa Đoạn 9', revs: [] }] });
  render(<DocumentPanel {...props} selection={{ id: 'W1', version: 2, key: 3 }} />);
  const log = await screen.findByRole('region', { name: 'Peto đã sửa' });
  expect(screen.queryByRole('navigation', { name: 'Danh sách tài liệu' })).toBeNull();
  expect(within(log).getAllByRole('button').slice(1).map(button => button.textContent)).toEqual(['Đoạn 1Xóa đoạn', 'Đoạn 2Chèn 1 đoạn, 1 bảng', 'Đoạn 9Xóa đoạn']);
  expect((within(log).getByRole('button', { name: 'Đoạn 9Xóa đoạn' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(within(log).getByRole('button', { name: 'Đoạn 2Chèn 1 đoạn, 1 bảng' }));
  expect(scrolled[0]).toContain('Ta có');
  const doc = screen.getByLabelText('Nội dung Bài tập 05');
  expect(doc.querySelectorAll('.wv-active')).toHaveLength(2);
  expect(doc.querySelector('.wv-del')?.textContent).toBe('Ghi chú cũ');
  expect(doc.querySelector('.katex')).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Tải Bài tập 05.docx' }).getAttribute('href')).toBe('/api/documents/W1/export/docx?version=2');
  expect(screen.queryByRole('button', { name: 'Sửa nội dung' })).toBeNull();
  expect(screen.getByText(/Accept All Changes/)).toBeTruthy();
  expect(api.getWordPreview).toHaveBeenCalledWith('W1', 2, expect.anything());
});
