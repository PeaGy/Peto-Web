import { useEffect, useRef, type RefObject } from "react";

/**
 * Cuộn Cài đặt tới một mục khi nơi khác xin (nút "Xem" ở dòng "Peto vừa ghi nhớ", đường dẫn "Peto nghe" trong bảng
 * Micro). Mỗi lần `request` tăng chỉ cuộn một lần: mở Cài đặt bình thường sau đó không bị kéo về mục này nữa.
 *
 * App mở hộp thoại trong useLayoutEffect, nên lúc effect ở đây chạy thì hộp thoại đã hiện và cuộn được. `settle` là giá
 * trị đổi khi mục tải xong dữ liệu: lần đổi đầu tiên sau yêu cầu thì cuộn lại, vì mục bên trên (Hồ sơ đang tải) có thể
 * vừa cao thêm, mà Safari không tự giữ chỗ cuộn như Chrome.
 */
export function useSettingsFocus(ref: RefObject<HTMLElement | null>, open: boolean, request: number, settle?: unknown) {
  const handled = useRef(0);
  const pending = useRef(false);
  const settleAtRequest = useRef<unknown>(undefined);

  useEffect(() => {
    if (!open) {
      pending.current = false;
      return;
    }
    if (request === handled.current) return;
    handled.current = request;
    pending.current = settle !== undefined;
    settleAtRequest.current = settle;
    ref.current?.scrollIntoView({ block: "start" });
    // settle cố ý không làm effect này chạy lại: effect dưới lo phần cuộn lại khi nó đổi.
  }, [open, request, ref]);

  useEffect(() => {
    if (!pending.current || Object.is(settle, settleAtRequest.current)) return;
    pending.current = false;
    ref.current?.scrollIntoView({ block: "start" });
  }, [settle, ref]);
}
