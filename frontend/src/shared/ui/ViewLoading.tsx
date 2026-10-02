

import { LoadingIndicator } from './LoadingIndicator';

/** Logo chờ lúc tệp của Tạo ảnh hay Companion đang tải lần đầu. */
export function ViewLoading({ label }: { label: string }) {
  return (
    <div className="view-loading">
      <LoadingIndicator label={label} />
    </div>
  );
}

