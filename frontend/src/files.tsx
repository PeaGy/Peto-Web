/**
 * Vài thứ nhỏ dùng chung khi hiện tệp đính kèm.
 *
 * Ô nhắn và bóng chat đều cần, mà `Composer.tsx` không được import ngược từ
 * `App.tsx` (vòng import), nên chúng nằm riêng ở đây.
 */

export interface DraftFile {
  id: string;
  file: File;
  previewUrl: string | null;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileGlyph({ name, kind }: { name: string; kind: "image" | "file" }) {
  if (kind === "image") return null;
  const ext = name.split(".").pop()?.slice(0, 4).toUpperCase() || "FILE";
  return <span className="file-ext">{ext}</span>;
}
