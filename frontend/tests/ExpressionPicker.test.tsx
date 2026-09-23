import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ExpressionPicker from '../src/ExpressionPicker';
import { readExpressions, watchExpressions } from '../src/characterExpressions';
afterEach(() => localStorage.clear());
it('allows opaque imported expressions to be mapped, previewed and disabled', () => {
  const preview = vi.fn(); const off = watchExpressions('model', () => {}, preview);
  const view = render(<ExpressionPicker characterId="model" choices={[{ id: 'f01.json', label: 'f01', index: 0 }]} />);
  fireEvent.click(screen.getByText('Gán biểu cảm'));
  fireEvent.change(screen.getByRole('combobox', { name: 'Vui' }), { target: { value: 'f01.json' } });
  expect(readExpressions('model').mapping.happy).toBe('f01.json');
  fireEvent.click(screen.getByRole('button', { name: 'Thử vui' })); expect(preview).toHaveBeenCalledWith('f01.json');
  fireEvent.click(screen.getByRole('switch')); expect(readExpressions('model').enabled).toBe(false);
  view.unmount(); off();
});
it('explains models without authored expressions and disables the switch', () => {
  render(<ExpressionPicker characterId="empty" choices={[]} />);
  expect((screen.getByRole('switch') as HTMLInputElement).disabled).toBe(true);
  expect(screen.getByText('Model chưa khai báo tệp biểu cảm riêng.')).toBeTruthy();
});
