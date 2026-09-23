import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import CharacterPicker from '../src/CharacterPicker';
import { DEFAULT_CHARACTER } from '../src/characterLibrary';
import { inspectLive2D } from '../src/characterImport';
vi.mock('../src/IdleMotionPicker', () => ({ default: () => null }));
vi.mock('../src/characterImport', () => ({ inspectLive2D: vi.fn() }));

it('waits for review confirmation before saving and discards a cancelled review', async () => {
  const prepared = { model: { ...DEFAULT_CHARACTER, id: 'new' }, assets: { id: 'new', entry: 'model.model3.json', files: [] } };
  vi.mocked(inspectLive2D).mockResolvedValue({ name: 'Avatar', entry: 'model.model3.json', bytes: 0, files: 3,
    motions: { found: [], referenced: [] }, expressions: { found: [], referenced: [] }, textures: [], parameters: null, physics: false, issues: [], prepared });
  const library = { models: [DEFAULT_CHARACTER], selected: DEFAULT_CHARACTER, loading: false, error: '', select: vi.fn(),
    add: vi.fn(), addPrepared: vi.fn().mockResolvedValue(undefined), rename: vi.fn(), remove: vi.fn(), savePreview: vi.fn() };
  render(<CharacterPicker library={library} onClose={vi.fn()} />);
  const choose = () => fireEvent.change(screen.getByLabelText('Nhập ZIP Live2D'), { target: { files: [new File(['zip'], 'Avatar.zip')] } });
  choose(); await screen.findByRole('heading', { name: 'Trước khi nhập' });
  expect(library.addPrepared).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Hủy', exact: true }));
  expect(screen.queryByRole('heading', { name: 'Trước khi nhập' })).toBeNull();
  expect(library.addPrepared).not.toHaveBeenCalled();
  choose(); await screen.findByRole('heading', { name: 'Trước khi nhập' });
  await waitFor(() => expect((screen.getByRole('button', { name: 'Nhập model', exact: true }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button', { name: 'Nhập model', exact: true }));
  await waitFor(() => expect(library.addPrepared).toHaveBeenCalledExactlyOnceWith(prepared));
  expect(library.add).not.toHaveBeenCalled();
});
