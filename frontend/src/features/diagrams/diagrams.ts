/**
 * Sơ đồ Mermaid trong câu trả lời của Peto. Chủ web chọn cách "Thẻ bên phải" ngày 2026-09-30: trong chat là một thẻ nhỏ
 * có ảnh thu nhỏ (DiagramCard), bấm thì sơ đồ mở lớn ở bảng bên phải (DiagramPanel), như bảng tài liệu.
 *
 * Mermaid rất nặng nên chỉ tải khi có sơ đồ cần vẽ. Dùng bản 11: bản 12 (ra ngày 10/9/2026) đòi Safari 17.4 trở lên và
 * kèm sẵn bộ xếp hình ELK nặng hơn.
 */
import { useEffect, useState, useSyncExternalStore } from "react";
import type { MermaidConfig } from "mermaid";

export type DiagramTheme = "dark" | "light";

const FONT = '"Segoe UI", system-ui, -apple-system, sans-serif';

// Màu theo token của app (styles.css). Mermaid 11 tô hàng thuộc tính ERD bằng rowOdd/rowEven; để mặc định thì nó lấy màu
// chính làm sáng 75%, nền tối thành các hàng xám nhạt chữ gần như không đọc được.
const PALETTE: Record<DiagramTheme, NonNullable<MermaidConfig["themeVariables"]>> = {
  dark: {
    background: "transparent", fontFamily: FONT, fontSize: "14px",
    primaryColor: "#242424", primaryTextColor: "#ececec", primaryBorderColor: "#4a4a4a",
    secondaryColor: "#1d2a36", tertiaryColor: "#1c1c1c", lineColor: "#8f8f8f", textColor: "#ececec",
    mainBkg: "#242424", nodeBorder: "#4a4a4a", clusterBkg: "#1c1c1c", edgeLabelBackground: "#1a1a1a", titleColor: "#ececec",
    attributeBackgroundColorOdd: "#1e1e1e", attributeBackgroundColorEven: "#262626", rowOdd: "#1e1e1e", rowEven: "#262626",
    actorBkg: "#242424", actorBorder: "#4a4a4a", actorTextColor: "#ececec", signalColor: "#bdbdbd", signalTextColor: "#ececec",
    noteBkgColor: "#2a2618", noteTextColor: "#ececec",
  },
  light: {
    background: "transparent", fontFamily: FONT, fontSize: "14px",
    primaryColor: "#f4f4f4", primaryTextColor: "#0d0d0d", primaryBorderColor: "#c4c4c4",
    secondaryColor: "#eaf1fb", tertiaryColor: "#fafafa", lineColor: "#6b6b6b", textColor: "#0d0d0d",
    mainBkg: "#f4f4f4", nodeBorder: "#c4c4c4", clusterBkg: "#fafafa", edgeLabelBackground: "#ffffff", titleColor: "#0d0d0d",
    attributeBackgroundColorOdd: "#ffffff", attributeBackgroundColorEven: "#f5f5f5", rowOdd: "#ffffff", rowEven: "#f5f5f5",
    actorBkg: "#f4f4f4", actorBorder: "#c4c4c4", actorTextColor: "#0d0d0d", signalColor: "#444444", signalTextColor: "#0d0d0d",
    noteBkgColor: "#fff7d6", noteTextColor: "#0d0d0d",
  },
};

let engine: Promise<typeof import("mermaid").default> | null = null;
let queue: Promise<unknown> = Promise.resolve();
let counter = 0;

/** Mã sơ đồ bỏ phần đầu ``---`` và dòng chú thích ``%%``: dòng đầu còn lại cho biết loại sơ đồ. */
function diagramBody(code: string): string {
  return code.replace(/^---\s*\n[\s\S]*?\n---\s*/, "").replace(/^\s*%%.*$/gm, "").trim();
}

// Sơ đồ phân làn (swimlane-beta, bản thử của Mermaid 11) vẽ hàng tên làn đúng chỗ Mermaid đặt tên sơ đồ, nên với lề
// mặc định 25px tên sơ đồ đè lên tên làn (thử ngày 2026-09-30).
const LANE_TITLE_MARGIN = 56;

/**
 * Vẽ một sơ đồ ra chuỗi SVG. Mermaid giữ cấu hình chung cho cả trang, nên các lượt vẽ xếp hàng để màu nền sáng của lượt
 * tải về không lẫn sang lượt vẽ nền tối trong chat.
 */
