import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ExpressionPicker from '../src/features/companion/characters/ExpressionPicker';
import { BUILTIN_FACE, publishSnapshot, readExpressions, watchExpressions } from '../src/features/companion/characters/characterExpressions';
afterEach(() => localStorage.clear());

it('nine emotion cards preview on the stage, and the selected card’s source can be changed', () => {
  const preview = vi.fn(); const off = watchExpressions('model', () => {}, preview);
  const view = render(<ExpressionPicker characterId="model" choices={[{ id: 'f01.json', label: 'f01', index: 0 }]} />);
  const cards = within(screen.getByRole('group', { name: 'Cảm xúc' })).getAllByRole('button');
  expect(cards.map(card => card.textContent)).toEqual(
    ['Vui', 'Buồn', 'Giận', 'Suy nghĩ', 'Ngạc nhiên', 'Ngại', 'Thắc mắc', 'Tò mò', 'Bình thường']);
  expect(screen.getByText('Bấm một thẻ để xem nhân vật làm mặt đó.')).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'Vui' }));
  expect(preview).toHaveBeenLastCalledWith('happy');
  expect(screen.getByRole('button', { name: 'Vui' }).getAttribute('aria-pressed')).toBe('true');
  const source = screen.getByRole('combobox', { name: 'Vui lấy từ' });
  expect(source.textContent).toContain('Tự động');

  fireEvent.click(source);
  fireEvent.click(screen.getByRole('option', { name: /f01/ }));
  expect(readExpressions('model').mapping.happy).toBe('f01.json');
  expect(preview).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole('combobox', { name: 'Vui lấy từ' }));
  fireEvent.click(screen.getByRole('option', { name: /^Dựng sẵn/ }));
  expect(readExpressions('model').mapping.happy).toBe(BUILTIN_FACE);
  fireEvent.click(screen.getByRole('combobox', { name: 'Vui lấy từ' }));
  fireEvent.click(screen.getByRole('option', { name: /^Tự động/ }));
  expect(readExpressions('model').mapping).toEqual({});

  fireEvent.click(screen.getByRole('button', { name: 'Bình thường' }));
  expect(preview).toHaveBeenLastCalledWith('neutral');
  expect(screen.queryByRole('combobox')).toBeNull();
  view.unmount(); off();
});

it('the switch turns off conversation faces but cards still preview', () => {
  const preview = vi.fn(); const off = watchExpressions('model', () => {}, preview);
  render(<ExpressionPicker characterId="model" choices={[]} />);
  fireEvent.click(screen.getByRole('switch', { name: 'Biểu cảm theo trò chuyện' }));
  expect(readExpressions('model').enabled).toBe(false);
  expect(screen.getByText(/Đang tắt: nhân vật giữ mặt bình thường/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Ngại' }));
  expect(preview).toHaveBeenLastCalledWith('awkward');
  off();
});

it('VRM characters use the model’s own expressions, with no source to pick', () => {
  render(<ExpressionPicker characterId="vrm" choices={[]} format="vrm" />);
  fireEvent.click(screen.getByRole('button', { name: 'Tò mò' }));
  expect(screen.getByText('Tò mò lấy từ biểu cảm có sẵn của model VRM.')).toBeTruthy();
  expect(screen.queryByRole('combobox')).toBeNull();
});

it('the panel covers the stage, so the selected card shows the snapshot the stage took of that face', () => {
  render(<ExpressionPicker characterId="model" choices={[]} />);
  fireEvent.click(screen.getByRole('button', { name: 'Ngạc nhiên' }));
  expect(screen.getByRole('status', { name: 'Đang chụp mặt nhân vật' })).toBeTruthy();
  // Ảnh của mặt khác (bấm thẻ trước đó) không được hiện nhầm.
  act(() => publishSnapshot('model', 'happy', 'data:image/png;base64,VUI'));
  expect(screen.queryByRole('img')).toBeNull();
  act(() => publishSnapshot('other', 'surprised', 'data:image/png;base64,KHAC'));
  expect(screen.queryByRole('img')).toBeNull();
  act(() => publishSnapshot('model', 'surprised', 'data:image/png;base64,NGAC'));
  expect(screen.getByRole('img', { name: 'Nhân vật làm mặt ngạc nhiên' }).getAttribute('src')).toBe('data:image/png;base64,NGAC');
  fireEvent.click(screen.getByRole('button', { name: 'Tò mò' }));
  expect(screen.queryByRole('img')).toBeNull();
});

