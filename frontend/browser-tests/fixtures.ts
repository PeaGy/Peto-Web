import { expect, type Page } from '@playwright/test';

export const title = 'Kiểm tra giao diện Peto';
const markdown = 'Giá thường là **$0.40** và **$0.20**, không phải công thức.\n\n'
  + '| Hạng mục | Giá | Ghi chú |\n| --- | --- | --- |\n| Input | $2.00 | Nội dung đầu vào |\n| Output | $10.00 | Câu trả lời |\n\n'
  + 'Công thức thật: $x^2 + y^2 = 1$.\n\n```js\nconst greeting = "Xin chào Peto";\n```';
export const chatMessages = [
  { id: 1, role: 'user', content: 'Giúp tôi so sánh giá và công thức nhé.' },
  { id: 2, role: 'assistant', content: markdown, status: 'complete' },
];
export const companionMessages = [
  { id: 21, role: 'user', content: 'Hello Peto!' },
  { id: 22, role: 'assistant', content: 'Hi! It is nice to see you today.' },
  { id: 23, role: 'user', content: 'The new background looks nice.' },
  { id: 24, role: 'assistant', content: 'Make yourself comfortable. What would you like to chat about?' },
];

/** API giả chỉ nằm trong bộ kiểm thử; mọi yêu cầu ra ngoài đều bị chặn. */
export async function mockPeto(page: Page, options: { long?: boolean; broken?: boolean; preservePreferences?: boolean } = {}) {
  const state = {
    posts: 0,
    recoveryReady: !options.broken,
    messages: options.long ? Array.from({ length: 40 }, (_, i) => ({ id: i + 1, role: i % 2 ? 'assistant' : 'user', content: `Tin nhắn lịch sử ${i + 1}: Nội dung đủ dài để kiểm tra cuộn và nhập liệu.` })) : [...chatMessages],
    companion: [...companionMessages],
  };
  await page.addInitScript(preserve => {
    // Bài kiểm tra lưu cài đặt cần giữ dữ liệu khi F5; lần vào đầu tiên vẫn luôn sạch.
    if (preserve && sessionStorage.getItem('test-peto-initialized') === '1') return;
    localStorage.clear(); sessionStorage.clear();
    localStorage.setItem('peto-theme', 'dark');
    localStorage.setItem('peto-companion-muted', '1');
    sessionStorage.setItem('test-peto-initialized', '1');
  }, options.preservePreferences ?? false);
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:5179') return route.abort();
    // Chỉ thay renderer nhân vật; các component và CSS bố cục dùng mã sản phẩm thật.
    if (/\/characters\/(Live2DStage|VRMStage)\.tsx/.test(url.pathname)) {
      return route.fulfill({ contentType: 'text/javascript', body: 'export default function Stage() { return null; }' });
    }
    if (!url.pathname.startsWith('/api/')) return route.continue();
    const json = (body: unknown) => route.fulfill({ json: body });
    if (url.pathname === '/api/auth/me') return json({ authenticated: true, login_configured: true,
      user: { id: 'test-account', provider: 'discord', username: 'demo', display_name: 'Người kiểm thử', avatar_url: '' } });
    if (url.pathname === '/api/app-info') return json({ name: 'Peto', avatar_url: null });
    if (url.pathname === '/api/projects') return json({ projects: [] });
    if (url.pathname === '/api/conversations') return json({ has_more: false, conversations: [
      { id: 'A', title, created_at: 1, updated_at: 2, message_count: state.messages.length, title_state: 'generated' },
      { id: 'B', title: 'Một hội thoại khác', created_at: 1, updated_at: 1, message_count: 2, title_state: 'generated' },
    ] });
    if (/\/api\/conversations\/[AB]\/messages$/.test(url.pathname)) {
      // Giữ tình huống lưu chậm ổn định cả khi máy chạy kiểm thử phản hồi chậm.
      return json({ messages: state.posts && !state.recoveryReady ? state.messages.slice(0, -1) : state.messages });
    }
    if (url.pathname === '/api/companion') return json({ conversation_id: 'A', messages: state.companion });
    if (url.pathname === '/api/companion/memory') return json({ available: false, enabled: false, pending: false, limit: 50, memories: [] });
    if (url.pathname === '/api/voice/health') return json({ ok: false, voices: [], home: { online: false, voices: [] }, official: { allowed: false, voices: [], used: 0, limit: 0 } });
    if (url.pathname === '/api/chat') {
      state.posts++;
      const payload = route.request().postDataJSON();
      const user = { id: 101, role: 'user', content: payload.message };
      const reply = { id: 102, role: 'assistant', content: 'Câu trả lời đã được lưu đầy đủ.', status: 'complete' };
      const base = payload.mode === 'companion' ? state.companion : state.messages;
      // Endpoint đọc lịch sử dùng cùng mã hội thoại giả cho cả hai chế độ.
      state.messages = [...base, user, reply];
      const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
      return route.fulfill({ contentType: 'text/event-stream', body:
        event({ type: 'meta', conversation_id: 'A', effort: 'low', message: user })
        + event({ type: 'delta', text: options.broken ? 'Phần đang nhận' : reply.content })
        + (options.broken ? '' : event({ type: 'done' })) });
    }
    if (url.pathname.startsWith('/api/documents')) return json({ documents: [] });
    if (url.pathname === '/api/imagine') return json({ jobs: [] });
    return route.fulfill({ status: 404, json: { detail: 'Endpoint không dùng trong bộ kiểm thử này.' } });
  });
  return state;
}

export async function openSidebar(page: Page) {
  if (!await page.locator('.sidebar').isVisible()) await page.getByRole('button', { name: 'Mở danh sách hội thoại', exact: true }).click();
  await expect(page.locator('.sidebar')).toBeVisible();
}
export async function openChat(page: Page) {
  await page.goto('/');
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button', { name: title, exact: true }).click();
  await expect(page.locator('.table-scroll')).toBeVisible();
  await expect(page.locator('.katex')).toBeVisible();
}
export async function noPageOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
}
