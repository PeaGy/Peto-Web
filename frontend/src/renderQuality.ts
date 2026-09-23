import { useEffect, useState } from 'react';
export interface RenderQuality { sharp: boolean; smooth: boolean }
const key = 'peto-mobile-render-quality';
const event = 'peto-render-quality';
export function readRenderQuality(): RenderQuality {
  try { const value = JSON.parse(localStorage.getItem(key) || '{}'); return { sharp: value.sharp === true, smooth: value.smooth === true }; }
  catch { return { sharp: false, smooth: false }; }
}
export function writeRenderQuality(value: RenderQuality) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Keep the setting for this session. */ }
  window.dispatchEvent(new CustomEvent(event, { detail: value }));
}
export function useRenderQuality() {
  const [quality, setQuality] = useState(readRenderQuality);
  useEffect(() => {
    const changed = (e: Event) => setQuality((e as CustomEvent<RenderQuality>).detail);
    const stored = (e: StorageEvent) => { if (e.key === key || e.key === null) setQuality(readRenderQuality()); };
    window.addEventListener(event, changed); window.addEventListener('storage', stored);
    return () => { window.removeEventListener(event, changed); window.removeEventListener('storage', stored); };
  }, []);
  return quality;
}
