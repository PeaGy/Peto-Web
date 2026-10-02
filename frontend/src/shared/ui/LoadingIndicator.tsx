import './loading.css';

/** Logo dùng chung cho màn hình mở trang và những vùng đang chờ dữ liệu. */
export function LoadingIndicator({ label, variant = 'panel' }: {
  label: string;
  variant?: 'screen' | 'panel' | 'icon';
}) {
  return <div className={`brand-loading brand-loading--${variant}`} role="status" aria-label={label}>
    <div className="brand-loading-identity" aria-hidden="true">
      <div className="brand-loading-mark">
        <img src="/docs-assets/logo.webp" width="144" height="100" alt="" draggable={false} />
      </div>
      {variant === 'screen' && <span className="brand-loading-name">Peto</span>}
    </div>
    {variant !== 'icon' && <div className="brand-loading-wait" aria-hidden="true">
      <span className="brand-loading-label">{variant === 'screen' ? 'Loading' : label}<span className="brand-loading-dots">…</span></span>
      <span className="brand-loading-track"><span /></span>
    </div>}
  </div>;
}
