import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './browser-tests',
  fullyParallel: true,
  // Máy CI không có GPU riêng: tránh hai sân khấu Live2D tranh tài nguyên cùng lúc.
  workers: process.env.CI ? 1 : 2,
  reporter: [['list'], ['html', { open: 'never' }]],
  timeout: 30000,
  expect: { timeout: 8000, toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.005 } },
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
