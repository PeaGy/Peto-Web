import { createRef } from 'react';
import { fireEvent, render, renderHook, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ChatReplyStatus, focusComposerIfOwned } from '../src/features/chat/ChatReplyStatus';
import { ChatMessage } from '../src/features/chat/ChatMessage';
import Composer from '../src/features/chat/Composer';
import { safeSources } from '../src/features/chat/WebSources';
import SourcesPanel from '../src/features/chat/SourcesPanel';
import { ChatMetrics } from '../src/features/admin/ChatMetrics';
import { usePreferencesPersistence } from '../src/app/usePreferencesPersistence';
import type { Message, WebSource } from '../src/shared/api/api';
import type { AdminChatMetrics } from '../src/features/admin/adminApi';

it('live region chỉ đọc mốc trạng thái, không đọc lại lịch sử hoặc từng token', () => {
  const last: Message = { role: 'assistant', content: 'Lịch sử cũ', status: 'complete' };
  const props = { busy: false, stopping: false, scope: 'A', last };
  const { rerender } = render(<ChatReplyStatus {...props} />);
  const status = screen.getByRole('status');
  expect(status.textContent).toBe('');
  rerender(<ChatReplyStatus {...props} busy />);
  expect(status.textContent).toBe('Peto đang trả lời.');
  rerender(<ChatReplyStatus {...props} busy last={{ ...last, content: 'Token mới' }} />);
  expect(status.textContent).toBe('Peto đang trả lời.');
  rerender(<ChatReplyStatus {...props} busy stopping />);
  expect(status.textContent).toBe('Đang dừng câu trả lời.');
  rerender(<ChatReplyStatus {...props} last={{ ...last, stopped: true }} />);
  expect(status.textContent).toBe('Đã dừng theo yêu cầu của bạn.');
  rerender(<ChatReplyStatus {...props} scope="B" />);
  expect(status.textContent).toBe('');
});

it('kết thúc lượt không cướp focus từ nguồn/code hoặc dialog', () => {
  render(<><div className="composer"><textarea aria-label="Draft" /><button className="stop">Dừng</button></div>
    <a href="https://example.com">Nguồn</a><pre tabIndex={0}>code</pre><button>Dialog khác</button></>);
  const draft = screen.getByLabelText<HTMLTextAreaElement>('Draft');
  for (const control of [screen.getByRole('link'), screen.getByText('code'), screen.getByText('Dialog khác')]) {
    control.focus(); focusComposerIfOwned(draft);
    expect(document.activeElement).toBe(control);
  }
  screen.getByText('Dừng').focus(); focusComposerIfOwned(draft);
  expect(document.activeElement).toBe(draft);
});

it('IME, Enter 229 và Shift+Enter không gửi tin khi đang soạn', () => {
  const onSubmit = vi.fn();
  render(<Composer draft="Tiếng Việt" files={[]} streaming={false} stopping={false} canSend onSubmit={onSubmit}
    onDraftChange={vi.fn()} onAddFiles={vi.fn()} onRemoveFile={vi.fn()} onStop={vi.fn()}
    effort="low" efforts={[{ value: 'low', label: 'Thấp', hint: '' }]} onEffortChange={vi.fn()} webSearch="off" onToggleWeb={vi.fn()} menuDisabled={false}
    model="peto" models={[]} onModelChange={vi.fn()} formRef={createRef()} boxRef={createRef()} textareaRef={createRef()} fileRef={createRef()} />);
  const textarea = screen.getByRole('textbox');
  fireEvent.keyDown(textarea, { key: 'Enter', isComposing: true });
  fireEvent.keyDown(textarea, { key: 'Enter', keyCode: 229 });
  fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
  expect(onSubmit).not.toHaveBeenCalled();
  fireEvent.keyDown(textarea, { key: 'Enter' });
  expect(onSubmit).toHaveBeenCalledOnce();
});

it('nguồn phân biệt snippet, trang mở và công cụ kể cả khi được trích dẫn', () => {
  render(<SourcesPanel onClose={() => {}} sources={[
    { url: 'https://example.com/s', title: 'Snippet', kind: 'citation', access: 'search' },
    { url: 'https://example.com/p', title: 'Page', kind: 'result', access: 'page' },
    { url: 'https://github.com/test/repo', title: 'Repo', kind: 'result', access: 'tool', partial: true },
  ]} />);
  expect(screen.getByText('Snippet').closest('a')?.textContent).toContain('Kết quả tìm kiếm');
  expect(screen.getByText('Page').closest('section')?.querySelector('h3')?.textContent).toContain('Trang đã mở');
  expect(screen.getByText('Repo').closest('a')?.textContent).toContain('Công cụ · một phần');
  expect(screen.queryByText(/Kết quả tìm kiếm khác/)).toBeNull();
});

