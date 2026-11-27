import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow, openSidebar } from './fixtures';

// Chỉ báo đang làm (27/11/2026): hình động thay mũi tên ở dòng "Đang làm" khi lượt còn chạy, chọn ở Cài đặt → Giao diện
// (Machine Love - 1 mặc định, Machine Love - 2, Tetris) cùng cỡ. Luồng /api/chat giả chạy trong trang: nghĩ, rồi tìm web,
// rồi đứng chờ tới khi test cho xong, để kiểm được lúc đang chạy.

async function setup(page: Page, choices?: Record<string, string>) {
  await mockPeto(page, { preservePreferences: true });
  await page.addInitScript((saved?: Record<string, string>) => {
    if (saved && !sessionStorage.getItem('indicator-seeded')) {
      for (const [key, value] of Object.entries(saved)) localStorage.setItem(key, value);
      sessionStorage.setItem('indicator-seeded', '1');
    }
    const original = window.fetch;
    const state = { phase: 'idle', finish: false };
    Object.assign(window, { turn: state });
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (!url.endsWith('/api/chat') || init?.method !== 'POST') return original(input, init);
      const body = JSON.parse(String(init.body));
      const encoder = new TextEncoder();
      const event = (value: object) => encoder.encode(`data: ${JSON.stringify(value)}\n\n`);
      const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
      const stream = new ReadableStream({
        async start(controller) {
          controller.enqueue(event({ type: 'meta', conversation_id: 'W', effort: 'low', message: { id: 201, role: 'user', content: body.message } }));
          controller.enqueue(event({ type: 'step', step: { id: 't1', kind: 'think', label: 'Đang suy nghĩ…', state: 'live', start: 0 } }));
          state.phase = 'think';
          await wait(1200);
          controller.enqueue(event({ type: 'step', step: { id: 't1', kind: 'think', label: 'Đã suy nghĩ', state: 'done', start: 0, end: 1200 } }));
          controller.enqueue(event({ type: 'step', step: { id: 's1', kind: 'search', label: 'Đang tìm trên web…', state: 'live', start: 1200 } }));
          state.phase = 'search';
          while (!state.finish) await wait(50);
          controller.enqueue(event({ type: 'step', step: { id: 's1', kind: 'search', label: 'Đã tìm trên web', state: 'done', start: 1200, end: 2400 } }));
          controller.enqueue(event({ type: 'delta', text: 'Xong rồi nè.' }));
          controller.enqueue(event({ type: 'done', message_id: 202 }));
          state.phase = 'done';
          controller.close();
        },
      });
      return new Response(stream, { headers: { 'content-type': 'text/event-stream' } });
    };
  }, choices);
  await page.goto('/');
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
}

const phase = (page: Page) => page.evaluate(() => (window as unknown as { turn: { phase: string } }).turn.phase);
const finish = (page: Page) => page.evaluate(() => { (window as unknown as { turn: { finish: boolean } }).turn.finish = true; });

async function send(page: Page) {
  const composer = page.getByLabel('Nhắn cho Peto', { exact: true });
  await composer.fill('Tìm giúp mình nhé');
  await composer.press('Enter');
}

test('mặc định Machine Love - 1: Peto đứng chỗ mũi tên khi lượt chạy, xong thì mũi tên quay lại', async ({ page }, info) => {
  await setup(page);
  await send(page);
  const head = page.locator('.bubble.assistant .work-head').last();
  const indicator = head.locator('.work-indicator');
  await expect(indicator).toHaveAttribute('data-indicator', 'machine-love-1');
  await expect(head.locator('.work-chevron')).toHaveCount(0);
  const box = (await indicator.boundingBox())!;
  expect(box.width).toBe(20);
  expect(box.height).toBe(20);
  // Hình có vẽ thật (không phải canvas trống).
  expect(await indicator.evaluate((canvas: HTMLCanvasElement) => {
    const data = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height).data;
    let painted = 0;
    for (let i = 3; i < data.length; i += 4) if (data[i] > 0) painted++;
    return painted;
  })).toBeGreaterThan(50);
  await expect.poll(() => phase(page)).toBe('search');
  await page.screenshot({ path: info.outputPath('machine-love-1.png') });
  await finish(page);
  await expect.poll(() => phase(page)).toBe('done');
  await expect(page.getByText('Xong rồi nè.')).toBeVisible();
  await expect(head.locator('.work-indicator')).toHaveCount(0);
  await expect(head.locator('.work-chevron')).toHaveCount(1);
  await noPageOverflow(page);
});

test('chọn Tetris cỡ Lớn trong Cài đặt: hình thử đổi ngay, Tetris đổi kiểu theo bước, giữ qua F5', async ({ page }) => {
  await setup(page);
  await openSidebar(page);
  await page.getByRole('button', { name: /^Tài khoản · / }).click();
  await page.getByRole('menuitem', { name: 'Cài đặt', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'Cài đặt', exact: true });
  const picker = settings.getByRole('combobox', { name: 'Chỉ báo đang làm' });
  if (!await picker.isVisible()) await settings.getByRole('button', { name: 'Giao diện', exact: true }).click();
  const preview = settings.getByTestId('indicator-preview').locator('canvas');
  await expect(preview).toHaveAttribute('data-indicator', 'machine-love-1');
  await picker.click();
  await settings.getByRole('option', { name: /^Tetris/ }).click();
  await expect(preview).toHaveAttribute('data-indicator', 'tetris');
  await settings.getByRole('radiogroup', { name: 'Kích thước chỉ báo' }).getByRole('radio', { name: 'Lớn', exact: true }).check();
  await expect.poll(async () => (await preview.boundingBox())?.width).toBe(24);
  expect(await page.evaluate(() => [localStorage.getItem('peto-indicator'), localStorage.getItem('peto-indicator-size')]))
    .toEqual(['tetris', '24']);
  await page.keyboard.press('Escape');
  await expect(settings).toBeHidden();

  await send(page);
  const indicator = page.locator('.bubble.assistant .work-head .work-indicator').last();
  await expect(indicator).toHaveAttribute('data-indicator', 'tetris');
  await expect(indicator).toHaveAttribute('data-mode', 'autoplay');
  expect((await indicator.boundingBox())!.width).toBe(24);
  // Tìm web: khối rơi như mưa.
  await expect(indicator).toHaveAttribute('data-mode', 'rain');
  await finish(page);
  await expect(page.getByText('Xong rồi nè.')).toBeVisible();

  await page.reload();
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('peto-indicator'))).toBe('tetris');
});

test('Machine Love - 2 theo màu chữ: giao diện sáng vẽ đen như ảnh GIF, tối vẽ sáng', async ({ page }) => {
  await setup(page, { 'peto-indicator': 'machine-love-2' });
  await send(page);
  const indicator = page.locator('.bubble.assistant .work-head .work-indicator').last();
  await expect(indicator).toHaveAttribute('data-indicator', 'machine-love-2');
  // Điểm ảnh đậm nhất trên canvas: theo --text của giao diện.
  const brightest = () => indicator.evaluate((canvas: HTMLCanvasElement) => {
    const data = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height).data;
    let best = { alpha: -1, light: 0 };
    for (let i = 0; i < data.length; i += 4) if (data[i + 3] > best.alpha) best = { alpha: data[i + 3], light: data[i] };
    return best.light;
  });
  expect(await brightest()).toBeGreaterThan(200);
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
  await expect.poll(brightest).toBeLessThan(40);
  await finish(page);
});
