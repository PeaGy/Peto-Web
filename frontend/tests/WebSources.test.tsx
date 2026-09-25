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
  for (const [label, title] of [['1 nguồn được trích dẫn', 'Cited'], ['1 kết quả tìm kiếm', 'Result'], ['1 nguồn tham khảo', 'Old']]) {
    const section = screen.getByText(label).closest('details')!;
    expect(within(section).getAllByRole('link', { hidden: true })).toHaveLength(1);
    expect(within(section).getByText(title)).toBeTruthy();
  }
  expect(screen.queryByText('Unsafe')).toBeNull();
});
