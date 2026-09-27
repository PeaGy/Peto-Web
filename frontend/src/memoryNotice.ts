/**
 * Dòng "Peto vừa ghi nhớ" trong cột chat Companion (chủ web chọn hiện dòng này ngày 2026-09-27). Máy chủ ghi nhớ ở tác
 * vụ nền sau khi trả lời xong, nên trang hỏi lại sau các khoảng chờ này; máy chủ báo xong (hết `pending`) thì thôi hỏi.
 */
export const MEMORY_POLL_DELAYS = [2500, 3500, 5000];

/** Chữ trên dòng báo: ghi nhớ đầu tiên, kèm số điều còn lại nếu lượt đó nhớ nhiều điều. */
export function noticeText(items: { text: string }[]): string {
  const [first, ...rest] = items;
  if (!first) return "";
  return rest.length ? `${first.text} (và ${rest.length} điều khác)` : first.text;
}
