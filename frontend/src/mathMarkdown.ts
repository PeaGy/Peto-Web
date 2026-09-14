/** Chuẩn hóa dấu phân cách LaTeX trước khi Markdown bỏ dấu gạch chéo. */
export function normalizeMath(source: string): string {
  // Giữ nguyên khối code, code trong dòng và công thức đã dùng dấu đô la.
  const tokens = /(^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:^ {0,3}\2[^\n]*(?:\n|$)|(?![\s\S])))|(`+)([^`]|(?!\3)`)*?\3|\$\$[\s\S]*?\$\$|\$[^\n$]+\$|\\\[([\s\S]*?)\\\]|\\\(([^\n]*?)\\\)/gm;
  return source.replace(tokens, (whole, _fence, _marker, _ticks, _code, display, inline, offset) => {
    // Dấu gạch chéo đã được escape là văn bản, không phải công thức.
    let slashes = 0;
    for (let i = offset - 1; i >= 0 && source[i] === "\\"; i--) slashes++;
    if (slashes % 2) return whole;
    if (display !== undefined) return `\n\n$$\n${display.trim()}\n$$\n\n`;
    if (inline !== undefined) return `$${inline}$`;
    return whole;
  });
}
