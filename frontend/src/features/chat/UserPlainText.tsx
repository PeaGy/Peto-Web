/**
 * Tin của người dùng hiện đúng như đã gõ (G4.1, chủ web chọn 13/11/2026, như ChatGPT): giữ xuống dòng và khoảng trắng,
 * link http(s) thành chip như trước, khối code rào bằng ``` hoặc ~~~ thành khối code. Không còn Markdown khác: gõ `*`,
 * `#`, `1.` hay `$x$` thì hiện đúng ký tự đó, không thành chữ nghiêng, tiêu đề, danh sách hay công thức.
 */
import { Fragment } from 'react';
import CodeBlock from './CodeBlock';
import { MessageLink } from './LinkChip';

export type UserSegment = { kind: 'text'; text: string } | { kind: 'code'; language: string; source: string };

const FENCE = /^ {0,3}(`{3,}|~{3,})[ \t]*([^\s`]*)[^`]*$/;

/** Tách tin thành đoạn chữ và khối code rào. Khối chưa đóng tới cuối tin vẫn là khối code (như Markdown). */
export function splitUserText(text: string): UserSegment[] {
  const segments: UserSegment[] = [];
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  let plain: string[] = [];
  let open: { mark: string; size: number; language: string; body: string[] } | null = null;
  const flush = () => {
    const value = plain.join('\n').replace(/^\n+|\n+$/g, '');
    if (value.trim()) segments.push({ kind: 'text', text: value });
    plain = [];
  };
  for (const line of lines) {
    if (open) {
      const close = new RegExp(`^ {0,3}${open.mark === '`' ? '`' : '~'}{${open.size},}[ \\t]*$`);
      if (close.test(line)) {
        segments.push({ kind: 'code', language: open.language, source: open.body.join('\n') });
        open = null;
      } else open.body.push(line);
      continue;
    }
    const fence = FENCE.exec(line);
    if (fence) {
      flush();
      open = { mark: fence[1][0], size: fence[1].length, language: fence[2].toLowerCase(), body: [] };
    } else plain.push(line);
  }
  if (open) segments.push({ kind: 'code', language: open.language, source: open.body.join('\n') });
  flush();
  return segments;
}

const URL = /https?:\/\/[^\s<>"'`]+/gi;
const TRAILING = /[.,;:!?'"”’»…]+$/;

/** Cắt link khỏi chữ; bỏ dấu câu dính ở cuối, và dấu đóng ngoặc thừa khi link không có ngoặc mở tương ứng. */
export function linkParts(text: string): { text: string; href?: string }[] {
  const parts: { text: string; href?: string }[] = [];
  let last = 0;
  for (const match of text.matchAll(URL)) {
    let href = match[0];
    for (;;) {
      const trimmed = href.replace(TRAILING, '');
      const closing = trimmed.endsWith(')') && (trimmed.match(/\(/g)?.length ?? 0) < (trimmed.match(/\)/g)?.length ?? 0)
        ? trimmed.slice(0, -1) : trimmed;
      if (closing === href) break;
      href = closing;
    }
    const start = match.index ?? 0;
    if (start > last) parts.push({ text: text.slice(last, start) });
    parts.push({ text: href, href });
    last = start + href.length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}

export default function UserPlainText({ text }: { text: string }) {
  return <>{splitUserText(text).map((segment, index) => segment.kind === 'code'
    ? <CodeBlock key={index} language={segment.language} source={segment.source}>
        <code className={segment.language ? `language-${segment.language}` : undefined}>{segment.source}</code>
      </CodeBlock>
    : <p key={index} className="user-plain-text">{linkParts(segment.text).map((part, at) => part.href
        ? <MessageLink key={at} href={part.href} />
        : <Fragment key={at}>{part.text}</Fragment>)}</p>)}</>;
}
