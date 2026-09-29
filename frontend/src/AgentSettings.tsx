import { useCallback, useEffect, useRef, useState } from "react";
import { UnauthorizedError, listAgentDevices, revokeAgentDevice, type AgentDevices } from "./api";
import { SettingsGroup, SettingsRow } from "./settingsUi";

const INTRO = "Peto sửa code ngay trên máy bạn qua chương trình dòng lệnh peto.";

/** "Dùng 5 phút trước" theo giờ của trình duyệt; thời điểm do máy chủ trả về tính bằng giây. */
export function lastUsedLabel(seconds: number, now = Date.now() / 1000): string {
  const elapsed = Math.max(0, now - seconds);
  if (elapsed < 60) return "Vừa dùng xong";
  if (elapsed < 3600) return `Dùng ${Math.floor(elapsed / 60)} phút trước`;
  if (elapsed < 86400) return `Dùng ${Math.floor(elapsed / 3600)} giờ trước`;
  return `Dùng ${Math.floor(elapsed / 86400)} ngày trước`;
}

/**
 * Mục Peto Agent trong Cài đặt: số bước còn lại hôm nay và các máy đã kết nối, ngắt được từng máy.
 * Tài khoản khách không dùng được agent nên chỉ thấy lời giải thích và không gọi API.
 */
export default function AgentSettings({ open, isGuest, onUnauthorized }: {
  open: boolean;
  isGuest: boolean;
  onUnauthorized: () => void;
}) {
  const [data, setData] = useState<AgentDevices | null>(null);
  const [failed, setFailed] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadVersion = useRef(0);

  const load = useCallback(async () => {
    const version = ++loadVersion.current;
    setFailed(false);
    try {
      const next = await listAgentDevices();
      if (version === loadVersion.current) setData(next);
    } catch (err) {
      if (version !== loadVersion.current) return;
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setFailed(true);
    }
  }, [onUnauthorized]);

  useEffect(() => {
    if (!open || isGuest) return;
    setError(null);
    void load();
    return () => {
      loadVersion.current += 1;
    };
  }, [open, isGuest, load]);

  async function revoke(deviceId: string) {
    setRevoking(deviceId);
    setError(null);
    try {
      await revokeAgentDevice(deviceId);
      setData((prev) => prev && { ...prev, devices: prev.devices.filter((device) => device.id !== deviceId) });
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setError(err instanceof Error ? err.message : "Chưa ngắt kết nối được. Thử lại nhé.");
    } finally {
      setRevoking(null);
    }
  }

  if (isGuest) return <p className="settings-intro">{INTRO} Tính năng này cần đăng nhập bằng Discord hoặc Google.</p>;

  const left = data ? Math.max(0, data.steps_limit - data.steps_used) : 0;
  return <>
    <p className="settings-intro">{INTRO}</p>
    {data && <SettingsGroup>
      <SettingsRow label="Bước hôm nay" desc="Mỗi lần Peto gọi model là một bước; mức Cao và các model lớn tính nhiều bước hơn.">
        <span className="settings-meter">
          <span>Còn {left}/{data.steps_limit}</span>
          <span className="settings-meter-bar" aria-hidden="true">
            <i style={{ width: `${data.steps_limit ? (left / data.steps_limit) * 100 : 0}%` }} />
          </span>
        </span>
      </SettingsRow>
    </SettingsGroup>}
    <SettingsGroup title="Máy đã kết nối">
      {failed ? <div className="voice-row">
        <p className="settings-hint" role="alert">Chưa tải được danh sách máy.</p>
        <button type="button" className="settings-button" onClick={() => void load()}>Thử lại</button>
      </div> : !data ? <p className="settings-note" role="status">Đang tải danh sách máy…</p>
        : data.devices.length === 0 ? <p className="settings-note agent-empty">
          Chưa có máy nào kết nối. Mở cửa sổ dòng lệnh trên máy của bạn và chạy <code>peto login</code>.
        </p> : <ul className="agent-devices" aria-label="Máy đã kết nối">
          {data.devices.map((device) => <li key={device.id}>
            <div>
              <strong>{device.name}</strong>
              <span>{lastUsedLabel(device.last_used_at)}</span>
            </div>
            <button type="button" className="settings-button" disabled={revoking === device.id}
              aria-label={`Ngắt kết nối ${device.name}`} onClick={() => void revoke(device.id)}>
              {revoking === device.id ? "Đang ngắt…" : "Ngắt kết nối"}
            </button>
          </li>)}
        </ul>}
    </SettingsGroup>
    {error && <p className="voice-error" role="alert">{error}</p>}
  </>;
}
