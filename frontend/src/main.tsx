import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
const Root = location.pathname === '/docs' || location.pathname.startsWith('/docs/')
  ? lazy(() => import('./features/docs/Docs')) : lazy(() => import('./app/App'));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Suspense fallback={<div role="status" aria-label="Đang tải" style={{position:'fixed',inset:0,display:'grid',placeItems:'center',background:'#141414'}}><style>{'@keyframes boot-spin{to{transform:rotate(360deg)}}'}</style><span style={{width:24,height:24,border:'3px solid #ffffff25',borderTopColor:'#bbb',borderRadius:'50%',animation:'boot-spin 1s linear infinite'}}/></div>}><Root /></Suspense>
  </StrictMode>,
);
