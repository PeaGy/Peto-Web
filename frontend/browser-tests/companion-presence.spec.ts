import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

// Model thật tải lõi, moc3 và texture lớn; máy CI chạy song song có thể cần hơn 8 giây.
// Chỉ bước đợi sân khấu được chờ lâu hơn, các kiểm tra tương tác vẫn dùng thời gian mặc định.
test.describe.configure({ timeout: 60000 });
const expectStage = expect.configure({ timeout: 30000 });

test('loading chờ model thật và lịch sử, rồi hiện nhân vật cùng chat khi F5', async ({ page }) => {
  await mockPeto(page);
  await page.route('**/characters/Live2DStage.tsx*', route => route.continue());
  let releaseModel!: () => void, releaseHistory!: () => void;
  let requestedModel!: () => void;
  const modelRequested = new Promise<void>(resolve => { requestedModel = resolve; });
  const modelWaiting = new Promise<void>(resolve => { releaseModel = resolve; });
  const historyWaiting = new Promise<void>(resolve => { releaseHistory = resolve; });
  await page.route('**/characters/hiyori/Hiyori.model3.json', async route => {
    requestedModel(); await modelWaiting; await route.continue();
  });
  await page.route('**/api/companion', async route => {
    await historyWaiting;
    await route.fulfill({ json: { conversation_id: 'A', messages: [] } });
  });
  await page.goto('/#companion');
  try {
    await modelRequested;
    await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' })).toHaveCount(0);
    releaseModel();
    await expectStage(page.locator('.character-canvas')).toHaveCSS('visibility', 'visible');
    await expect(page.locator('.character-fallback')).toHaveCount(0);
    await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible();
    releaseHistory();
    await expectStage(page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' })).toBeVisible();
    await expect(page.locator('.companion-stage')).toHaveCSS('opacity', '1');
    await expect(page.locator('.companion-panel')).toHaveCSS('opacity', '1');
    await expect(page.getByRole('status', { name: 'Loading', exact: true })).toHaveCount(0);
    const size = await page.locator('.character-canvas canvas').evaluate((canvas: HTMLCanvasElement) => ({ width: canvas.width, height: canvas.height }));
    expect(size.width).toBeGreaterThan(100); expect(size.height).toBeGreaterThan(100);
    await noPageOverflow(page);
    await page.reload();
    await expectStage(page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' })).toBeVisible();
    await expect(page.locator('.character-fallback')).toHaveCount(0);
    await expect(page.locator('.character-canvas')).toBeVisible();
  } finally { releaseModel(); releaseHistory(); }
});

test('nhân vật thật hiện bong bóng khi đợi trả lời và ẩn khi viết xong', async ({ page }) => {
  await mockPeto(page);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  // Giữ renderer Live2D thật và tài nguyên đi kèm; chỉ giả phản hồi máy chủ để điều khiển thời gian chờ.
  await page.route('**/characters/Live2DStage.tsx*', route => route.continue());
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/chat', async route => {
    await waiting;
    const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
    await route.fulfill({ contentType: 'text/event-stream', body:
      event({ type: 'meta', conversation_id: 'A', effort: 'low', message: { id: 101, role: 'user', content: 'Hello again!' } })
      + event({ type: 'delta', text: 'Hello!' }) + event({ type: 'done' }) });
  });
  await page.goto('/#companion');
  await expectStage(page.locator('.character-canvas')).toBeVisible();
  await expect(page.locator('.character-fallback')).toHaveCount(0);
  const input = page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  await input.fill('Hello again!');
  await page.getByRole('button', { name: 'Gửi', exact: true }).click();
  const bubble = page.getByRole('status', { name: 'Peto đang nghĩ và trả lời' });
  try {
    await expect(bubble).toBeVisible();
    await expect(bubble).toBeInViewport();
    await expect(bubble).toHaveAttribute('data-animated', 'true');
    expect(await bubble.locator('i').first().evaluate(node => getComputedStyle(node).animationName)).toBe('character-thinking-dot');
    // Vị trí thay đổi theo đầu model thật kể cả khi không kéo/phóng sân khấu.
    const travel = await bubble.evaluate(async node => {
      const positions: number[][] = [];
      const until = performance.now() + 1200;
      while (performance.now() < until) {
        await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
        const matrix = new DOMMatrixReadOnly(getComputedStyle(node).transform);
        positions.push([matrix.m41, matrix.m42]);
      }
      return Math.max(...positions.map(point => point[0])) - Math.min(...positions.map(point => point[0]))
        + Math.max(...positions.map(point => point[1])) - Math.min(...positions.map(point => point[1]));
    });
    expect(travel).toBeGreaterThan(0.1);
    await page.screenshot({ path: test.info().outputPath('thinking.png') });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(bubble).toHaveAttribute('data-animated', 'false');
    expect(await bubble.locator('i').first().evaluate(node => getComputedStyle(node).animationName)).toBe('none');
    await noPageOverflow(page);
  } finally { release(); }
  await expect(bubble).toBeHidden();
});

test('công tắc nhìn ô chat mặc định bật và nhớ lựa chọn qua F5', async ({ page }) => {
  await mockPeto(page, { preservePreferences: true });
  await page.goto('/#companion');
  const input = page.getByRole('textbox', { name: 'Nhắn cho Peto trong Companion' });
  await expect(input).toBeVisible();
  await page.getByRole('button', { name: 'Đổi nhân vật Peto' }).click();
  const dialog = page.getByRole('dialog', { name: 'Nhân vật' });
  await dialog.locator('summary').filter({ hasText: 'Cài đặt nhân vật' }).click();
  const toggle = dialog.getByRole('switch', { name: 'Nhìn vào ô chat khi bạn gõ' });
  await expect(toggle).toBeChecked();
  await toggle.uncheck();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(input).toBeVisible();
  await page.getByRole('button', { name: 'Đổi nhân vật Peto' }).click();
  await dialog.locator('summary').filter({ hasText: 'Cài đặt nhân vật' }).click();
  await expect(toggle).not.toBeChecked();
});