export function renderDiagram(code: string, theme: DiagramTheme): Promise<string> {
  engine ??= import("mermaid").then((module) => module.default);
  const lanes = /^swimlane-beta\b/.test(diagramBody(code));
  const line = PALETTE[theme].lineColor;
  const job = queue.then(async () => {
    const mermaid = await engine!;
    mermaid.initialize({
      startOnLoad: false,
      // Mã sơ đồ do model viết, có thể bị một trang web dụ: chế độ strict bỏ HTML, liên kết và lệnh click.
      securityLevel: "strict",
      theme: "base",
      darkMode: theme === "dark",
      themeVariables: PALETTE[theme],
      fontFamily: FONT,
      // Chữ SVG thật thay cho HTML nhúng: vẽ lên canvas để tải PNG/PDF được (HTML nhúng làm canvas bị khóa).
      htmlLabels: false,
      flowchart: { htmlLabels: false, curve: "basis", padding: 12, titleTopMargin: lanes ? LANE_TITLE_MARGIN : 25 },
      // Ký hiệu UML của sơ đồ hoạt động vẽ bằng lưu đồ: điểm bắt đầu (@{ shape: sm-circ }) là chấm tô kín, điểm kết thúc
      // (fr-circ) là hình bia có chấm đặc ở giữa. Để mặc định thì chấm đầu có màu nền nút, chấm giữa có màu viền nhạt gần
      // như không thấy. Nút không có chữ mới đổi, để vòng tròn đôi có chữ ((( ))) giữ nguyên.
      themeCSS: `.node .state-start { fill: ${line}; stroke: ${line}; }
        .node:not(:has(text)) .outer-path > g > path { fill: ${line}; stroke: ${line}; }`,
    });
    const { svg } = await mermaid.render(`peto-diagram-${++counter}`, code);
    return svg;
  });
  queue = job.catch(() => undefined);
  return job;
}

export function describeError(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  const line = /line (\d+)/i.exec(text);
  return line ? `Lỗi cú pháp ở dòng ${line[1]} của mã sơ đồ.` : "Mã sơ đồ không hợp lệ.";
}

const KINDS: [RegExp, string][] = [
  [/^(flowchart|graph)\b/, "Lưu đồ"],
  [/^swimlane-beta\b/, "Sơ đồ phân làn"],
  [/^classDiagram/, "Sơ đồ lớp"],
  [/^sequenceDiagram\b/, "Sơ đồ tuần tự"],
  [/^stateDiagram/, "Sơ đồ trạng thái"],
  [/^erDiagram\b/, "Sơ đồ quan hệ"],
  [/^gantt\b/, "Biểu đồ Gantt"],
  [/^mindmap\b/, "Sơ đồ tư duy"],
  [/^pie\b/, "Biểu đồ tròn"],
  [/^timeline\b/, "Dòng thời gian"],
  [/^journey\b/, "Hành trình người dùng"],
];

// Mermaid không có sơ đồ hoạt động hay use case riêng: Peto vẽ chúng bằng stateDiagram-v2 (có làn thì swimlane-beta) và
// flowchart (persona.DIAGRAM_PROMPT), rồi đặt tên bắt đầu bằng tên loại để thẻ không ghi nhầm thành "Sơ đồ trạng thái" hay "Lưu đồ".
const NAMED_KINDS: [RegExp, string][] = [
  [/^sơ đồ hoạt động(?=$|[\s:,.–-])/i, "Sơ đồ hoạt động"],
  [/^sơ đồ (use case|ca sử dụng)(?=$|[\s:,.–-])/i, "Sơ đồ use case"],
];

