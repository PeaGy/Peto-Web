/**
 * Chia Markdown của câu trả lời đang chạy thành các khối độc lập (28/11/2026, ý từ `parse-blocks` của vercel/streamdown).
 *
 * Khối trước đã đủ thì chữ của nó không đổi nữa; nơi vẽ nhớ từng khối theo chữ, nên mỗi mảnh mới chỉ dựng lại khối cuối
 * thay vì cả câu trả lời. Ghép các khối lại luôn ra đúng chuỗi ban đầu.
 *
 * Chỉ cắt ở chỗ chắc chắn không đổi nghĩa: sau một dòng trống, ngoài khối code (```/~~~) và khối công thức `$$`, trước
 * một dòng sát lề trái, và không cắt đôi danh sách (dòng sau là mục danh sách mà khối trước đang là danh sách). Có chú
 * thích cuối trang hay định nghĩa link (cần thấy cả bài) thì để nguyên một khối, như streamdown.
 */

const FENCE = /^ {0,3}(`{3,}|~{3,})/;
const LIST_ITEM = /^ {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)/;
const WHOLE_DOCUMENT = /^ {0,3}\[\^[^\]\n]+\]:|^ {0,3}\[[^\]\n]+\]:\s/m;

export function splitMarkdownBlocks(text: string): string[] {
  if (!text || WHOLE_DOCUMENT.test(text)) return text ? [text] : [];
  const lines = text.split('\n');
  const blocks: string[] = [];
  let current: string[] = [];
  let fence: string | null = null;
  let math = false;
  let blank = false;
  // Dòng có chữ gần nhất của khối đang gom: là mục danh sách hay dòng thụt lề (thuộc danh sách).
  let lastWasList = false;

  const flush = () => {
    if (current.length) blocks.push(current.join('\n') + '\n');
    current = [];
  };

  lines.forEach((line, index) => {
    const last = index === lines.length - 1;
    if (fence === null && !math && blank && line.trim() !== '' && !/^[ \t]/.test(line)
      && !(LIST_ITEM.test(line) && lastWasList)) {
      flush();
      lastWasList = false;
    }
    // Dòng cuối không có "\n" phía sau: giữ đúng chuỗi gốc khi ghép lại.
    if (last) {
      if (current.length || line !== '') current.push(line);
      if (current.length) blocks.push(current.join('\n'));
      current = [];
    } else current.push(line);

    const opener = fence === null ? FENCE.exec(line) : null;
    if (fence !== null) {
      const closing = FENCE.exec(line);
      if (closing && closing[1][0] === fence[0] && closing[1].length >= fence.length && line.trim() === closing[1]) fence = null;
    } else if (opener) fence = opener[1];
    else if (!math && /^ {0,3}\$\$/.test(line) && (line.match(/\$\$/g)?.length ?? 0) % 2 === 1) math = true;
    else if (math && (line.match(/\$\$/g)?.length ?? 0) % 2 === 1) math = false;

    if (line.trim() === '') blank = true;
    else {
      blank = false;
      if (fence === null && !math) lastWasList = LIST_ITEM.test(line) || (/^[ \t]/.test(line) && lastWasList);
    }
  });
  return blocks;
}
