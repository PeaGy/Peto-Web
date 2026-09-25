import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import WebSources from '../src/WebSources';

it('phân biệt trích dẫn, kết quả tìm kiếm và dữ liệu cũ', () => {
  render(<WebSources sources={[
    { url: 'https://example.com/cited', title: 'Cited', kind: 'citation' },
    { url: 'https://example.com/result', title: 'Result', kind: 'result' },
    { url: 'https://example.com/old', title: 'Old' },
    { url: 'javascript:alert(1)', title: 'Unsafe', kind: 'citation' },
  ]} />);
  const panel = screen.getByText('Nguồn · 1').closest('details')!;
  expect(panel.open).toBe(false);
  expect(within(panel).getAllByRole('link', { hidden: true })).toHaveLength(3);
  const others = screen.getByText('Kết quả tìm kiếm khác · 1').closest('details')!;
  expect(others.open).toBe(false);
  expect(within(others).getAllByRole('link', { hidden: true })).toHaveLength(1);
  expect(within(others).getByText('Result')).toBeTruthy();
  expect(within(panel).getByText('Cited')).toBeTruthy();
  expect(within(panel).getByText('Old')).toBeTruthy();
  expect(screen.queryByText('Unsafe')).toBeNull();
});
