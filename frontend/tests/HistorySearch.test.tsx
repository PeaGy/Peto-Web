import { useState } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import HistorySearch, { boundedHistoryPreview } from '../src/app/HistorySearch';
import * as api from '../src/shared/api/api';

vi.mock('../src/shared/api/api', async importOriginal => {
  const actual = await importOriginal<typeof import('../src/shared/api/api')>();
  return { ...actual, listConversations: vi.fn(), getConversationPreview: vi.fn() };
});
const rows = ['A', 'B'].map((id, index) => ({ id, title: `Hội thoại ${id}`, created_at: index, updated_at: index, message_count: 2 }));
const preview = (content: string) => ({ messages: [{ id: 2, role: 'assistant' as const, content }], truncated: false });
const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }

beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks();
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  vi.mocked(api.listConversations).mockResolvedValue({ conversations: rows, has_more: false });
  vi.mocked(api.getConversationPreview).mockImplementation(async id => preview(`Nội dung ${id}`));
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

async function open(options: Partial<Parameters<typeof HistorySearch>[0]> = {}) {
  const props = { onClose: vi.fn(), onSelect: vi.fn(), onUnauthorized: vi.fn(), ...options };
  const result = render(<HistorySearch {...props} />);
  await tick(250);
  return { ...result, ...props, input: screen.getByRole('searchbox', { name: 'Tìm trong lịch sử chat' }) };
}

it('ArrowDown/Up xem trước, Enter mở đúng chat và không gọi AI', async () => {
  const { input, onSelect } = await open();
  expect(api.getConversationPreview).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  expect(screen.getByText('Nội dung A')).toBeTruthy();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  expect(screen.getByText('Nội dung B')).toBeTruthy();
  expect(screen.queryByText('Nội dung A')).toBeNull();
  fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
  expect(onSelect).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(onSelect).toHaveBeenCalledExactlyOnceWith('B');
  expect(api.getConversationPreview).toHaveBeenLastCalledWith('B', expect.any(AbortSignal));
});

it('kết quả preview cũ đến muộn không ghi đè chat vừa chọn', async () => {
  const first = deferred<ReturnType<typeof preview>>();
  vi.mocked(api.getConversationPreview).mockImplementation(async id => id === 'A' ? first.promise : preview('Nội dung B mới'));
  const { input } = await open();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  const signal = vi.mocked(api.getConversationPreview).mock.calls[0][1]!;
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  expect(signal.aborted).toBe(true);
  expect(screen.getByText('Nội dung B mới')).toBeTruthy();
  await act(async () => { first.resolve(preview('Dữ liệu A đến muộn')); });
  expect(screen.queryByText('Dữ liệu A đến muộn')).toBeNull();
  expect(screen.getByText('Nội dung B mới')).toBeTruthy();
});

it('đổi query xóa preview ngay, bỏ phản hồi tìm kiếm cũ và hủy request', async () => {
  const old = deferred<{ conversations: api.Conversation[]; has_more: boolean }>();
  vi.mocked(api.listConversations).mockImplementation(async (_offset, _limit, query) => query === 'cũ' ? old.promise : { conversations: rows, has_more: false });
  const { input } = await open();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  fireEvent.change(input, { target: { value: 'cũ' } }); await tick(250);
  expect(screen.queryByText('Nội dung A')).toBeNull();
  const signal = vi.mocked(api.listConversations).mock.calls.at(-1)![4]!;
  fireEvent.change(input, { target: { value: 'mới' } }); await tick(250);
  expect(signal.aborted).toBe(true);
  await act(async () => { old.resolve({ conversations: [{ ...rows[0], title: 'Kết quả sai đã cũ' }], has_more: false }); });
  expect(screen.queryByText('Kết quả sai đã cũ')).toBeNull();
  expect(screen.getByRole('button', { name: 'Hội thoại A' })).toBeTruthy();
});

