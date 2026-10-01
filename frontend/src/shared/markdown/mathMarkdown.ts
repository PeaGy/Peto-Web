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

function escaped(source: string, offset: number): boolean {
  let slashes = 0;
  for (let i = offset - 1; i >= 0 && source[i] === "\\"; i--) slashes++;
  return slashes % 2 === 1;
}

/** Không ghép hai dấu tiền tệ qua văn xuôi hay dấu đậm thành một công thức. */
function inlineMath(body: string, after: string): boolean {
  if (!body.trim() || /\*\*|__/.test(body)) return false;
  // $2.00 và $3.00: dấu đóng giả thực ra là dấu mở của giá tiếp theo.
  if (/^\d/.test(body)) {
    if (/\d/.test(after) || body !== body.trim()) return false;
    // Giá tiền rồi văn xuôi trước công thức tiếp theo, chẳng hạn $5 rồi $x^2$.
    if (/^\d+(?:[.,]\d+)*[.,;:]?\s+\p{L}{2,}/u.test(body)
        && !/^\d+(?:[.,]\d+)*\s+(?:sin|cos|tan|log|ln)\b/.test(body)) return false;
  }
  return true;
}

function normalizeDollars(source: string): string {
  const result: string[] = [];
  for (let i = 0; i < source.length; i++) {
    if (source[i] !== "$" || escaped(source, i)) {
      result.push(source[i]);
      continue;
    }
    let end = i + 1;
    while (end < source.length && source[end] !== "\n" && (source[end] !== "$" || escaped(source, end))) end++;
    const body = source.slice(i + 1, end);
    if (source[end] === "$" && inlineMath(body, source[end + 1] ?? "")) {
      result.push(`$${tildeNegation(body)}$`);
      i = end;
    } else {
      // Chỉ escape dấu hiện tại, để $5 rồi $x^2$ vẫn nhận đúng công thức phía sau.
      result.push("\\$");
    }
  }
  return result.join("");
}

/** Chuẩn hóa LaTeX và giữ dấu tiền tệ là văn bản trước khi xử lý Markdown. */
export function normalizeMath(source: string): string {
  // Giữ code và công thức tường minh riêng; không xử lý dấu tiền tệ bên trong chúng.
  const tokens = /(^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:^ {0,3}\2[^\n]*(?:\n|$)|(?![\s\S])))|(`+)([^`]|(?!\3)`)*?\3|\$\$[\s\S]*?\$\$|\\\[([\s\S]*?)\\\]|\\\(([^\n]*?)\\\)/gm;
  const result: string[] = [];
  let cursor = 0;
  for (const match of source.matchAll(tokens)) {
    const [whole, fence, _marker, ticks, _code, display, inline] = match;
    const offset = match.index;
    result.push(normalizeDollars(source.slice(cursor, offset)));
    // Dấu gạch chéo đã được escape là văn bản, không phải công thức.
    if (escaped(source, offset) || fence !== undefined || ticks !== undefined) result.push(whole);
    else if (display !== undefined) result.push(`\n\n$$\n${tildeNegation(display.trim())}\n$$\n\n`);
    else if (inline !== undefined) result.push(`$${tildeNegation(inline)}$`);
    else result.push(`$$${tildeNegation(whole.slice(2, -2))}$$`);
    cursor = offset + whole.length;
  }
  result.push(normalizeDollars(source.slice(cursor)));
  return result.join("");
}
