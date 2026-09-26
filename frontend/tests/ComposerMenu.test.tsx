import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import ComposerMenu from '../src/ComposerMenu';

it('keeps options usable when a touch browser blurs without a new focus target', () => {
  const onAttach = vi.fn();
  render(<ComposerMenu disabled={false} webDisabled={false} onToggleWeb={vi.fn()} onAttach={onAttach} />);
  const trigger = screen.getByRole('button', { name: 'Thêm ảnh và tùy chọn' });
  fireEvent.click(trigger);
  const attach = screen.getByRole('button', { name: /Thêm ảnh hoặc tệp/ });
  fireEvent.blur(attach, { relatedTarget: null });
  expect(screen.getByRole('group', { name: 'Tùy chọn tin nhắn' })).toBeTruthy();
  fireEvent.click(attach);
  expect(onAttach).toHaveBeenCalledOnce();
  expect(screen.queryByRole('group')).toBeNull();
  fireEvent.click(trigger);
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole('group')).toBeNull();
});
