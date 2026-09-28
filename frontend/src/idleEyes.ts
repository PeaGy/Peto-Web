/** Small, smooth eye offsets. Uses frame time so hidden tabs never accumulate catch-up motion. */
export class IdleEyes {
  private remaining = 0;
  private x = 0;
  private y = 0;
  private targetX = 0;
  private targetY = 0;
  private weight = 0;
  constructor(private random: () => number = Math.random) {}
  step(seconds: number, enabled: boolean) {
    const dt = Math.max(0, Math.min(seconds, 0.05));
    if (enabled) {
      this.remaining -= dt;
      if (this.remaining <= 0) {
        this.remaining = 0.8 + this.random() * 3.6;
        const center = this.random() < 0.3;
        this.targetX = center ? 0 : (this.random() * 2 - 1) * 0.9;
        this.targetY = center ? 0 : -0.7 + this.random() * 1.2;
      }
    } else {
      this.remaining = 0;
      this.targetX = this.targetY = 0;
    }
    const blend = 1 - Math.exp(-dt / 0.22);
    this.x += (this.targetX - this.x) * blend;
    this.y += (this.targetY - this.y) * blend;
    this.weight += ((enabled ? 1 : 0) - this.weight) * blend;
    return { x: this.x, y: this.y, weight: this.weight };
  }
}

const CLOSE = 0.08, SHUT = 0.05, OPEN = 0.15;

/** Chớp mắt cho VRM (Live2D đã có chớp mắt của model): cách nhau 1,5–6 giây ngẫu nhiên, thỉnh thoảng chớp hai lần liền. */
export class Blinker {
  private wait: number;
  private time = -1;
  private again = false;
  constructor(private random: () => number = Math.random) { this.wait = this.pause(); }
  private pause() { return 1.5 + this.random() * 4.5; }
  /** Độ nhắm mắt 0..1 của khung hình này. */
  step(seconds: number) {
    const dt = Math.max(0, Math.min(seconds, 0.05));
    if (this.time < 0) {
      this.wait -= dt;
      if (this.wait > 0) return 0;
      this.time = 0;
    } else {
      this.time += dt;
    }
    if (this.time >= CLOSE + SHUT + OPEN) {
      this.time = -1;
      this.again = !this.again && this.random() < 0.2;
      this.wait = this.again ? 0.1 : this.pause();
      return 0;
    }
    if (this.time < CLOSE) return this.time / CLOSE;
    return this.time < CLOSE + SHUT ? 1 : 1 - (this.time - CLOSE - SHUT) / OPEN;
  }
}
