/** Small, smooth eye offsets. Uses frame time so hidden tabs never accumulate catch-up motion. */
export class IdleEyes {
  private remaining = 0;
  private x = 0;
  private y = 0;
  private targetX = 0;
  private targetY = 0;
  constructor(private random: () => number = Math.random) {}
  step(seconds: number, enabled: boolean) {
    const dt = Math.max(0, Math.min(seconds, 0.05));
    if (enabled) {
      this.remaining -= dt;
      if (this.remaining <= 0) {
        this.remaining = 2 + this.random() * 3;
        const center = this.random() < 0.3;
        this.targetX = center ? 0 : (this.random() * 2 - 1) * 0.35;
        this.targetY = center ? 0 : (this.random() * 2 - 1) * 0.18;
      }
    } else {
      this.remaining = 0;
      this.targetX = this.targetY = 0;
    }
    const blend = 1 - Math.exp(-dt / 0.22);
    this.x += (this.targetX - this.x) * blend;
    this.y += (this.targetY - this.y) * blend;
    return { x: this.x, y: this.y };
  }
}
