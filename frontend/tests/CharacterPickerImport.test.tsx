import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import CharacterPicker from '../src/features/companion/characters/CharacterPicker';
import { DEFAULT_CHARACTER } from '../src/features/companion/characters/characterLibrary';
import { inspectLive2D } from '../src/features/companion/characters/characterImport';
vi.mock('../src/features/companion/characters/characterImport', () => ({ inspectLive2D: vi.fn() }));

it('waits for review confirmation before saving and discards a cancelled review', async () => {
  const prepared = { model: { ...DEFAULT_CHARACTER, id: 'new' }, assets: { id: 'new', entry: 'model.model3.json', files: [] } };
  vi.mocked(inspectLive2D).mockResolvedValue({ name: 'Avatar', entry: 'model.model3.json', bytes: 0, files: 3,
    motions: { found: [], referenced: [] }, expressions: { found: [], referenced: [] }, textures: [], parameters: null, physics: false, issues: [], prepared });
  const library = { models: [DEFAULT_CHARACTER], selected: DEFAULT_CHARACTER, loading: false, error: '', select: vi.fn(),
    add: vi.fn(), addPrepared: vi.fn().mockResolvedValue(undefined), rename: vi.fn(), remove: vi.fn(), savePreview: vi.fn() };
  const onClose = vi.fn();
  render(<CharacterPicker library={library} onClose={onClose} />);
  const choose = () => fireEvent.change(screen.getByLabelText('Nhập ZIP Live2D'), { target: { files: [new File(['zip'], 'Avatar.zip')] } });
  choose(); await screen.findByRole('heading', { name: 'Trước khi nhập' }, { timeout: 10000 });
  expect(library.addPrepared).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Hủy', exact: true }));
  expect(screen.queryByRole('heading', { name: 'Trước khi nhập' })).toBeNull();
  expect(library.addPrepared).not.toHaveBeenCalled();
  choose(); await screen.findByRole('heading', { name: 'Trước khi nhập' }, { timeout: 10000 });
  await waitFor(() => expect((screen.getByRole('button', { name: 'Nhập model', exact: true }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button', { name: 'Nhập model', exact: true }));
  await waitFor(() => expect(library.addPrepared).toHaveBeenCalledExactlyOnceWith(prepared));
  expect(library.add).not.toHaveBeenCalled();
  // Nhập xong thì hộp đóng để thấy ngay nhân vật mới trên sân khấu của trang Nhân vật.
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
});

it('hộp Chọn nhân vật chỉ có thư viện; chọn một thẻ thì đổi nhân vật và đóng hộp', () => {
  const other = { ...DEFAULT_CHARACTER, id: 'teto', name: 'Teto', builtin: false, bytes: 2 * 1024 * 1024 };
  const library = { models: [DEFAULT_CHARACTER, other], selected: DEFAULT_CHARACTER, loading: false, error: '', select: vi.fn(),
    add: vi.fn(), addPrepared: vi.fn(), rename: vi.fn(), remove: vi.fn(), savePreview: vi.fn() };
  const onClose = vi.fn();
  render(<CharacterPicker library={library} onClose={onClose} />);
  expect(screen.getByRole('heading', { name: 'Chọn nhân vật' })).toBeTruthy();
  expect(screen.getByText('2 nhân vật · Trên thiết bị này')).toBeTruthy();
  expect(screen.queryByRole('radiogroup', { name: 'Nhân vật cử động' })).toBeNull();
  expect(screen.queryByText(/Cài đặt nhân vật/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Chọn Teto' }));
  expect(library.select).toHaveBeenCalledWith('teto');
  expect(onClose).toHaveBeenCalledOnce();
});
