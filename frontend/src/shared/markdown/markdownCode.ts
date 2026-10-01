/**
 * Tô màu khối code trong tin nhắn. Tệp này tải riêng, chỉ khi có tin nhắn chứa khối code (xem markdownExtras.ts).
 *
 * Dùng thẳng lõi lowlight với đúng các ngôn ngữ dưới đây, không qua rehype-highlight: gói đó luôn kéo theo cả bộ
 * `common` của lowlight dù được truyền `languages`, nên bản build từng chứa 63 bộ ngữ pháp thay vì 26 (đo ngày
 * 2026-09-27). Thêm ngôn ngữ mới thì thêm cả nhãn vào CODE_LABELS trong App.tsx, không thì đầu khối code hiện tên thô
 * viết hoa như "CSHARP".
 */
import type { Element, ElementContent, Root, RootContent } from "hast";
import { createLowlight } from "lowlight";
import bash from "highlight.js/lib/languages/bash";
import c from "highlight.js/lib/languages/c";
import cpp from "highlight.js/lib/languages/cpp";
import csharp from "highlight.js/lib/languages/csharp";
import css from "highlight.js/lib/languages/css";
import dart from "highlight.js/lib/languages/dart";
import diff from "highlight.js/lib/languages/diff";
import dockerfile from "highlight.js/lib/languages/dockerfile";
import go from "highlight.js/lib/languages/go";
import ini from "highlight.js/lib/languages/ini";
import java from "highlight.js/lib/languages/java";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import kotlin from "highlight.js/lib/languages/kotlin";
import lua from "highlight.js/lib/languages/lua";
import markdown from "highlight.js/lib/languages/markdown";
import php from "highlight.js/lib/languages/php";
import plaintext from "highlight.js/lib/languages/plaintext";
import powershell from "highlight.js/lib/languages/powershell";
import python from "highlight.js/lib/languages/python";
import ruby from "highlight.js/lib/languages/ruby";
import rust from "highlight.js/lib/languages/rust";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";
import type { MarkdownExtra } from "./markdownExtras";

const lowlight = createLowlight({
  bash, c, cpp, csharp, css, dart, diff, dockerfile, go, ini, java, javascript, json,
  kotlin, lua, markdown, php, plaintext, powershell, python, ruby, rust, sql, typescript,
  xml, yaml,
});

// Grammar tự khai báo alias riêng, nhưng khai thêm ở đây cho chắc: đây là những tên Peto hay viết sau dấu ``` nhất.
lowlight.registerAlias({
  bash: ["sh", "shell", "console", "zsh"],
  cpp: ["c++", "cc"],
  csharp: ["cs", "c#"],
  dockerfile: ["docker"],
  go: ["golang"],
  ini: ["toml"],
  javascript: ["js", "jsx"],
  kotlin: ["kt"],
  markdown: ["md"],
  plaintext: ["text", "txt"],
  powershell: ["ps1", "pwsh"],
  ruby: ["rb"],
  rust: ["rs"],
  typescript: ["ts", "tsx"],
  xml: ["html"],
  yaml: ["yml"],
});

/** Ngôn ngữ ghi trên khối code (`language-x` hay `lang-x`); false khi khối đánh dấu không tô màu. */
export function codeLanguage(node: Element): string | false | undefined {
  const names = Array.isArray(node.properties.className) ? node.properties.className.map(String) : [];
  if (names.includes("no-highlight") || names.includes("nohighlight")) return false;
  const name = names.find((value) => value.startsWith("language-") || value.startsWith("lang-"));
  return name ? name.slice(name.indexOf("-") + 1) : undefined;
}

function textOf(node: Element | ElementContent): string {
  if (node.type === "text") return node.value;
  if (node.type === "element") return node.children.map(textOf).join("");
  return "";
}

function highlightTree(parent: Root | Element) {
  for (const child of parent.children as (RootContent | ElementContent)[]) {
    if (child.type !== "element") continue;
    const code = child.tagName === "pre" ? child.children.find((item): item is Element => item.type === "element") : undefined;
    if (!code || code.tagName !== "code") {
      highlightTree(child);
      continue;
    }
    const language = codeLanguage(code);
    // Không ghi ngôn ngữ hay ngôn ngữ chưa đăng ký thì để chữ thường, như ignoreMissing của rehype-highlight.
    if (!language || !lowlight.registered(language)) continue;
    const result = lowlight.highlight(language, textOf(code));
    const names = Array.isArray(code.properties.className) ? code.properties.className : [];
    code.properties.className = names.includes("hljs") ? names : ["hljs", ...names];
    if (result.children.length) code.children = result.children as ElementContent[];
  }
}

function rehypeCode() {
  return (tree: Root) => highlightTree(tree);
}

export const extra: MarkdownExtra = { remark: [], rehype: [rehypeCode] };