/** Loại sơ đồ (theo tên hoặc từ khóa đầu) và tên (lấy ``title:`` ở phần đầu ``---`` của mã, không có thì dùng tên loại). */
export function describe(code: string): { kind: string; title: string } {
  const front = /^---\s*\n([\s\S]*?)\n---/.exec(code)?.[1] ?? "";
  const title = (/^\s*title:\s*(.+?)\s*$/m.exec(front)?.[1]?.replace(/^(["'])(.*)\1$/, "$2") ?? "").normalize("NFC");
  const body = diagramBody(code);
  const kind = NAMED_KINDS.find(([pattern]) => pattern.test(title))?.[1]
    ?? KINDS.find(([pattern]) => pattern.test(body))?.[1] ?? "Sơ đồ";
  return { kind, title: title || kind };
}

/** Loại sơ đồ để ghi cạnh tên, hoặc chuỗi rỗng khi tên đã bắt đầu bằng loại (khỏi ghi "Sơ đồ tuần tự · Sơ đồ tuần tự"). */
export function kindNote(kind: string, title: string): string {
  return title.toLocaleLowerCase("vi").startsWith(kind.toLocaleLowerCase("vi")) ? "" : kind;
}

export function svgSize(svg: string): { width: number; height: number } {
  const box = /viewBox="([^"]+)"/.exec(svg)?.[1].trim().split(/[\s,]+/).map(Number);
  return box && box.length === 4 && box[2] > 0 && box[3] > 0 ? { width: box[2], height: box[3] } : { width: 640, height: 400 };
}

/** Đặt kích thước cố định cho thẻ svg gốc (Mermaid để width="100%" và max-width bằng cỡ thật). */
export function sized(svg: string, width: number, height: number): string {
  return svg.replace(/<svg\b([^>]*)>/, (_match, attributes: string) => {
    const rest = attributes.replace(/\s(width|height)="[^"]*"/g, "").replace(/\sstyle="[^"]*"/, "");
    return `<svg${rest} width="${width}" height="${height}">`;
  });
}

/** Tin nhắn có khối ```mermaid (hoặc ~~~mermaid) không. */
export function hasDiagram(text: string): boolean {
  return /(^|\n)[ \t]*(```|~~~)[ \t]*mermaid\b/i.test(text);
}

/**
 * Bỏ thụt lề chung và dòng trống hai đầu. Cùng một sơ đồ, lấy từ cây Markdown (thẻ trong chat) hay từ chữ gốc (danh sách
 * của bảng bên phải), thì ra cùng một chuỗi, kể cả khi khối nằm trong danh sách.
 */
export function normalizeDiagram(code: string): string {
  const lines = code.replace(/\r\n?/g, "\n").split("\n");
  const indent = Math.min(...lines.filter((line) => line.trim()).map((line) => /^[ \t]*/.exec(line)![0].length));
  return lines.map((line) => line.slice(Number.isFinite(indent) ? indent : 0)).join("\n").trim();
}

/** Các sơ đồ trong một câu trả lời theo thứ tự, để bảng bên phải chuyển qua lại. Khối code khác bị bỏ qua cả nội dung. */
export function diagramBlocks(markdown: string): string[] {
  const found: string[] = [];
  let open: { mark: string; size: number; body: string[] | null } | null = null;
  for (const line of markdown.replace(/\r\n?/g, "\n").split("\n")) {
    const fence = /^[ \t]*(`{3,}|~{3,})[ \t]*([^\s`]*)/.exec(line);
    if (open) {
      if (fence && fence[1][0] === open.mark && fence[1].length >= open.size && !fence[2] && !line.trim().slice(fence[1].length)) {
        if (open.body) found.push(normalizeDiagram(open.body.join("\n")));
        open = null;
      } else open.body?.push(line);
    } else if (fence) {
      open = { mark: fence[1][0], size: fence[1].length, body: fence[2].toLowerCase() === "mermaid" ? [] : null };
    }
  }
  // Khối chưa đóng tới cuối tin vẫn là một khối (Markdown cũng hiển thị như vậy); tin đang viết dở thì bên gọi bỏ qua.
  if (open?.body) found.push(normalizeDiagram(open.body.join("\n")));
  return found;
}

/** Chữ của một nút trong cây Markdown (hast), như nội dung khối code. */
export function hastText(node: unknown): string {
  if (!node || typeof node !== "object") return "";
  const item = node as { type?: string; value?: string; children?: unknown[] };
  if (item.type === "text") return item.value ?? "";
  return (item.children ?? []).map(hastText).join("");
}

function subscribeTheme(listener: () => void) {
  const observer = new MutationObserver(listener);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

/** Nền sáng hay tối đang dùng (App ghi ở data-theme của thẻ html), để vẽ lại sơ đồ khi người dùng đổi nền. */
export function useDiagramTheme(): DiagramTheme {
  return useSyncExternalStore(
    subscribeTheme,
    () => (document.documentElement.dataset.theme === "light" ? "light" : "dark"),
    () => "dark",
  );
}

/** Vẽ ``code`` theo nền hiện tại. Đổi nền thì giữ hình cũ tới khi hình mới xong, khỏi nháy trống. */
export function useDiagram(code: string, theme: DiagramTheme, enabled = true) {
  const [state, setState] = useState({ code: "", svg: "", error: "" });
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    renderDiagram(code, theme).then(
      (svg) => { if (alive) setState({ code, svg, error: "" }); },
      (error) => { if (alive) setState({ code, svg: "", error: describeError(error) }); },
    );
    return () => { alive = false; };
  }, [code, theme, enabled]);
  const current = state.code === code;
  return { svg: current ? state.svg : "", error: current ? state.error : "", ready: current };
}
