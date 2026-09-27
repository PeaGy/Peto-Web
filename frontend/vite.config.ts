import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        // React đứng riêng một tệp: mỗi lần deploy chỉ tệp mã của Peto đổi tên, người quay lại giữ được React trong cache
        // (tệp trong assets/ được cache một năm, xem backend/static_files.py). Chỉ gom đúng ba gói này, vì gom rộng hơn
        // (cả node_modules) sẽ kéo KaTeX, highlight.js, three… vốn tải riêng vào tệp phải tải ngay từ đầu.
        codeSplitting: {
          groups: [{ name: "react", test: /[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/ }],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Dev server goi thang backend FastAPI, khong can CORS.
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
