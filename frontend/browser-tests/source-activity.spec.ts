import { createServer } from 'node:http';
import { test, expect, type Page } from '@playwright/test';
import { mockPeto, openChat, openSidebar, noPageOverflow, chatMessages } from './fixtures';
import type { WebActivity } from '../src/features/chat/sourceActivity';

function fixtureWeb(count = 105): WebActivity {
  const sources = Array.from({ length: count }, (_, i) => ({
    url: i === 0 ? 'https://gearvn.com/pages/man-hinh' : i === 1 ? 'https://phongvu.vn/man-hinh' : `https://source${i}.example.com/monitor`,
    title: i === 0 ? 'Màn hình gaming: thông số và giá tham khảo' : `Màn hình gaming ${i + 1} — ${'nội dung khá dài '.repeat(4)}`,
    snippet: 'Đoạn trích do nguồn cung cấp: tấm nền IPS, Full HD và tần số quét từ 144 Hz. Có thể mở bài viết để đối chiếu thông số.',
    kind: 'result' as const, access: 'search' as const,
  }));
  return { version: 1, sources, calls: Array.from({ length: Math.ceil(count / 15) }, (_, i) => ({
    id: `xai:1:web-${i}`, kind: 'search', operation: 'search', state: 'done',
    queries: [i === 0 ? 'màn hình gaming 2 triệu đáng mua' : `so sánh màn hình IPS — lượt ${i + 1}`],
    source_urls: sources.slice(i * 15, (i + 1) * 15).map(source => source.url),
  })) };
}

const answer = '## Gợi ý chọn theo nhu cầu\n\nƯu tiên tấm nền **IPS**, Full HD và tần số quét 144 Hz trở lên.\n\n'
  + '- **Ngân sách khoảng 2 triệu:** màn hình 24 inch vừa bàn.\n- **Chơi FPS:** kiểm tra cổng DisplayPort và độ trễ.\n- **Học tập:** ưu tiên bảo hành và chân đế chắc.\n\n'
  + 'Bạn có thể mở bảng nguồn để đối chiếu thông số tại nơi bán.';

async function prepare(page: Page, options: { web?: WebActivity; iconsFail?: boolean; legacy?: boolean } = {}) {
  const state = await mockPeto(page);
  await page.route('https://www.google.com/s2/favicons**', route => options.iconsFail ? route.abort() : route.fulfill({
    contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" rx="9" fill="#d42d35"/><path d="M8 10h16v4H12v4h12v4H8z" fill="white"/></svg>',
  }));
  const web = options.web ?? fixtureWeb();
  let messages: object[] = [...chatMessages, { id: 3, role: 'user', content: 'Màn hình gaming giá 2 triệu đáng mua?' },
    { id: 4, role: 'assistant', content: answer, status: 'complete', sources: web.sources.slice(0, 30),
      ...(options.legacy ? {} : { work: { ms: 22000, steps: [], complete: true, web } }) }];
  await page.route('**/api/conversations/A/messages', route => route.fulfill({ json: { messages } }));
  await openChat(page);
  return { state, web, setMessages: (value: object[]) => { messages = value; } };
}

