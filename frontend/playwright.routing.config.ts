import { defineConfig } from '@playwright/test';
import config from './playwright.config';

const python = process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python';

/** Dùng fallback FastAPI thật, chỉ thay dữ liệu AI/tài khoản bằng các fixture trình duyệt. */
export default defineConfig({
  ...config,
  testMatch: 'routing.spec.ts',
  webServer: {
    command: `"${python}" browser-tests/serve_build.py`,
    url: 'http://127.0.0.1:5179', reuseExistingServer: false,
  },
});