it('cache chỉ trong dialog, không tải lại preview vừa xem và mất khi đóng', async () => {
  const { input, unmount } = await open();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  fireEvent.keyDown(input, { key: 'ArrowUp' }); await tick(140);
  expect(api.getConversationPreview).toHaveBeenCalledTimes(2);
  unmount();
  const next = await open();
  fireEvent.keyDown(next.input, { key: 'ArrowDown' }); await tick(140);
  expect(api.getConversationPreview).toHaveBeenCalledTimes(3);
});

it('scroll/enter không cướp lựa chọn bàn phím; di chuột thật đổi preview', async () => {
  const { input } = await open();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  const first = screen.getByRole('button', { name: 'Hội thoại A' });
  fireEvent.pointerEnter(first); fireEvent.scroll(screen.getByRole('region', { name: 'Kết quả hội thoại' }));
  expect(screen.getByText('Nội dung B')).toBeTruthy();
  const move = new Event('pointermove', { bubbles: true });
  Object.defineProperties(move, { pointerType: { value: 'mouse' }, clientX: { value: 20 }, clientY: { value: 30 } });
  fireEvent(first, move); await tick(140);
  expect(screen.getByText('Nội dung A')).toBeTruthy();
  expect(api.getConversationPreview).toHaveBeenCalledTimes(2);
});

it('lỗi preview có thể thử lại mà không điều hướng chat', async () => {
  vi.mocked(api.getConversationPreview).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(preview('Đã thử lại thành công'));
  const { input, onSelect } = await open();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  expect(screen.getByRole('alert').textContent).toContain('Không thể xem trước');
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại xem trước' })); await tick(140);
  expect(screen.getByText('Đã thử lại thành công')).toBeTruthy();
  expect(onSelect).not.toHaveBeenCalled();
});

