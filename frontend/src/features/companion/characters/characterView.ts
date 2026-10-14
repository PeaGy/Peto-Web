/** Góc nhìn và cử động của nhân vật Companion: phần tính toán thuần, tách khỏi PixiJS để kiểm thử được. */

export type CharacterMotion = "system" | "always";

export interface CharacterView {
  /** Hệ số phóng so với cỡ vừa khung; 1 là vừa khung. */
  zoom: number;
  /** Độ dời theo tỉ lệ bề ngang và chiều cao sân khấu, để đổi cỡ cửa sổ vẫn giữ đúng chỗ. */
  panX: number;
  panY: number;
}

/** Cỡ sân khấu cùng vị trí gốc (giữa đáy model) và tỉ lệ vừa khung khi chưa phóng hay dời. */
export interface StageBox {
  width: number;
  height: number;
  baseX: number;
  baseY: number;
  baseScale: number;
}

export const CHARACTER_MOTION_KEY = "peto-character-motion";
export const CHARACTER_VIEW_KEY = "peto-character-view";
export const DEFAULT_VIEW: CharacterView = { zoom: 1, panX: 0, panY: 0 };
export const MIN_ZOOM = 0.6;
export const MAX_ZOOM = 4;
/** Cùng mốc với CSS: dưới mốc này Companion dùng giao diện điện thoại, nhân vật khóa khung. */
export const COMPACT_QUERY = "(max-width: 720px)";

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export function readCharacterMotion(): CharacterMotion {
  try {
    return localStorage.getItem(CHARACTER_MOTION_KEY) === "always" ? "always" : "system";
  } catch {
    return "system";
  }
}

export function writeCharacterMotion(value: CharacterMotion) {
  try {
    localStorage.setItem(CHARACTER_MOTION_KEY, value);
  } catch {}
}

/**
 * "Theo cài đặt chung" (giá trị lưu vẫn là "system") nhường cho Cài đặt → Giao diện → Chuyển động của web từ 13/10/2026
 * (trước đó là cài đặt giảm chuyển động của thiết bị); "Luôn cử động" thì bỏ qua cài đặt đó.
 */
export function motionEnabled(preference: CharacterMotion, webReducesMotion: boolean): boolean {
  return preference === "always" || !webReducesMotion;
}

/** Giới hạn mức phóng và độ dời, đủ rộng để soi mặt khi phóng to nhưng không đẩy nhân vật mất hẳn. */
export function clampView(view: CharacterView): CharacterView {
  const zoom = clamp(Number.isFinite(view.zoom) ? view.zoom : 1, MIN_ZOOM, MAX_ZOOM);
  const reachX = 0.35 + zoom / 2;
  return {
    zoom,
    panX: clamp(Number.isFinite(view.panX) ? view.panX : 0, -reachX, reachX),
    panY: clamp(Number.isFinite(view.panY) ? view.panY : 0, -0.5, zoom),
  };
}

/**
 * Khóa lưu góc nhìn của một model. Điện thoại (`compact`) lưu riêng từ 15/10/2026: khung điện thoại là cận cảnh nửa người,
 * máy tính là cả người, nên cùng một mức phóng không hợp cho cả hai. Hiyori trên máy tính giữ khóa cũ không kèm mã.
 */
function viewKey(modelId: string, compact: boolean) {
  if (compact) return `${CHARACTER_VIEW_KEY}-compact:${modelId}`;
  return modelId === 'hiyori' ? CHARACTER_VIEW_KEY : `${CHARACTER_VIEW_KEY}:${modelId}`;
}

export function readCharacterView(modelId = 'hiyori', compact = false): CharacterView {
  try {
    const raw = JSON.parse(localStorage.getItem(viewKey(modelId, compact)) ?? "null") as Partial<CharacterView> | null;
    if (!raw || typeof raw !== "object") return DEFAULT_VIEW;
    return clampView({ zoom: Number(raw.zoom), panX: Number(raw.panX), panY: Number(raw.panY) });
  } catch {
    return DEFAULT_VIEW;
  }
}

const VIEW_CHANGE = "peto-character-view-change";

/**
 * Lưu góc nhìn và báo cho nơi khác cùng trang: sân khấu đổi theo thanh trượt "Kích thước và vị trí", thanh trượt đi theo
 * thao tác cuộn hay kéo trên sân khấu. ``source`` là bên ghi, để bên đó bỏ qua thông báo của chính mình; ``compact`` cho
 * biết góc nhìn của khung điện thoại hay máy tính.
 */
export function writeCharacterView(view: CharacterView, modelId = 'hiyori', source?: unknown, compact = false) {
  try {
    localStorage.setItem(viewKey(modelId, compact), JSON.stringify(view));
  } catch {}
  window.dispatchEvent(new CustomEvent(VIEW_CHANGE, { detail: { id: modelId, view, source, compact } }));
}

export function watchCharacterView(modelId: string, update: (view: CharacterView, source: unknown, compact: boolean) => void): () => void {
  const changed = (event: Event) => {
    const detail = (event as CustomEvent<{ id: string; view: CharacterView; source: unknown; compact: boolean }>).detail;
    if (detail?.id === modelId) update(clampView(detail.view), detail.source, detail.compact === true);
  };
  window.addEventListener(VIEW_CHANGE, changed);
  return () => window.removeEventListener(VIEW_CHANGE, changed);
}

export function placement(view: CharacterView, box: StageBox) {
  return {
    scale: box.baseScale * view.zoom,
    x: box.baseX + view.panX * box.width,
    y: box.baseY + view.panY * box.height,
  };
}

/** Phóng quanh một điểm trên sân khấu: chỗ dưới con trỏ hay giữa hai ngón tay đứng yên. */
export function zoomAt(view: CharacterView, factor: number, pointX: number, pointY: number, box: StageBox): CharacterView {
  const zoom = clamp(view.zoom * factor, MIN_ZOOM, MAX_ZOOM);
  const ratio = zoom / view.zoom;
  const { x, y } = placement(view, box);
  return clampView({
    zoom,
    panX: (pointX + (x - pointX) * ratio - box.baseX) / box.width,
    panY: (pointY + (y - pointY) * ratio - box.baseY) / box.height,
  });
}

export function panBy(view: CharacterView, dx: number, dy: number, box: StageBox): CharacterView {
  return clampView({ ...view, panX: view.panX + dx / box.width, panY: view.panY + dy / box.height });
}

/** Đổi một nấc cuộn (tính theo pixel, dòng hoặc trang) thành hệ số phóng; cuộn lên là phóng to. */
export function wheelZoomFactor(deltaY: number, deltaMode: number): number {
  const pixels = deltaMode === 1 ? deltaY * 16 : deltaMode === 2 ? deltaY * 400 : deltaY;
  return Math.exp(clamp(-pixels, -240, 240) * 0.0015);
}

/** Hướng nhìn trong khoảng [-1, 1] từ vị trí con trỏ so với đầu nhân vật; y dương là nhìn lên. */
export function lookTarget(pointerX: number, pointerY: number, headX: number, headY: number, width: number, height: number) {
  return {
    x: clamp((pointerX - headX) / Math.max(1, width / 2), -1, 1),
    y: clamp((headY - pointerY) / Math.max(1, height / 2), -1, 1),
  };
}
