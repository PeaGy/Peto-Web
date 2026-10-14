import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import CharacterSections from '../src/features/companion/characters/CharacterSections';
import { DEFAULT_CHARACTER } from '../src/features/companion/characters/characterLibrary';
import { readIdle } from '../src/features/companion/characters/live2dMotions';
import { readEffects } from '../src/features/companion/characters/characterEffects';
import { DEFAULT_MAGIC, readMagic } from '../src/features/companion/characters/magic/magicSettings';
import { readCharacterView, writeCharacterView } from '../src/features/companion/characters/characterView';
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

const VRM = { ...DEFAULT_CHARACTER, id: 'vrm-1', name: 'Ani', format: 'vrm' as const, builtin: false };

/** Mở một khối theo tên tiêu đề (khối Kích thước và vị trí mở sẵn). */
function open(name: string) {
  const button = screen.getByRole('button', { name });
  if (button.getAttribute('aria-expanded') !== 'true') fireEvent.click(button);
  expect(button.getAttribute('aria-expanded')).toBe('true');
}

it('khối gập mở như AIRI: Kích thước và vị trí mở sẵn, các khối khác gập, Hiển thị trên điện thoại chỉ có trên điện thoại', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ FileReferences: { Motions: {} } }) }));
  render(<CharacterSections character={DEFAULT_CHARACTER} motion="system" onMotionChange={vi.fn()} />);
  expect(screen.getByRole('button', { name: 'Kích thước và vị trí' }).getAttribute('aria-expanded')).toBe('true');
  for (const name of ['Chuyển động', 'Biểu cảm', 'Nhún theo nhạc']) {
    const button = screen.getByRole('button', { name });
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(document.getElementById(button.getAttribute('aria-controls')!)!.hasAttribute('inert')).toBe(true);
  }
  expect(screen.queryByRole('button', { name: 'Hiển thị trên điện thoại' })).toBeNull();
  open('Biểu cảm');
  expect(document.getElementById(screen.getByRole('button', { name: 'Biểu cảm' }).getAttribute('aria-controls')!)!.hasAttribute('inert')).toBe(false);
  await waitFor(() => expect(screen.getByRole('group', { name: 'Cảm xúc' })).toBeTruthy());
});

it('Kích thước và vị trí ghi góc nhìn cho sân khấu và đi theo khi sân khấu đổi góc nhìn', () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ FileReferences: { Motions: {} } }) }));
  render(<CharacterSections character={DEFAULT_CHARACTER} motion="system" onMotionChange={vi.fn()} />);
  const zoom = screen.getByRole('slider', { name: 'Thu phóng' }) as HTMLInputElement;
  expect(zoom.value).toBe('100');
  fireEvent.change(zoom, { target: { value: '180' } });
  // Chỉ gửi mức phóng; sân khấu tự dời để giữ mặt đứng yên.
  expect(readCharacterView(DEFAULT_CHARACTER.id)).toEqual({ zoom: 1.8, panX: 0, panY: 0 });
  fireEvent.change(screen.getByRole('slider', { name: 'Ngang' }), { target: { value: '-20' } });
  expect(readCharacterView(DEFAULT_CHARACTER.id).panX).toBe(-0.2);
  // Sân khấu (bên ghi khác) báo góc nhìn mới: thanh trượt đi theo.
  act(() => writeCharacterView({ zoom: 2.5, panX: 0.1, panY: 0.4 }, DEFAULT_CHARACTER.id, {}));
  expect(zoom.value).toBe('250');
  expect((screen.getByRole('slider', { name: 'Dọc' }) as HTMLInputElement).value).toBe('40');
  expect(screen.getByText('250%')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Đặt lại thu phóng' }));
  expect(readCharacterView(DEFAULT_CHARACTER.id).zoom).toBe(1);
  fireEvent.click(screen.getByRole('button', { name: 'Về vừa khung' }));
  expect(readCharacterView(DEFAULT_CHARACTER.id)).toEqual({ zoom: 1, panX: 0, panY: 0 });
});

it('Chuyển động: chọn motion khi chờ, tắt idle và các hiệu ứng phụ, lưu theo nhân vật', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ FileReferences: {
    Motions: { Idle: [{ File: 'motions/a.motion3.json' }], Wave: [{ File: 'wave.motion3.json' }] },
  } }) }));
  const onMotionChange = vi.fn();
  render(<CharacterSections character={DEFAULT_CHARACTER} motion="system" onMotionChange={onMotionChange} />);
  open('Chuyển động');
  const general = screen.getByRole('radiogroup', { name: 'Nhân vật cử động' });
  expect((within(general).getByRole('radio', { name: /Theo cài đặt chung/ }) as HTMLInputElement).checked).toBe(true);
  fireEvent.click(within(general).getByRole('radio', { name: /Luôn cử động/ }));
  expect(onMotionChange).toHaveBeenCalledWith('always');
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

