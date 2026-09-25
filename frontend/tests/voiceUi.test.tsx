import { useState } from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { keyProvider } from '../src/voiceProviders';
import { Dropdown, Field, type DropdownOption } from '../src/voiceUi';

const OPENAI: DropdownOption[] = [
  { value: 'alloy', label: 'Alloy' },
  { value: 'echo', label: 'Echo' },
  { value: 'nova', label: 'Nova' },
];

function Harness({ options, initial = '', editable, onChange }: {
  options: DropdownOption[];
  initial?: string;
  editable?: boolean;
  onChange?: (value: string) => void;
}) {
  const [value, setValue] = useState(initial);
  return (
    <Field id="giong" label="Giọng">
      <Dropdown
        id="giong"
        value={value}
        options={options}
        editable={editable}
        placeholder="Chọn giọng"
        onChange={(next) => { setValue(next); onChange?.(next); }}
      />
    </Field>
  );
}

const trigger = () => screen.getByRole('combobox', { name: 'Giọng' });
const activeName = () => document.getElementById(trigger().getAttribute('aria-activedescendant') ?? '')?.textContent;

it('bấm ô thì mở bảng lựa chọn mang tên của nhãn, bấm một dòng thì chọn và đóng bảng', () => {
  const onChange = vi.fn();
  render(<Harness options={OPENAI} initial="echo" onChange={onChange} />);
  expect(trigger().textContent).toBe('Echo');
  expect(trigger().getAttribute('aria-expanded')).toBe('false');

  fireEvent.click(trigger());
  const list = screen.getByRole('listbox', { name: 'Giọng' });
  expect(within(list).getByRole('option', { name: 'Echo' }).getAttribute('aria-selected')).toBe('true');
  fireEvent.click(within(list).getByRole('option', { name: 'Nova' }));

  expect(onChange).toHaveBeenCalledWith('nova');
  expect(trigger().textContent).toBe('Nova');
  expect(screen.queryByRole('listbox')).toBeNull();
});

it('dùng được bằng bàn phím: mũi tên, Enter, gõ chữ cái đầu, Esc chỉ đóng bảng', () => {
  const onChange = vi.fn();
  render(<Harness options={OPENAI} initial="echo" onChange={onChange} />);

  fireEvent.keyDown(trigger(), { key: 'ArrowDown' });
  expect(trigger().getAttribute('aria-expanded')).toBe('true');
  expect(activeName()).toBe('Echo');
  fireEvent.keyDown(trigger(), { key: 'ArrowDown' });
  expect(activeName()).toBe('Nova');
  fireEvent.keyDown(trigger(), { key: 'Enter' });
  expect(onChange).toHaveBeenLastCalledWith('nova');
  expect(screen.queryByRole('listbox')).toBeNull();

  fireEvent.keyDown(trigger(), { key: 'a' });
  expect(activeName()).toBe('Alloy');

  // Esc đóng bảng nhưng không lọt ra ngoài, nên không đóng luôn hộp Cài đặt hay bảng Micro.
  const outer = vi.fn();
  document.addEventListener('keydown', outer);
  fireEvent.keyDown(trigger(), { key: 'Escape' });
  document.removeEventListener('keydown', outer);
  expect(screen.queryByRole('listbox')).toBeNull();
  expect(outer).not.toHaveBeenCalled();
  expect(onChange).toHaveBeenCalledTimes(1);
});

it('bấm ra ngoài thì đóng bảng; không có lựa chọn nào khớp thì hiện chữ gợi ý', () => {
  render(<Harness options={OPENAI} initial="shimmer" />);
  expect(trigger().textContent).toBe('Chọn giọng');
  fireEvent.click(trigger());
  expect(screen.getByRole('listbox')).toBeTruthy();
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole('listbox')).toBeNull();
});

it('bảng lật lên khi phía dưới hết chỗ, cuộn xuống thì mở lại phía dưới như AIRI', () => {
  const rects = { area: { top: 0, bottom: 400 }, field: { top: 340, bottom: 382 } };
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    const rect = this.classList.contains('scroll-area') ? rects.area
      : this.classList.contains('dropdown') ? rects.field
      : { top: 0, bottom: 0 };
    return { ...rect, left: 0, right: 320, width: 320, height: rect.bottom - rect.top, x: 0, y: rect.top, toJSON: () => ({}) } as DOMRect;
  });
  vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(240);
  render(<div className="scroll-area" style={{ overflowY: 'auto' }}><Harness options={OPENAI} initial="echo" /></div>);

  fireEvent.click(trigger());
  const list = screen.getByRole('listbox');
  expect(list.classList.contains('above')).toBe(true);
  expect(list.style.maxHeight).toBe('300px');

  // Cuộn xuống: ô trôi lên gần đầu vùng cuộn, phía dưới đủ chỗ nên bảng về lại phía dưới ô.
  rects.field = { top: 60, bottom: 102 };
  act(() => { document.querySelector('.scroll-area')!.dispatchEvent(new Event('scroll')); });
  expect(list.classList.contains('above')).toBe(false);
  expect(list.style.maxHeight).toBe('290px');
});

it('ô gõ được: danh sách gợi ý có nhóm, lọc theo tên và mô tả, vẫn nhận mã gõ tay', () => {
  const qwen = keyProvider('qwen')!.voices!.map((voice) => ({ value: voice.id, label: voice.label, hint: voice.hint, group: voice.group }));
  const onChange = vi.fn();
  render(<Harness editable options={qwen} initial="Cherry" onChange={onChange} />);

  fireEvent.click(screen.getByRole('button', { name: 'Xem danh sách gợi ý' }));
  expect(screen.getAllByRole('option')).toHaveLength(48);
  expect(screen.getByText('Phương ngữ Trung Quốc')).toBeTruthy();

  fireEvent.change(trigger(), { target: { value: 'quảng đông' } });
  expect(screen.getAllByRole('option').map((option) => option.firstElementChild?.firstElementChild?.textContent)).toEqual(['Rocky', 'Kiki']);
  fireEvent.keyDown(trigger(), { key: 'ArrowDown' });
  fireEvent.keyDown(trigger(), { key: 'ArrowDown' });
  fireEvent.keyDown(trigger(), { key: 'Enter' });
  expect((trigger() as HTMLInputElement).value).toBe('Kiki');
  expect(screen.queryByRole('listbox')).toBeNull();

  fireEvent.change(trigger(), { target: { value: 'giong-tu-tao-1' } });
  expect(onChange).toHaveBeenLastCalledWith('giong-tu-tao-1');
  expect(screen.queryByRole('listbox')).toBeNull();
});
