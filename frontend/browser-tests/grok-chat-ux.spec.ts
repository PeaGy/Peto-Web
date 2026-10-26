import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow, title } from './fixtures';

const excerpt = 'Một đoạn trả lời để hỏi tiếp mà không phải nhập lại ngữ cảnh.';
const code = Array.from({ length: 9 }, (_, i) => `const item${i} = "${'Dòng mã dài kiểm tra ngắt dòng. '.repeat(4)}";`).join('\n');
const answer = `${excerpt}\n\n| Mục | Giá |\n| --- | --- |\n| Đầu vào | 2,00 USD |\n| Đầu ra | 10 USD |\n\n\`\`\`js\n${code}\n\`\`\``;
const browserErrors = new WeakMap<Page, string[]>();
test.afterEach(async ({ page }) => { expect(browserErrors.get(page) ?? []).toEqual([]); });
async function setup(page: Page) {
  const errors: string[] = []; browserErrors.set(page, errors);
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error' && !message.text().includes('Failed to load resource:')) errors.push(message.text()); });
  await mockPeto(page, { preservePreferences: true });
  const family = [{ conversation_id: 'A', message_id: 2 }, { conversation_id: 'B', message_id: 4 }];
  const histories: Record<string, object[]> = {
    A: [{ id: 1, role: 'user', content: 'Hãy so sánh và đưa ví dụ mã.' }, { id: 2, role: 'assistant', content: answer, status: 'complete' }],
    B: [{ id: 3, role: 'user', content: 'Hãy so sánh và đưa ví dụ mã.' }, { id: 4, role: 'assistant', content: 'Một cách trả lời khác, bản cũ vẫn còn.', status: 'complete' }],
  };
  const payloads: Record<string, unknown>[] = [];
  await page.route('**/api/conversations/*/messages', route => route.fulfill({ json: { messages: histories[route.request().url().split('/').at(-2)!] ?? [] } }));
  await page.route('**/api/conversations/*/preview', route => route.fulfill({ json: { messages: histories[route.request().url().split('/').at(-2)!] ?? [], truncated: false } }));
  await page.route('**/api/chat', route => {
    const payload = route.request().postDataJSON(); payloads.push(payload);
    const regenerating = payload.branch_message_id === 1;
    let cid = 'A', user: object, reply: object, replyText: string, replyId: number;
    if (regenerating) {
      cid = 'B';
      histories.A[1] = { ...histories.A[1], reply_variants: { index: 0, choices: family } };
      histories.B[1] = { ...histories.B[1], reply_variants: { index: 1, choices: family } };
      [user, reply] = histories.B; replyText = 'Một cách trả lời khác, bản cũ vẫn còn.'; replyId = 4;
    } else {
      user = { id: 5, role: 'user', content: payload.message, ...(payload.quoted_source ? { quoted_source: payload.quoted_source } : {}) };
      replyText = 'Đã nhận câu hỏi cùng đoạn trích, đây là phản hồi giả lập.'; replyId = 6;
      reply = { id: replyId, role: 'assistant', content: replyText, status: 'complete' };
      histories.A.push(user, reply);
    }
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    return route.fulfill({ contentType: 'text/event-stream', body: event({ type: 'meta', conversation_id: cid, effort: 'low', message: user })
      + event({ type: 'delta', text: replyText }) + event({ type: 'done', message_id: replyId }) });
  });
  await page.addInitScript(() => {
    const store = window as unknown as { copied: string; printHtml: string };
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
      writeText: async (value: string) => { store.copied = value; },
      write: async (items: ClipboardItem[]) => { store.copied = await (await items[0].getType('text/plain')).text(); },
    } });
    const open = window.open;
    window.open = function (...args: Parameters<typeof window.open>) {
      const popup = open.apply(window, args);
      if (popup) popup.print = () => { store.printHtml = popup.document.body.innerHTML; popup.close(); };
      return popup;
    };
  });
  await page.goto('/chat/A');
  await expect(page.locator('article[data-message-id="2"]')).toContainText(excerpt);
  return { payloads, histories };
}

