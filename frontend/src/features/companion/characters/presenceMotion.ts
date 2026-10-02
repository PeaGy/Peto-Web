import { bubblePlacement, type BubbleSide, type HeadBox } from './stageInteraction';

/** Lò xo theo AIRI follow.ts: chậm theo đầu một chút, vượt nhẹ rồi ổn định; chia bước để 24/30/60 FPS có cùng cảm giác. */
export class BubbleMotion {
  private position: { x: number; y: number; side: BubbleSide } | null = null;
  private head: HeadBox | null = null;
  private vx = 0;
  private vy = 0;
  reset() { this.position = null; this.head = null; this.vx = this.vy = 0; }
  step(head: HeadBox, width: number, height: number, seconds: number, animated: boolean) {
    const dt = Math.max(0, Math.min(seconds, 0.1));
    const blend = animated ? 1 - Math.exp(-dt / 0.18) : 1;
    if (!this.head) this.head = { ...head };
    else for (const key of ['x', 'y', 'width', 'height'] as const) this.head[key] += (head[key] - this.head[key]) * blend;
    const target = bubblePlacement(head, width, height, this.position?.side, this.head);
    if (!this.position || !animated) {
      this.vx = this.vy = 0;
      return this.position = target;
    }
    let remaining = dt;
    while (remaining > 0) {
      const step = Math.min(remaining, 1 / 120);
      this.vx += ((target.x - this.position.x) * 170 - this.vx * 20) * step;
      this.vy += ((target.y - this.position.y) * 170 - this.vy * 20) * step;
      this.position.x += this.vx * step; this.position.y += this.vy * step;
      remaining -= step;
    }
    this.position.side = target.side;
    return this.position;
  }
}

/** Giữ quyền nhìn qua đoạn quay về, để con trỏ/idle không giành mắt và làm đầu giật ở khung tiếp theo. */
export class ComposerGaze {
  owned = false;
  private x = 0;
  private y = 0;
  reset() { this.owned = false; this.x = this.y = 0; }
  step(target: { x: number; y: number } | null, normal: { x: number; y: number }, seconds: number) {
    if (target) {
      this.owned = true; this.x = target.x; this.y = target.y;
    } else if (this.owned) {
      const blend = 1 - Math.exp(-Math.max(0, Math.min(seconds, 0.05)) / 0.45);
      this.x += (normal.x - this.x) * blend; this.y += (normal.y - this.y) * blend;
      if (Math.hypot(this.x - normal.x, this.y - normal.y) < 0.004) {
        this.owned = false; this.x = normal.x; this.y = normal.y;
      }
    }
    return { x: this.x, y: this.y };
  }
}
