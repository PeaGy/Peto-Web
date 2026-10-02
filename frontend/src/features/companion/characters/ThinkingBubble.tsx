import { useCallback, useRef } from 'react';
import { bubblePlacement, type BubbleSide, type HeadBox } from './stageInteraction';

/** Renderer cập nhật vị trí trực tiếp theo khung vẽ, không bắt React dựng lại cả Companion mỗi frame. */
export function useThinkingBubble(visible: boolean) {
  const element = useRef<HTMLDivElement>(null);
  const enabled = useRef(visible); enabled.current = visible;
  const position = useRef<{ x: number; y: number; side: BubbleSide } | null>(null);
  const update = useCallback((head: HeadBox | null, width: number, height: number, dt: number, animated: boolean) => {
    const node = element.current;
    if (!node) return;
    if (!enabled.current || !head || width < 88 || height < 58 || head.x + head.width < 0 || head.x > width
      || head.y + head.height < 0 || head.y > height) {
      node.style.visibility = 'hidden'; position.current = null; return;
    }
    const target = bubblePlacement(head, width, height, position.current?.side);
    const previous = position.current;
    const blend = animated && previous ? 1 - Math.exp(-Math.min(dt, 0.05) * 16) : 1;
    const next = { x: previous ? previous.x + (target.x - previous.x) * blend : target.x,
      y: previous ? previous.y + (target.y - previous.y) * blend : target.y, side: target.side };
    position.current = next;
    node.dataset.side = next.side;
    node.dataset.animated = String(animated);
    node.style.transform = `translate3d(${next.x}px, ${next.y}px, 0)`;
    node.style.visibility = 'visible';
  }, []);
  return { element, update };
}

export default function ThinkingBubble({ bubble, visible }: { bubble: ReturnType<typeof useThinkingBubble>; visible: boolean }) {
  return <div ref={bubble.element} className="character-thinking-bubble" hidden={!visible}
    role="status" aria-label="Peto đang nghĩ và trả lời" style={{ visibility: 'hidden' }}>
    <span aria-hidden="true"><i /><i /><i /></span>
  </div>;
}
