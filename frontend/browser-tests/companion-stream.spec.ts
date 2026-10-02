import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow, openSidebar } from './fixtures';

test('đọc sớm qua luồng SSE thật, giữ nháp mới và Dừng hủy tiếng lẫn lượt trên PC/điện thoại', async ({ page }) => {
  await mockPeto(page);
  await page.addInitScript(() => {
    localStorage.setItem('peto-local-voice', '1'); localStorage.setItem('peto-companion-muted', '0');
    // Luồng giả cho phép test chủ động cho chữ về, thay vì trả toàn bộ đáp án một lần.
    const original = window.fetch;
    const turns: { emit(value: object): void; aborted: boolean }[] = [];
    window.fetch = async (input, init) => {
      if (String(input) !== '/api/chat') return original(input, init);
      const signal = init?.signal;
      let ended = false;
      const body = new ReadableStream<Uint8Array>({ start(controller) {
        const turn = { aborted: false, emit(value: object) {
          if (ended) return;
          controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(value)}\n\n`));
          if ((value as { type?: string }).type === 'done') { ended = true; controller.close(); }
        } };
        turns.push(turn);
        signal?.addEventListener('abort', () => {
          turn.aborted = true;
          if (!ended) { ended = true; controller.error(new DOMException('Đã dừng', 'AbortError')); }
        }, { once: true });
      } });
      return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } });
    };
    class AudioStub {
      onplaying = null; onwaiting = null; onended = null; onerror = null; onpause = null;
      play() { return Promise.resolve(); } pause() {}
      addEventListener() {} removeEventListener() {}
    }
    Object.assign(window, { Audio: AudioStub, testTurns: turns });
  });
  await page.route('**/api/voice/health', route => route.fulfill({ json: {
    ok: true, voices: ['stepfun:jilingshaonv'], home: { online: false, voices: [] },
    official: { allowed: true, voices: ['stepfun:jilingshaonv'], used: 0, limit: 5000 },
  } }));
  const spoken: string[] = [];
  await page.route('**/api/voice/speak', route => {
    spoken.push(route.request().postDataJSON().text);
    return route.fulfill({ contentType: 'audio/wav', body: 'RIFF' });
  });
  await page.goto('/');
  await expect(page.getByRole('textbox', { name: 'Nhắn cho Peto', exact: true })).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button', { name: 'Companion', exact: true }).click();
  const composer = page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  const panel = page.getByRole('region', { name: 'Trò chuyện trong Companion' });
  await expect(page.getByRole('button', { name: 'Tắt tiếng', exact: true })).toBeVisible();
  const emit = (index: number, value: object) => page.evaluate(({ index, value }) => {
    (window as unknown as { testTurns: { emit(value: object): void }[] }).testTurns[index].emit(value);
  }, { index, value });
  await composer.fill('Hello Peto'); await panel.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { testTurns: unknown[] }).testTurns.length)).toBe(1);
  await emit(0, { type: 'meta', conversation_id: 'A', effort: 'low', voice_stream: true });
  await emit(0, { type: 'emotion', emotion: 'surprised', offset: 0 });
  await emit(0, { type: 'delta', text: 'Hi there. ' });
  await expect(panel.getByText('Đang nói…', { exact: true })).toBeVisible();
  expect(spoken).toEqual(['Hi there.']);
  await expect(panel.getByRole('button', { name: 'Dừng', exact: true })).toBeVisible();
  await composer.fill('My next message');
  await emit(0, { type: 'emotion', emotion: 'happy', offset: 9 });
  await emit(0, { type: 'delta', text: 'How are you?' }); await emit(0, { type: 'done' });
  await expect(panel.getByRole('button', { name: 'Gửi', exact: true })).toBeVisible();
  await expect(composer).toHaveValue('My next message');
  await expect.poll(() => spoken).toEqual(['Hi there.', 'How are you?']);
  await noPageOverflow(page);
  await panel.getByRole('button', { name: 'Dừng', exact: true }).click();
  await panel.getByRole('button', { name: 'Gửi', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { testTurns: unknown[] }).testTurns.length)).toBe(2);
  await emit(1, { type: 'meta', conversation_id: 'A', effort: 'low', voice_stream: true });
  await emit(1, { type: 'delta', text: 'A fresh reply. ' });
  await expect(panel.getByText('Đang nói…', { exact: true })).toBeVisible();
  await composer.fill('Draft after stopping');
  await panel.getByRole('button', { name: 'Dừng', exact: true }).click();
  await expect(panel.getByRole('button', { name: 'Gửi', exact: true })).toBeEnabled();
  await expect.poll(() => page.evaluate(() => (window as unknown as { testTurns: { aborted: boolean }[] }).testTurns[1].aborted)).toBe(true);
  await emit(1, { type: 'delta', text: 'Late old words. ' });
  await emit(1, { type: 'emotion', emotion: 'angry', offset: 0 });
  await expect(panel.getByText(/Late old words/)).toHaveCount(0);
  await expect(composer).toHaveValue('Draft after stopping');
  expect(spoken).toEqual(['Hi there.', 'How are you?', 'A fresh reply.']);
  await noPageOverflow(page);
  // Bảng đo nằm trong Cài đặt, không thêm chữ hoặc bảng vào sân khấu.
  if (!await page.locator('.sidebar').isVisible()) await page.getByRole('button', { name: 'Mở menu', exact: true }).click();
  await page.getByRole('button', { name: 'Tài khoản · Người kiểm thử' }).click();
  await page.getByRole('menuitem', { name: 'Cài đặt', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'Cài đặt', exact: true });
  await settings.getByRole('button', { name: 'Giọng nói', exact: true }).click();
  await settings.getByText('Kiểm tra tốc độ Companion', { exact: true }).click();
  await expect(settings.getByRole('combobox', { name: 'Lượt đo' })).toHaveValue(/\d+/);
  await expect(settings.getByRole('combobox', { name: 'Lượt đo' }).locator('option').first()).toHaveText('Gần nhất · Đã dừng');
  await expect(settings.locator('.companion-timing dt', { hasText: 'Tạo tiếng → bắt đầu phát' }).locator('..').locator('dd')).toHaveText(/\d+\.\d{2} giây/);
  const bounds = await settings.locator('.companion-timing').boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  await settings.getByRole('button', { name: 'Xóa kết quả đo' }).click();
  await expect(settings.getByText(/Chưa có lượt đo/)).toBeVisible();
});
