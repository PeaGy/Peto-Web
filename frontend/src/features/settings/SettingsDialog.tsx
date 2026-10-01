import { Fragment, useEffect, useLayoutEffect, useRef, useState, type AnimationEvent, type ReactNode } from "react";
import { SettingsIcon, type SettingsIconName } from "./settingsUi";

export type SettingsSection = "giao-dien" | "ho-so" | "tai-khoan" | "agent" | "giong-noi" | "tri-nho" | "tra-web";

export interface SettingsView {
  open: boolean;
  section: SettingsSection;
  /** Điện thoại: đang ở trang của mục (true) hay ở danh sách mục (false). Máy tính luôn thấy cả hai. */
  page: boolean;
}

export const CLOSED_SETTINGS: SettingsView = { open: false, section: "giao-dien", page: false };

/** Thứ tự các mục; nhóm Companion có nhãn riêng như nhóm "Customize" trong Cài đặt của Claude. */
export const SETTINGS_SECTIONS: { id: SettingsSection; title: string; icon: SettingsIconName; group?: "Companion" }[] = [
  { id: "giao-dien", title: "Giao diện", icon: "palette" },
  { id: "ho-so", title: "Hồ sơ", icon: "user" },
  { id: "tai-khoan", title: "Tài khoản", icon: "idcard" },
  { id: "agent", title: "Peto Agent", icon: "terminal" },
  { id: "giong-noi", title: "Giọng nói", icon: "wave", group: "Companion" },
  { id: "tri-nho", title: "Trí nhớ", icon: "bookmark", group: "Companion" },
  { id: "tra-web", title: "Tra web", icon: "globe", group: "Companion" },
];

const GROUPS = [...new Set(SETTINGS_SECTIONS.map((item) => item.group))].map(
  (group) => [group, SETTINGS_SECTIONS.filter((item) => item.group === group)] as const,
);

/** Dưới 720px hộp là danh sách mục rồi tới trang của mục, như ngăn kéo thanh bên. */
function narrow(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(max-width: 720px)").matches;
}

/** Trang của mục chỉ trượt vào, trượt ra trên điện thoại, và chỉ khi máy không bật giảm chuyển động. */
function slides(): boolean {
  return narrow() && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Hộp Cài đặt kiểu "Từng mục" (chủ web chọn từ ba bản mẫu ngày 2026-09-29, theo Cài đặt của Claude): danh sách mục bên
 * trái, mỗi lần một mục bên phải. Dưới 720px hộp phủ kín màn hình: trước là danh sách mục, chạm một mục thì trang của nó
 * trượt vào như Cài đặt của iOS, nút quay lại đưa về danh sách.
 *
 * Mục nào đã mở thì giữ nguyên (chỉ ẩn đi) tới khi rời app, nên chữ đang gõ dở trong Hồ sơ không mất khi sang mục khác.
 * `render(mục, đang xem)`: mục chỉ tải dữ liệu khi đang được xem, như trước đây khi cả hộp mở.
 */
export default function SettingsDialog({ view, onView, onClose, render }: {
  view: SettingsView;
  onView: (view: SettingsView) => void;
  onClose: () => void;
  render: (section: SettingsSection, active: boolean) => ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const [visited, setVisited] = useState<ReadonlySet<SettingsSection>>(() => new Set());
  const [motion, setMotion] = useState<"push" | "pop" | null>(null);
  const latest = useRef({ view, onView });
  latest.current = { view, onView };
  if (view.open && !visited.has(view.section)) setVisited(new Set(visited).add(view.section));

  // useLayoutEffect: hộp đã mở trước effect của các mục bên trong, vì chúng tải dữ liệu ngay khi thấy mình đang được xem.
  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (view.open && !dialog.open) {
      dialog.showModal();
      // showModal đặt tiêu điểm vào mục đầu danh sách; mở thẳng Hồ sơ hay Trí nhớ thì tiêu điểm phải ở mục đó. Điện thoại
      // đang ở trang của mục thì danh sách nằm khuất sau trang, nên vào nút quay lại.
      const target = view.page && narrow()
        ? dialog.querySelector<HTMLElement>(".settings-back")
        : dialog.querySelector<HTMLElement>('.settings-nav-item[aria-current="page"]');
      target?.focus();
    } else if (!view.open && dialog.open) dialog.close();
  }, [view.open]);

  // Sang mục khác thì đọc từ đầu mục đó.
  useLayoutEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
  }, [view.section]);

  // Hiệu ứng trượt xong thì gỡ; phòng khi trình duyệt không báo animationend (cửa sổ bị ẩn), vẫn gỡ sau một lúc.
  useEffect(() => {
    if (!motion) return;
    const timer = window.setTimeout(() => settle(motion), 400);
    return () => window.clearTimeout(timer);
  }, [motion]);

  function settle(done: "push" | "pop") {
    setMotion(null);
    if (done === "pop") latest.current.onView({ ...latest.current.view, page: false });
  }

  function pick(section: SettingsSection) {
    if (!view.page && slides()) setMotion("push");
    onView({ ...view, section, page: true });
  }

  function back() {
    if (slides()) setMotion("pop");
    else onView({ ...view, page: false });
  }

  function ended(event: AnimationEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && motion) settle(motion);
  }

  const current = SETTINGS_SECTIONS.find((item) => item.id === view.section) ?? SETTINGS_SECTIONS[0];

  return (
    <dialog
      ref={dialogRef}
      className="settings-dialog"
      aria-labelledby="settings-title"
      data-page={view.page ? "section" : "list"}
      data-motion={motion ?? undefined}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <nav className="settings-nav" aria-labelledby="settings-title">
        <h2 id="settings-title" className="settings-nav-title">Cài đặt</h2>
        <div className="settings-nav-scroll">
          {GROUPS.map(([group, items]) => (
            <Fragment key={group ?? "chung"}>
              {group && <h3 className="settings-nav-group">{group}</h3>}
              <ul className="settings-nav-list">
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className="settings-nav-item"
                      aria-current={item.id === view.section ? "page" : undefined}
                      onClick={() => pick(item.id)}
                    >
                      <SettingsIcon name={item.icon} />
                      <span className="settings-nav-label">{item.title}</span>
                      <span className="settings-nav-chevron"><SettingsIcon name="chevronRight" size={16} /></span>
                    </button>
                  </li>
                ))}
              </ul>
            </Fragment>
          ))}
        </div>
      </nav>

      <div className="settings-main" onAnimationEnd={ended}>
        <div className="settings-page-head">
          <button type="button" className="settings-back" aria-label="Quay lại danh sách cài đặt" onClick={back}>
            <SettingsIcon name="chevronLeft" size={20} />
          </button>
          <h2 className="settings-page-title">{current.title}</h2>
        </div>
        {/* Chỉ phần dưới tiêu đề mục được cuộn. */}
        <div className="settings-page-body" ref={bodyRef}>
          {SETTINGS_SECTIONS.filter((item) => visited.has(item.id)).map((item) => (
            <section key={item.id} className="settings-page" aria-label={item.title} hidden={item.id !== view.section}>
              {render(item.id, view.open && item.id === view.section)}
            </section>
          ))}
        </div>
      </div>

      <button type="button" className="settings-close" aria-label="Đóng cài đặt" title="Đóng" onClick={onClose}>
        <SettingsIcon name="close" size={18} />
      </button>
    </dialog>
  );
}