test('105 nguồn theo query, mở nhóm/cuộn riêng/đóng trả focus trên desktop và sheet', async ({ page }, info) => {
  await prepare(page);
  const trigger = page.getByRole('button', { name: 'Mở 105 nguồn tham khảo' });
  await expect(trigger.locator('.source-favicon')).toHaveCount(3);
  await expect(page.locator('article .web-source-card')).toHaveCount(0);
  await trigger.click();
  const panel = page.locator('.sources-panel');
  await expect(panel).toBeVisible();
  await expect(panel.locator('.source-query-toggle')).toHaveCount(7);
  await expect(panel.locator('.web-source-card')).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('query-groups.png') });
  const first = panel.getByRole('button', { name: /Đã tìm trên web: màn hình gaming 2 triệu đáng mua/ });
  await first.click();
  await expect(panel.locator('.web-source-card')).toHaveCount(15);
  await expect(panel.locator('.web-source-snippet').first()).toBeVisible();
  await expect(panel.locator('.web-source-icon img').first()).toBeVisible();
  if (info.project.name === 'pc') {
    expect(await panel.evaluate(node => node.matches(':modal'))).toBe(false);
    const chat = (await page.getByRole('main', { name: 'Trò chuyện với Peto' }).boundingBox())!;
    const box = (await panel.boundingBox())!;
    expect(chat.x + chat.width).toBeLessThanOrEqual(box.x + 1);
    await expect(page.getByRole('textbox', { name: 'Nhắn cho Peto', exact: true })).toBeVisible();
  } else {
    expect(await panel.evaluate(node => node.matches(':modal'))).toBe(true);
    const box = (await panel.boundingBox())!;
    expect(box.y).toBeGreaterThan(0);
    expect(box.height).toBeLessThan(page.viewportSize()!.height);
    await page.getByRole('button', { name: 'Đóng bảng nguồn' }).focus();
    await page.keyboard.press('Shift+Tab');
    expect(await panel.evaluate(node => node.contains(document.activeElement))).toBe(true);
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'Đóng bảng nguồn' })).toBeFocused();
    await panel.locator('.sources-panel-scroll').evaluate(node => node.scrollTop = 0);
  }
  await page.screenshot({ path: info.outputPath('grouped-sources.png') });
  const scroll = await page.locator('.messages').evaluate(node => node.scrollTop);
  await panel.locator('.source-query-toggle').last().focus();
  await expect(panel.locator('.source-query-toggle').last()).toBeInViewport();
  expect(await page.locator('.messages').evaluate(node => node.scrollTop)).toBe(scroll);
  await page.getByRole('button', { name: 'Đóng bảng nguồn' }).click();
  await expect(panel).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  await noPageOverflow(page);
});

