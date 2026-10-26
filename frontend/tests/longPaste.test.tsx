import { useRef, useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Composer from '../src/features/chat/Composer';
import PastedTextPreview from '../src/features/chat/PastedTextPreview';
import { LONG_PASTE_CHARS, isPastedTextFile, pasteAtSelection, pastedTextFile } from '../src/features/chat/longPaste';
import { joinDraft } from '../src/features/chat/draftLinks';
import type { DraftFile } from '../src/features/chat/files';

beforeEach(() => { vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => window.setTimeout(() => callback(performance.now()), 0)); });
afterEach(() => vi.unstubAllGlobals());
function read(file: Blob) { return new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsText(file); }); }
const incoming = 'Tiếng Việt 👋\n'.repeat(4000);
function paste(textarea: HTMLElement, text: string, files: File[] = []) {
  const event = new Event('paste', { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'clipboardData', { value: { files, getData: (format: string) => ['text', 'text/plain'].includes(format) ? text : '' } });
  fireEvent(textarea, event); return event;
}

function Harness({ initial = '', reject = false, streaming = false, onFiles = vi.fn(), onSubmit = vi.fn(), context = 'A', quote = false }: {
  initial?: string; reject?: boolean; streaming?: boolean; onFiles?: (files: File[]) => void; onSubmit?: () => void; context?: string; quote?: boolean;
}) {
  const [draft, setDraft] = useState(initial), [files, setFiles] = useState<DraftFile[]>([]);
  const [hasQuote, setHasQuote] = useState(quote);
  return <Composer draft={draft} onDraftChange={setDraft} files={files} onAddFiles={input => {
    const added = Array.from(input); onFiles(added); if (reject) return false;
    setFiles(current => [...current, ...added.map((file, index) => ({ id: `${file.name}-${index}`, file, previewUrl: null }))]); return true;
  }} onRemoveFile={id => setFiles(current => current.filter(file => file.id !== id))} streaming={streaming} stopping={false}
    canSend={Boolean(draft || files.length)} onSubmit={onSubmit} onStop={vi.fn()} effort="low" efforts={[{ value: 'low', label: 'Thấp', hint: '' }]} onEffortChange={vi.fn()}
    webSearch="auto" onToggleWeb={vi.fn()} menuDisabled={false} model="peto" models={[]} onModelChange={vi.fn()}
    formRef={useRef(null)} boxRef={useRef(null)} textareaRef={useRef(null)} fileRef={useRef(null)} contextKey={context}
    quote={hasQuote ? { message_id: 2, text: 'Trích dẫn giữ riêng với chữ đang gõ' } : undefined} onRemoveQuote={() => setHasQuote(false)} />;
}

describe('long paste conversion', () => {
  it('keeps exact Unicode UTF-8 bytes and unique names; ordinary File is not a converted paste', async () => {
    const file = pastedTextFile(incoming, ['pasted-text.txt', 'pasted-text-2.txt']);
    expect(incoming.length).toBeGreaterThan(LONG_PASTE_CHARS);
    expect(file.name).toBe('pasted-text-3.txt'); expect(file.type).toBe('text/plain');
    expect(await read(file)).toBe(incoming); expect(file.size).toBe(new TextEncoder().encode(incoming).length);
    expect(isPastedTextFile(file)).toBe(true); expect(isPastedTextFile(new File([incoming], file.name))).toBe(false);
  });
  it('converts a selected range, preserving surrounding draft and links; Undo restores native paste text/caret', async () => {
    const onFiles = vi.fn(), onSubmit = vi.fn();
    render(<Harness initial={joinDraft('đầu chọn cuối', ['https://example.com/path'])} onFiles={onFiles} onSubmit={onSubmit} quote />);
    const textarea = screen.getByRole('textbox', { name: 'Nhắn cho Peto' }) as HTMLTextAreaElement;
    textarea.focus(); textarea.setSelectionRange(4, 8);
    const event = paste(textarea, incoming);
    expect(event.defaultPrevented).toBe(true); expect(onFiles).toHaveBeenCalledOnce();
    expect(textarea.value).toBe('đầu  cuối'); expect(screen.getByText('Trích dẫn giữ riêng với chữ đang gõ')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Gỡ link example.com › path' })).toBeTruthy();
    expect(await read(onFiles.mock.calls[0][0][0])).toBe(incoming); expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Hoàn tác' }));
    expect(textarea.value).toBe(`đầu ${incoming} cuối`);
    await waitFor(() => expect(textarea.selectionStart).toBe(4 + incoming.length)); expect(textarea.selectionEnd).toBe(4 + incoming.length);
    expect(screen.queryByRole('button', { name: 'Xem pasted-text.txt' })).toBeNull();
    expect(screen.queryByText('Đã thêm nội dung dán thành tệp')).toBeNull();
  });
  it('does not overwrite text typed after conversion when Undo is pressed', () => {
    render(<Harness initial="ban đầu" />); const textarea = screen.getByRole('textbox', { name: 'Nhắn cho Peto' });
    paste(textarea, incoming); fireEvent.change(textarea, { target: { value: 'viết tiếp' } });
    const undo = screen.getByRole('button', { name: 'Hoàn tác' }) as HTMLButtonElement;
    expect(undo.disabled).toBe(true); fireEvent.click(undo);
    expect((textarea as HTMLTextAreaElement).value).toBe('viết tiếp'); expect(screen.getByRole('button', { name: 'Xem pasted-text.txt' })).toBeTruthy();
  });
  it.each([{ text: 'x'.repeat(50_000), reject: false, streaming: false }, { text: incoming, reject: true, streaming: false },
    { text: incoming, reject: false, streaming: true }])('lets ordinary/rejected/streaming paste use native insertion %#', options => {
    const onFiles = vi.fn(); render(<Harness onFiles={onFiles} reject={options.reject} streaming={options.streaming} />);
    const event = paste(screen.getByRole('textbox', { name: 'Nhắn cho Peto' }), options.text);
    expect(event.defaultPrevented).toBe(false);
    expect(onFiles).toHaveBeenCalledTimes(options.reject ? 1 : 0); expect(screen.queryByRole('button', { name: 'Hoàn tác' })).toBeNull();
  });
  it('treats actual clipboard files as attachments without converting accompanying text', () => {
    const onFiles = vi.fn(); render(<Harness onFiles={onFiles} />); const file = new File(['image'], 'photo.png');
    expect(paste(screen.getByRole('textbox', { name: 'Nhắn cho Peto' }), incoming, [file]).defaultPrevented).toBe(true);
    expect(onFiles).toHaveBeenCalledWith([file]); expect(screen.queryByRole('button', { name: 'Hoàn tác' })).toBeNull();
  });
  it('previews converted text as escaped local content, removes the file, and clears Undo', async () => {
    render(<Harness />); paste(screen.getByRole('textbox', { name: 'Nhắn cho Peto' }), `<script>alert(1)</script>${incoming}`);
    fireEvent.click(screen.getByRole('button', { name: 'Xem pasted-text.txt' }));
    await waitFor(() => expect(screen.getByLabelText('Nội dung tệp đã dán').textContent).toContain('<script>alert(1)</script>'));
    expect(screen.getByRole('dialog').querySelector('script')).toBeNull(); fireEvent.click(screen.getByRole('button', { name: 'Đóng xem tệp' }));
    expect(screen.queryByRole('dialog')).toBeNull(); fireEvent.click(screen.getByRole('button', { name: 'Gỡ pasted-text.txt' }));
    expect(screen.queryByRole('button', { name: 'Hoàn tác' })).toBeNull();
  });
  it('clears only transient conversion status on chat scope change', () => {
    const view = render(<Harness context="A" />); paste(screen.getByRole('textbox', { name: 'Nhắn cho Peto' }), incoming);
    expect(screen.getByRole('button', { name: 'Hoàn tác' })).toBeTruthy(); view.rerender(<Harness context="B" />);
    expect(screen.queryByRole('button', { name: 'Hoàn tác' })).toBeNull(); expect(screen.getByRole('button', { name: 'Xem pasted-text.txt' })).toBeTruthy();
  });
  it('removes the quote strip without changing the draft', () => {
    render(<Harness initial="câu hỏi" quote />); fireEvent.click(screen.getByRole('button', { name: 'Gỡ đoạn trích' }));
    expect(screen.queryByText('Trích dẫn giữ riêng với chữ đang gõ')).toBeNull(); expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('câu hỏi');
  });
});

it('bounds only the text preview, preserving the full File', async () => {
  const text = 'a'.repeat(110_000), file = pastedTextFile(text, []);
  render(<PastedTextPreview file={file} onClose={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText('Nội dung tệp đã dán').textContent).toHaveLength(100_000));
  expect(screen.getByText(/tệp đính kèm vẫn giữ toàn bộ nội dung/)).toBeTruthy(); expect(await read(file)).toBe(text);
});

it('normalizes selection bounds when preparing an Undo', () => {
  expect(pasteAtSelection('abcd', 'X', -10, 100)).toEqual({ remaining: '', restored: 'X', caret: 1 });
  expect(pasteAtSelection('abcd', 'X', 3, 1)).toEqual({ remaining: 'abcd', restored: 'abcXd', caret: 4 });
});
