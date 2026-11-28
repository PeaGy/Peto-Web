import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useStreamingText } from '../src/features/chat/useStreamingText';

// Chữ của câu trả lời đang chạy vẽ thưa theo độ nặng (27/11/2026): lần sau chờ gấp đôi thời gian lần vẽ trước, tối đa
// 1.5 giây, gộp các mảnh tới trong lúc chờ; xong lượt thì hiện đủ ngay.

let clock = 0;
let renderCost = 0;
let drawn: string | null = null;

function Probe({ content, active }: { content: string; active: boolean }) {
  const shown = useStreamingText(content, active);
  // Chỉ lần vẽ ra chữ mới mới "tốn" renderCost mili giây, như dựng lại Markdown.
  if (shown !== drawn) { clock += renderCost; drawn = shown; }
  return <p data-testid="shown">{shown}</p>;
}

beforeEach(() => {
  clock = 1000;
  renderCost = 0;
  drawn = null;
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  vi.spyOn(performance, 'now').mockImplementation(() => clock);
});
afterEach(() => { vi.useRealTimers(); });

const shown = () => screen.getByTestId('shown').textContent;

describe('useStreamingText', () => {
  it('vẽ nhẹ thì mảnh nào cũng hiện ngay', () => {
    const view = render(<Probe content="A" active />);
    view.rerender(<Probe content="AB" active />);
    expect(shown()).toBe('AB');
    view.rerender(<Probe content="ABC" active />);
    expect(shown()).toBe('ABC');
  });

  it('vẽ nặng thì chờ gấp đôi thời gian vẽ, gộp các mảnh tới trong lúc chờ', () => {
    renderCost = 100;
    // Lần vẽ đầu tốn ~100ms: các mảnh tới ngay sau phải chờ ~200ms.
    const view = render(<Probe content="A" active />);
    view.rerender(<Probe content="AB" active />);
    view.rerender(<Probe content="ABC" active />);
    expect(shown()).toBe('A');
    act(() => { clock += 250; vi.advanceTimersByTime(250); });
    expect(shown()).toBe('ABC');
  });

  it('không chờ quá 1.5 giây dù lần vẽ rất nặng', () => {
    renderCost = 5000;
    const view = render(<Probe content="A" active />);
    view.rerender(<Probe content="AB" active />);
    expect(shown()).toBe('A');
    act(() => { vi.advanceTimersByTime(1499); });
    expect(shown()).toBe('A');
    act(() => { vi.advanceTimersByTime(1); });
    expect(shown()).toBe('AB');
  });

  it('xong lượt (tắt) thì hiện đủ chữ ngay, không chờ', () => {
    renderCost = 100;
    const view = render(<Probe content="A" active />);
    view.rerender(<Probe content="AB" active />);
    expect(shown()).toBe('A');
    view.rerender(<Probe content="ABCD" active={false} />);
    expect(shown()).toBe('ABCD');
  });
});
