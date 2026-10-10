import { test, expect } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

test('soạn câu tiếp theo khi chờ trả lời, giữ qua ID mới và F5, chỉ gửi khi người dùng bấm', async ({ page }) => {
  await mockPeto(page, { preservePreferences: true });
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const requests: { message: string; conversation_id: string | null }[] = [];
  await page.route('**/api/chat', async route => {
    const payload = route.request().postDataJSON(); requests.push(payload);
    if (requests.length === 1) await gate;
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    await route.fulfill({ contentType: 'text/event-stream', body:
      event({ type: 'meta', conversation_id: 'A', effort: 'low', message: { id: requests.length * 10, role: 'user', content: payload.message } })
      + event({ type: 'delta', text: 'Đã trả lời câu hỏi.' }) + event({ type: 'done' }) });
  });
  await page.goto('/');
  const input = page.getByLabel('Nhắn cho Peto', { exact: true });
  await input.fill('Câu hỏi đầu tiên');
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect.poll(() => requests.length).toBe(1);
  await expect(page.getByRole('button', { name: 'Dừng', exact: true })).toBeVisible();
  await expect(input).toBeEnabled();
  await input.fill('Câu tiếp theo'); await input.press('Shift+Enter'); await input.pressSequentially('Đã soạn sẵn');
  await input.press('Enter');
  await expect(input).toHaveValue('Câu tiếp theo\nĐã soạn sẵn');
  expect(requests).toHaveLength(1);
  await noPageOverflow(page);
  release();
  await expect(page).toHaveURL(/\/chat\/A$/);
  await expect(page.getByRole('button', { name: 'Gửi', exact: true })).toBeEnabled();
  await expect(input).toHaveValue('Câu tiếp theo\nĐã soạn sẵn');
  expect(requests).toHaveLength(1);
  await page.reload();
  await expect(input).toHaveValue('Câu tiếp theo\nĐã soạn sẵn');
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1]).toMatchObject({ message: 'Câu tiếp theo\nĐã soạn sẵn', conversation_id: 'A' });
  await expect(input).toHaveValue('');
});
