import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QuoteExcerpt, QuoteSelection, safeQuotedSource, selectedQuote } from '../src/features/chat/QuotedFollowup';
import { validReplyVariants } from '../src/features/chat/replyVariants';

beforeEach(() => {
  Object.defineProperty(Range.prototype, 'getBoundingClientRect', { configurable: true,
    value: () => ({ top: 100, left: 20, bottom: 120, right: 170, width: 150, height: 20 }) });
});
afterEach(() => { window.getSelection()?.removeAllRanges(); vi.useRealTimers(); });

function select(start: Node, end: Node = start, startOffset = 0, endOffset = end.textContent?.length ?? 0) {
  const range = document.createRange(); range.setStart(start, startOffset); range.setEnd(end, endOffset);
  const selection = window.getSelection()!; selection.removeAllRanges(); selection.addRange(range); return selection;
}
function source(role = 'assistant', id = '7', streaming = false) {
  const container = document.createElement('div');
  container.innerHTML = `<article data-role="${role}" data-message-id="${id}" ${streaming ? 'data-streaming="true"' : ''}><div data-message-content><p>Đoạn trả lời gốc</p><button>copy</button><pre><code>const x = 1;</code></pre></div></article>`;
  document.body.append(container); return container;
}

describe('selection scope', () => {
  it('returns exact trimmed text and stored ID only inside one complete assistant response', () => {
    const container = source();
    const text = container.querySelector('p')!.firstChild!;
    expect(selectedQuote(container, select(text))).toMatchObject({ quote: { message_id: 7, text: 'Đoạn trả lời gốc' }, tooLong: false });
    expect(selectedQuote(document.createElement('div'), window.getSelection())).toBeUndefined();
    container.remove();
  });
  it.each([['user', '7', false], ['assistant', '', false], ['assistant', 'NaN', false], ['assistant', '7', true]])(
    'rejects user/local/streaming selections (%s %s %s)', (role, id, streaming) => {
      const container = source(role, id, streaming);
      expect(selectedQuote(container, select(container.querySelector('p')!.firstChild!))).toBeUndefined();
      container.remove();
    });
  it('rejects selections across messages and control-only selections, while code text is valid', () => {
    const container = source(), other = source();
    const first = container.querySelector('p')!.firstChild!, last = other.querySelector('p')!.firstChild!;
    expect(selectedQuote(document.body, select(first, last))).toBeUndefined();
    expect(selectedQuote(container, select(container.querySelector('button')!.firstChild!))).toBeUndefined();
    expect(selectedQuote(container, select(container.querySelector('code')!.firstChild!))).toMatchObject({ quote: { text: 'const x = 1;' } });
    container.remove(); other.remove();
  });
  it('rejects a prose selection that crosses into a Markdown control toolbar', () => {
    const container = source();
    expect(selectedQuote(container, select(container.querySelector('p')!.firstChild!, container.querySelector('button')!.firstChild!))).toBeUndefined();
    container.remove();
  });
  it('rejects a persisted incomplete/stopped assistant even without an active stream', () => {
    const container = source(); container.querySelector('article')!.dataset.quoteable = 'false';
    expect(selectedQuote(container, select(container.querySelector('p')!.firstChild!))).toBeUndefined(); container.remove();
  });
  it('bounds oversized excerpts without allowing them to be submitted', () => {
    const container = source(); container.querySelector('p')!.textContent = 'a'.repeat(2300);
    const quote = selectedQuote(container, select(container.querySelector('p')!.firstChild!))!;
    expect(quote.tooLong).toBe(true); expect(quote.quote.text).toHaveLength(2001);
    expect(safeQuotedSource(quote.quote)).toBeUndefined(); container.remove();
  });
  it('only adds context when explicitly clicked, then clears the selection', async () => {
    vi.useFakeTimers(); const container = source(); const onQuote = vi.fn();
    render(<QuoteSelection containerRef={{ current: container }} disabled={false} onQuote={onQuote} />);
    select(container.querySelector('p')!.firstChild!); fireEvent(document, new Event('selectionchange'));
    act(() => vi.advanceTimersByTime(140));
    const button = screen.getByRole('button', { name: 'Thêm đoạn trích vào câu hỏi' });
    expect(onQuote).not.toHaveBeenCalled(); fireEvent.click(button);
    expect(onQuote).toHaveBeenCalledWith({ message_id: 7, text: 'Đoạn trả lời gốc' });
    expect(window.getSelection()!.rangeCount).toBe(0); container.remove();
  });
  it('disables long selections and hides its popup during a modal or stream', () => {
    vi.useFakeTimers(); const container = source(); container.querySelector('p')!.textContent = 'x'.repeat(2001);
    const onQuote = vi.fn(); const view = render(<QuoteSelection containerRef={{ current: container }} disabled={false} onQuote={onQuote} />);
    select(container.querySelector('p')!.firstChild!); fireEvent(document, new Event('selectionchange')); act(() => vi.advanceTimersByTime(140));
    expect((screen.getByRole('button', { name: 'Chọn tối đa 2.000 ký tự' }) as HTMLButtonElement).disabled).toBe(true);
    view.rerender(<QuoteSelection containerRef={{ current: container }} disabled onQuote={onQuote} />);
    expect(screen.queryByRole('button', { name: 'Chọn tối đa 2.000 ký tự' })).toBeNull();
    const dialog = document.createElement('dialog'); dialog.setAttribute('open', ''); dialog.setAttribute('aria-modal', 'true'); document.body.append(dialog);
    view.rerender(<QuoteSelection containerRef={{ current: container }} disabled={false} onQuote={onQuote} />);
    fireEvent(document, new Event('selectionchange')); act(() => vi.advanceTimersByTime(140));
    expect(screen.queryByRole('button', { name: 'Chọn tối đa 2.000 ký tự' })).toBeNull();
    expect(onQuote).not.toHaveBeenCalled(); container.remove(); dialog.remove();
  });
});