it('schema nguồn sai được bỏ an toàn; citation ưu tiên và không hạ bằng chứng page thành snippet', () => {
  const values = [null, {}, { url: 55 }, { url: 'https://u:pass@example.com/private' }, { url: 'javascript:alert(1)' },
    { url: 'https://example.com/a', title: {}, access: {} },
    { url: 'https://example.com/a', kind: 'citation', access: 'page' },
    { url: 'https://example.com/a', kind: 'result', access: 'search' }];
  expect(safeSources(values as unknown as WebSource[])).toEqual([
    { url: 'https://example.com/a', title: 'example.com', kind: 'citation', access: 'page' }]);
  expect(safeSources({ unsafe: true } as unknown as WebSource[])).toEqual([]);
});

it('Markdown giữ câu trả lời khi metadata sai, không thực thi HTML/JSX/script; code và bảng có focus', () => {
  const content = 'Nội dung vẫn đọc được.\n\n<script>window.stage4=1</script>\n\n<img src=x onerror="window.stage4=1">'
    + '\n\n[Đường dẫn lạ](javascript:alert(1))\n\n```jsx\n<Widget onClick={() => alert(1)} />\n```'
    + '\n\n| Cột |\n| --- |\n| Nội dung |';
  const { container } = render(<ChatMessage message={{ role: 'assistant', content,
    sources: [null, { url: 'javascript:bad' }] as unknown as WebSource[] }} live={false} writing={false} onPreview={vi.fn()} onEdit={vi.fn()} />);
  expect(screen.getByText('Nội dung vẫn đọc được.')).toBeTruthy();
  expect(container.querySelector('script,img,widget,[onerror]')).toBeNull();
  expect(screen.getByText('Đường dẫn lạ').getAttribute('href')).not.toMatch(/^javascript:/);
  expect(container.querySelector('pre')?.textContent).toContain('<Widget onClick');
  expect(container.querySelector('pre')?.tabIndex).toBe(0);
  expect(container.querySelector('.table-scroll')?.getAttribute('role')).toBe('region');
});

it('admin hiển thị cỡ mẫu, cấu hình API, dữ liệu thiếu và giới hạn phục hồi', () => {
  const data: AdminChatMetrics = { configs: [{ model: 'luna', label: '6 Luna', slug: 'gpt-6-luna', effort: 'low',
    turns: 2, complete: 1, total_samples: 1, first_samples: 2, p50_ms: 2000, p95_ms: 2000, first_p50_ms: 500, first_p95_ms: 800 }],
    legacy_turns: 3, summary: { attempts: 1, complete: 0, errors: 1, source_changed: 0, cancelled: 0, sdk_calls: 1, usage_calls: 0,
      latency_samples: 1, p50_ms: 1000, p95_ms: 1000 }, tools: { results: 2, errors: 1, web_errors: 1 },
    context_overflows: 1, recovery: { checks: 2, complete: 0, partial: 1, pending: 1, missing: 0 } };
  render(<ChatMetrics data={data} />);
  fireEvent.click(screen.getByText('Ngữ cảnh và phục hồi Chat'));
  const table = screen.getByRole('region', { name: 'Số đo Chat theo model và mức suy nghĩ' });
  expect(within(table).getByText('gpt-6-luna')).toBeTruthy();
  expect(within(table).getAllByText('1 / 2')).toHaveLength(2);
  expect(screen.getByText(/Mẫu nhỏ chưa đủ kết luận/).textContent).toContain('không tính được lỗi mạng chưa tới máy chủ');
});

it('màu thanh trình duyệt đổi cùng theme app, kể cả khi người dùng ghi đè theme hệ thống', () => {
  const meta = document.createElement('meta'); meta.name = 'theme-color'; document.head.append(meta);
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  const { rerender, unmount } = renderHook(({ theme }: { theme: 'dark' | 'light' }) =>
    usePreferencesPersistence({ collapsed: false, theme, motion: 'reduced' }), { initialProps: { theme: 'dark' } });
  expect(meta.content).toBe('#141414');
  rerender({ theme: 'light' });
  expect(meta.content).toBe('#ffffff');
  unmount(); meta.remove(); vi.unstubAllGlobals();
});
