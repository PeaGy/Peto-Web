import { PETO_FRAMES } from './petoSprite';

// Machine Love (27/11/2026): Peto pixel nhún đầu ở dòng "Đang làm", từ ảnh chủ web gửi. Hai tư thế đổi nhau mỗi 250ms,
// như ảnh GIF đen trắng. Bản 1 giữ màu ảnh; bản 2 đơn sắc, vẽ bằng màu chữ của giao diện (sáng thì tóc đen như GIF,
// tối thì đảo lại).

const COLORS: Record<string, string> = {
  k: '#000000', R: '#d50000', r: '#ff2424', w: '#ffffff', s: '#ffe4bd', p: '#ff4081', m: '#f50057',
};
/** Ô được tô ở bản đơn sắc: nét đen, tóc và lưỡi; mặt, nơ và ruột nốt nhạc để trống. */
const INK = new Set(['k', 'R', 'r', 'm']);
const FACE = new Set(['s', 'p', 'm']);
export const PETO_FRAME_MS = 250;
const W = PETO_FRAMES[0][0].length, H = PETO_FRAMES[0].length;

/** Nét đen không chạm mặt (nốt nhạc, viền nơ) gần như mất trên nền tối: ở giao diện tối vẽ bằng màu chữ. */
function lineOffFace(frame: string[], x: number, y: number) {
  return ![[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dy]) => FACE.has(frame[y + dy]?.[x + dx] ?? '.'));
}

function sprite(frame: string[], mono: boolean, ink: string, dark: boolean) {
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');
  if (!ctx) return canvas;
  frame.forEach((row, y) => [...row].forEach((cell, x) => {
    if (cell === '.') return;
    if (mono) {
      if (!INK.has(cell)) return;
      ctx.fillStyle = ink;
    } else ctx.fillStyle = dark && cell === 'k' && lineOffFace(frame, x, y) ? ink : COLORS[cell];
    ctx.fillRect(x, y, 1, 1);
  }));
  return canvas;
}

/**
 * Vẽ Peto lên canvas vuông `size` px. Phóng kiểu "sắc nét": nhân nguyên lần bằng ô vuông rồi thu mượt về đúng cỡ, để
 * cỡ nào cũng không nhòe hẳn mà các ô vẫn đều. `still` (giảm chuyển động) chỉ vẽ tư thế đầu. Trả hàm dừng.
 */
export function mountPeto(canvas: HTMLCanvasElement, mono: boolean, size: number, still: boolean) {
  const dpr = window.devicePixelRatio || 1, px = Math.round(size * dpr);
  canvas.width = canvas.height = px;
  const ctx = canvas.getContext('2d');
  if (!ctx) return () => {};
  const scale = px / H, up = Math.max(1, Math.ceil(scale));
  const big = document.createElement('canvas');
  big.width = W * up; big.height = H * up;
  const bigCtx = big.getContext('2d')!;
  let cache: { key: string; frames: HTMLCanvasElement[] } | null = null;

  function frames() {
    const ink = getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#ececec';
    const dark = document.documentElement.dataset.theme !== 'light';
    const key = `${ink}|${dark}`;
    if (cache?.key !== key) cache = { key, frames: PETO_FRAMES.map(frame => sprite(frame, mono, ink, dark)) };
    return cache.frames;
  }

  let index = 0;
  function draw() {
    bigCtx.imageSmoothingEnabled = false;
    bigCtx.clearRect(0, 0, big.width, big.height);
    bigCtx.drawImage(frames()[index], 0, 0, big.width, big.height);
    const w = W * scale, h = H * scale;
    ctx!.clearRect(0, 0, px, px);
    ctx!.imageSmoothingEnabled = true;
    ctx!.imageSmoothingQuality = 'high';
    ctx!.drawImage(big, (px - w) / 2, (px - h) / 2, w, h);
  }

  draw();
  // Đổi giao diện sáng/tối giữa chừng: vẽ lại ngay bằng màu mới.
  const watch = new MutationObserver(draw);
  watch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  const timer = still ? 0 : window.setInterval(() => { index = (index + 1) % PETO_FRAMES.length; draw(); }, PETO_FRAME_MS);
  return () => { window.clearInterval(timer); watch.disconnect(); };
}
