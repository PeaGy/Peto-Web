import { useCallback, useRef } from 'react';
import type { HeadBox } from './stageInteraction';
import { BubbleMotion } from './presenceMotion';

/** Renderer cập nhật vị trí trực tiếp theo khung vẽ, không bắt React dựng lại cả Companion mỗi frame. */
export function useThinkingBubble(visible: boolean) {
  const element = useRef<HTMLDivElement>(null);
  const enabled = useRef(visible); enabled.current = visible;
  const motion = useRef(new BubbleMotion());
  const update = useCallback((head: HeadBox | null, width: number, height: number, dt: number, animated: boolean) => {
    const node = element.current;
    if (!node) return;
    if (!enabled.current || !head || width < 88 || height < 58 || head.x + head.width < 0 || head.x > width
      || head.y + head.height < 0 || head.y > height) {
      node.style.visibility = 'hidden'; motion.current.reset(); return;
    }
    const next = motion.current.step(head, width, height, dt, animated);
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
