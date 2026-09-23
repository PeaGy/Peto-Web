import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import IdleMotionPicker from '../src/IdleMotionPicker';
import { DEFAULT_CHARACTER } from '../src/characterLibrary';
import { readIdle } from '../src/live2dMotions';
import { readEffects } from '../src/characterEffects';
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });
it('offers named motions, saves selection and supports disabling', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ FileReferences: {
    Motions: { Idle: [{ File: 'motions/a.motion3.json' }], Wave: [{ File: 'wave.motion3.json' }] },
  } }) }));
  render(<IdleMotionPicker character={DEFAULT_CHARACTER} />);
  const option = await screen.findByRole('option', { name: 'wave.motion3.json' });
  const select = screen.getByRole('combobox', { name: 'Chuyển động khi chờ' });
  fireEvent.change(select, { target: { value: (option as HTMLOptionElement).value } });
  expect(readIdle(DEFAULT_CHARACTER.id)).toContain('Wave');
  fireEvent.change(select, { target: { value: 'off' } });
  expect(readIdle(DEFAULT_CHARACTER.id)).toBe('off');
  const physics = screen.getByRole('switch', { name: 'Vật lý' }) as HTMLInputElement;
  expect(physics.disabled).toBe(true);
  fireEvent.click(screen.getByRole('switch', { name: 'Nhìn theo con trỏ' }));
  expect(readEffects(DEFAULT_CHARACTER.id)).toEqual({ cursor: false, breath: true, physics: true, idleEyes: true });
  const idleEyes = screen.getByRole('switch', { name: 'Đảo mắt khi chờ' }) as HTMLInputElement;
  expect(idleEyes.checked).toBe(true);
  fireEvent.click(idleEyes);
  expect(readEffects(DEFAULT_CHARACTER.id).idleEyes).toBe(false);
  expect(readIdle(DEFAULT_CHARACTER.id)).toBe('off');
});
