import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { LoadingIndicator } from './shared/ui/LoadingIndicator';
import { takeEmailToken } from './app/emailLink';
const path = location.pathname;
// Token của nút đăng nhập trong thư (/#email_token=…) rời thanh địa chỉ trước khi router hay trang nào đọc tới nó.
if (path === '/') takeEmailToken();
// Peto Docs và trang tải Peto Agent là trang công khai riêng, không cần đăng nhập và không tải ứng dụng chính.
const Root = path === '/docs' || path.startsWith('/docs/') ? lazy(() => import('./features/docs/Docs'))
  : path === '/download' || path === '/download/' ? lazy(() => import('./features/download/Download'))
  : lazy(() => import('./app/App'));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Suspense fallback={<LoadingIndicator variant="screen" label="Loading" />}><Root /></Suspense>
  </StrictMode>,
);
