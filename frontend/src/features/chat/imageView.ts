export interface ImageSize { width: number; height: number }
export interface ImagePoint { x: number; y: number }
export interface ImageView extends ImagePoint { scale: number; fit: boolean }
export const INITIAL_IMAGE_VIEW: ImageView = { scale: 1, x: 0, y: 0, fit: true };
export const MAX_IMAGE_SCALE = 8;
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

/** 100% là kích thước gốc; cỡ vừa khung không phóng lớn ảnh nhỏ. */
export function fitImageScale(image: ImageSize, viewport: ImageSize): number {
  if (!image.width || !image.height || !viewport.width || !viewport.height) return 1;
  return Math.min(1, Math.max(1, viewport.width - 32) / image.width, Math.max(1, viewport.height - 32) / image.height);
}

/** Giữ mép ảnh trong tầm kéo; ảnh nhỏ hơn khung luôn nằm giữa. */
export function boundImageView(view: ImageView, image: ImageSize, viewport: ImageSize): ImageView {
  const fit = fitImageScale(image, viewport);
  if (view.fit) return { scale: fit, x: 0, y: 0, fit: true };
  const scale = clamp(view.scale, Math.min(0.05, fit), MAX_IMAGE_SCALE);
  const reachX = Math.max(0, (image.width * scale - Math.max(1, viewport.width - 32)) / 2);
  const reachY = Math.max(0, (image.height * scale - Math.max(1, viewport.height - 32)) / 2);
  return { scale, x: clamp(view.x, -reachX, reachX), y: clamp(view.y, -reachY, reachY), fit: false };
}

/** Giữ đúng điểm ảnh dưới con trỏ hoặc giữa hai ngón, cả khi vừa zoom vừa kéo. */
export function transformImageView(view: ImageView, scale: number, from: ImagePoint, to: ImagePoint,
  image: ImageSize, viewport: ImageSize): ImageView {
  const nextScale = clamp(scale, Math.min(0.05, fitImageScale(image, viewport)), MAX_IMAGE_SCALE);
  const ratio = nextScale / view.scale;
  return boundImageView({ scale: nextScale, x: to.x + (view.x - from.x) * ratio,
    y: to.y + (view.y - from.y) * ratio, fit: false }, image, viewport);
}
