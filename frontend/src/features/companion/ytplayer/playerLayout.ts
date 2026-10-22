import { useEffect, useState } from 'react';

export const PLAYER_MOBILE_LAYOUT = '(max-width: 720px), (max-height: 520px) and (pointer: coarse)';

export function usePlayerLayout(layout = PLAYER_MOBILE_LAYOUT) {
  const [mobile, setMobile] = useState(() => window.matchMedia?.(layout).matches ?? false);
  useEffect(() => {
    const query = window.matchMedia?.(layout);
    if (!query) return;
    const update = () => setMobile(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, [layout]);
  return mobile;
}
