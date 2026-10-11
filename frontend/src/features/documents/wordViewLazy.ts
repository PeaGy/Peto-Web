// Bản xem tệp Word Peto đã sửa (KaTeX cho công thức) tải riêng khi mở lần đầu trong bảng tài liệu.
import { preloadable } from "../../shared/ui/preloadable";

export const wordView = preloadable(() => import("./WordView"));
