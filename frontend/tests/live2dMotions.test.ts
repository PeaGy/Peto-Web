import { beforeEach, expect, it, vi } from 'vitest';
import { controlIdle, motionChoices, readIdle, watchIdle, writeIdle } from '../src/live2dMotions';
import hiyori from '../public/characters/hiyori/Hiyori.model3.json';

const choices = motionChoices({ Idle: [{ File: 'motions/idle.motion3.json' }], Dance: [{ File: 'dance.motion3.json' }] });
function setup() {
  const manager = { groups: { idle: 'Idle' }, startRandomMotion: vi.fn().mockResolvedValue(true),
    startMotion: vi.fn().mockResolvedValue(true), loadMotion: vi.fn().mockResolvedValue({}), stopAllMotions: vi.fn() };
  const original = manager.startRandomMotion;
  const error = vi.fn();
  return { manager, original, error, controller: controlIdle(manager, choices, error) };
}
beforeEach(() => localStorage.clear());
it('discovers Hiyori and custom motion groups without treating other JSON as motion', () => {
  const items = motionChoices(hiyori.FileReferences.Motions);
  expect(items.filter(item => item.group === 'Idle')).toHaveLength(9);
  expect(items.filter(item => item.group === 'TapBody')).toHaveLength(1);
  expect(choices[1].label).toBe('dance.motion3.json');
  expect(motionChoices(null)).toEqual([]);
});
it('remembers preferences separately and notifies only the selected model', () => {
  const update = vi.fn(); const stop = watchIdle('one', update);
  writeIdle('two', 'off'); expect(update).not.toHaveBeenCalled();
  writeIdle('one', choices[1].id);
  expect(update).toHaveBeenCalledWith(choices[1].id);
  expect(readIdle('two')).toBe('off'); expect(readIdle('one')).toBe(choices[1].id);
  stop(); writeIdle('one', 'auto'); expect(update).toHaveBeenCalledTimes(1);
});
it('keeps automatic idle and repeats a selected motion from any group', async () => {
  const { manager, original, controller } = setup();
  await manager.startRandomMotion('Idle', 1); expect(original).toHaveBeenCalledWith('Idle', 1);
  controller.select(choices[1].id);
  await manager.startRandomMotion('Idle', 1); await manager.startRandomMotion('Idle', 1);
  expect(manager.startMotion).toHaveBeenCalledTimes(2);
  expect(manager.startMotion).toHaveBeenLastCalledWith('Dance', 0, 1);
  controller.select('off'); await manager.startRandomMotion('Idle', 1);
  expect(manager.startMotion).toHaveBeenCalledTimes(2);
  controller.dispose(); expect(manager.startRandomMotion).toBe(original);
});
it('does not start an obsolete motion after loading finishes', async () => {
  const { manager, controller } = setup();
  let finish!: (value: unknown) => void;
  manager.loadMotion.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  controller.select(choices[1].id);
  const pending = manager.startRandomMotion('Idle', 1);
  controller.select('off'); finish({}); await pending;
  expect(manager.startMotion).not.toHaveBeenCalled();
});
it('respects reduced movement and falls back for an obsolete saved choice', async () => {
  const { manager, original, controller } = setup();
  controller.enable(false); await manager.startRandomMotion('Idle', 1);
  expect(original).not.toHaveBeenCalled();
  controller.select('missing'); controller.enable(true);
  await manager.startRandomMotion('Idle', 1); expect(original).toHaveBeenCalledOnce();
});
it('reports a missing motion once without retrying every frame', async () => {
  const { manager, controller, error } = setup();
  manager.loadMotion.mockResolvedValue(undefined);
  controller.select(choices[1].id);
  await manager.startRandomMotion('Idle', 1); await manager.startRandomMotion('Idle', 1);
  expect(error).toHaveBeenCalledOnce(); expect(manager.loadMotion).toHaveBeenCalledOnce();
});
