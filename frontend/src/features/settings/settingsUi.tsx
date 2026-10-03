import { useId, type ReactNode } from "react";

/*
 * Mảnh ghép chung của Cài đặt, kiểu "Từng mục" chủ web chọn từ ba bản mẫu ngày 2026-09-29 (theo Cài đặt của Claude):
 * mỗi hàng có nhãn và lời giải thích bên trái, nút điều khiển bên phải, các hàng ngăn nhau bằng vạch mảnh.
 */

/** Biểu tượng nét 1.7px cùng họ với thanh bên, cho danh sách mục của Cài đặt và menu tài khoản. */
const ICONS = {
  archive: <><rect x="3.5" y="4" width="17" height="4" rx="1" /><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4" /></>,
  palette: <>
    <path d="M12 3.5a8.5 8.5 0 0 0 0 17c1 0 1.7-.7 1.7-1.6 0-.5-.2-.9-.5-1.2a1.7 1.7 0 0 1 1.2-2.9h2A4.6 4.6 0 0 0 21 10.2C21 6.5 17 3.5 12 3.5Z" />
    <circle cx="7.7" cy="11.2" r="1.05" fill="currentColor" stroke="none" />
    <circle cx="10.5" cy="7.6" r="1.05" fill="currentColor" stroke="none" />
    <circle cx="15" cy="7.9" r="1.05" fill="currentColor" stroke="none" />
  </>,
  user: <><circle cx="12" cy="8.4" r="3.7" /><path d="M4.8 20a7.2 7.2 0 0 1 14.4 0" /></>,
  character: <><circle cx="12" cy="12" r="8.5" /><path d="M8 14.5a4.5 4.5 0 0 0 8 0M8.5 9.5v1M15.5 9.5v1" /></>,
  idcard: <>
    <rect x="3.5" y="5.5" width="17" height="13" rx="3" />
    <circle cx="9" cy="10.8" r="2" />
    <path d="M5.9 15.8c.6-1.3 1.7-2 3.1-2s2.5.7 3.1 2M14.5 10h3.5M14.5 13.5h2.5" />
  </>,
  terminal: <><rect x="3.5" y="4.5" width="17" height="15" rx="3" /><path d="m7.5 9.5 3 2.5-3 2.5M12.5 15h4" /></>,
  wave: <path d="M4 10.5v3M8 7.5v9M12 4.5v15M16 8v8M20 10.5v3" />,
  bookmark: <path d="M7.5 4h9a1 1 0 0 1 1 1v15l-5.5-3.6L6.5 20V5a1 1 0 0 1 1-1Z" />,
  globe: <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M3.5 12h17M12 3.5c2.2 2.4 3.3 5.2 3.3 8.5s-1.1 6.1-3.3 8.5c-2.2-2.4-3.3-5.2-3.3-8.5s1.1-6.1 3.3-8.5Z" />
  </>,
  gear: <>
    <circle cx="12" cy="12" r="3.1" />
    <path strokeWidth="1.5" d="M19.4 14.2a1.6 1.6 0 0 0 .32 1.77l.06.06a1.9 1.9 0 1 1-2.7 2.7l-.05-.06a1.6 1.6 0 0 0-1.78-.32 1.6 1.6 0 0 0-.96 1.46v.17a1.9 1.9 0 1 1-3.8 0v-.09a1.6 1.6 0 0 0-1.05-1.46 1.6 1.6 0 0 0-1.77.32l-.06.06a1.9 1.9 0 1 1-2.7-2.7l.06-.06a1.6 1.6 0 0 0 .32-1.77 1.6 1.6 0 0 0-1.46-.96h-.17a1.9 1.9 0 0 1 0-3.8h.09a1.6 1.6 0 0 0 1.46-1.05 1.6 1.6 0 0 0-.32-1.78l-.06-.05a1.9 1.9 0 1 1 2.7-2.7l.06.06a1.6 1.6 0 0 0 1.77.32h.08a1.6 1.6 0 0 0 .96-1.46v-.17a1.9 1.9 0 1 1 3.8 0v.09a1.6 1.6 0 0 0 .96 1.46 1.6 1.6 0 0 0 1.78-.32l.05-.06a1.9 1.9 0 1 1 2.7 2.7l-.06.06a1.6 1.6 0 0 0-.32 1.77v.08a1.6 1.6 0 0 0 1.46.96h.17a1.9 1.9 0 0 1 0 3.8h-.09a1.6 1.6 0 0 0-1.46.96Z" />
  </>,
  help: <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.7" />
    <circle cx="12" cy="16.9" r=".95" fill="currentColor" stroke="none" />
  </>,
  logout: <><path d="M14 4.5H7A2.5 2.5 0 0 0 4.5 7v10A2.5 2.5 0 0 0 7 19.5h7" /><path d="M10.5 12h10M17 8.5l3.5 3.5-3.5 3.5" /></>,
  chevronRight: <path d="m9.5 6 6 6-6 6" />,
  chevronLeft: <path d="m14.5 6-6 6 6 6" />,
  close: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  external: <path d="M10 5.5H7A2.5 2.5 0 0 0 4.5 8v9A2.5 2.5 0 0 0 7 19.5h9a2.5 2.5 0 0 0 2.5-2.5v-3M14 4.5h5.5V10M19.5 4.5 11.5 12.5" />,
  monitor: <><rect x="3.5" y="4.5" width="17" height="11.5" rx="2.5" /><path d="M9 20h6M12 16v4" /></>,
  sun: <>
    <circle cx="12" cy="12" r="3.8" />
    <path d="M12 3v1.8M12 19.2V21M3 12h1.8M19.2 12H21M5.6 5.6l1.3 1.3M17.1 17.1l1.3 1.3M5.6 18.4l1.3-1.3M17.1 6.9l1.3-1.3" />
  </>,
  moon: <path d="M19.5 14.3A7.8 7.8 0 0 1 9.7 4.5a7.8 7.8 0 1 0 9.8 9.8Z" />,
} satisfies Record<string, ReactNode>;

