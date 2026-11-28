import { useEffect, useRef, useState } from 'react';

/** Lâu nhất giữa hai lần vẽ khi câu trả lời đang chạy. */
const MAX_WAIT = 1500;
/** Chờ gấp mấy lần thời gian lần vẽ trước. */
const COST_RATE = 2;

/**
 * Chữ của câu trả lời đang chạy, vẽ thưa theo độ nặng (27/11/2026, ý từ `useThrottleMarkdownRender` của deepseek-ai/chat-demo).
 *
 * Mỗi mảnh chữ mới làm cả câu trả lời dựng lại Markdown, công thức, code và bảng; câu trả lời dài thì mỗi lần một lâu
 * hơn mà số lần cũng nhiều hơn. Hook đo lần vẽ trước mất bao lâu và chờ gấp đôi chừng đó (tối đa 1.5 giây) mới vẽ lại,
 * gộp các mảnh tới trong lúc chờ. Câu trả lời ngắn vẽ nhẹ nên gần như mảnh nào cũng hiện ngay. `active` tắt (xong lượt,
 * dừng, tin cũ) thì trả ngay chữ mới nhất.
 */
export function useStreamingText(content: string, active: boolean): string {
  const [shown, setShown] = useState(content);
  const renderStart = useRef(performance.now());
  const nextAt = useRef(0);
  const latest = useRef(content);
  latest.current = content;

  // Vẽ xong một bản: lần sau được vẽ sau gấp đôi thời gian vừa tốn.
  useEffect(() => {
    const now = performance.now();
    nextAt.current = now + Math.min(MAX_WAIT, (now - renderStart.current) * COST_RATE);
  }, [shown]);

  useEffect(() => {
    if (!active || content === shown) return;
    const show = () => {
      renderStart.current = performance.now();
      setShown(latest.current);
    };
    const wait = nextAt.current - performance.now();
    if (wait <= 0) {
      show();
      return;
    }
    const timer = window.setTimeout(show, wait);
    return () => window.clearTimeout(timer);
  }, [content, active, shown]);

  return active ? shown : content;
}