test('table, code and compact export actions work without model requests', async ({ page }, info) => {
  const { payloads } = await setup(page);
  const response = page.locator('article[data-message-id="2"]');
  await response.getByRole('button', { name: 'Sao chép bảng', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { copied: string }).copied)).toContain('Đầu vào,"2,00 USD"');
  const download = page.waitForEvent('download');
  await response.getByRole('button', { name: 'Lưu bảng CSV' }).click();
  expect((await download).suggestedFilename()).toBe('peto-table.csv');
  await response.getByRole('button', { name: 'Ngắt dòng', exact: true }).click();
  await expect(response.locator('.message-code')).toHaveClass(/wrapped/);
  await response.getByRole('button', { name: 'Thu gọn mã' }).click();
  await expect(response.locator('pre')).toBeHidden();
  await response.locator('.code-copy').click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { copied: string }).copied)).toBe(code + '\n');
  await page.screenshot({ path: info.outputPath('output-dark.png') });
  await response.getByRole('button', { name: 'Mở rộng mã', exact: true }).click();
  await expect(response.locator('pre')).toBeVisible();
  await expect(response.locator('.message-code')).toHaveClass(/wrapped/);
  const more = response.getByRole('button', { name: 'Thêm thao tác' });
  await more.focus(); await more.press('ArrowUp');
  await expect(page.getByRole('menuitem', { name: 'In / lưu PDF' })).toBeFocused();
  const markdown = page.waitForEvent('download');
  await page.getByRole('menuitem', { name: 'Lưu Markdown' }).click();
  expect((await markdown).suggestedFilename()).toBe('peto-response-2.md');
  await more.click(); await page.getByRole('menuitem', { name: 'In / lưu PDF' }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { printHtml: string }).printHtml ?? '')).toContain('item8');
  expect(await page.evaluate(() => (window as unknown as { printHtml: string }).printHtml)).not.toContain('data-export-exclude');
  expect(payloads).toHaveLength(0);
  await noPageOverflow(page);
});

test('selected excerpt and long paste preserve the draft; excerpt survives reload', async ({ page }, info) => {
  const { payloads } = await setup(page);
  const input = page.getByRole('textbox', { name: 'Nhắn cho Peto' });
  await input.fill('Giải thích thêm');
  const prose = page.locator('article[data-message-id="2"] [data-message-content] > p').first();
  await prose.scrollIntoViewIfNeeded();
  await prose.evaluate(element => {
    const range = document.createRange(); range.selectNodeContents(element);
    const selection = window.getSelection()!; selection.removeAllRanges(); selection.addRange(range);
    document.dispatchEvent(new Event('selectionchange'));
  });
  await page.getByRole('button', { name: 'Thêm đoạn trích vào câu hỏi' }).click();
  await expect(input).toHaveValue('Giải thích thêm');
  await expect(page.locator('.composer .quoted-source')).toContainText(excerpt);
  await page.screenshot({ path: info.outputPath('quoted-draft.png') });
  const long = 'Nội dung đã dán tiếng Việt 🐱\n'.repeat(2100);
  await input.evaluate((node, text) => {
    const element = node as HTMLTextAreaElement; element.setSelectionRange(3, 7);
    const data = new DataTransfer(); data.setData('text/plain', text);
    element.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: data }));
  }, long);
  await expect(page.getByRole('button', { name: 'Xem pasted-text.txt' })).toBeVisible();
  await page.getByRole('button', { name: 'Xem pasted-text.txt' }).click();
  await expect(page.getByLabel('Nội dung tệp đã dán')).toHaveText(long);
  await page.getByRole('button', { name: 'Đóng xem tệp' }).click();
  await page.getByRole('button', { name: 'Hoàn tác', exact: true }).click();
  await expect(input).toHaveValue('Giả' + long + 'ích thêm');
  await expect(page.getByRole('button', { name: 'Xem pasted-text.txt' })).toHaveCount(0);
  await input.fill('Giải thích thêm');
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect(page.locator('article[data-message-id="6"]')).toContainText('phản hồi giả lập');
  expect(payloads).toHaveLength(1);
  expect(payloads[0]).toMatchObject({ message: 'Giải thích thêm', quoted_source: { message_id: 2, text: excerpt } });
  await page.reload();
  await expect(page.locator('article[data-message-id="5"] .quoted-source')).toContainText(excerpt);
  await page.locator('article[data-message-id="5"]').getByRole('button', { name: 'Về tin nhắn được trích dẫn' }).click();
  await expect(page.locator('article[data-message-id="2"]')).toBeFocused();
  await noPageOverflow(page);
});

