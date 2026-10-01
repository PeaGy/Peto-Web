export type CompanionActivity = 'idle' | 'listening' | 'thinking' | 'speaking';

/** Blend small additive poses; authored idle motions and lip sync remain independent. */
export class CompanionMotion {
  private thinking = 0;
  private speaking = 0;
  private listening = 0;
  private time = 0;
  step(activity: CompanionActivity, deltaSeconds: number, mouth: number) {
    const dt = Math.max(0, Math.min(0.05, deltaSeconds));
    const blend = 1 - Math.exp(-dt / 0.35);
    this.thinking += ((activity === 'thinking' ? 1 : 0) - this.thinking) * blend;
    this.speaking += ((activity === 'speaking' ? 1 : 0) - this.speaking) * blend;
    this.listening += ((activity === 'listening' ? 1 : 0) - this.listening) * blend;
    this.time += dt;
    return {
      pitch: this.thinking * 2 + this.listening * -1 + this.speaking * Math.sin(this.time * 3) * Math.max(0, Math.min(1, mouth)) * 1.5,
      roll: this.thinking * 1.5,
      musicWeight: 1 - this.thinking * 0.55 - this.speaking * 0.65 - this.listening * 0.25,
    };
  }
}
export const stageQuality = (compact: boolean, pixelRatio: number, quality = { sharp: false, smooth: false }) => ({
  fps: compact ? (quality.smooth ? 60 : 24) : 30,
  resolution: Math.min(pixelRatio || 1, compact ? (quality.sharp ? 2 : 1) : 1.5),
});
