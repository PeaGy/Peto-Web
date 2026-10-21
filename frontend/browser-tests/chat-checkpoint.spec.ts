import { test, expect } from '@playwright/test';
import { mockPeto, openChat, noPageOverflow } from './fixtures';

test('F5 giữ lượt ngắt rỗng, không tự gọi AI; Thử lại dùng đúng tin nguồn và giữ bản nháp', async ({ page }) => {
  const state = await mockPeto(page, { preservePreferences: true });
  const user = { id: 103, role: 'user', content: 'Câu bị ngắt trước khi có chữ' };
  state.messages = [...state.messages, user, { id: 104, role: 'assistant', content: '', status: 'incomplete',
    turn_state: 'interrupted', turn_outcome: 'process_restarted' } as typeof state.messages[number]];
  let posts = 0;
  await page.route('**/api/chat', async route => {
    posts++;
    const request = route.request().postDataJSON();
    expect(request.branch_message_id).toBe(user.id);
    expect(request.conversation_id).toBe('A');
    expect(request.request_id).toMatch(/^[a-zA-Z0-9-]{16,64}$/);
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    await route.fulfill({ contentType: 'text/event-stream', body:
      event({ type: 'meta', conversation_id: 'A', effort: 'low', message: user })
      + event({ type: 'delta', text: 'Đã thử lại theo yêu cầu' }) + event({ type: 'done' }) });
  });
  await openChat(page);
  const draft = page.getByLabel('Nhắn cho Peto', { exact: true });
  await draft.fill('Bản nháp vẫn còn');
  await page.reload();
  await expect(page.getByText('Lượt bị ngắt khi máy chủ khởi động lại.', { exact: true })).toBeVisible();
  await expect(draft).toHaveValue('Bản nháp vẫn còn');
  expect(posts).toBe(0);
  await page.screenshot({ path: test.info().outputPath('recovered-empty.png'), fullPage: true });
  await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
  await expect(page.getByText('Đã thử lại theo yêu cầu', { exact: true })).toBeVisible();
  expect(posts).toBe(1);
  await expect(page.locator('.bubble.user').filter({ hasText: user.content })).toHaveCount(1);
  await expect(draft).toHaveValue('Bản nháp vẫn còn');
  await noPageOverflow(page);
});

test('checkpoint còn chạy không có nút Thử lại sau reload', async ({ page }) => {
  const state = await mockPeto(page);
  state.messages = [...state.messages, { id: 103, role: 'user', content: 'Câu đang xử lý' },
    { id: 104, role: 'assistant', content: 'Phần đã lưu', status: 'incomplete', turn_state: 'running' } as typeof state.messages[number]];
  await openChat(page);
  await expect(page.getByText('Lượt này vẫn đang được xử lý.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Thử lại', exact: true })).toHaveCount(0);
  expect(state.posts).toBe(0);
  await noPageOverflow(page);
});
