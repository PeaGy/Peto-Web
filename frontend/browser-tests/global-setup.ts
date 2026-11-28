import { chromium, type FullConfig } from '@playwright/test';
import { mockPeto } from './fixtures';

/**
 * Làm nóng Vite trước khi chạy test (28/11/2026). Máy chủ dev chỉ biên dịch mã khi có trang xin tới, và lần đầu còn tối
 * ưu thêm thư viện rồi tải lại trang. Hai worker chạy song song mà gặp lúc đó thì trang đầu tiên của các phần nặng
 * (ứng dụng chính, Companion với Live2D/three.js, Cài đặt Companion, Docs) mất hơn 8 giây, và test hỏng ở bước chờ đầu
 * tiên: màn "Loading" treo, tiêu đề trang Cài đặt Companion chưa hiện (routing.spec), lưu trữ… Mở trước mỗi phần một lần
 * ở đây, với API giả như test, thì test nào cũng gặp máy chủ đã biên dịch xong.
 */
const PAGES = [
  '/', '/chat/A', '/imagine', '/companion',
  '/companion/settings/modules/hearing', '/companion/settings/providers/deepseek', '/companion/settings/character',
  '/companion/settings/cards/peto/edit', '/docs/', '/download', '/s/AAAAAAAAAAAAAAAAAAAAAA',
];

export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]?.use.baseURL;
  if (!baseURL) return;
  const started = Date.now();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ baseURL, viewport: { width: 1440, height: 900 } });
    await mockPeto(page);
    for (const path of PAGES) {
      await page.goto(path, { timeout: 120_000 }).catch(() => {});
      // Chờ mạng yên (mã các phần tải sau đã về) nhưng không để một trang treo cả lượt chạy.
      await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
    }
  } finally {
    await browser.close();
  }
  console.log(`Đã làm nóng Vite trong ${Math.round((Date.now() - started) / 1000)} giây.`);
}