test('metadata streaming đến muộn không đóng nhóm đang đọc, F5 giữ đúng nguồn', async ({ page }) => {
  const fixture = await prepare(page);
  const partial = fixtureWeb(15), complete = fixtureWeb(30);
  partial.calls[0].state = 'live';
  let connected!: () => void;
  const started = new Promise<void>(resolve => { connected = resolve; });
  let response: import('node:http').ServerResponse | undefined;
  const server = createServer((request, reply) => {
    request.resume(); response = reply;
    reply.writeHead(200, { 'Content-Type': 'text/event-stream', 'Access-Control-Allow-Origin': 'http://127.0.0.1:5179', 'Access-Control-Allow-Credentials': 'true' });
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    reply.write(event({ type: 'meta', conversation_id: 'A', effort: 'low', message: { id: 5, role: 'user', content: 'Kiểm tra stream' } })
      + event({ type: 'delta', text: 'Đang đối chiếu nguồn.' }) + event({ type: 'source_activity', web: partial }));
    connected();
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address() as import('node:net').AddressInfo;
  try {
    await page.route('**/api/chat', route => route.continue({ url: `http://127.0.0.1:${address.port}/chat` }));
    await page.getByRole('textbox', { name: 'Nhắn cho Peto', exact: true }).fill('Kiểm tra stream');
    await page.getByRole('button', { name: 'Gửi', exact: true }).click();
    await started;
    const trigger = page.getByRole('button', { name: 'Mở 15 nguồn tham khảo' });
    await trigger.click();
    const group = page.locator('.sources-panel .source-query-toggle').first();
    await group.click();
    await expect(group).toHaveAttribute('aria-expanded', 'true');
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    response!.write(event({ type: 'source_activity', web: complete }));
    await expect(group).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('.sources-panel .source-query-toggle')).toHaveCount(2);
    await expect(page.locator('.sources-panel .web-source-card')).toHaveCount(15);
    fixture.setMessages([...chatMessages, { id: 5, role: 'user', content: 'Kiểm tra stream' },
      { id: 6, role: 'assistant', content: 'Đang đối chiếu nguồn.', status: 'complete', work: { ms: 1000, steps: [], complete: true, web: complete } }]);
    response!.end(event({ type: 'work', work: { ms: 1000, steps: [], complete: true, web: complete } }) + event({ type: 'done' }));
    await page.getByRole('button', { name: 'Đóng bảng nguồn' }).click();
    await page.reload();
    await page.getByRole('button', { name: 'Mở 30 nguồn tham khảo' }).click();
    await expect(page.locator('.sources-panel .source-query-toggle')).toHaveCount(2);
  } finally { response?.end(); await new Promise<void>(resolve => server.close(() => resolve())); }
});

test('hội thoại cũ không bị gán query giả, favicon lỗi vẫn xem được ở giao diện sáng', async ({ page }, info) => {
  await prepare(page, { legacy: true, iconsFail: true });
  await page.evaluate(() => document.documentElement.dataset.theme = 'light');
  await page.getByRole('button', { name: 'Mở 30 nguồn tham khảo' }).click();
  const panel = page.locator('.sources-panel');
  await expect(panel.locator('.source-query-toggle')).toHaveCount(0);
  await expect(panel.locator('.web-source-card')).toHaveCount(30);
  await expect(panel.locator('.web-source-icon svg').first()).toBeVisible();
  await expect(panel).not.toContainText('màn hình gaming 2 triệu đáng mua');
  await page.screenshot({ path: info.outputPath('legacy-sources-light.png') });
  await noPageOverflow(page);
});

test('bảng nguồn thay bảng tài liệu, đổi hội thoại và breakpoint không giữ nhầm nguồn', async ({ page }, info) => {
  await prepare(page);
  await page.getByRole('button', { name: 'Mở 105 nguồn tham khảo' }).click();
  if (info.project.name === 'pc') {
    await page.getByRole('button', { name: 'Mở bảng tài liệu' }).click();
    await expect(page.locator('.sources-panel')).toHaveCount(0);
    await expect(page.locator('.document-panel')).toHaveAttribute('open', '');
    await page.getByRole('button', { name: 'Mở 105 nguồn tham khảo' }).click();
    await expect(page.locator('.document-panel')).not.toHaveAttribute('open');
    await page.setViewportSize({ width: 900, height: 800 });
    await expect.poll(() => page.locator('.sources-panel').evaluate(node => node.matches(':modal'))).toBe(true);
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect.poll(() => page.locator('.sources-panel').evaluate(node => node.matches(':modal'))).toBe(false);
  } else await page.getByRole('button', { name: 'Đóng bảng nguồn' }).click();
  await openSidebar(page);
  await page.getByRole('button', { name: 'Một hội thoại khác', exact: true }).click();
  await expect(page).toHaveURL(/\/chat\/B$/);
  await expect(page.locator('.sources-panel')).toHaveCount(0);
});

test('giới hạn danh mục và title độc hại không phá bảng hoặc tạo liên kết nguy hiểm', async ({ page }) => {
  const web = fixtureWeb(205);
  web.sources[0].title = '<img src=x onerror=window.sourceXss=1>';
  web.sources.push({ url: 'javascript:alert(1)', title: 'Unsafe' });
  await prepare(page, { web });
  await page.getByRole('button', { name: 'Mở 200 nguồn tham khảo' }).click();
  const panel = page.locator('.sources-panel');
  await expect(panel.getByText(/giới hạn/i)).toBeVisible();
  await panel.locator('.source-query-toggle').first().click();
  await expect(panel.getByText('<img src=x onerror=window.sourceXss=1>', { exact: true })).toBeVisible();
  await expect(panel.locator('img[src="x"], img[onerror], a[href^="javascript:"]')).toHaveCount(0);
  expect(await page.evaluate(() => 'sourceXss' in window)).toBe(false);
  await noPageOverflow(page);
});

test('sửa câu hỏi đóng bảng nguồn của câu trả lời bị thay thế', async ({ page }, info) => {
  await prepare(page);
  await page.getByRole('button', { name: 'Mở 105 nguồn tham khảo' }).click();
  // On a narrow screen the modal sheet must be closed before reaching the message actions.
  if (info.project.name === 'mobile') await page.getByRole('button', { name: 'Đóng bảng nguồn' }).click();
  const edit = page.getByRole('button', { name: 'Sửa tin nhắn', exact: true }).last();
  await edit.focus();
  await page.keyboard.press('Enter');
  await page.getByRole('textbox', { name: 'Sửa tin nhắn', exact: true }).fill('Câu hỏi đã sửa');
  await page.locator('.inline-message-editor').getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect(page.locator('.sources-panel')).toHaveCount(0);
});
