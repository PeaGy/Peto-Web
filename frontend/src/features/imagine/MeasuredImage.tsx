import { useEffect, useRef, useState, type ComponentPropsWithoutRef } from "react";

function dimensions(width: number, height: number) {
  const gcd = (a: number, b: number): number => b ? gcd(b, a % b) : a;
  const divisor = gcd(width, height);
  const w = width / divisor, h = height / divisor;
  const ratio = w <= 25 && h <= 25 ? `${w}:${h}` : `≈ ${(width / height).toLocaleString("vi-VN", { maximumFractionDigits: 2 })}:1`;
  return `${width} × ${height} · ${ratio}`;
}

/** Chỉ hiện kích thước từ tệp đã tải, không suy ra từ lựa chọn 1K/2K hay tỉ lệ yêu cầu. */
export default function MeasuredImage({ src, onLoad, onError, ...props }: ComponentPropsWithoutRef<"img"> & { src: string }) {
  const ref = useRef<HTMLImageElement>(null);
  const [measurement, setMeasurement] = useState<{ src: string; text: string } | null>(null);
  function measure(image: HTMLImageElement) {
    if (image.naturalWidth && image.naturalHeight) setMeasurement({ src, text: dimensions(image.naturalWidth, image.naturalHeight) });
  }
  useEffect(() => {
    if (ref.current?.complete) measure(ref.current);
  }, [src]);
  return <>
    <img {...props} key={src} ref={ref} src={src} onLoad={event => { measure(event.currentTarget); onLoad?.(event); }}
      onError={event => { setMeasurement(null); onError?.(event); }} />
    {measurement?.src === src && <span className="image-dimensions" aria-label="Kích thước ảnh thực tế">{measurement.text}</span>}
  </>;
}