test('history list previews before opening; keyboard and mobile back retain selection', async ({ page }, info) => {
  const { payloads } = await setup(page);
  await page.keyboard.press('Control+k');
  const dialog = page.getByRole('dialog', { name: 'Tìm kiếm hội thoại' });
  const search = dialog.getByRole('searchbox');
  await expect(dialog.getByRole('button', { name: title, exact: true })).toBeVisible();
  if (info.project.name === 'mobile') {
    await dialog.getByRole('button', { name: title, exact: true }).click();
    await expect(dialog.getByRole('button', { name: 'Mở hội thoại đang xem trước' })).toBeFocused();
    await expect(dialog.getByRole('region', { name: 'Nội dung xem trước' })).toContainText(excerpt);
    await page.screenshot({ path: info.outputPath('search-mobile.png') });
    await dialog.getByRole('button', { name: 'Về kết quả tìm kiếm' }).click();
    await expect(dialog.getByRole('button', { name: title, exact: true })).toBeFocused();
    await dialog.getByRole('button', { name: 'Một hội thoại khác', exact: true }).click();
    await expect(dialog.getByRole('region', { name: 'Nội dung xem trước' })).toContainText('Một cách trả lời khác');
    await dialog.getByRole('button', { name: 'Mở hội thoại đang xem trước' }).click();
  } else {
    await search.press('ArrowDown');
    await expect(dialog.getByRole('region', { name: 'Nội dung xem trước' })).toContainText(excerpt);
    await page.screenshot({ path: info.outputPath('search-desktop.png') });
    await search.press('ArrowDown');
    await expect(dialog.getByRole('region', { name: 'Nội dung xem trước' })).toContainText('Một cách trả lời khác');
    await search.press('Enter');
  }
  await expect(page).toHaveURL(/\/chat\/B$/);
  await expect(dialog).toHaveCount(0);
  expect(payloads).toHaveLength(0);
  await noPageOverflow(page);
});

test('regenerate creates a real family and preserves both answers across reload', async ({ page }, info) => {
  const { payloads } = await setup(page);
  await page.getByRole('button', { name: 'Tạo lại câu trả lời' }).click();
  await expect(page).toHaveURL(/\/chat\/B$/);
  await expect(page.getByRole('group', { name: 'Phiên bản câu trả lời' })).toContainText('2/2');
  expect(payloads).toHaveLength(1);
  expect(payloads[0]).toMatchObject({ branch_message_id: 1, message: 'Hãy so sánh và đưa ví dụ mã.' });
  await page.getByRole('button', { name: 'Câu trả lời trước' }).click();
  await expect(page.locator('article[data-message-id="2"]')).toBeFocused();
  await expect(page.getByRole('group', { name: 'Phiên bản câu trả lời' })).toContainText('1/2');
  await page.reload();
  await expect(page.getByRole('group', { name: 'Phiên bản câu trả lời' })).toContainText('1/2');
  await page.getByRole('button', { name: 'Câu trả lời sau' }).click();
  await expect(page.locator('article[data-message-id="4"]')).toBeFocused();
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
  await page.screenshot({ path: info.outputPath('variants-light.png') });
  expect(payloads).toHaveLength(1);
  await noPageOverflow(page);
});
