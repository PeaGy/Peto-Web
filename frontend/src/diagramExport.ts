/** Tải sơ đồ về (PNG, SVG, PDF) và mở bằng draw.io. Chỉ bảng sơ đồ dùng, nên nằm trong phần tải riêng của bảng. */
import { describe, renderDiagram, sized, svgSize } from "./diagrams";

// Safari trên iPhone không vẽ canvas lớn hơn khoảng 16,7 triệu điểm ảnh (ra ảnh trắng), nên giới hạn dưới mức đó.
const MAX_CANVAS_PIXELS = 16_000_000;
const PADDING = 24;

function save(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function fileName(code: string) {
  return describe(code).title.replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim() || "So do Peto";
}

/** Vẽ sơ đồ lên canvas nền trắng. Bản tải về luôn theo nền sáng, để dán vào Word hay in ra không thành một khối đen. */
async function rasterize(code: string, scale: number, type: "image/png" | "image/jpeg") {
  const svg = await renderDiagram(code, "light");
  const { width, height } = svgSize(svg);
  const outerWidth = width + PADDING * 2;
  const outerHeight = height + PADDING * 2;
  const factor = Math.min(scale, Math.sqrt(MAX_CANVAS_PIXELS / (outerWidth * outerHeight)));
  const image = new Image();
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(sized(svg, width, height))}`;
  await image.decode();
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(outerWidth * factor);
  canvas.height = Math.round(outerHeight * factor);
  const context = canvas.getContext("2d")!;
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, PADDING * factor, PADDING * factor, width * factor, height * factor);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, 0.92));
  if (!blob) throw new Error("Trình duyệt không vẽ được ảnh sơ đồ.");
  return { blob, width: canvas.width, height: canvas.height };
}

export async function downloadPng(code: string) {
  const { blob } = await rasterize(code, 2, "image/png");
  save(blob, `${fileName(code)}.png`);
}

export async function downloadSvg(code: string) {
  const svg = await renderDiagram(code, "light");
  save(new Blob([svg], { type: "image/svg+xml" }), `${fileName(code)}.svg`);
}

/** PDF khổ A4 (dọc hay ngang theo sơ đồ), sơ đồ là ảnh độ nét cao nằm giữa trang: in hay nộp đều đẹp. */
export async function downloadPdf(code: string) {
  const { blob, width, height } = await rasterize(code, 3, "image/jpeg");
  const pdf = pdfFromJpeg(new Uint8Array(await blob.arrayBuffer()), width, height);
  save(new Blob([pdf], { type: "application/pdf" }), `${fileName(code)}.pdf`);
}

/** Một trang PDF chứa một ảnh JPEG (đưa thẳng vào PDF, không phải giải nén lại). */
export function pdfFromJpeg(jpeg: Uint8Array, width: number, height: number): Uint8Array<ArrayBuffer> {
  const landscape = width > height;
  const [pageWidth, pageHeight] = landscape ? [841.89, 595.28] : [595.28, 841.89];
  const margin = 36;
  const scale = Math.min((pageWidth - margin * 2) / width, (pageHeight - margin * 2) / height);
  const drawWidth = width * scale;
  const drawHeight = height * scale;
  const number = (value: number) => value.toFixed(2);
  const encoder = new TextEncoder();
  const parts: Uint8Array[] = [];
  const offsets: number[] = [];
  let length = 0;
  const push = (chunk: Uint8Array | string) => {
    const bytes = typeof chunk === "string" ? encoder.encode(chunk) : chunk;
    parts.push(bytes);
    length += bytes.length;
  };
  const object = (id: number, dictionary: string, stream?: Uint8Array) => {
    offsets[id] = length;
    push(`${id} 0 obj\n${dictionary}\n`);
    if (stream) {
      push("stream\n");
      push(stream);
      push("\nendstream\n");
    }
    push("endobj\n");
  };
  push("%PDF-1.4\n");
  push(new Uint8Array([0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a])); // dòng chú thích nhị phân: báo đây là tệp nhị phân
  const content = encoder.encode(`q ${number(drawWidth)} 0 0 ${number(drawHeight)} ${number((pageWidth - drawWidth) / 2)} ${number((pageHeight - drawHeight) / 2)} cm /Im0 Do Q`);
  object(1, "<< /Type /Catalog /Pages 2 0 R >>");
  object(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  object(3, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${number(pageWidth)} ${number(pageHeight)}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`);
  object(4, `<< /Type /XObject /Subtype /Image /Width ${width} /Height ${height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>`, jpeg);
  object(5, `<< /Length ${content.length} >>`, content);
  const xref = length;
  push(`xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")}`);
  push(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  const output = new Uint8Array(length);
  let position = 0;
  for (const part of parts) {
    output.set(part, position);
    position += part.length;
  }
  return output;
}

function base64(bytes: Uint8Array): string {
  let binary = "";
  for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  return btoa(binary);
}

/**
 * Liên kết mở sơ đồ trong draw.io, dựng như công cụ chính thức của draw.io (@drawio/mcp): mã sơ đồ nằm sau dấu #, nên trình
 * duyệt không gửi nó lên máy chủ draw.io; draw.io tự đổi Mermaid thành hình sửa được. Nén giống họ (deflate-raw rồi
 * base64 của chuỗi đã encodeURIComponent); trình duyệt chưa có CompressionStream thì gửi nguyên văn (draw.io nhận cả hai).
 *
 * Không thêm tham số sau dấu ? như công cụ kia (grid, pv, border, edit): thử ngày 2026-09-30, có bất kỳ tham số nào là
 * draw.io mở sơ đồ xong lại hỏi "Tất cả mọi thay đổi sẽ mất!", bấm nhầm "Loại bỏ" là mất sơ đồ vừa mở.
 */
export async function drawioUrl(code: string): Promise<string> {
  let payload = { type: "mermaid", compressed: false, data: code };
  if (typeof CompressionStream === "function") {
    try {
      const stream = new Blob([encodeURIComponent(code)]).stream().pipeThrough(new CompressionStream("deflate-raw"));
      payload = { type: "mermaid", compressed: true, data: base64(new Uint8Array(await new Response(stream).arrayBuffer())) };
    } catch {
      // Giữ bản nguyên văn.
    }
  }
  return `https://app.diagrams.net/#create=${encodeURIComponent(JSON.stringify(payload))}`;
}
