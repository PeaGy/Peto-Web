/**
 * Adapted from Project AIRI's sway-sine trajectory and beat-sync spring.
 * Copyright (c) 2024-PRESENT Neko Ayaka. MIT license; see public/vendor/beat-sync/AIRI-LICENSE.txt.
 * Peto adaptation: framework-independent offsets, seconds-based bounded integration,
 * fixed substeps for stable 30/60 Hz rendering, no modification of other character effects.
 */
type Point = { pitch: number; roll: number };
type Segment = { start: number; duration: number; from: Point; to: Point };
const zero = (): Point => ({ pitch: 0, roll: 0 });

export class BeatPulse {
  private lastBeat: number | undefined;
  private lastFrame: number | undefined;
  private side = -1;
  private started = false;
  private segments: Segment[] = [];
  private target = zero();
  private position = zero();
  private velocity = zero();

  beat(now: number) {
    this.advance(now);
    if (this.lastBeat === undefined || now - this.lastBeat > 1800) {
      this.started = false; this.side = -1; this.lastBeat = now;
      return;
    }
    const interval = Math.min(2000, Math.max(220, now - this.lastBeat));
    this.lastBeat = now;
    const from = { ...this.target };
    if (!this.started) {
      this.segments = [{ start: now, duration: interval / 2, from, to: { pitch: -10, roll: 10 } }];
      this.started = true;
    } else {
      this.side *= -1;
      const apex = { pitch: 0, roll: 10 };
      this.segments = [
        { start: now, duration: interval / 2, from, to: apex },
        { start: now + interval / 2, duration: interval / 2, from: apex, to: { pitch: this.side * 10, roll: 10 } },
      ];
    }
  }

  private updateTarget(now: number) {
    while (this.segments.length) {
      const segment = this.segments[0];
      if (now < segment.start) break;
      const progress = Math.min(1, (now - segment.start) / segment.duration);
      const eased = 1 - (1 - progress) ** 3;
      this.target = {
        pitch: segment.from.pitch + (segment.to.pitch - segment.from.pitch) * eased,
        roll: segment.from.roll + (segment.to.roll - segment.from.roll) * eased,
      };
      if (progress < 1) break;
      this.segments.shift();
    }
    if (this.lastBeat !== undefined && now - this.lastBeat > 1800 && !this.segments.length) {
      this.target = zero(); this.started = false;
    }
  }

  private advance(now: number) {
    if (this.lastFrame === undefined) { this.lastFrame = now; return; }
    if (now <= this.lastFrame) return;
    // Do not replay seconds of animation after a hidden tab resumes.
    let time = Math.max(this.lastFrame, now - 250);
    while (time < now) {
      const step = Math.min(1000 / 120, now - time);
      time += step;
      this.updateTarget(time);
      const dt = step / 1000;
      for (const axis of ['pitch', 'roll'] as const) {
        const acceleration = 120 * (this.target[axis] - this.position[axis]) - 16 * this.velocity[axis];
        this.velocity[axis] += acceleration * dt;
        this.position[axis] += this.velocity[axis] * dt;
        if (Math.abs(this.target[axis] - this.position[axis]) < 0.001 && Math.abs(this.velocity[axis]) < 0.001) {
          this.position[axis] = this.target[axis]; this.velocity[axis] = 0;
        }
      }
    }
    this.lastFrame = now;
  }

  pose(now: number, strength: number) {
    this.advance(now);
    const amount = Math.max(0, Math.min(1, strength));
    return { yaw: 0, pitch: this.position.pitch * amount, roll: this.position.roll * amount };
  }
}
