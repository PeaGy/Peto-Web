import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import Docs from '../src/Docs';

const data = { version: '0.14.1', pages: [{slug:'giong-noi',title:'Giọng nói',group:'Companion',description:'Cấu hình giọng',keywords:['tts'],body:'## Chọn giọng\nNội dung hướng dẫn.'}] };
beforeEach(() => {
  history.replaceState({}, '', '/docs/');
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,json:async()=>data}));
});

it('finds unaccented text and navigates to an article', async () => {
  render(<Docs/>);
  fireEvent.click(screen.getByRole('button',{name:'Tìm trong hướng dẫn'}));
  fireEvent.change(screen.getByRole('textbox'),{target:{value:'giong noi'}});
  const result = await screen.findByRole('link',{name:/Giọng nói Cấu hình giọng/});
  fireEvent.click(result);
  expect(await screen.findByRole('heading',{level:1,name:'Giọng nói'})).toBeTruthy();
  expect(location.pathname).toBe('/docs/giong-noi/');
  expect(screen.getByRole('link',{name:'Đọc bản Markdown ↗'}).getAttribute('href')).toBe('/api/docs/giong-noi.md');
  fireEvent.click(screen.getByRole('button',{name:'Danh mục'}));
  expect(screen.getByRole('button',{name:'Danh mục'}).getAttribute('aria-expanded')).toBe('true');
});

it('allows retry after a failed request', async () => {
  vi.mocked(fetch).mockResolvedValueOnce({ok:false} as Response);
  render(<Docs/>);
  const alert = await screen.findByRole('alert');
  fireEvent.click(within(alert).getByRole('button',{name:'Thử lại'}));
  fireEvent.click(screen.getByRole('button',{name:'Tìm trong hướng dẫn'}));
  fireEvent.change(screen.getByRole('textbox'),{target:{value:'giong'}});
  expect(await screen.findByRole('link',{name:/Giọng nói Cấu hình giọng/})).toBeTruthy();
});
