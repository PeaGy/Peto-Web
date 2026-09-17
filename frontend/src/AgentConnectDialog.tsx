import { useEffect, useRef, useState } from "react";
import { UnauthorizedError, answerAgentDevice, getAgentDevice, type AgentDevicePending } from "./api";

const CODE_KEY = "peto-agent-code";
const CODE_PATTERN = /^[A-Z2-9]{4}-?[A-Z2-9]{4}$/i;

/**
 * Lấy mã kết nối Peto Agent từ liên kết `?agent_code=` rồi xóa khỏi thanh địa chỉ.
 *
 * Mã được giữ trong sessionStorage vì đăng nhập Discord/Google chuyển hướng đi rồi quay về, làm mất tham số trên URL.
 */
export function takeAgentCode(): string | null {
  try {
    const url = new URL(window.location.href);
    const fromUrl = url.searchParams.get("agent_code");
    if (fromUrl !== null) {
      url.searchParams.delete("agent_code");
      window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
      if (CODE_PATTERN.test(fromUrl.trim())) sessionStorage.setItem(CODE_KEY, fromUrl.trim().toUpperCase());
    }
    return sessionStorage.getItem(CODE_KEY);
  } catch {
    return null;
  }
}

export function forgetAgentCode(): void {
  try {
    sessionStorage.removeItem(CODE_KEY);
  } catch {
    // Không xóa được thì lần tải trang sau hộp chỉ báo mã đã hết hạn.
  }
}

type State =
  | { kind: "guest" }
  | { kind: "loading" }
  | { kind: "ready"; device: AgentDevicePending; sending: boolean }
  | { kind: "allowed"; name: string }
  | { kind: "denied" }
  | { kind: "error"; message: string };

/** Hộp "Kết nối Peto Agent?" mở từ liên kết mà lệnh peto login in ra. */
export default function AgentConnectDialog({ code, isGuest, onClose, onUnauthorized }: {
  code: string;
  isGuest: boolean;
  onClose: () => void;
  onUnauthorized: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [state, setState] = useState<State>(isGuest ? { kind: "guest" } : { kind: "loading" });

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  useEffect(() => {
    if (isGuest) {
      setState({ kind: "guest" });
      return;
    }
    const controller = new AbortController();
    setState({ kind: "loading" });
    getAgentDevice(code, controller.signal)
      .then((device) => setState({ kind: "ready", device, sending: false }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (err instanceof UnauthorizedError) return onUnauthorized();
        setState({ kind: "error", message: err instanceof Error ? err.message : "Chưa kiểm tra được mã kết nối." });
      });
    return () => controller.abort();
  }, [code, isGuest, onUnauthorized]);

  async function answer(allow: boolean) {
    if (state.kind !== "ready" || state.sending) return;
    const { device } = state;
    setState({ kind: "ready", device, sending: true });
    try {
      await answerAgentDevice(code, allow);
      setState(allow ? { kind: "allowed", name: device.name } : { kind: "denied" });
    } catch (err) {
      if (err instanceof UnauthorizedError) return onUnauthorized();
      setState({ kind: "error", message: err instanceof Error ? err.message : "Chưa gửi được lựa chọn. Thử lại nhé." });
    }
  }

  const sending = state.kind === "ready" && state.sending;
  const title = state.kind === "allowed" ? "Đã kết nối" : state.kind === "denied" ? "Đã từ chối kết nối"
    : state.kind === "error" ? "Chưa kết nối được" : "Kết nối Peto Agent?";

  return <dialog ref={dialogRef} className="confirm-dialog agent-connect" aria-labelledby="agent-connect-title"
    onCancel={(event) => { event.preventDefault(); if (!sending) onClose(); }}>
    <h2 id="agent-connect-title">{title}</h2>
    {state.kind === "guest" && <p>
      Peto Agent chỉ dùng được với tài khoản Discord hoặc Google. Đăng xuất tài khoản khách rồi đăng nhập bằng Discord
      hoặc Google để kết nối máy này.
    </p>}
    {state.kind === "loading" && <p role="status">Đang kiểm tra mã kết nối…</p>}
    {state.kind === "ready" && <>
      <p>
        Máy <strong className="agent-device-name">{state.device.name}</strong> muốn dùng Peto Agent bằng tài khoản của bạn.
        Chỉ cho phép khi mã này khớp với mã trên máy.
      </p>
      <p className="agent-code" aria-label="Mã kết nối">{state.device.user_code}</p>
    </>}
    {state.kind === "allowed" && <p role="status">
      Máy <strong className="agent-device-name">{state.name}</strong> đã dùng được Peto Agent. Quay lại cửa sổ dòng lệnh để
      bắt đầu.
    </p>}
    {state.kind === "denied" && <p role="status">Máy này không được kết nối. Nếu bấm nhầm, chạy lại peto login để lấy mã mới.</p>}
    {state.kind === "error" && <p role="alert">{state.message}</p>}
    <div className="dialog-actions">
      {state.kind === "ready" ? <>
        <button type="button" disabled={sending} onClick={() => void answer(false)}>Không cho phép</button>
        <button type="button" className="agent-allow" disabled={sending} onClick={() => void answer(true)}>
          {sending ? "Đang gửi…" : "Cho phép"}
        </button>
      </> : <button type="button" autoFocus disabled={state.kind === "loading"} onClick={onClose}>
        {state.kind === "allowed" ? "Xong" : "Đóng"}
      </button>}
    </div>
  </dialog>;
}
