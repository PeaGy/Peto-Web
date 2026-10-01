/**
 * Mở micro cho phần Peto nghe: getUserMedia rồi AudioWorklet (hearingWorklet.js) đưa từng khúc âm thanh về trang.
 * Tách riêng để test thay được bằng micro giả, vì jsdom không có Web Audio.
 */
// no-inline: tệp nhỏ thì Vite mặc định nhúng thành địa chỉ data:, mà không phải trình duyệt nào cũng nạp worklet từ đó.
import workletUrl from "./hearingWorklet.js?url&no-inline";

export interface MicCapture {
  sampleRate: number;
  stop(): void;
}

export interface Microphone {
  id: string;
  label: string;
}

export function captureSupported(): boolean {
  return !!navigator.mediaDevices?.getUserMedia && typeof AudioContext !== "undefined" && typeof AudioWorkletNode !== "undefined";
}

function micError(error: unknown): Error {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return new Error("Chưa được phép dùng micro. Bấm biểu tượng ổ khóa cạnh địa chỉ trang để cho phép, rồi thử lại.");
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") return new Error("Không tìm thấy micro nào trên máy này.");
  if (name === "NotReadableError" || name === "AbortError") return new Error("Micro đang bị ứng dụng khác giữ. Tắt ứng dụng đó rồi thử lại.");
  return error instanceof Error ? error : new Error("Chưa mở được micro.");
}

async function openStream(deviceId: string): Promise<MediaStream> {
  const audio = { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 };
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: deviceId ? { ...audio, deviceId: { exact: deviceId } } : audio });
  } catch (error) {
    // Micro đã chọn bị rút ra: dùng micro mặc định thay vì không nghe được gì.
    if (deviceId && error instanceof DOMException && (error.name === "OverconstrainedError" || error.name === "NotFoundError")) {
      return navigator.mediaDevices.getUserMedia({ audio });
    }
    throw error;
  }
}

/** Mở micro và gửi từng khúc âm thanh (Float32, tần số `sampleRate`) cho `onChunk` tới khi gọi `stop()`. */
export async function openMicrophone(deviceId: string, onChunk: (samples: Float32Array) => void): Promise<MicCapture> {
  if (!captureSupported()) throw new Error("Trình duyệt này chưa cho ghi âm từ micro.");
  let stream: MediaStream | undefined;
  let context: AudioContext | undefined;
  try {
    stream = await openStream(deviceId);
    context = new AudioContext();
    await context.audioWorklet.addModule(workletUrl);
    const source = context.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(context, "peto-mic-capture");
    // Nối tới loa với âm lượng 0: nút không nằm trên đường ra loa thì có trình duyệt không chạy nó.
    const silent = context.createGain();
    silent.gain.value = 0;
    node.port.onmessage = (event: MessageEvent<Float32Array>) => onChunk(event.data);
    source.connect(node);
    node.connect(silent);
    silent.connect(context.destination);
    await context.resume();
    const opened = { stream, context };
    return {
      sampleRate: context.sampleRate,
      stop() {
        node.port.onmessage = null;
        source.disconnect();
        node.disconnect();
        silent.disconnect();
        opened.stream.getTracks().forEach((track) => track.stop());
        void opened.context.close().catch(() => {});
      },
    };
  } catch (error) {
    stream?.getTracks().forEach((track) => track.stop());
    void context?.close().catch(() => {});
    throw micError(error);
  }
}

/** Các micro trên máy. Trước khi người dùng cho phép dùng micro, trình duyệt chưa cho biết tên. */
export async function listMicrophones(): Promise<Microphone[]> {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices
      .filter((device) => device.kind === "audioinput" && device.deviceId && device.deviceId !== "default")
      .map((device, index) => ({ id: device.deviceId, label: device.label || `Micro ${index + 1}` }));
  } catch {
    return [];
  }
}
