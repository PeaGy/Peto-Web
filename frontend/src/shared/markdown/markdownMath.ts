/** Công thức toán trong tin nhắn (KaTeX). Tệp này tải riêng, chỉ khi có tin nhắn chứa công thức (xem markdownExtras.ts). */
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import type { MarkdownExtra } from "./markdownExtras";

export const extra: MarkdownExtra = {
  remark: [remarkMath],
  rehype: [[rehypeKatex, { trust: false, strict: "ignore" }]],
};
