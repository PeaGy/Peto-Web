import { test, expect } from '@playwright/test';
import { mockPeto, openChat, noPageOverflow } from './fixtures';

test('bàn phím đi thẳng tới ô nhắn, đóng editor trả focus và drawer mobile giữ Tab', async ({ page }, info) => {
  await mockPeto(page);
  await openChat(page);
  const skip = page.getByRole('button', { name: 'Đến ô nhắn', exact: true });
  await skip.focus(); await page.keyboard.press('Enter');
  await expect(page.getByRole('textbox', { name: 'Nhắn cho Peto', exact: true })).toBeFocused();
  const revise = page.getByRole('button', { name: 'Sửa tin nhắn', exact: true }).first();
  await revise.focus(); await page.keyboard.press('Enter');
  await expect(page.getByRole('textbox', { name: 'Sửa tin nhắn', exact: true })).toBeFocused();
  await page.keyboard.press('Escape'); await expect(revise).toBeFocused();
  if (info.project.name === 'mobile') {
    const trigger = page.getByRole('button', { name: 'Mở danh sách hội thoại', exact: true });
    await trigger.focus(); await page.keyboard.press('Enter');
    const sidebar = page.getByRole('complementary', { name: 'Điều hướng Peto' });
    const visibleButtons = sidebar.getByRole('button');
    await expect(visibleButtons.first()).toBeFocused();
    await visibleButtons.last().focus(); await page.keyboard.press('Tab');
    await expect(visibleButtons.first()).toBeFocused();
    await page.keyboard.press('Shift+Tab'); await expect(visibleButtons.last()).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(sidebar).toBeHidden(); await expect(trigger).toBeFocused();
  }
  await noPageOverflow(page);
});

