import { SETTINGS_SECTIONS, type SettingsSection } from "./SettingsDialog";

const LINK_KEY = "peto-settings-link";

function section(value: string | null): SettingsSection | null {
  return SETTINGS_SECTIONS.find((item) => item.id === value)?.id ?? null;
}

/**
 * Mục Cài đặt mà liên kết `?settings=<mục>` muốn mở, rồi xóa tham số khỏi thanh địa chỉ. Peto Agent bản desktop mở
 * `?settings=agent` từ nút "Manage on Peto Web" để người dùng tới thẳng danh sách thiết bị và số bước.
 *
 * Mục được giữ trong sessionStorage vì đăng nhập Discord/Google/GitHub chuyển hướng đi rồi quay về, làm mất tham số.
 */
export function takeSettingsLink(): SettingsSection | null {
  try {
    const url = new URL(window.location.href);
    const fromUrl = url.searchParams.get("settings");
    if (fromUrl !== null) {
      url.searchParams.delete("settings");
      window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
      const wanted = section(fromUrl);
      if (wanted) sessionStorage.setItem(LINK_KEY, wanted);
    }
    return section(sessionStorage.getItem(LINK_KEY));
  } catch {
    return null;
  }
}

export function forgetSettingsLink(): void {
  try {
    sessionStorage.removeItem(LINK_KEY);
  } catch {
    // Không xóa được thì lần tải trang sau trong cùng tab lại mở mục đó một lần nữa.
  }
}
