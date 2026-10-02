import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

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
  await expect(page.locator('.character-canvas')).toBeVisible();
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
