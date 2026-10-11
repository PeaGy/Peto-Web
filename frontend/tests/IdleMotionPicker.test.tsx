import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import IdleMotionPicker from '../src/features/companion/characters/IdleMotionPicker';
import { DEFAULT_CHARACTER } from '../src/features/companion/characters/characterLibrary';
import { readIdle } from '../src/features/companion/characters/live2dMotions';
import { readEffects } from '../src/features/companion/characters/characterEffects';
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });
it('offers named motions, saves selection and supports disabling', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ FileReferences: {
    Motions: { Idle: [{ File: 'motions/a.motion3.json' }], Wave: [{ File: 'wave.motion3.json' }] },
  } }) }));
  render(<IdleMotionPicker character={DEFAULT_CHARACTER} />);
  const select = screen.getByRole('combobox', { name: 'Chuyển động khi chờ' }) as HTMLButtonElement;
  await waitFor(() => expect(select.disabled).toBe(false));
  fireEvent.click(select);
  expect(screen.getByRole('listbox').textContent).toContain('Wave');
  fireEvent.click(screen.getByRole('option', { name: 'wave.motion3.json' }));
  expect(readIdle(DEFAULT_CHARACTER.id)).toContain('Wave');
  expect(select.textContent).toBe('wave.motion3.json');
  fireEvent.click(select);
  fireEvent.click(screen.getByRole('option', { name: 'Tắt idle animation' }));
  expect(readIdle(DEFAULT_CHARACTER.id)).toBe('off');
  const physics = screen.getByRole('switch', { name: 'Vật lý' }) as HTMLInputElement;
  expect(physics.disabled).toBe(true);
  fireEvent.click(screen.getByRole('switch', { name: 'Nhìn theo con trỏ' }));
  expect(readEffects(DEFAULT_CHARACTER.id)).toEqual({ cursor: false, breath: true, physics: true, idleEyes: true, composerGaze: true });
  const composer = screen.getByRole('switch', { name: 'Nhìn vào ô chat khi bạn gõ' }) as HTMLInputElement;
  expect(composer.checked).toBe(true);
  fireEvent.click(composer);
  expect(readEffects(DEFAULT_CHARACTER.id).composerGaze).toBe(false);
  const idleEyes = screen.getByRole('switch', { name: 'Đảo mắt khi chờ' }) as HTMLInputElement;
  expect(idleEyes.checked).toBe(true);
  fireEvent.click(idleEyes);
  expect(readEffects(DEFAULT_CHARACTER.id).idleEyes).toBe(false);
  expect(readEffects(DEFAULT_CHARACTER.id).composerGaze).toBe(false);
  expect(readIdle(DEFAULT_CHARACTER.id)).toBe('off');
});
