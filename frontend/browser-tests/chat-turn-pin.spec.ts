import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

// Gửi tin như Claude (22/11/2026): câu hỏi vừa gửi trượt lên gần đỉnh khung tin nhắn, câu trả lời viết dần xuống bên
// dưới, khung không tự cuộn theo chữ nên kéo lên xuống được trong lúc Peto đang viết. Luồng /api/chat là luồng giả
// chạy từng mảnh trong trang (fetch bị thay), để kiểm được lúc đang viết chứ không chỉ khi xong.
const history = Array.from({ length: 6 }, (_, i) => [
  { id: i * 2 + 1, role: 'user', content: `Câu hỏi cũ số ${i + 1}` },
  { id: i * 2 + 2, role: 'assistant', content: `Câu trả lời cũ số ${i + 1}. ${'Một đoạn văn để lịch sử đủ dài. '.repeat(12)}`, status: 'complete' },
]).flat();

async function setup(page: Page, pieces: number) {
  await mockPeto(page, { preservePreferences: true });
  await page.route('**/api/conversations/A/messages*', route => route.fulfill({ json: { messages: history } }));
  await page.addInitScript((count: number) => {
    const original = window.fetch;
    const state = { sent: 0, done: false };
    Object.assign(window, { turnStream: state });
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (!url.endsWith('/api/chat') || init?.method !== 'POST') return original(input, init);
      const body = JSON.parse(String(init.body));
      const encoder = new TextEncoder();
      const event = (value: object) => encoder.encode(`data: ${JSON.stringify(value)}\n\n`);
      const stream = new ReadableStream({
        async start(controller) {
          controller.enqueue(event({ type: 'meta', conversation_id: 'A', effort: 'low', message: { id: 101, role: 'user', content: body.message } }));
          for (let i = 0; i < count; i += 1) {
            await new Promise(resolve => setTimeout(resolve, 60));
            controller.enqueue(event({ type: 'delta', text: `Đoạn ${i + 1} của câu trả lời đang viết dần xuống dưới. ` }));
            state.sent = i + 1;
          }
          controller.enqueue(event({ type: 'done', message_id: 102 }));
          state.done = true;
          controller.close();
        },
      });
      return new Response(stream, { headers: { 'content-type': 'text/event-stream' } });
    };
  }, pieces);
  await page.goto('/chat/A');
  await expect(page.getByText('Câu trả lời cũ số 6')).toBeVisible();
}

// Khoảng cách từ câu hỏi vừa gửi tới chỗ nó nằm khi được ghim: ngay dưới padding trên của khung (điện thoại chừa chỗ
// cho nút đầu trang).
const questionTop = (page: Page) => page.locator('.messages').evaluate(container => {
  const question = [...container.querySelectorAll<HTMLElement>(':scope > article[data-role="user"]')].at(-1)!;
  return question.getBoundingClientRect().top - container.getBoundingClientRect().top - parseFloat(getComputedStyle(container).paddingTop);
});
const streamState = (page: Page) => page.evaluate(() => (window as unknown as { turnStream: { sent: number; done: boolean } }).turnStream);

async function send(page: Page) {
  const composer = page.getByLabel('Nhắn cho Peto', { exact: true });
  await composer.fill('Câu hỏi mới');
  await composer.press('Enter');
}

test('câu hỏi vừa gửi lên đỉnh, câu trả lời dài viết xuống mà không kéo khung theo', async ({ page }) => {
  await setup(page, 120);
  await send(page);
  // Câu hỏi trượt lên đỉnh trong lúc Peto bắt đầu viết.
  await expect.poll(async () => Math.abs(await questionTop(page))).toBeLessThan(2);
  expect((await streamState(page)).done).toBe(false);
  // Chữ mới chạy dài quá màn hình mà khung vẫn đứng yên ở câu hỏi.
  await expect.poll(async () => (await streamState(page)).sent).toBeGreaterThan(60);
  expect(Math.abs(await questionTop(page))).toBeLessThan(2);
  // Kéo lên giữa lúc đang viết: không bị giật về đáy.
  await page.locator('.messages').evaluate(container => { container.scrollTop -= 300; });
  const scrolled = await page.locator('.messages').evaluate(container => container.scrollTop);
  await page.waitForTimeout(600);
  expect((await streamState(page)).done).toBe(false);
  expect(Math.abs(await page.locator('.messages').evaluate(container => container.scrollTop) - scrolled)).toBeLessThan(2);
  // Nút "Tin mới nhất" đưa xuống đáy và từ đó bám theo chữ mới.
  await page.getByRole('button', { name: 'Tin mới nhất' }).click();
  await expect.poll(async () => (await streamState(page)).done, { timeout: 20_000 }).toBe(true);
  await expect.poll(() => page.locator('.messages').evaluate(container =>
    container.scrollHeight - container.scrollTop - container.clientHeight)).toBeLessThan(80);
  await noPageOverflow(page);
});

