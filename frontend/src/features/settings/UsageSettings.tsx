import { useCallback, useEffect, useRef, useState } from "react";
import { UnauthorizedError, getUsage, type WeeklyUsage } from "../../shared/api/api";
import { SettingsGroup } from "./settingsUi";
import "./usage.css";

/** "20:00, thứ Ba 25/11" theo giờ của trình duyệt; thời điểm máy chủ trả về tính bằng giây. */
export function resetLabel(seconds: number): string {
  const date = new Date(seconds * 1000);
  const time = date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false });
  const weekday = date.toLocaleDateString("vi-VN", { weekday: "long" });
  return `${time}, ${weekday} ${date.getDate()}/${date.getMonth() + 1}`;
}

/** Phần trăm hiện cho người dùng: số nguyên, phần lẻ dưới 1% ghi "<1%" để không thành "0%" khi đã có dùng. */
export function percentLabel(value: number): string {
  if (value > 0 && value < 1) return "<1%";
  return `${Math.round(value)}%`;
}

/**
 * Cài đặt → Mức dùng (mẫu A, giống trang Usage của Grok; chủ web chọn ngày 23/11/2026): một thanh chia màu theo mục,
 * phần trăm đã dùng trong tuần và giờ đặt lại. Đang ở bước chỉ đo: chưa chặn, nên thanh có thể vượt 100%.
 */
export default function UsageSettings({ open, onUnauthorized }: { open: boolean; onUnauthorized: () => void }) {
  const [usage, setUsage] = useState<WeeklyUsage | null>(null);
  const [failed, setFailed] = useState(false);
  const loadVersion = useRef(0);

  const load = useCallback(async () => {
    const version = ++loadVersion.current;
    setFailed(false);
    try {
      const next = await getUsage();
      if (version === loadVersion.current) setUsage(next);
    } catch (err) {
      if (version !== loadVersion.current) return;
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setFailed(true);
    }
  }, [onUnauthorized]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  if (failed) return <SettingsGroup>
    <p className="usage-note" role="alert">Chưa tải được mức dùng. <button type="button" className="usage-retry" onClick={() => void load()}>Thử lại</button></p>
  </SettingsGroup>;
  if (!usage) return <SettingsGroup><p className="usage-note">Đang tải mức dùng…</p></SettingsGroup>;

  // Thanh luôn vừa khung: tổng quá 100% thì chia lại theo tỉ lệ, con số vẫn ghi đúng phần trăm thật.
  const scale = Math.max(100, usage.used_percent);
  const used = usage.groups.filter(group => group.percent > 0);
  return (
    <SettingsGroup title="Mức dùng trong tuần">
      <div className="usage-card">
        <div className="usage-head">
          <span><strong>{percentLabel(usage.used_percent)}</strong> đã dùng</span>
          <span className="usage-reset">{usage.resets_at ? <>Đặt lại <b>{resetLabel(usage.resets_at)}</b></> : "Tuần mới bắt đầu từ lần dùng tới"}</span>
        </div>
        <div className="usage-bar" role="img" aria-label={`Đã dùng ${percentLabel(usage.used_percent)} mức dùng trong tuần`}>
          {used.map(group => <span key={group.key} className={`usage-fill usage-${group.key}`} style={{ width: `${(group.percent / scale) * 100}%` }} />)}
        </div>
        <ul className="usage-legend">
          {usage.groups.map(group => <li key={group.key}><span className={`usage-dot usage-${group.key}`} aria-hidden="true" />{group.label} <b>{percentLabel(group.percent)}</b></li>)}
        </ul>
        <p className="usage-note">
          {usage.unlimited ? "Tài khoản chủ web không bị giới hạn; số này để đo." : "Đang đo thử, chưa giới hạn."}
        </p>
      </div>
    </SettingsGroup>
  );
}
