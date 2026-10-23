/** Native-tool protocol. This state belongs to this Companion instance, never localStorage or another tab. */
export type PlayerAction = 'status' | 'open' | 'hide' | 'close' | 'play' | 'pause' | 'next' | 'restart'
  | 'seek' | 'set_volume' | 'mute' | 'unmute' | 'set_shuffle' | 'set_repeat';
export interface PlayerCommand {
  id: string; expires_at: number; action: PlayerAction; volume?: number; seconds?: number; enabled?: boolean; repeat?: 'off' | 'all' | 'one';
}
export interface PlayerSnapshot {
  window: 'closed' | 'visible' | 'hidden';
  status: 'empty' | 'loading' | 'ready' | 'playing' | 'paused' | 'buffering' | 'ended' | 'blocked' | 'suspended' | 'error';
  track: { video_id: string; title: string; artist: string } | null;
  position: number; duration: number; volume: number; shuffle: boolean; repeat: 'off' | 'all' | 'one'; queue_count: number;
}
export interface PlayerResult { ok: boolean; state?: PlayerSnapshot; error?: string }
export type PlayerExecutor = (command: PlayerCommand, signal: AbortSignal) => Promise<PlayerResult>;
export const emptyPlayer = (): PlayerSnapshot => ({ window: 'closed', status: 'empty', track: null,
  position: 0, duration: 0, volume: 60, shuffle: false, repeat: 'off', queue_count: 0 });

export async function waitForPlayer<T>(read: () => T | undefined, signal: AbortSignal, available: () => boolean) {
  const until = performance.now() + 8000;
  while (true) {
    signal.throwIfAborted();
    if (!available()) throw new Error('Companion không còn ở phía trước; thao tác chưa được xác nhận.');
    const result = read();
    if (result !== undefined) return result;
    if (performance.now() >= until) throw new Error('Player chưa xác nhận thao tác. Không tự lặp lại lệnh; hãy kiểm tra trạng thái.');
    await new Promise(resolve => window.setTimeout(resolve, 40));
  }
}

export class PlayerControlBridge {
  private target: PlayerExecutor | null = null;
  private results = new Map<string, Promise<PlayerResult>>();
  register = (target: PlayerExecutor) => {
    this.target = target;
    return () => { if (this.target === target) this.target = null; };
  };
  constructor(private show: () => void, private available: () => boolean) {}
  run = (command: PlayerCommand, signal: AbortSignal): Promise<PlayerResult> => {
    // SSE duplication must not skip two tracks or restart twice.
    const existing = this.results.get(command.id);
    if (existing) return existing;
    const operation = this.execute(command, signal).catch(reason => ({ ok: false,
      error: reason instanceof Error ? reason.message.slice(0, 500) : 'Chưa điều khiển được Player.' }));
    if (this.results.size >= 100) this.results.delete(this.results.keys().next().value!);
    this.results.set(command.id, operation);
    return operation;
  };
  private async execute(command: PlayerCommand, signal: AbortSignal): Promise<PlayerResult> {
    signal.throwIfAborted();
    if (!Number.isFinite(command.expires_at) || command.expires_at <= Date.now()) return { ok: false, error: 'Lệnh Player đã hết hạn; chưa thực hiện.' };
    if (!this.available()) return { ok: false, error: 'Hãy quay lại Companion để điều khiển Player.' };
    if (!this.target) {
      if (['status', 'hide', 'close'].includes(command.action)) return { ok: true, state: emptyPlayer() };
      if (command.action !== 'open') return { ok: false, state: emptyPlayer(), error: 'Player chưa có video. Mở và chọn một bài trước nhé.' };
      this.show();
      await waitForPlayer(() => this.target ?? undefined, signal, this.available);
    }
    if (command.expires_at <= Date.now()) return { ok: false, error: 'Lệnh Player đã hết hạn; chưa thực hiện.' };
    return this.target!(command, signal);
  }
}
