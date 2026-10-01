import { useEffect } from 'react';
import type { Effort } from '../shared/api/api';
import { EFFORT_KEY, MODEL_KEY, SIDEBAR_KEY, THEME_KEY, lightMediaQuery, type ThemeChoice } from './preferences';

export function usePreferencesPersistence({ effort, model, collapsed, theme }: {
  effort: Effort; model: string; collapsed: boolean; theme: ThemeChoice;
}) {
  useEffect(() => {
    try {
      localStorage.setItem(EFFORT_KEY, effort);
    } catch {}
  }, [effort]);

  useEffect(() => {
    try {
      localStorage.setItem(MODEL_KEY, model);
    } catch {}
  }, [model]);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
    } catch {}
  }, [collapsed]);

  // Giao diện sáng/tối: "Theo máy" bám theo cài đặt hệ thống và đổi ngay khi
  // hệ thống đổi, hai lựa chọn còn lại thì giữ nguyên.
  useEffect(() => {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {}
    const media = lightMediaQuery();
    const apply = () => {
      document.documentElement.dataset.theme =
        theme === "system" ? (media?.matches ? "light" : "dark") : theme;
    };
    apply();
    if (theme !== "system" || !media?.addEventListener) return;
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);


}