export type SettingsIconName = keyof typeof ICONS;

export function SettingsIcon({ name, size = 18 }: { name: SettingsIconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICONS[name]}
    </svg>
  );
}

/**
 * Một hàng. `htmlFor` nối nhãn với ô nhập (không bọc ô nhập trong <label>: iOS Safari có khi không cho sửa ô nằm trong
 * phần tử user-select: none, xem ProfileSettings). `labelId` là mã nhãn mà Dropdown mượn làm tên bảng lựa chọn.
 */
export function SettingsRow({ label, desc, descId, htmlFor, labelId, stack, className, children }: {
  label: ReactNode;
  desc?: ReactNode;
  descId?: string;
  htmlFor?: string;
  labelId?: string;
  /** Nút điều khiển nằm dưới nhãn, rộng hết hàng (ô nhập dài). */
  stack?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <div className={["settings-row", stack && "stack", className].filter(Boolean).join(" ")}>
      <div className="settings-row-text">
        {htmlFor
          ? <label className="settings-row-label" htmlFor={htmlFor} id={labelId}>{label}</label>
          : <span className="settings-row-label" id={labelId}>{label}</span>}
        {desc && <p className="settings-row-desc" id={descId}>{desc}</p>}
      </div>
      {children && <div className="settings-row-control">{children}</div>}
    </div>
  );
}

/** Một nhóm hàng, có hoặc không có tiêu đề nhỏ. */
export function SettingsGroup({ title, className, children }: { title?: string; className?: string; children: ReactNode }) {
  return (
    <div className={className ? `settings-group ${className}` : "settings-group"}>
      {title && <h3 className="settings-group-title">{title}</h3>}
      <div className="settings-group-body">{children}</div>
    </div>
  );
}

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  /** Có biểu tượng thì nút chỉ hiện biểu tượng; nhãn thành tên đọc và chú thích khi rê chuột. */
  icon?: ReactNode;
  hint?: string;
}

/**
 * Nút chọn liền khối như "Theme" trong Cài đặt của Claude. Bên trong là nhóm radio thật, nên mũi tên trái phải đổi lựa
 * chọn và trình đọc màn hình đọc đúng "đang chọn".
 */
export function Segmented<T extends string>({ label, value, options, onChange }: {
  label: string;
  value: T;
  options: SegmentOption<T>[];
  onChange: (value: T) => void;
}) {
  const name = useId();
  return (
    <div className={options.some((item) => item.icon) ? "settings-seg icons" : "settings-seg"} role="radiogroup" aria-label={label}>
      {options.map((item) => (
        <label key={item.value} title={item.hint ?? (item.icon ? item.label : undefined)}>
          <input
            type="radio"
            name={name}
            value={item.value}
            checked={item.value === value}
            aria-label={item.icon ? item.label : undefined}
            onChange={() => onChange(item.value)}
          />
          <span>{item.icon ?? item.label}</span>
        </label>
      ))}
    </div>
  );
}

/** Công tắc bật tắt ở bên phải một hàng. */
export function SettingsSwitch({ id, label, checked, disabled, onChange }: {
  id?: string;
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <span className="settings-switch">
      <input
        id={id}
        type="checkbox"
        role="switch"
        aria-label={label}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
    </span>
  );
}
