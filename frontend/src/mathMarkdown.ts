// Sách toán rời rạc hay viết phủ định là ~p, nhưng trong LaTeX dấu ~ là khoảng trắng không ngắt dòng: KaTeX vẽ ~p
// thành " p" và dấu phủ định biến mất, câu trả lời đúng trông như sai. Chỉ ~ đứng ở chỗ của một toán hạng (đầu công
// thức, sau dấu mở ngoặc, sau một phép logic hay sau một phủ định khác) mới được đổi thành {\sim}; ~ nằm giữa hai
// chữ như a~b hay sau \text{…} vẫn là khoảng trắng như LaTeX định nghĩa. Không dùng lookbehind để Safari cũ chạy được.
const OPERAND_START =
  /(?:^|[([{]|\\[{(]|\{\\sim\}|\\(?:lor|land|vee|wedge|to|rightarrow|leftarrow|leftrightarrow|Rightarrow|Leftarrow|Leftrightarrow|iff|implies|equiv|neg|lnot|oplus))$/;

/** Đổi dấu ~ dùng làm phủ định trong một công thức thành {\sim}, để KaTeX vẽ ra ∼ thay vì một khoảng trắng. */
export function tildeNegation(tex: string): string {
  let result = "";
  for (let i = 0; i < tex.length; i++) {
    const char = tex[i];
    if (char === "~" && tex[i - 1] !== "\\" && /[A-Za-z(\\~[]/.test(tex[i + 1] ?? "")
        && OPERAND_START.test(result.trimEnd())) {
      result += "{\\sim}";
      continue;
    }
    result += char;
  }
  return result;
}

/** Chuẩn hóa dấu phân cách LaTeX trước khi Markdown bỏ dấu gạch chéo. */
export function normalizeMath(source: string): string {
  // Giữ nguyên khối code, code trong dòng và công thức đã dùng dấu đô la.
  const tokens = /(^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:^ {0,3}\2[^\n]*(?:\n|$)|(?![\s\S])))|(`+)([^`]|(?!\3)`)*?\3|\$\$[\s\S]*?\$\$|\$[^\n$]+\$|\\\[([\s\S]*?)\\\]|\\\(([^\n]*?)\\\)/gm;
  return source.replace(tokens, (whole, fence, _marker, ticks, _code, display, inline, offset) => {
    // Dấu gạch chéo đã được escape là văn bản, không phải công thức.
    let slashes = 0;
    for (let i = offset - 1; i >= 0 && source[i] === "\\"; i--) slashes++;
    if (slashes % 2) return whole;
    if (display !== undefined) return `\n\n$$\n${tildeNegation(display.trim())}\n$$\n\n`;
    if (inline !== undefined) return `$${tildeNegation(inline)}$`;
    if (fence !== undefined || ticks !== undefined) return whole;
    if (whole.startsWith("$$")) return `$$${tildeNegation(whole.slice(2, -2))}$$`;
    return `$${tildeNegation(whole.slice(1, -1))}$`;
  });
}
