import { test, expect } from '@playwright/test';
import { mockPeto, openChat, noPageOverflow } from './fixtures';

test('Dừng trước metadata, F5 giữ trạng thái, Thử lại cùng chat bằng mã lượt mới', async ({ page }) => {
  const state = await mockPeto(page, { preservePreferences: true });
  let release!: () => void;
  const stopSignal = new Promise<void>(resolve => { release = resolve; });
  let requestId = '';
  let posts = 0;
  const user = { id: 103, role: 'user', content: 'Giải thích Docker' };
  const base = [...state.messages];
  await page.route('**/api/chat', async route => {
    const request = route.request().postDataJSON();
    posts++;
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    if (posts === 1) {
      requestId = request.request_id;
      expect(requestId).toMatch(/^[a-zA-Z0-9-]{16,64}$/);
      await stopSignal;
      await route.fulfill({ contentType: 'text/event-stream', body: event({ type: 'stopped' }) });
    } else {
      expect(request.request_id).not.toBe(requestId);
      expect(request.branch_message_id).toBe(user.id);
      expect(request.conversation_id).toBe('A');
      state.messages = [...base, user, { id: 105, role: 'assistant', content: 'Thử lại thành công', status: 'complete' } as typeof state.messages[number]];
      await route.fulfill({ contentType: 'text/event-stream', body:
        event({ type: 'meta', conversation_id: 'A', effort: 'low', message: user })
        + event({ type: 'delta', text: 'Thử lại thành công' }) + event({ type: 'done' }) });
    }
  });
  await page.route('**/api/chat/stop', async route => {
    expect(route.request().postDataJSON().request_id).toBe(requestId);
    state.messages = [...base, user, { id: 104, role: 'assistant', content: '', status: 'incomplete',
      stopped: true, turn_state: 'stopped' } as typeof state.messages[number]];
    release();
    await route.fulfill({ json: { stopped: true, state: 'stopped', conversation_id: 'A', message: user } });
  });
  await openChat(page);
  const input = page.getByLabel('Nhắn cho Peto', { exact: true });
  await input.fill(user.content);
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect.poll(() => requestId).not.toBe('');
  await input.fill('Nháp tiếp theo');
  await page.getByRole('button', { name: 'Dừng', exact: true }).click();
  await expect(page.getByText('Đã dừng theo yêu cầu của bạn.', { exact: true })).toBeVisible();
  await expect(input).toHaveValue('Nháp tiếp theo');
  await expect(page).toHaveURL(/\/chat\/A$/);
  await page.reload();
  await expect(page.getByText('Đã dừng theo yêu cầu của bạn.', { exact: true })).toBeVisible();
  await expect(input).toHaveValue('Nháp tiếp theo');
  await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
  await expect(page.getByText('Thử lại thành công', { exact: true })).toBeVisible();
  await expect(page.getByText('Đã dừng theo yêu cầu của bạn.', { exact: true })).toHaveCount(0);
  expect(posts).toBe(2);
  await expect(page.locator('.bubble.user').filter({ hasText: user.content })).toHaveCount(1);
  await expect(input).toHaveValue('Nháp tiếp theo');
  await noPageOverflow(page);
});
