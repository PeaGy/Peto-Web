import { test, expect } from '@playwright/test';
import { mockPeto, openChat, openSidebar, noPageOverflow, chatMessages } from './fixtures';

test('citation badges, tooltip, nguồn và F5 giữ đúng ánh xạ', async ({ page, context }, testInfo) => {
  await mockPeto(page);
  const sources = [
    { url: 'https://example.com/ending-c', title: 'Ending C — nguồn gốc', kind: 'citation', citation_ids: ['web:21'] },
    { url: 'https://example.com/friendship?lookup=' + 'z'.repeat(1700), title: '<img onerror=alert(1)> ' + 'x'.repeat(180), kind: 'citation', citation_ids: ['web:26'] },
  ];
  const reply = 'Cả ba vẫn liên lạc. [web:21] [web:26]\n\nNguồn cũ chưa có ánh xạ [web:999].';
  let messages: object[] = [...chatMessages];
  await page.route('**/api/conversations/A/messages', route => route.fulfill({ json: { messages } }));
  await page.route('**/api/chat', route => {
    const payload = route.request().postDataJSON();
    const user = { id: 201, role: 'user', content: payload.message };
    messages = [...chatMessages, user, { id: 202, role: 'assistant', content: reply, sources, status: 'complete' }];
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    return route.fulfill({ contentType: 'text/event-stream', body:
      event({ type: 'meta', conversation_id: 'A', effort: 'low', message: user })
      + event({ type: 'delta', text: 'Cả ba vẫn liên lạc. [' })
      + event({ type: 'delta', text: 'web:21] [we' })
      + event({ type: 'delta', text: 'b:26]\n\nNguồn cũ chưa có ánh xạ [web:999].' })
      + event({ type: 'sources', sources }) + event({ type: 'done' }) });
  });
  await openChat(page);
  await page.getByLabel('Nhắn cho Peto', { exact: true }).fill('Giải thích ending C bằng fixture.');
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  const answer = page.locator('article.bubble.assistant').last();
  const badge = answer.getByRole('link', { name: 'Nguồn 21: Ending C — nguồn gốc' });
  await expect(badge).toHaveAttribute('href', sources[0].url);
  await expect(answer.locator('a.citation-badge')).toHaveCount(2);
  await expect(answer.locator('.citation-unavailable')).toHaveCount(1);
  await expect(answer).not.toContainText('[web:');
  await expect(answer.locator('img[src="x"], img[onerror]')).toHaveCount(0);
  await answer.getByRole('button', { name: 'Mở 2 nguồn tham khảo' }).click();
  await expect(page.locator('.sources-panel .web-source-card').filter({ hasText: 'Ending C — nguồn gốc' })).toBeVisible();
  await page.getByRole('button', { name: 'Đóng bảng nguồn' }).click();
  await badge.scrollIntoViewIfNeeded();
  await badge.focus();
  await badge.press('Tab');
  await page.keyboard.press('Shift+Tab');
  await expect(badge).toBeFocused();
  await expect(page.getByRole('tooltip')).toContainText(sources[0].url);
  const bounds = await page.getByRole('tooltip').boundingBox();
  const viewport = page.viewportSize()!;
  expect(bounds && bounds.x >= 0 && bounds.x + bounds.width <= viewport.width).toBe(true);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('tooltip')).toContainText(sources[1].url);
  const longTip = await page.getByRole('tooltip').boundingBox();
  expect(longTip && longTip.x >= 0 && longTip.x + longTip.width <= viewport.width).toBe(true);
  expect(longTip && longTip.y >= 0 && longTip.y + longTip.height <= viewport.height).toBe(true);
  await badge.press('Escape');
  await noPageOverflow(page);
  await testInfo.attach('Citations trong Peto', { body: await answer.screenshot(), contentType: 'image/png' });
  // Opening a source is intercepted; no real external HTTP request is made.
  await context.route(sources[0].url, route => route.fulfill({ contentType: 'text/html', body: '<title>Fixture source</title>' }));
  const popupReady = page.waitForEvent('popup');
  await badge.click();
  const popup = await popupReady;
  await expect(popup).toHaveURL(sources[0].url);
  await popup.close();
  await page.reload();
  await expect(page.getByRole('link', { name: 'Nguồn 21: Ending C — nguồn gốc' })).toHaveAttribute('href', sources[0].url);
  await expect(page.locator('article.bubble.assistant').last()).not.toContainText('[web:');
  await openSidebar(page); // Existing navigation remains usable after reload.
  await noPageOverflow(page);
});
