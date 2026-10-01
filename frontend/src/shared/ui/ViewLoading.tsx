

/** Vòng chờ lúc tệp của Tạo ảnh hay Companion đang tải lần đầu. */
export function ViewLoading({ label }: { label: string }) {
  return (
    <div className="view-loading" role="status" aria-label={label}>
      <span className="loading-spinner" aria-hidden="true" />
    </div>
  );
}

