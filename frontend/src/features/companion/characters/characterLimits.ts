// Giới hạn nhập model nhân vật, dùng chung cho bộ nhập (characterImport.ts, tải riêng khi cần) và chú thích trong bảng
// Nhân vật. Chủ web nâng từ 80/160/64 MB ngày 11/10/2026 cho model lớn. Model chỉ lưu trong IndexedDB của trình duyệt,
// không qua máy chủ; hết chỗ thì characterLibrary báo "Bộ nhớ trình duyệt đã đầy".
const MB = 1024 * 1024;

/** Tổng dung lượng các tệp chọn trong một lần nhập (ZIP, thư mục Live2D hoặc tệp .vrm). */
export const MAX_IMPORT_BYTES = 200 * MB;
/** Tổng dung lượng sau khi giải nén ZIP. */
export const MAX_EXPANDED_BYTES = 400 * MB;
/** Một tệp bên trong model (.moc3, texture…). */
export const MAX_FILE_BYTES = 128 * MB;
export const MAX_JSON_BYTES = 4 * MB;
export const MAX_FILES = 512;

/** Số MB để ghi trong thông báo, lấy từ chính giới hạn để chữ không lệch khi đổi số. */
export const megabytes = (bytes: number) => `${Math.round(bytes / MB)} MB`;
