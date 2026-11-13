import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { CLOSED_SETTINGS, type SettingsSection, type SettingsView } from '../features/settings/SettingsDialog';
import { forgetSettingsLink } from '../features/settings/settingsLink';
import { placeAccountMenu, type AccountMenuPlace } from './AccountMenu';

/** Hộp Cài đặt chung và menu của ô tài khoản (mở Cài đặt từ menu thì đóng xong trả tiêu điểm về ô tài khoản).
 * Tách khỏi App.tsx (G3.3, 13/11/2026); thân các hàm giữ nguyên. */
export function useSettingsMenu(authenticated: boolean | undefined, connectorResult: string | null,
  settingsLink: SettingsSection | null, setSettingsLink: Dispatch<SetStateAction<SettingsSection | null>>,
  setSidebarOpen: Dispatch<SetStateAction<boolean>>) {
  // Hộp Cài đặt: mở hay đóng, mục đang xem, và trên điện thoại đang ở danh sách mục hay trang của mục.
  const [settings, setSettings] = useState<SettingsView>(CLOSED_SETTINGS);
  const settingsOpen = settings.open;
  useEffect(() => {
    if (authenticated && connectorResult) setSettings({ open: true, section: 'ket-noi', page: true });
  }, [authenticated, connectorResult]);
  useEffect(() => {
    if (!authenticated || !settingsLink) return;
    forgetSettingsLink();
    setSettingsLink(null);
    setSettings({ open: true, section: settingsLink, page: true });
  }, [authenticated, settingsLink]);
  const closeSettings = useCallback(() => setSettings((current) => ({ ...current, open: false })), []);
  // Menu của ô tài khoản (như ChatGPT). Nó nằm ngoài thanh bên, vì thanh bên cắt phần tràn khi thu gọn còn 64px.
  const [accountMenu, setAccountMenu] = useState<AccountMenuPlace | null>(null);
  const accountRef = useRef<HTMLButtonElement>(null);
  // Mở Cài đặt từ menu thì đóng xong trả tiêu điểm về ô tài khoản: mục trong menu đã gỡ nên hộp thoại không tự trả được.
  const settingsReturn = useRef<HTMLElement | null>(null);
  const closeAccountMenu = useCallback((focusBack: boolean) => {
    setAccountMenu((current) => current && { ...current, closing: true });
    if (focusBack) accountRef.current?.focus();
  }, []);
  const dropAccountMenu = useCallback(() => setAccountMenu(null), []);
  useEffect(() => {
    if (settingsOpen || !settingsReturn.current) return;
    settingsReturn.current.focus({ preventScroll: true });
    settingsReturn.current = null;
  }, [settingsOpen]);

  function toggleAccountMenu() {
    if (accountMenu && !accountMenu.closing) closeAccountMenu(false);
    else if (accountRef.current) setAccountMenu(placeAccountMenu(accountRef.current));
  }

  function openFromAccountMenu(section: SettingsSection, page: boolean) {
    settingsReturn.current = accountRef.current;
    closeAccountMenu(false);
    setSidebarOpen(false);
    setSettings({ open: true, section, page });
  }
  return { settings, setSettings, settingsOpen, closeSettings, accountMenu, setAccountMenu, accountRef, closeAccountMenu, dropAccountMenu,
    toggleAccountMenu, openFromAccountMenu };
}