test('câu trả lời ngắn: câu hỏi vẫn ở đỉnh sau khi xong, có chỗ trống bên dưới như Claude', async ({ page }) => {
  await setup(page, 4);
  await send(page);
  await expect.poll(async () => (await streamState(page)).done).toBe(true);
  await expect(page.getByText('Đoạn 4 của câu trả lời')).toBeVisible();
  await expect.poll(async () => Math.abs(await questionTop(page))).toBeLessThan(2);
  await expect(page.getByRole('button', { name: 'Tin mới nhất' })).toHaveCount(0);
  // Mở lại cuộc trò chuyện thì bỏ phần đệm: tin cuối nằm sát đáy như thường.
  await page.reload();
  await expect(page.getByText('Câu trả lời cũ số 6')).toBeVisible();
  expect(await page.locator('.messages > .turn-room').evaluate(node => node.getBoundingClientRect().height)).toBe(0);
  await noPageOverflow(page);
});

test('tin rất dài gập lại như Claude: câu hỏi ghim lên đỉnh mà đầu câu trả lời vẫn trong màn hình', async ({ page }, info) => {
  await setup(page, 30);
  const composer = page.getByLabel('Nhắn cho Peto', { exact: true });
  await composer.fill(Array.from({ length: 40 }, (_, i) => `Dòng thứ ${i + 1} của một tin rất dài.`).join('\n'));
  await composer.press('Enter');
  await expect.poll(async () => Math.abs(await questionTop(page))).toBeLessThan(2);
  const question = page.locator('.messages > article[data-role="user"]').last();
  const fold = question.locator('.user-fold');
  await expect(fold).toHaveClass(/folded/);
  expect((await fold.boundingBox())!.height).toBeLessThanOrEqual(200);
  // Đầu câu trả lời nằm ngay dưới câu hỏi đã gập, trong khung nhìn.
  const answer = page.locator('.messages > article[data-role="assistant"]').last();
  await expect(answer).toContainText('Đoạn 1 của câu trả lời');
  const view = (await page.locator('.messages').boundingBox())!;
  expect((await answer.boundingBox())!.y).toBeLessThan(view.y + view.height - 40);
  await expect.poll(async () => (await streamState(page)).done, { timeout: 20_000 }).toBe(true);
  await page.screenshot({ path: info.outputPath('user-fold.png') });
  // Xem thêm mở hết tin mà mép trên đứng yên; Thu gọn gập lại.
  const top = (await question.boundingBox())!.y;
  await question.getByRole('button', { name: 'Xem thêm' }).click();
  await expect(fold).not.toHaveClass(/folded/);
  expect((await fold.boundingBox())!.height).toBeGreaterThan(400);
  expect(Math.abs((await question.boundingBox())!.y - top)).toBeLessThan(2);
  await question.getByRole('button', { name: 'Thu gọn' }).click();
  await expect(fold).toHaveClass(/folded/);
  await noPageOverflow(page);
});

// Bàn phím điện thoại (25/11/2026): khung thấp lại, ô nhắn nhảy lên. Cuối tin nhắn cuối đang thấy thì vẫn thấy, ngay
// trên ô nhắn; đang đọc giữa một câu trả lời dài thì khung đứng yên. Bàn phím giả bằng cách thu thấp cửa sổ
// (interactive-widget=resizes-content cũng làm khung thấp lại như vậy).
const lastEnd = (page: Page) => page.evaluate(() => {
  const last = [...document.querySelectorAll<HTMLElement>('.messages > article')].at(-1)!;
  return { end: last.getBoundingClientRect().bottom, composer: document.querySelector('.chat-dock .composer')!.getBoundingClientRect().top };
});
async function openKeyboard(page: Page) {
  const size = page.viewportSize()!;
  await page.setViewportSize({ width: size.width, height: size.height - 320 });
}

test('mở bàn phím sau lượt vừa xong: cuối câu trả lời vẫn nằm ngay trên ô nhắn', async ({ page }) => {
  await setup(page, 12);
  await send(page);
  await expect.poll(async () => (await streamState(page)).done).toBe(true);
  await expect(page.getByRole('button', { name: 'Gửi', exact: true })).toBeVisible();
  const before = await lastEnd(page);
  expect(before.end).toBeLessThan(before.composer);
  await openKeyboard(page);
  await expect.poll(async () => { const now = await lastEnd(page); return now.end <= now.composer; }).toBe(true);
});

test('mở bàn phím khi đang ở cuối cuộc cũ: tin cuối vẫn thấy; đang đọc chỗ khác thì khung đứng yên', async ({ page }) => {
  await setup(page, 1);
  await expect.poll(async () => { const now = await lastEnd(page); return now.end <= now.composer; }).toBe(true);
  await openKeyboard(page);
  await expect.poll(async () => { const now = await lastEnd(page); return now.end <= now.composer; }).toBe(true);
  const size = page.viewportSize()!;
  await page.setViewportSize({ width: size.width, height: size.height + 320 });
  await page.locator('.messages').evaluate(node => { node.scrollTop = 0; });
  await page.waitForTimeout(200);
  await openKeyboard(page);
  await page.waitForTimeout(300);
  expect(await page.locator('.messages').evaluate(node => node.scrollTop)).toBe(0);
});