it('unauthorized xóa dữ liệu đang xem và gọi luồng đăng nhập của App', async () => {
  vi.mocked(api.getConversationPreview).mockResolvedValueOnce(preview('Riêng tư A')).mockRejectedValueOnce(new api.UnauthorizedError());
  const { input, onUnauthorized } = await open();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  expect(screen.getByText('Riêng tư A')).toBeTruthy();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  expect(onUnauthorized).toHaveBeenCalledOnce();
  expect(screen.queryByText('Riêng tư A')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Hội thoại A' })).toBeNull();
});

it('Markdown preview không tạo ảnh theo dõi, raw HTML hoặc URL javascript', async () => {
  vi.mocked(api.getConversationPreview).mockResolvedValue(preview('[Nguồn](https://example.com/a)\n\n[Không an toàn](javascript:alert(1))\n\n<img src=x onerror=alert(1)>\n\n![Bản vẽ](https://tracking.example/x)'));
  const { input, container } = await open();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  expect(container.querySelector('img, script, a[href^="javascript:"], [onerror]')).toBeNull();
  expect(screen.getByText('[Ảnh: Bản vẽ]')).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Nguồn' }).getAttribute('rel')).toBe('noopener noreferrer');
});

it('preview chỉ bỏ citation control trong prose assistant, giữ code/link label/user nguyên văn', async () => {
  const content = 'Nội dung **đã đối chiếu [web:21]** và \ue200cite\ue202turn0search1\ue201.\n\n'
    + '`[web:22]`\n\n```txt\n[web:23]\n```\n\n[[web:24]](https://example.com/a)';
  vi.mocked(api.getConversationPreview).mockResolvedValue({ messages: [
    { role: 'user', content: 'Giải thích [web:25]' }, { role: 'assistant', content },
  ], truncated: false });
  const { input, container } = await open();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  const assistant = container.querySelector('.history-preview-message.assistant')!;
  expect(assistant.textContent).not.toContain('[web:21]');
  expect(assistant.textContent).not.toContain('\ue200');
  expect(assistant.querySelectorAll('code')[0].textContent).toBe('[web:22]');
  expect(assistant.querySelectorAll('code')[1].textContent).toContain('[web:23]');
  expect(screen.getByRole('link', { name: '[web:24]' })).toBeTruthy();
  expect(screen.getByText('Giải thích [web:25]')).toBeTruthy();
  expect(content).toContain('[web:21]');
});

it('Escape đóng dialog, trả focus về nút đã mở và hủy preview còn tải', async () => {
  const pending = deferred<ReturnType<typeof preview>>();
  vi.mocked(api.getConversationPreview).mockReturnValue(pending.promise);
  function Harness() {
    const [opened, setOpened] = useState(false);
    return <><button type="button" onClick={() => setOpened(true)}>Mở tìm kiếm</button>{opened && <HistorySearch onClose={() => setOpened(false)} onSelect={() => {}} onUnauthorized={() => {}} />}</>;
  }
  render(<Harness />);
  const trigger = screen.getByRole('button', { name: 'Mở tìm kiếm' }); trigger.focus(); fireEvent.click(trigger); await tick(250);
  const input = screen.getByRole('searchbox', { name: 'Tìm trong lịch sử chat' });
  expect(document.activeElement).toBe(input);
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  const signal = vi.mocked(api.getConversationPreview).mock.calls[0][1]!;
  fireEvent.keyDown(input, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(document.activeElement).toBe(trigger);
  expect(signal.aborted).toBe(true);
});

it('mobile mở preview trước, có Back trả focus và nút mở chat riêng', async () => {
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  const { onSelect, container } = await open();
  const item = screen.getByRole('button', { name: 'Hội thoại A' });
  fireEvent.click(item); await tick(140);
  expect(onSelect).not.toHaveBeenCalled();
  expect(container.querySelector('.showing-preview')).toBeTruthy();
  expect(screen.getByText('Nội dung A')).toBeTruthy();
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Mở hội thoại đang xem trước' }));
  fireEvent.click(screen.getByRole('button', { name: 'Về kết quả tìm kiếm' }));
  expect(container.querySelector('.showing-preview')).toBeNull();
  expect(document.activeElement).toBe(item);
  fireEvent.click(item);
  fireEvent.click(screen.getByRole('button', { name: 'Mở hội thoại đang xem trước' }));
  expect(onSelect).toHaveBeenCalledExactlyOnceWith('A');
});

it('dữ liệu rỗng, tiêu đề dài và CJK/emoji vẫn có nhãn dùng được', async () => {
  vi.mocked(api.listConversations).mockResolvedValue({ conversations: [{ ...rows[0], title: '日本語🙂'.repeat(100) }, { ...rows[1], title: '' }], has_more: false });
  vi.mocked(api.getConversationPreview).mockResolvedValue({ messages: [], truncated: false });
  const { input } = await open();
  expect(screen.getByRole('button', { name: 'Chưa có tiêu đề' })).toBeTruthy();
  fireEvent.keyDown(input, { key: 'ArrowDown' }); await tick(140);
  expect(screen.getByText('Hội thoại chưa có nội dung chữ để xem trước.')).toBeTruthy();
});

it('preview giữ phần cuối có giới hạn và báo cắt thay vì dựng dữ liệu thiếu', () => {
  const result = boundedHistoryPreview({ messages: Array.from({ length: 20 }, (_, index) => ({ role: 'assistant', content: `${index}:` + 'x'.repeat(5000) })), truncated: false });
  expect(result.truncated).toBe(true);
  expect(result.messages.length).toBeLessThanOrEqual(12);
  expect(result.messages.reduce((total, row) => total + row.content.length, 0)).toBeLessThanOrEqual(24_000);
  expect(result.messages.at(-1)!.content.startsWith('19:')).toBe(true);
  expect(boundedHistoryPreview({ messages: [null, {}, { role: 'system', content: 'Secret' }] }).messages).toEqual([]);
});
