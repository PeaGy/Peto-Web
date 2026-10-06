import { test, expect, type Route } from '@playwright/test';
import { mockPeto, openChat, noPageOverflow } from './fixtures';

test('thông báo lỗi có nút thử lại gọn và gửi lại đúng tin đã lưu', async ({ page }) => {
  await mockPeto(page);
  let posts = 0;
  await page.route('**/api/chat', async route => {
    posts++;
    const request = route.request().postDataJSON();
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    if (posts === 2) expect(request.branch_message_id).toBe(103);
    await route.fulfill({ contentType: 'text/event-stream', body:
      event({ type: 'meta', conversation_id: 'A', effort: 'low', message: { id: 103, role: 'user', content: request.message } })
      + (posts === 1 ? event({ type: 'error', message: 'Chưa kết nối được với dịch vụ AI. Bạn thử lại nhé.' })
        : event({ type: 'delta', text: 'Đã thử lại thành công.' }) + event({ type: 'done' })) });
  });
  await openChat(page);
  await page.getByLabel('Nhắn cho Peto', { exact: true }).fill('Đọc repo và đề xuất cải thiện');
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  const alert = page.locator('.chat-error');
  const retry = alert.getByRole('button', { name: 'Thử lại', exact: true });
  await expect(retry).toBeEnabled();
  const style = await retry.evaluate(node => {
    const css = getComputedStyle(node);
    return { radius: parseFloat(css.borderRadius), height: node.getBoundingClientRect().height };
  });
  expect(style.radius).toBeGreaterThanOrEqual(10);
  expect(style.height).toBeGreaterThanOrEqual(36);
  await noPageOverflow(page);
  await expect(alert).toHaveScreenshot('chat-retry.png');
  await retry.click();
  await expect(page.getByText('Đã thử lại thành công.', { exact: true })).toBeVisible();
  await expect(alert).toHaveCount(0);
  expect(posts).toBe(2);
  await expect(page.locator('.bubble.user').filter({ hasText: 'Đọc repo và đề xuất cải thiện' })).toHaveCount(1);
});

for (const companion of [false, true]) {
  test(`đồng bộ ${companion ? 'Companion' : 'Trò chuyện'} sau khi luồng ngắt, không gửi trùng`, async ({ page, context }) => {
    const state = await mockPeto(page, { broken: true });
    if (companion) {
      await page.goto('/#companion');
      await expect(page.getByText('Hi! It is nice to see you today.', { exact: true })).toBeVisible();
    } else await openChat(page);
    const draft = page.getByLabel(companion ? 'Nhắn cho Peto trong Companion' : 'Nhắn cho Peto', { exact: true });
    const pane = page.locator(companion ? '.companion-panel' : '.chat');
    await draft.fill('Tin kiểm tra phục hồi');
    await page.getByRole('button', { name: 'Gửi', exact: true }).click();
    await expect(page.getByText('Phần đang nhận', { exact: true })).toBeVisible();
    // Yêu cầu đã giả lập vẫn được trả lời khi setOffline, nên lần hỏi máy chủ "có mạng chưa" phải hỏng như mạng thật.
    const probe = (route: Route) => route.abort('internetdisconnected');
    await page.route('**/api/auth/me', probe);
    await context.setOffline(true);
    await expect(pane.getByText('Bạn đang ngoại tuyến.', { exact: false })).toBeVisible();
    await draft.fill('Bản nháp tiếp theo');
    await expect(pane.getByRole('button', { name: 'Gửi', exact: true })).toBeDisabled();
    await noPageOverflow(page);
    if (!companion) {
      // Thông báo ngoại tuyến làm đổi chiều cao dock. Đợi phép đo rồi chụp cùng vị trí cuối chat.
      await expect.poll(() => pane.evaluate(node => {
        const dock = node.querySelector('.chat-dock')!;
        return Math.abs(parseFloat(getComputedStyle(node).getPropertyValue('--chat-dock-height')) - dock.getBoundingClientRect().height);
      })).toBeLessThan(1);
      await pane.locator('.messages').evaluate(node => { node.scrollTop = node.scrollHeight; });
    }
    await expect(page).toHaveScreenshot(`${companion ? 'companion' : 'chat'}-offline.png`);
    state.recoveryReady = true;
    await page.unroute('**/api/auth/me', probe);
    await context.setOffline(false);
    await expect(page.getByText('Câu trả lời đã được lưu đầy đủ.', { exact: true })).toBeVisible();
    await expect(pane.getByText('Đã đồng bộ câu trả lời từ máy chủ.', { exact: true })).toBeVisible();
    await expect(draft).toHaveValue('Bản nháp tiếp theo');
    expect(state.posts).toBe(1);
    await expect(page.locator('.bubble').filter({ hasText: 'Tin kiểm tra phục hồi' })).toHaveCount(1);
  });
}

for (const action of ['retry', 'dismiss'] as const) {
  test(`${action === 'retry' ? 'kiểm tra lại' : 'đóng'} thông báo đồng bộ thất bại bằng chuột/chạm, không gửi trùng`, async ({ page }) => {
    const state = await mockPeto(page, { broken: true });
    let reads = 0;
    page.on('request', request => { if (new URL(request.url()).pathname === '/api/conversations/A/messages') reads++; });
    await openChat(page);
    const draft = page.getByLabel('Nhắn cho Peto', { exact: true });
    await draft.fill('Tin kiểm tra nút đồng bộ');
    await page.getByRole('button', { name: 'Gửi', exact: true }).click();
    await expect(page.getByText('Phần đang nhận', { exact: true })).toBeVisible();
    await draft.fill('Bản nháp cần giữ');
    const notice = page.locator('.chat-dock > .reply-recovery');
    await expect(notice.getByText('Chưa lấy được câu trả lời đã lưu.', { exact: false })).toBeVisible();
    const retry = notice.getByRole('button', { name: 'Kiểm tra lại', exact: true });
    const close = notice.getByRole('button', { name: 'Đóng thông báo đồng bộ', exact: true });
    // Kiểm tra vùng nhận cú bấm thật, không dùng force hoặc gọi trực tiếp trình xử lý.
    await retry.click({ trial: true, timeout: 1500 });
    await close.click({ trial: true, timeout: 1500 });
    const previousReads = reads;
    if (action === 'retry') {
      state.recoveryReady = true;
      await retry.click();
      await expect(page.getByText('Câu trả lời đã được lưu đầy đủ.', { exact: true })).toBeVisible();
      await expect(notice.getByText('Đã đồng bộ câu trả lời từ máy chủ.', { exact: true })).toBeVisible();
      expect(reads).toBe(previousReads + 1);
      await close.click();
    } else {
      await close.click();
      await expect(page.getByText('Phần đang nhận', { exact: true })).toBeVisible();
      expect(reads).toBe(previousReads);
    }
    await expect(notice).toHaveCount(0);
    await expect(draft).toHaveValue('Bản nháp cần giữ');
    expect(state.posts).toBe(1);
    await expect(page.locator('.bubble.user').filter({ hasText: 'Tin kiểm tra nút đồng bộ' })).toHaveCount(1);
    await noPageOverflow(page);
  });
}
