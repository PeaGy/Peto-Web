/**
 * Tô màu code và công thức toán của Markdown nằm ở hai tệp tải sau (markdownCode.ts, markdownMath.ts). Trước đây
 * highlight.js và KaTeX nằm trong tệp JS chính, gần một nửa của nó: điện thoại phải tải và chạy hết trước khi thấy ô
 * chat, dù phần lớn hội thoại không có code hay công thức (đo ngày 2026-09-27).
 *
 * Tin nhắn nào cần thì mới kéo tệp tương ứng về, mỗi tệp một lần. Lúc tệp chưa về, code hiện chữ thường và công thức
 * hiện nguyên dạng `$...$`; về xong thì chỉ những tin cần tới nó vẽ lại.
 */
import { useEffect, useSyncExternalStore } from "react";
import type { Options } from "react-markdown";
import remarkGfm from "remark-gfm";

type Plugins = NonNullable<Options["remarkPlugins"]>;

export interface MarkdownExtra {
  remark: Plugins;
  rehype: Plugins;
}

type Kind = "math" | "code";

// Mỗi import() đứng riêng một hàm: gộp hai cái vào một biểu thức điều kiện thì bản build chỉ tải kèm phụ thuộc của một
// nhánh, và CSS của KaTeX không về (công thức hiện lặp chữ, gặp ngày 2026-09-27).
const loaders: Record<Kind, () => Promise<{ extra: MarkdownExtra }>> = {
  math: () => import("./markdownMath"),
  code: () => import("./markdownCode"),
};

const loaded: Partial<Record<Kind, MarkdownExtra>> = {};
const pending = new Set<Kind>();
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Bắt đầu tải phần mở rộng (nếu chưa); cũng dùng để tải trước. */
export function loadMarkdownExtra(kind: Kind): void {
  if (loaded[kind] || pending.has(kind)) return;
  pending.add(kind);
  loaders[kind]().then(
    (module) => {
      loaded[kind] = module.extra;
      pending.delete(kind);
      listeners.forEach((listener) => listener());
    },
    // Mất mạng giữa chừng: tin vẫn hiện chữ thường, lần vẽ sau sẽ thử tải lại.
    () => pending.delete(kind),
  );
}

/** Có khối code rào bằng ``` hay ~~~ (chỉ khối này mới được tô màu). */
export function hasCode(text: string): boolean {
  return /(^|\n) {0,3}(```|~~~)/.test(text);
}

/** Có thể có công thức. normalizeMath đã đổi \(…\) và \[…\] thành $…$; "$5" cũng tính, chỉ tốn một lần tải thừa. */
export function hasMath(text: string): boolean {
  return text.includes("$");
}

/** Plugin cho react-markdown của một tin nhắn: GFM luôn có, toán và tô màu code khi tin cần và tệp đã về. */
export function useMarkdownPlugins(text: string): { remarkPlugins: Plugins; rehypePlugins: Plugins } {
  const needMath = hasMath(text);
  const needCode = hasCode(text);
  // Chỉ những phần tin này cần mới làm nó vẽ lại khi tải xong.
  const ready = useSyncExternalStore(subscribe, () => (needMath && loaded.math ? 1 : 0) + (needCode && loaded.code ? 2 : 0));
  useEffect(() => {
    if (needMath) loadMarkdownExtra("math");
    if (needCode) loadMarkdownExtra("code");
  }, [needMath, needCode]);
  const math = ready & 1 ? loaded.math : undefined;
  const code = ready & 2 ? loaded.code : undefined;
  return {
    remarkPlugins: [remarkGfm, ...(math?.remark ?? []), ...(code?.remark ?? [])],
    rehypePlugins: [...(math?.rehype ?? []), ...(code?.rehype ?? [])],
  };
}
