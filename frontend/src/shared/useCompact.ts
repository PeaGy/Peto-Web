import { useSyncExternalStore } from 'react';

export const COMPACT_QUERY = '(max-width: 720px)';

function subscribe(listener: () => void) {
  const query = window.matchMedia?.(COMPACT_QUERY);
  query?.addEventListener?.('change', listener);
  return () => query?.removeEventListener?.('change', listener);
}

export function useCompact() {
  return useSyncExternalStore(subscribe, () => window.matchMedia?.(COMPACT_QUERY)?.matches === true, () => false);
}
