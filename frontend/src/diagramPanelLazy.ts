// Bảng sơ đồ (kéo, phóng, tải, draw.io) tải riêng khi mở lần đầu; rê chuột lên thẻ sơ đồ là bắt đầu tải trước.
import { preloadable } from "./preloadable";

export const diagramPanel = preloadable(() => import("./DiagramPanel"));
