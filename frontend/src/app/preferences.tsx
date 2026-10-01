import type { Effort } from '../shared/api/api';
import { SettingsIcon, type SegmentOption } from '../features/settings/settingsUi';

export const EFFORT_KEY = "peto-effort";
export const MODEL_KEY = "peto-model";
export const THEME_KEY = "peto-theme";
export const SIDEBAR_KEY = "peto-sidebar-collapsed";
export const EFFORTS: { value: Effort; label: string; hint: string }[] = [
  { value: "auto", label: "Tự động", hint: "Peto tự chọn mức phù hợp" },
  { value: "none", label: "Không suy luận", hint: "Ưu tiên phản hồi nhanh" },
  { value: "low", label: "Thấp", hint: "Trả lời nhanh, chat thường" },
  { value: "medium", label: "Trung bình", hint: "Cân bằng tốc độ và độ sâu" },
  { value: "high", label: "Cao", hint: "Suy nghĩ kỹ cho bài khó" },
  { value: "xhigh", label: "Rất cao", hint: "Đào sâu hơn, có thể chờ lâu hơn" },
  { value: "max", label: "Tối đa", hint: "Mức suy luận cao nhất, dùng nhiều token hơn" },
];

export type ThemeChoice = "light" | "dark" | "system";
export type AppView = "chat" | "imagine" | "companion";

export const THEMES: SegmentOption<ThemeChoice>[] = [
  { value: "system", label: "Theo máy", hint: "Theo máy: đổi theo cài đặt của thiết bị", icon: <SettingsIcon name="monitor" size={17} /> },
  { value: "light", label: "Sáng", hint: "Sáng: nền trắng, hợp ban ngày", icon: <SettingsIcon name="sun" size={17} /> },
  { value: "dark", label: "Tối", hint: "Tối: nền tối, dịu mắt buổi đêm", icon: <SettingsIcon name="moon" size={17} /> },
];

/** Model đã chọn lần trước; tài khoản không còn được dùng model đó thì lúc gửi tự về Peto. */
export function readStoredModel(): string {
  try {
    return localStorage.getItem(MODEL_KEY) || "peto";
  } catch {
    return "peto";
  }
}

export function readStoredEffort(): Effort {
  try {
    const value = localStorage.getItem(EFFORT_KEY);
    return EFFORTS.some((item) => item.value === value) ? (value as Effort) : "auto";
  } catch {
    return "auto";
  }
}

export function readStoredTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return THEMES.some((item) => item.value === value) ? (value as ThemeChoice) : "system";
  } catch {
    return "system";
  }
}

export function readStoredCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  } catch {
    return false;
  }
}

/** Trình duyệt cũ hoặc môi trường test có thể không có matchMedia. */
export function lightMediaQuery(): MediaQueryList | null {
  try {
    return typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: light)")
      : null;
  } catch {
    return null;
  }
}