it('Cách chuyển động: mặc định Hiện tại; MAGIC lưu riêng nhân vật, khóa chuyển động chờ, đảo mắt và nhìn theo con trỏ', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ FileReferences: { Motions: { Idle: [{ File: 'a.motion3.json' }] } } }) }));
  render(<CharacterSections character={DEFAULT_CHARACTER} motion="system" onMotionChange={vi.fn()} />);
  open('Chuyển động');
  const idle = screen.getByRole('combobox', { name: 'Chuyển động khi chờ' }) as HTMLButtonElement;
  await waitFor(() => expect(idle.disabled).toBe(false));
  const current = screen.getByRole('radio', { name: 'Hiện tại' }) as HTMLInputElement;
  expect(current.checked).toBe(true);
  expect(screen.queryByRole('combobox', { name: 'Bộ chuyển động MAGIC' })).toBeNull();
  fireEvent.click(screen.getByRole('radio', { name: 'MAGIC' }));
  expect(readMagic(DEFAULT_CHARACTER.id)).toEqual({ driver: 'magic', profile: 'excited', viewTarget: true, mouthForm: true });
  expect(idle.disabled).toBe(true);
  expect((screen.getByRole('switch', { name: 'Nhìn theo con trỏ' }) as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByRole('switch', { name: 'Đảo mắt khi chờ' }) as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByRole('switch', { name: 'Thở' }) as HTMLInputElement).disabled).toBe(false);
  const profile = screen.getByRole('combobox', { name: 'Bộ chuyển động MAGIC' });
  expect(profile.textContent).toBe('Hào hứng');
  fireEvent.click(profile);
  fireEvent.click(screen.getByRole('option', { name: /Theo lúc nói/ }));
  fireEvent.click(screen.getByRole('switch', { name: 'MAGIC điều khiển dáng miệng' }));
  expect(readMagic(DEFAULT_CHARACTER.id)).toEqual({ driver: 'magic', profile: 'speech', viewTarget: true, mouthForm: false });
  expect(readMagic('khac')).toEqual(DEFAULT_MAGIC);
  fireEvent.click(current);
  expect(readMagic(DEFAULT_CHARACTER.id).driver).toBe('universal');
  expect(idle.disabled).toBe(false);
  expect(screen.queryByRole('switch', { name: 'Mắt nhìn thẳng' })).toBeNull();
});

it('VRM chỉ có cử động chung, nhìn ô chat và biểu cảm; không có cỡ, vị trí hay Nhún theo nhạc', () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  render(<CharacterSections character={VRM} motion="system" onMotionChange={vi.fn()} />);
  expect(screen.getByText('Model VRM luôn đứng giữa khung; chưa chỉnh được cỡ và vị trí.')).toBeTruthy();
  expect(screen.queryByRole('slider')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Nhún theo nhạc' })).toBeNull();
  open('Chuyển động');
  expect(screen.getByRole('radiogroup', { name: 'Nhân vật cử động' })).toBeTruthy();
  expect(screen.getByRole('switch', { name: 'Nhìn vào ô chat khi bạn gõ' })).toBeTruthy();
  expect(screen.queryByRole('combobox', { name: 'Chuyển động khi chờ' })).toBeNull();
  open('Biểu cảm');
  fireEvent.click(screen.getByRole('button', { name: 'Tò mò' }));
  expect(screen.getByText('Tò mò lấy từ biểu cảm có sẵn của model VRM.')).toBeTruthy();
  expect(fetch).not.toHaveBeenCalled();
});

it('trên điện thoại có thêm Hiển thị trên điện thoại, lưu chất lượng và độ mượt', () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ FileReferences: { Motions: {} } }) }));
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query.includes('720px'), addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  render(<CharacterSections character={DEFAULT_CHARACTER} motion="system" onMotionChange={vi.fn()} />);
  expect(screen.getByText(/Trên điện thoại nhân vật giữ khung cố định/)).toBeTruthy();
  open('Hiển thị trên điện thoại');
  fireEvent.click(screen.getByRole('combobox', { name: 'Độ mượt' }));
  fireEvent.click(screen.getByRole('option', { name: 'Cao · tối đa 60 FPS' }));
  expect(JSON.parse(localStorage.getItem('peto-mobile-render-quality') ?? '{}')).toMatchObject({ smooth: true });
});
