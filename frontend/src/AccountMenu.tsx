import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import type { SettingsSection } from "./SettingsDialog";
import { SettingsIcon } from "./settingsUi";

export interface AccountMenuPlace {
  left: number;
  bottom: number;
  width: number;
  /** Đang mờ đi trước khi gỡ. */
  closing: boolean;
}

/** Menu nằm ngay trên ô tài khoản và rộng bằng ô; thanh bên thu gọn chỉ còn avatar thì menu giãn sang phải như ChatGPT. */
export function placeAccountMenu(anchor: HTMLElement): AccountMenuPlace {
  const rect = anchor.getBoundingClientRect();
  return { left: rect.left, bottom: window.innerHeight - rect.top + 6, width: rect.width < 120 ? 248 : rect.width, closing: false };
}

/**
 * Menu tài khoản như ChatGPT (chủ web chọn ngày 2026-09-29): tên tài khoản, Hồ sơ, Cài đặt, Hướng dẫn, Đăng xuất. Mở
 * thì tiêu điểm vào mục đầu; mũi tên, Home, End đi giữa các mục; Esc đóng và trả tiêu điểm về ô tài khoản; bấm ra ngoài
 * hay đổi cỡ cửa sổ thì đóng.
 */
export default function AccountMenu({ place, avatar, name, subtitle, signOutDisabled, onClose, onExited, onOpenSettings, onSignOut }: {
  place: AccountMenuPlace;
  avatar: ReactNode;
  name: string;
  subtitle: string;
  signOutDisabled: boolean;
  onClose: (focusBack: boolean) => void;
  onExited: () => void;
  /** `page`: trên điện thoại vào thẳng trang của mục, không dừng ở danh sách mục. */
  onOpenSettings: (section: SettingsSection, page: boolean) => void;
  onSignOut: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (place.closing) {
      // Phòng khi trình duyệt không chạy hiệu ứng đóng (cửa sổ bị ẩn): menu vẫn phải gỡ.
      const timer = window.setTimeout(onExited, 200);
      return () => window.clearTimeout(timer);
    }
    ref.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus({ preventScroll: true });
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      // Bấm lại ô tài khoản thì chính ô đó đóng menu.
      if (ref.current?.contains(target) || (target instanceof Element && target.closest(".account"))) return;
      onClose(false);
    };
    const resize = () => onClose(false);
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", resize);
    return () => {
      document.removeEventListener("pointerdown", outside);
      window.removeEventListener("resize", resize);
    };
  }, [place.closing, onClose, onExited]);

  function keys(event: KeyboardEvent<HTMLDivElement>) {
    const items = [...ref.current!.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)')];
    const index = items.indexOf(document.activeElement as HTMLElement);
    const move = (next: number) => {
      event.preventDefault();
      items[(next + items.length) % items.length]?.focus();
    };
    if (event.key === "ArrowDown") move(index + 1);
    else if (event.key === "ArrowUp") move(index < 0 ? items.length - 1 : index - 1);
    else if (event.key === "Home") move(0);
    else if (event.key === "End") move(items.length - 1);
    else if (event.key === "Escape") {
      event.preventDefault();
      onClose(true);
    } else if (event.key === "Tab") onClose(false);
  }

  return (
    <div
      ref={ref}
      className={place.closing ? "account-menu closing" : "account-menu"}
      role="menu"
      aria-label="Tài khoản"
      style={{ left: place.left, bottom: place.bottom, width: place.width }}
      onKeyDown={keys}
      onAnimationEnd={(event) => {
        if (place.closing && event.target === event.currentTarget) onExited();
      }}
    >
      <button type="button" role="menuitem" tabIndex={-1} className="account-menu-head" onClick={() => onOpenSettings("tai-khoan", true)}>
        {avatar}
        <span className="account-name"><strong>{name}</strong>{" "}<span>{subtitle}</span></span>
        <span className="account-menu-trail"><SettingsIcon name="chevronRight" size={16} /></span>
      </button>
      <div className="account-menu-sep" role="separator" />
      <button type="button" role="menuitem" tabIndex={-1} onClick={() => onOpenSettings("ho-so", true)}>
        <SettingsIcon name="user" />Hồ sơ
      </button>
      <button type="button" role="menuitem" tabIndex={-1} onClick={() => onOpenSettings("giao-dien", false)}>
        <SettingsIcon name="gear" />Cài đặt
      </button>
      <div className="account-menu-sep" role="separator" />
      <a role="menuitem" tabIndex={-1} href="/docs/" target="_blank" rel="noreferrer" onClick={() => onClose(false)}>
        <SettingsIcon name="help" />Hướng dẫn
        <span className="account-menu-trail"><SettingsIcon name="external" size={14} /></span>
      </a>
      <button type="button" role="menuitem" tabIndex={-1} disabled={signOutDisabled} onClick={onSignOut}>
        <SettingsIcon name="logout" />Đăng xuất
      </button>
    </div>
  );
}
