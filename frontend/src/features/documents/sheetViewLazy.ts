// Lưới xem bảng tính (thanh công thức, biểu đồ) tải riêng khi mở bảng tính lần đầu trong bảng tài liệu.
import { preloadable } from "../../shared/ui/preloadable";

export const sheetView = preloadable(() => import("./SheetView"));
