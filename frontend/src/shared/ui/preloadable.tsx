/**
 * React.lazy có thêm hàm tải trước. React.lazy luôn treo ở lần dựng đầu, kể cả khi tệp đã tải xong từ trước, và React
 * giữ vòng chờ ít nhất khoảng 300 ms cho đỡ nhấp nháy: tải sẵn lúc rảnh mà mở Tạo ảnh vẫn mất 0,35 giây (đo ngày
 * 2026-09-27). Ở đây tệp đã về thì dựng thẳng thành phần, không qua vòng chờ.
 */
import { lazy, useState, type ComponentProps, type ComponentType } from "react";

// any: nhận mọi thành phần; props lấy lại đúng kiểu qua ComponentProps.
export function preloadable<C extends ComponentType<any>>(load: () => Promise<{ default: C }>) {
  let ready: C | null = null;
  const preload = () => load().then((module) => {
    ready = module.default;
    return module;
  });
  const Lazy = lazy(preload);

  function View(props: ComponentProps<C>) {
    // Chốt cách dựng ngay lần đầu: đổi từ Lazy sang thành phần thật giữa chừng là đổi loại phần tử, React sẽ dựng lại
    // từ đầu và mất trạng thái (ảnh đang tạo, cuộc trò chuyện Companion).
    const [Loaded] = useState(() => ready);
    const Component = (Loaded ?? Lazy) as ComponentType<ComponentProps<C>>;
    return <Component {...props} />;
  }

  return { View, preload };
}