test('code, bảng và nguồn dùng được bằng bàn phím; metadata và HTML lạ không phá câu trả lời', async ({ page }) => {
  const state = await mockPeto(page);
  const content = 'Kiểm thử bằng chứng nguồn.\n\n<script>window.stage4Unsafe=true</script>\n\n'
    + '```js\nconst veryLong = "' + 'code_'.repeat(90) + '";\n```\n\n'
    + '| Giá trị |\n| --- |\n| ' + 'data_'.repeat(100) + ' |';
  state.messages.push({ id: 4, role: 'assistant', content, status: 'complete', sources: [
    null, { url: 'javascript:alert(1)', title: 'Unsafe' },
    { url: 'https://youtu.be/demo', title: 'Video — mới tìm thấy', kind: 'citation', access: 'search' },
    { url: 'https://example.com/page', title: 'Trang đã đọc', kind: 'result', access: 'page' },
    { url: 'https://github.com/test/repo', title: 'Tệp GitHub', kind: 'result', access: 'tool', partial: true },
  ] } as typeof state.messages[number]);
  await openChat(page);
  const code = page.getByRole('region', { name: 'Mã JavaScript', exact: true }).last();
  await code.focus(); await page.keyboard.press('ArrowRight');
  await expect.poll(() => code.evaluate(node => node.scrollLeft)).toBeGreaterThan(0);
  const table = page.locator('.table-scroll').last();
  await table.focus(); await page.keyboard.press('ArrowRight');
  await expect.poll(() => table.evaluate(node => node.scrollLeft)).toBeGreaterThan(0);
  const sources = page.locator('.web-sources > summary');
  await sources.focus(); await page.keyboard.press('Enter');
  await expect(page.getByText('Kết quả tìm kiếm', { exact: true })).toBeVisible();
  await expect(page.getByText('Đã mở trang', { exact: true })).toBeVisible();
  await expect(page.getByText('Công cụ · một phần', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: /Video — mới tìm thấy/ }).locator('.youtube-icon')).toBeVisible();
  await expect(page.getByText('Unsafe', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Kiểm thử bằng chứng nguồn.', { exact: true })).toHaveCount(1);
  expect(await page.evaluate(() => 'stage4Unsafe' in window)).toBe(false);
  const lastSource = page.locator('.web-source-card').last();
  await lastSource.focus();
  await expect(lastSource).toBeInViewport();
  expect((await lastSource.boundingBox())!.y + (await lastSource.boundingBox())!.height)
    .toBeLessThanOrEqual((await page.locator('.chat-dock').boundingBox())!.y);
  await page.screenshot({ path: test.info().outputPath('sources-and-keyboard.png'), fullPage: true });
  await noPageOverflow(page);
});

test('hoàn tất lượt giữ focus ở code; Enter bằng IME không tự gửi', async ({ page }) => {
  const state = await mockPeto(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let posts = 0;
  await page.route('**/api/chat', async route => {
    posts++;
    const user = { id: 101, role: 'user', content: route.request().postDataJSON().message };
    const reply = { id: 102, role: 'assistant', content: 'Đã hoàn tất kiểm thử focus.', status: 'complete' };
    await gate;
    state.messages = [...state.messages, user, reply];
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    await route.fulfill({ contentType: 'text/event-stream', body: event({ type: 'meta', conversation_id: 'A', effort: 'low', message: user })
      + event({ type: 'delta', text: reply.content }) + event({ type: 'done' }) });
  });
  await openChat(page);
  const draft = page.getByRole('textbox', { name: 'Nhắn cho Peto', exact: true });
  await draft.fill('Đang soạn tiếng Việt');
  await draft.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', isComposing: true, bubbles: true });
  expect(posts).toBe(0);
  await draft.press('Enter');
  await expect(page.getByRole('button', { name: 'Dừng', exact: true })).toBeVisible();
  const code = page.getByRole('region', { name: 'Mã JavaScript', exact: true });
  await code.focus(); release();
  await expect(page.getByText('Đã hoàn tất kiểm thử focus.', { exact: true })).toBeVisible();
  await expect(code).toBeFocused();
  await expect(page.getByRole('status', { name: 'Trạng thái câu trả lời', exact: true })).toHaveText('Peto đã trả lời xong.');
  expect(posts).toBe(1);
});

test('nút tin mới nhất bằng bàn phím giữ điểm focus sau khi ẩn', async ({ page }) => {
  await mockPeto(page, { long: true });
  await page.goto('/chat/A');
  const messages = page.getByRole('region', { name: 'Nội dung hội thoại', exact: true });
  await expect(page.locator('.bubble')).toHaveCount(40);
  await messages.evaluate(node => { node.scrollTop = 0; });
  const jump = page.getByRole('button', { name: 'Tin mới nhất', exact: true });
  await expect(jump).toBeVisible(); await jump.focus(); await page.keyboard.press('Enter');
  await expect(jump).toBeHidden(); await expect(messages).toBeFocused();
  await noPageOverflow(page);
});

test('chỉ số Chat có cỡ mẫu, thiếu dữ liệu và cuộn ngang trên mobile', async ({ page }) => {
  await mockPeto(page);
  await page.route('**/api/auth/me', route => route.fulfill({ json: { authenticated: true, login_configured: true,
    user: { id: 'test-account', provider: 'discord', username: 'demo', display_name: 'Người kiểm thử', avatar_url: '', is_owner: true } } }));
  await page.route('**/api/admin/overview?*', route => route.fulfill({ json: {
    range: '7d', timezone: 'Asia/Ho_Chi_Minh', generated_at: 1792576800, data_since: 1792576800,
    buckets: [], bucket_unit: 'day', covered_buckets: 0, calls: 0, turns: 0, success_rate: null,
    outcomes: [], latency: { p50_ms: null, p95_ms: null, first_p50_ms: null, first_p95_ms: null },
    cost: { total_usd: null, by_service: null, rates: 'missing', unpriced_models: [], cache_unknown_models: [], previous_total_usd: null, not_counted: [] },
    previous_calls: null, models: [], searches: 0, accounts: 0, dropped_events: 0,
    chat: { configs: [{ model: 'luna', slug: 'gpt-6-luna', label: '6 Luna', effort: 'low', turns: 2, complete: 1,
      total_samples: 1, first_samples: 2, p50_ms: 2000, p95_ms: 2000, first_p50_ms: 400, first_p95_ms: 800 }],
      legacy_turns: 3, summary: { attempts: 1, complete: 0, source_changed: 0, errors: 1, cancelled: 0, sdk_calls: 1, usage_calls: 0,
        latency_samples: 1, p50_ms: 1000, p95_ms: 1000 }, tools: { results: 2, errors: 1, web_errors: 1 }, context_overflows: 1,
      recovery: { checks: 2, complete: 0, partial: 1, pending: 1, missing: 0 } },
  } }));
  await page.goto('/admin');
  const summary = page.getByText('Ngữ cảnh và phục hồi Chat', { exact: true });
  await summary.focus(); await page.keyboard.press('Enter');
  await expect(page.getByText('gpt-6-luna', { exact: true })).toBeVisible();
  const table = page.getByRole('region', { name: 'Số đo Chat theo model và mức suy nghĩ' });
  await table.focus();
  await page.screenshot({ path: test.info().outputPath('chat-metrics.png'), fullPage: true });
  await noPageOverflow(page);
});