it('quote strip escapes text and exposes jump/remove only when available', () => {
  const onJump = vi.fn(), onRemove = vi.fn(), text = '<img src=x onerror=alert(1)>';
  const view = render(<QuoteExcerpt quote={{ message_id: 7, text }} onJump={onJump} onRemove={onRemove} />);
  expect(view.container.querySelector('img')).toBeNull(); expect(screen.getByText(text)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Về tin nhắn được trích dẫn' })); expect(onJump).toHaveBeenCalledWith(7);
  fireEvent.click(screen.getByRole('button', { name: 'Gỡ đoạn trích' })); expect(onRemove).toHaveBeenCalledOnce();
  view.rerender(<QuoteExcerpt quote={{ message_id: null, text }} onJump={onJump} />);
  expect(screen.queryByRole('button', { name: 'Về tin nhắn được trích dẫn' })).toBeNull(); expect(screen.getByText(text)).toBeTruthy();
  expect(safeQuotedSource({ message_id: null, text })).toEqual({ message_id: null, text, unavailable: true });
});

describe('response family validation', () => {
  const family = { index: 1, choices: [{ conversation_id: 'A', message_id: 2 }, { conversation_id: 'B', message_id: 4 }] };
  it('preserves identity of the current real family and refuses stale indices', () => {
    expect(validReplyVariants(family, 'B', 4)).toBe(family);
    expect(validReplyVariants(family, 'A', 2)).toBeUndefined();
    expect(validReplyVariants(family, 'B', 2)).toBeUndefined();
  });
  it.each([null, {}, { ...family, index: -1 }, { ...family, index: 2 }, { ...family, index: 0.5 },
    { index: 0, choices: [family.choices[0]] }, { index: 0, choices: [family.choices[0], family.choices[0]] },
    { index: 0, choices: [family.choices[0], { conversation_id: '../other', message_id: 3 }] },
    { index: 0, choices: [family.choices[0], { conversation_id: 'C', message_id: 0 }] },
    { index: 0, choices: Array.from({ length: 21 }, (_, i) => ({ conversation_id: `C${i}`, message_id: i + 1 })) }])(
    'rejects malformed/duplicate/oversized families %#', bad => expect(validReplyVariants(bad, 'A', 2)).toBeUndefined());
});
