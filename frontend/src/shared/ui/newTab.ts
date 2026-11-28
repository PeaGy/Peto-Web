/**
 * Link mở thẻ mới báo cho trình đọc màn hình (28/11/2026, như "(opens in a new tab)" của assistant-ui). Không chèn chữ
 * vào link: chữ đó sẽ lọt vào bản in, chép có định dạng và trích dẫn. Thay vào đó link trỏ ``aria-describedby`` tới một
 * phần tử ẩn duy nhất trong ``index.html`` (``#new-tab-hint``); trình đọc màn hình đọc tên link rồi tới mô tả này.
 */
export const NEW_TAB = { target: '_blank', rel: 'noopener noreferrer', 'aria-describedby': 'new-tab-hint' } as const;
