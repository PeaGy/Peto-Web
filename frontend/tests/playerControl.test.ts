import { afterEach, expect, it, vi } from 'vitest';
import { PlayerControlBridge, emptyPlayer, type PlayerCommand } from '../src/features/companion/ytplayer/playerControl';
import { sendMessage, acknowledgePlayer } from '../src/shared/api/api';
import { controlTrack } from '../src/features/companion/ytplayer/playerLibraryControl';
import { mediaFromId } from '../src/features/companion/ytplayer/playerApi';

const cmd = (action: PlayerCommand['action'], id = 'command-one'): PlayerCommand => ({ id, action, expires_at: Date.now() + 12000 });
const signal = () => new AbortController().signal;
afterEach(() => vi.unstubAllGlobals());

it('manual reset aborts running work and rejects not-yet-received commands of older chat turns', async () => {
  const bridge = new PlayerControlBridge(vi.fn(), () => true), turn = signal(), slow = signal();
  bridge.bindTurn(turn); bridge.bindTurn(slow);
  const execute = vi.fn(async (_c: PlayerCommand, s: AbortSignal) => {
    await new Promise((_, reject) => s.addEventListener('abort', () => reject(s.reason), { once: true }));
    return { ok: true, state: emptyPlayer() };
  });
  bridge.register(execute);
  const pending = bridge.run(cmd('play_video'), turn);
  bridge.invalidate();
  expect((await pending).ok).toBe(false);
  expect((await bridge.run(cmd('enqueue_playlist', 'late'), slow)).ok).toBe(false);
  expect(execute).toHaveBeenCalledOnce();
});

it('an AI clear does not abort itself or execute a duplicate; its turn can read the new state', async () => {
  const bridge = new PlayerControlBridge(vi.fn(), () => true), turn = signal();
  const execute = vi.fn(async (c: PlayerCommand, s: AbortSignal) => {
    if (c.action === 'clear_all') bridge.invalidate(s);
    s.throwIfAborted(); return { ok: true, state: emptyPlayer() };
  });
  bridge.register(execute); bridge.bindTurn(turn);
  const c = cmd('clear_all');
  expect((await bridge.run(c, turn)).ok).toBe(true);
  expect((await bridge.run(c, turn)).ok).toBe(true); expect(execute).toHaveBeenCalledOnce();
  expect((await bridge.run(cmd('status', 'read'), turn)).ok).toBe(true);
});

it('bounded tool metadata preserves complete Unicode characters', () => {
  const track = controlTrack(mediaFromId('Soy4jGPHr3g', '🎵'.repeat(301), '🎤'.repeat(201)));
  expect(Array.from(track.title)).toHaveLength(300); expect(Array.from(track.artist)).toHaveLength(200);
  expect(JSON.parse(JSON.stringify(track)).title).toBe('🎵'.repeat(300));
});

it('status for an unopened player does not load the player, API or favorites', async () => {
  const show = vi.fn(), bridge = new PlayerControlBridge(show, () => true);
  expect(await bridge.run(cmd('status'), signal())).toEqual({ ok: true, state: emptyPlayer() });
  expect((await bridge.run(cmd('play', 'play'), signal())).ok).toBe(false);
  expect(show).not.toHaveBeenCalled();
});

it('a saved session prepares the lazy controller for status/list reads without showing a window or returning empty', async () => {
  const show = vi.fn();
  const execute = vi.fn(async () => ({ ok: true, state: { ...emptyPlayer(), queue_count: 2 } }));
  const prepare = vi.fn(() => { bridge.register(execute); });
  const bridge = new PlayerControlBridge(show, () => true, prepare, () => true);
  expect((await bridge.run(cmd('status'), signal())).state?.queue_count).toBe(2);
  expect(prepare).toHaveBeenCalledOnce(); expect(show).not.toHaveBeenCalled();
});

it('duplicate command ids share a result and cannot advance the queue twice', async () => {
  const bridge = new PlayerControlBridge(vi.fn(), () => true);
  const execute = vi.fn(async () => ({ ok: true, state: emptyPlayer() }));
  bridge.register(execute);
  const command = cmd('next');
  const [a, b] = await Promise.all([bridge.run(command, signal()), bridge.run(command, signal())]);
  expect(a).toEqual(b); expect(execute).toHaveBeenCalledOnce();
});

it('expired, background and cancelled commands cannot reach the player', async () => {
  let active = true;
  const bridge = new PlayerControlBridge(vi.fn(), () => active);
  const execute = vi.fn(async () => ({ ok: true, state: emptyPlayer() })); bridge.register(execute);
  expect((await bridge.run({ ...cmd('next'), expires_at: Date.now() - 1 }, signal())).ok).toBe(false);
  active = false;
  expect((await bridge.run(cmd('next', 'background'), signal())).ok).toBe(false);
  active = true;
  const controller = new AbortController(); controller.abort();
  expect((await bridge.run(cmd('next', 'stopped'), controller.signal)).ok).toBe(false);
  expect(execute).not.toHaveBeenCalled();
});

it('open waits for the lazy player to register and does not toggle an already-visible window', async () => {
  const execute = vi.fn(async () => ({ ok: true, state: { ...emptyPlayer(), window: 'visible' as const } }));
  const bridge = new PlayerControlBridge(() => { bridge.register(execute); }, () => true);
  expect((await bridge.run(cmd('open'), signal())).state?.window).toBe('visible');
  expect(execute).toHaveBeenCalledOnce();
});

it.each([true, 2, 3, 4] as const)('only Companion advertises protocol %s and acknowledges player SSE before final text', async version => {
  const command = cmd('pause');
  const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
  const order: string[] = [];
  const fetchMock = vi.fn(async (url: string) => {
    if (url.includes('/commands/')) { order.push('ack'); return new Response('{}'); }
    return new Response(event({ type: 'player_command', command }) + event({ type: 'delta', text: 'Done.' }) + event({ type: 'done' }));
  });
  vi.stubGlobal('fetch', fetchMock);
  const onPlayerCommand = vi.fn(async (c: PlayerCommand) => { order.push('action'); await acknowledgePlayer(c.id, { ok: true, state: emptyPlayer() }, signal()); });
  const base = { message: 'Pause', conversationId: null, effort: 'low' as const, playerControl: version };
  await sendMessage({ ...base, mode: 'companion' }, { onPlayerCommand, onDelta: () => { order.push('reply'); } });
  expect(order).toEqual(['action', 'ack', 'reply']);
  expect(JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string).player_control).toBe(typeof version === 'number' ? version : 1);
  onPlayerCommand.mockClear();
  await sendMessage({ ...base, mode: 'chat' }, { onPlayerCommand });
  expect(onPlayerCommand).not.toHaveBeenCalled();
});
