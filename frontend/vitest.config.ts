import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Hạn giờ rộng hơn mặc định (5 giây): khi cả bộ test chạy song song, vài test vẽ nhiều tin nhắn hay mở phần tải riêng
  // (React.lazy) lần đầu có lúc vượt 5 giây dù không sai gì (gặp ngày 2026-09-27).
  test: { environment: 'jsdom', setupFiles: ['./tests/setup.ts'], testTimeout: 15000 },
});
