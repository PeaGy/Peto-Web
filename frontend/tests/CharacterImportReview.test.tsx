import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import CharacterImportReview from '../src/CharacterImportReview';
import type { Live2DImportReport } from '../src/characterImport';

const report: Live2DImportReport = { name: 'Avatar', entry: '模型/model.model3.json', bytes: 1024, files: 4,
  motions: { found: ['idle.motion3.json'], referenced: [] }, expressions: { found: [], referenced: [] }, textures: ['texture.png'], parameters: null, physics: false,
  issues: [{ severity: 'warning', message: 'Chuyển động chưa khai báo', paths: ['idle.motion3.json'] }],
  prepared: { model: { id: 'test', name: 'Avatar', format: 'live2d', bytes: 1024, createdAt: 0 }, assets: { id: 'test', entry: 'model.model3.json', files: [] } } };
it('requires explicit confirmation and lets the user inspect orphan filenames', () => {
  const confirm = vi.fn(), cancel = vi.fn();
  render(<CharacterImportReview report={report} busy={false} error="" onConfirm={confirm} onCancel={cancel} />);
  expect(confirm).not.toHaveBeenCalled();
  expect(screen.getByText('0 lỗi · 1 cảnh báo')).toBeTruthy();
  fireEvent.click(screen.getByText('Xem các tệp')); expect(screen.getByText('idle.motion3.json')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Hủy' })); expect(cancel).toHaveBeenCalledOnce();
  expect(confirm).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Vẫn nhập model' })); expect(confirm).toHaveBeenCalledOnce();
});
it('blocks errors and preserves the report when saving fails', () => {
  const confirm = vi.fn();
  render(<CharacterImportReview report={{ ...report, prepared: undefined, issues: [{ severity: 'error', message: 'Thiếu texture' }] }}
    busy={false} error="Không đủ dung lượng" onConfirm={confirm} onCancel={vi.fn()} />);
  const button = screen.getByRole('button', { name: 'Cần sửa lỗi trước khi nhập' }) as HTMLButtonElement;
  expect(button.disabled).toBe(true); fireEvent.click(button); expect(confirm).not.toHaveBeenCalled();
  expect(screen.getByRole('alert').textContent).toBe('Không đủ dung lượng');
});
