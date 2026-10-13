import { useEffect } from 'react';
import { SIDEBAR_KEY, THEME_KEY, lightMediaQuery, type ThemeChoice } from './preferences';
import { MOTION_KEY, applyMotion, systemMotionQuery, type MotionChoice } from '../shared/motion';

export function usePreferencesPersistence({ collapsed, theme, motion }: {
  collapsed: boolean; theme: ThemeChoice; motion: MotionChoice;
}) {
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

  // Chuyển động: "Theo máy" bám cài đặt giảm chuyển động của thiết bị và đổi ngay khi thiết bị đổi; "Mượt" (mặc định)
  // và "Giảm" thì giữ nguyên. index.html đã gắn data-motion trước khi React chạy, nên trang không nháy hiệu ứng.
  useEffect(() => {
    try {
      localStorage.setItem(MOTION_KEY, motion);
    } catch {}
    applyMotion(motion);
    const media = systemMotionQuery();
    if (motion !== "system" || !media?.addEventListener) return;
    const apply = () => applyMotion(motion);
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [motion]);


}
