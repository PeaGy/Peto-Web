/**
 * Cú bấm này có mở một mục trong tin nhắn không: nút ``aria-expanded="false"`` ("Đang làm", Xem thêm, khối code gập)
 * hay ``<summary>`` của một ``<details>`` đang đóng (28/11/2026, theo ``isOpeningDisclosure`` của assistant-ui). Nút mở
 * menu (``aria-haspopup``) hay ô chọn không tính: chúng không làm tin nhắn dài ra.
 */
export function opensDisclosure(target: EventTarget | null): boolean {
  if (!(target instanceof Element) || !target.closest('article')) return false;
  if (target.closest('textarea, input, select, [contenteditable]:not([contenteditable="false"])')) return false;
  const control = target.closest('[aria-expanded], summary');
  if (!control) return false;
  if (control.tagName === 'SUMMARY') return control.parentElement?.hasAttribute('open') === false;
  const popup = control.getAttribute('aria-haspopup');
  return control.getAttribute('aria-expanded') === 'false' && (popup === null || popup === 'false')
    && control.getAttribute('role') !== 'combobox';
}
