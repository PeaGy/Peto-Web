export type CropArea = { x: number; y: number; width: number; height: number };
export type Stroke = { points: { x: number; y: number }[]; color: string; size: number; erasing: boolean };
export const FULL_CROP: CropArea = { x: 0, y: 0, width: 1, height: 1 };

export async function loadImage(src: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('Chưa tải được ảnh để chỉnh sửa. Bạn thử lại nhé.'));
    image.src = src;
  });
}

export function drawStrokes(context: CanvasRenderingContext2D, strokes: Stroke[], width: number, height: number) {
  context.clearRect(0, 0, width, height);
  for (const stroke of strokes) {
    context.globalCompositeOperation = stroke.erasing ? 'destination-out' : 'source-over';
    context.strokeStyle = stroke.color; context.fillStyle = stroke.color;
    context.lineWidth = stroke.size * width; context.lineCap = 'round'; context.lineJoin = 'round';
    context.beginPath();
    stroke.points.forEach((point, index) => index ? context.lineTo(point.x * width, point.y * height) : context.moveTo(point.x * width, point.y * height));
    context.stroke();
    if (stroke.points.length === 1) { const point = stroke.points[0]; context.beginPath(); context.arc(point.x * width, point.y * height, context.lineWidth / 2, 0, Math.PI * 2); context.fill(); }
  }
  context.globalCompositeOperation = 'source-over';
}

/** Cắt/vẽ chỉ tạo nguồn mới; không ghi đè ảnh đã lưu trên máy chủ. */
export async function renderEdit(src: string, crop: CropArea = FULL_CROP, strokes: Stroke[] = []) {
  const image = await loadImage(src);
  if (!image.naturalWidth || !image.naturalHeight || image.naturalWidth * image.naturalHeight > 40_000_000) throw new Error('Ảnh quá lớn để chỉnh sửa trong trình duyệt.');
  const left = Math.round(crop.x * image.naturalWidth), top = Math.round(crop.y * image.naturalHeight);
  const width = Math.max(1, Math.min(image.naturalWidth - left, Math.round(crop.width * image.naturalWidth)));
  const height = Math.max(1, Math.min(image.naturalHeight - top, Math.round(crop.height * image.naturalHeight)));
  const canvas = document.createElement('canvas');
  canvas.width = width; canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Trình duyệt chưa mở được công cụ chỉnh ảnh.');
  context.drawImage(image, left, top, width, height, 0, 0, width, height);
  if (strokes.length) {
    const layer = document.createElement('canvas'); layer.width = image.naturalWidth; layer.height = image.naturalHeight;
    const layerContext = layer.getContext('2d');
    if (!layerContext) throw new Error('Trình duyệt chưa mở được bút vẽ.');
    drawStrokes(layerContext, strokes, layer.width, layer.height);
    context.drawImage(layer, left, top, width, height, 0, 0, width, height);
  }
  const data = canvas.toDataURL('image/png');
  if (data.length * .75 > 8 * 1024 * 1024) throw new Error('Bản chỉnh sửa vượt quá 8 MB. Bạn cắt nhỏ hơn trước khi dùng làm tham chiếu nhé.');
  return data;
}

export async function extractPalette(src: string): Promise<string[]> {
  const image = await loadImage(src);
  const canvas = document.createElement('canvas'); canvas.width = 64; canvas.height = 64;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) throw new Error('Trình duyệt chưa đọc được màu ảnh.');
  context.drawImage(image, 0, 0, 64, 64);
  const data = context.getImageData(0, 0, 64, 64).data;
  const groups = new Map<string, { count: number; r: number; g: number; b: number }>();
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 128) continue;
    const key = `${data[i] >> 5},${data[i + 1] >> 5},${data[i + 2] >> 5}`;
    const group = groups.get(key) ?? { count: 0, r: 0, g: 0, b: 0 };
    group.count++; group.r += data[i]; group.g += data[i + 1]; group.b += data[i + 2]; groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => b.count - a.count).slice(0, 4).map(group => '#' + [group.r, group.g, group.b].map(value => Math.round(value / group.count).toString(16).padStart(2, '0')).join(''));
}
