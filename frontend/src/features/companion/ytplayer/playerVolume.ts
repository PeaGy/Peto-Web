import type { YouTubePlayer } from './youtubeApi';

export const DUCK_FACTOR = 0.2;
const clamp = (value: number) => Math.round(Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0);
type NativeVolume = { volume: number; muted: boolean };
const equal = (a: NativeVolume, b: NativeVolume) => a.volume === b.volume && a.muted === b.muted;

/** The user's setting survives temporary attenuation, native controls and iframe replacement. */
export class PlayerVolume {
  private player: YouTubePlayer | null = null;
  private selected: number;
  private audible: number;
  private ducked = false;
  private expected: NativeVolume | null = null;
  private pending: NativeVolume[] = [];
  private pendingUntil = 0;

  constructor(initial: number) { this.selected = clamp(initial); this.audible = this.selected || 60; }
  get effective() { return this.level(this.selected); }
  get attenuated() { return this.ducked; }
  private level(value: number) { return this.ducked && value > 0 ? Math.max(1, Math.round(value * DUCK_FACTOR)) : value; }
  private native(): NativeVolume | null {
    try {
      if (!this.player) return null;
      const volume = this.player.getVolume(), muted = this.player.isMuted();
      // YouTube clears parts of its info cache while cueing, even after onReady.
      if (typeof volume !== 'number' || !Number.isFinite(volume) || typeof muted !== 'boolean') return null;
      return { volume: clamp(volume), muted };
    }
    catch { return null; }
  }
  attach(player: YouTubePlayer) {
    this.player = player; this.expected = null; this.pending = []; this.apply();
  }
  detach() { this.player = null; this.expected = null; this.pending = []; }
  read() { this.reconcile(); return this.selected; }
  set(value: number) {
    this.selected = clamp(value);
    if (this.selected > 0) this.audible = this.selected;
    this.apply();
  }
  duck(value: boolean) {
    if (value === this.ducked) return;
    // Pick up a native adjustment immediately before restoring/changing the multiplier.
    this.reconcile(); this.ducked = value; this.apply();
  }
  private reconcile() {
    const actual = this.native();
    if (!actual || !this.expected) return;
    if (equal(actual, this.expected)) { this.pending = []; this.pendingUntil = 0; return; }
    // IFrame commands are asynchronous: an old acknowledgement must not overwrite the user's new setting.
    if (Date.now() < this.pendingUntil && this.pending.some(value => equal(value, actual))) return;
    if (actual.muted) this.selected = 0;
    else if (this.selected === 0 && actual.volume === this.expected.volume) this.selected = this.audible;
    else { this.selected = actual.volume; if (this.selected > 0) this.audible = this.selected; }
    this.apply(true);
  }
  private apply(force = false) {
    if (!this.player) return;
    // Keep the underlying nonzero level while muted, so the YouTube mute button can unmute normally.
    const target = { volume: this.level(this.selected || this.audible), muted: this.selected === 0 };
    if (!force && this.expected && equal(this.expected, target)) return;
    const before = this.native();
    if (Date.now() >= this.pendingUntil) this.pending = [];
    if (before) this.pending.push(before, { volume: target.volume, muted: before.muted });
    if (this.expected) this.pending.push(this.expected);
    this.pending = this.pending.slice(-60); this.pendingUntil = Date.now() + 1500;
    this.expected = target;
    try {
      this.player.setVolume(target.volume);
      if (target.muted) this.player.mute(); else this.player.unMute();
    } catch { /* Native observation, rather than this write, confirms a chat volume command. */ }
  }
}
