import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

// Cài đặt → Mức dùng (mẫu A giống Grok, 23/11/2026): mở thẳng bằng ?settings=muc-dung, số liệu giả từ /api/usage.
test('mục Mức dùng hiện thanh chia màu, giờ đặt lại và dòng đang đo trên máy tính lẫn điện thoại', async ({ page }, info) => {
  await mockPeto(page);
  await page.route('**/api/usage', route => route.fulfill({ json: {
    measuring: true, unlimited: false, started_at: 1795000000, resets_at: 1795604800, used_percent: 47.2,
    groups: [{ key: 'chat', label: 'Trò chuyện', percent: 24 }, { key: 'agent', label: 'Peto Agent', percent: 15.1 },
      { key: 'companion', label: 'Companion', percent: 6 }, { key: 'imagine', label: 'Tạo ảnh', percent: 2.1 }],
    unpriced_calls: 0,
  } }));
  await page.goto('/?settings=muc-dung');
  const card = page.locator('.usage-card');
  await expect(card).toContainText('47% đã dùng');
  await expect(card).toContainText('Đặt lại');
  await expect(card).toContainText('Đang đo thử, chưa giới hạn.');
  await expect(card.locator('.usage-fill')).toHaveCount(4);
  // Phần tô màu đúng 47% bề ngang thanh (ngày 23/11 lớp .chat/.imagine của app làm thanh tô kín, nên lớp màu có tiền tố).
  const share = await card.locator('.usage-bar').evaluate(bar => [...bar.children].reduce((sum, item) =>
    sum + item.getBoundingClientRect().width, 0) / bar.getBoundingClientRect().width);
  expect(share).toBeGreaterThan(0.44);
  expect(share).toBeLessThan(0.5);
  await noPageOverflow(page);
  await page.screenshot({ path: info.outputPath('usage.png') });
});
