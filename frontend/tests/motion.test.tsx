import { act, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { applyMotion, isReducedMotion, readMotionChoice, resolveMotion, useReducedMotion } from '../src/shared/motion';

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); delete document.documentElement.dataset.motion; });

function deviceReduces(value: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce') ? value : false }));
}

it('mặc định Mượt kể cả khi thiết bị giảm chuyển động; Theo máy mới nghe thiết bị', () => {
  deviceReduces(true);
  expect(readMotionChoice()).toBe('full');
  expect(resolveMotion('full')).toBe('full');
  expect(resolveMotion('system')).toBe('reduced');
  expect(resolveMotion('reduced')).toBe('reduced');
  deviceReduces(false);
  expect(resolveMotion('system')).toBe('full');
  localStorage.setItem('peto-motion', 'lạ');
  expect(readMotionChoice()).toBe('full');
  localStorage.setItem('peto-motion', 'reduced');
  expect(readMotionChoice()).toBe('reduced');
});

it('useReducedMotion vẽ lại khi data-motion của trang đổi', async () => {
  function Probe() { return <p>{useReducedMotion() ? 'giảm' : 'mượt'}</p>; }
  applyMotion('full');
  render(<Probe />);
  expect(screen.getByText('mượt')).toBeTruthy();
  await act(async () => { applyMotion('reduced'); await Promise.resolve(); });
  expect(isReducedMotion()).toBe(true);
  expect(await screen.findByText('giảm')).toBeTruthy();
});
