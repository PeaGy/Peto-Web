import type { RefObject } from 'react';

export interface ComposerAttention { typing: boolean; input: RefObject<HTMLTextAreaElement | null> }
export interface HeadBox { x: number; y: number; width: number; height: number }
export type BubbleSide = 'above' | 'left' | 'right';

/** Theo cách AIRI đặt bong bóng: ưu tiên trên đầu, giữ phía đã chọn để tránh rung ở mép khung. */
export function bubblePlacement(head: HeadBox, width: number, height: number, previous?: BubbleSide, decision = head) {
  const w = 72, h = 42, gap = 14, margin = 8;
  const room = { above: decision.y - gap - margin, left: decision.x - gap - margin,
    right: width - margin - decision.x - decision.width - gap };
  const side: BubbleSide = room.above >= h + 6 ? 'above'
    : previous && room[previous] >= (previous === 'above' ? h : w) - 6 ? previous
      : room.right >= room.left ? 'right' : 'left';
  const x = side === 'above' ? head.x + head.width / 2 - w / 2
    : side === 'right' ? head.x + head.width + gap : head.x - gap - w;
  const y = side === 'above' ? head.y - gap - h : head.y + head.height * 0.25 - h;
  return { x: Math.max(margin, Math.min(x, width - w - margin)),
    y: Math.max(margin, Math.min(y, height - h - margin)), side };
}

/** Chỉ nhận thao tác gõ thực, không coi chữ từ micro hay chữ nháp cũ là đang gõ. */
export function composerPoint(attention: ComposerAttention | undefined, enabled: boolean, compact: boolean, moving: boolean) {
  const input = attention?.input.current;
  if (!enabled || compact || !moving || !attention?.typing || !input || input.disabled || input.readOnly
    || document.activeElement !== input || !document.hasFocus()) return null;
  const rect = input.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}
