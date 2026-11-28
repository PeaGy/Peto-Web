import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './browser-tests',
  // Mở trước các phần nặng một lần để Vite biên dịch xong trước khi test chạy song song (xem global-setup.ts).
  globalSetup: './browser-tests/global-setup.ts',
  fullyParallel: true,
  // Máy CI không có GPU riêng: tránh hai sân khấu Live2D tranh tài nguyên cùng lúc.
  workers: process.env.CI ? 1 : 2,
  // Lỗi tài nguyên trình duyệt tạm thời trên CI được thử lại một lần với worker/browser mới.
  // Playwright vẫn báo flaky khi lần đầu lỗi; lỗi lặp lại tiếp tục làm workflow thất bại.
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }], ['json', { outputFile: 'playwright-report/results.json' }]],
  // 28/11/2026: 30 s / 8 s cũ làm lần chạy đầy đủ nào cũng có vài test hỏng ở lần chờ đầu tiên sau khi mở trang. Chế độ
  // dev tải từng tệp mã riêng, và hai worker trên máy bận thỉnh thoảng cần hơn 8 giây; chạy lại riêng thì qua. Nâng lên
  // để lỗi đỏ là lỗi thật (xem docs/notes/frontend.md, "Flaky browser tests cleaned up").
  timeout: 45000,
  expect: { timeout: 15000, toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.005 } },
  use: {
    baseURL: 'http://127.0.0.1:5179', colorScheme: 'dark', reducedMotion: 'reduce', locale: 'vi-VN', timezoneId: 'Asia/Ho_Chi_Minh', trace: 'retain-on-failure',
    // Chỉ renderer của trình duyệt kiểm thử dùng phần mềm; mã nhân vật vẫn chạy thật.
    launchOptions: process.env.CI ? { args: ['--use-gl=angle', '--use-angle=swiftshader-webgl', '--enable-unsafe-swiftshader'] } : {},
  },
  projects: [
    { name: 'pc', use: { browserName: 'chromium', viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { browserName: 'chromium', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 1 } },
  ],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5179 --strictPort',
    url: 'http://127.0.0.1:5179', reuseExistingServer: false,
  },
});
