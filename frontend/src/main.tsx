import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { LoadingIndicator } from './shared/ui/LoadingIndicator';
const Root = location.pathname === '/docs' || location.pathname.startsWith('/docs/')
  ? lazy(() => import('./features/docs/Docs')) : lazy(() => import('./app/App'));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Suspense fallback={<LoadingIndicator variant="screen" label="Loading" />}><Root /></Suspense>
  </StrictMode>,
);
