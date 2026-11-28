import type { Message, WebSource } from '../../shared/api/api';
import { safeSourceUrl } from './sourceData';

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.append(link);
  try { link.click(); }
  finally {
    link.remove();
    // Do not revoke before the browser has consumed the download URL.
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

function exportSources(sources: WebSource[] | undefined): WebSource[] {
  const seen = new Set<string>();
  return (sources ?? []).filter(source => {
    if (!safeSourceUrl(source.url) || seen.has(source.url)) return false;
    seen.add(source.url);
    return true;
  }).slice(0, 200);
}

/** Danh sách nguồn dạng Markdown, mỗi nguồn một dòng; rỗng khi không có nguồn hợp lệ. */
function sourceLines(sources: WebSource[] | undefined): string {
  return exportSources(sources).map(source => {
    const title = (source.title || new URL(source.url).hostname).replace(/[\r\n\x00-\x1f]/g, ' ').replace(/[\\[\]]/g, '\\$&');
    const url = source.url.replace(/[<>]/g, character => character === '<' ? '%3C' : '%3E');
    const ids = source.citation_ids?.filter(id => /^(?:web:[0-9]+|x:[0-9]+|src:[a-f0-9]+|turn[0-9]+(?:search|view|fetch)[0-9]+)$/.test(id));
    return `- [${title}](<${url}>)${ids?.length ? ` (${ids.join(', ')})` : ''}`;
  }).join('\n');
}

export function responseMarkdown(text: string, sources?: WebSource[]): string {
  const lines = sourceLines(sources);
  if (!lines) return text;
  return `${text}\n\n---\n\n## Nguồn\n\n${lines}\n`;
}

export function saveResponseMarkdown(text: string, sources?: WebSource[], messageId?: number): void {
  downloadBlob(new Blob([responseMarkdown(text, sources)], { type: 'text/markdown;charset=utf-8' }),
    messageId === undefined ? 'peto-response.md' : `peto-response-${messageId}.md`);
}

/** "28/11/2026", theo giờ của máy. */
const exportDate = (date: Date) => `${date.getDate()}/${date.getMonth() + 1}/${date.getFullYear()}`;
const oneLine = (value: string) => value.replace(/[\r\n\x00-\x1f]+/g, ' ').trim();
/** Tên tệp trong dấu `…` của Markdown: bỏ dấu ` để không vỡ khung. */
const fileName = (value: string) => `\`${oneLine(value).replace(/`/g, "'")}\``;

/**
 * Cả cuộc trò chuyện thành Markdown (28/11/2026): tiêu đề, ngày xuất, rồi từng tin "Bạn"/"Peto" ngăn bằng gạch ngang.
 * Tệp người dùng gửi và tài liệu Peto tạo chỉ ghi tên; nguồn đi theo câu trả lời của nó. Tin trống (lượt hỏng) bỏ qua.
 */
export function conversationMarkdown(title: string, messages: Message[], exportedAt = new Date()): string {
  const parts = [`# ${oneLine(title) || 'Hội thoại với Peto'}\n\n_Xuất từ Peto ngày ${exportDate(exportedAt)}_`];
  for (const message of messages) {
    if (message.role !== 'user' && message.role !== 'assistant') continue;
    const body = message.content.trim();
    const files = message.attachments?.map(item => fileName(item.name)) ?? [];
    const documents = message.role === 'assistant' ? message.artifacts?.map(item => fileName(item.filename || item.title)) ?? [] : [];
    if (!body && !files.length && !documents.length) continue;
    const lines = [message.role === 'user' ? '## Bạn' : '## Peto'];
    if (body) lines.push(body);
    if (files.length) lines.push(`Tệp đính kèm: ${files.join(', ')}`);
    if (documents.length) lines.push(`Tài liệu Peto tạo: ${documents.join(', ')}`);
    const sources = message.role === 'assistant' ? sourceLines(message.sources) : '';
    if (sources) lines.push('### Nguồn', sources);
    parts.push(lines.join('\n\n'));
  }
  return `${parts.join('\n\n---\n\n')}\n`;
}

/** "Báo cáo quý 3!" → "peto-bao-cao-quy-3.md": không dấu, không ký tự lạ, tối đa 60 ký tự. */
export function conversationFilename(title: string, extension = 'md'): string {
  const slug = title.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[đĐ]/g, 'd').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60).replace(/-+$/, '');
  return `peto-${slug || 'hoi-thoai'}.${extension}`;
}

export function saveConversationMarkdown(title: string, messages: Message[]): void {
  downloadBlob(new Blob([conversationMarkdown(title, messages)], { type: 'text/markdown;charset=utf-8' }),
    conversationFilename(title));
}

const HTML_TAGS = new Set('a b blockquote br code dd del div dl dt em h1 h2 h3 h4 h5 h6 hr i li ol p pre s small span strong sub sup table tbody td tfoot th thead tr u ul'.split(' '));
const MATH_TAGS = new Set('math semantics annotation mrow mi mn mo mtext ms mspace mfrac msqrt mroot mstyle merror mpadded mphantom mfenced menclose msub msup msubsup munder mover munderover mmultiscripts mprescripts none mtable mtr mtd maligngroup malignmark'.split(' '));
const DROP_TAGS = new Set('script style iframe object embed link meta base svg canvas form input select textarea noscript'.split(' '));

/** Rebuild only safe rendered nodes. No response HTML is inserted with innerHTML or document.write. */
export function printableResponse(root: HTMLElement, target: Document = document): HTMLElement {
  const output = target.createElement('main');
  function append(node: Node, parent: Node) {
    if (node.nodeType === 3) { parent.appendChild(target.createTextNode(node.textContent ?? '')); return; }
    if (node.nodeType !== 1) return;
    const source = node as Element;
    const tag = source.localName.toLowerCase();
    if (DROP_TAGS.has(tag) || source.matches('[data-export-exclude],.katex-html,.table-actions,.code-actions,.code-collapsed-summary,.user-fold-toggle')) return;
    if (tag === 'img') {
      const alt = source.getAttribute('alt');
      if (alt) parent.appendChild(target.createTextNode(alt));
      return;
    }
    let destination: Node = parent;
    if (HTML_TAGS.has(tag) || MATH_TAGS.has(tag)) {
      const element = MATH_TAGS.has(tag) ? target.createElementNS('http://www.w3.org/1998/Math/MathML', tag) : target.createElement(tag);
      const classes = [...source.classList].filter(value => /^[\w-]+$/.test(value));
      if (classes.length) element.setAttribute('class', classes.join(' '));
      if (tag === 'a') {
        const href = safeSourceUrl(source.getAttribute('href'));
        if (href) element.setAttribute('href', href);
      }
      for (const name of ['colspan', 'rowspan', 'start']) {
        const value = source.getAttribute(name);
        if (value && /^[0-9]{1,3}$/.test(value)) element.setAttribute(name, value);
      }
      if (tag === 'math' && source.getAttribute('display') === 'block') element.setAttribute('display', 'block');
      if (tag === 'annotation') element.setAttribute('encoding', 'application/x-tex');
      parent.appendChild(element);
      destination = element;
    }
    for (const child of source.childNodes) append(child, destination);
  }
  for (const child of root.childNodes) append(child, output);
  return output;
}

/**
 * HTML để dán vào Word, Google Docs hay Gmail mà giữ định dạng (28/11/2026). Dựng lại từ các nút an toàn như bản in, rồi:
 * công thức thành mã TeX ($…$, $$…$$) vì nơi dán hiểu MathML mỗi nơi một kiểu; nguồn thành [n]; bảng và code có
 * style ngay trên thẻ vì nơi dán không có CSS của Peto; bỏ dòng tên ngôn ngữ trên khối code.
 */
export function clipboardHtml(root: HTMLElement, target: Document = document): string {
  const main = printableResponse(root, target);
  main.querySelectorAll('.code-head').forEach(node => node.remove());
  main.querySelectorAll('.katex').forEach(node => {
    const tex = node.querySelector('annotation')?.textContent?.trim();
    if (!tex) return;
    const display = Boolean(node.closest('.katex-display'));
    const replacement = target.createElement(display ? 'p' : 'span');
    replacement.textContent = display ? `$$${tex}$$` : `$${tex}$`;
    (display ? node.closest('.katex-display')! : node).replaceWith(replacement);
  });
  main.querySelectorAll('.citation-badge').forEach(node => { node.textContent = `[${node.textContent}]`; });
  const cell = 'border:1px solid #bbb;padding:4px 8px;text-align:left;vertical-align:top';
  main.querySelectorAll('table').forEach(node => node.setAttribute('style', 'border-collapse:collapse'));
  main.querySelectorAll('th,td').forEach(node => node.setAttribute('style', cell));
  main.querySelectorAll('pre').forEach(node => node.setAttribute('style', 'font-family:Consolas,monospace;white-space:pre-wrap'));
  main.querySelectorAll('[class]').forEach(node => node.removeAttribute('class'));
  return `<meta charset="utf-8"><div>${main.innerHTML}</div>`;
}

const PRINT_CSS = `
  :root { color-scheme: light; }
  body { margin: 32px; color: #111; background: #fff; font: 15px/1.6 system-ui, sans-serif; }
  main { max-width: 100%; overflow-wrap: anywhere; }
  h1,h2,h3,h4 { line-height: 1.3; break-after: avoid; }
  a { color: inherit; text-decoration: underline; }
  pre { white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; padding: 12px; font: 12px/1.5 ui-monospace, monospace; }
  code { font-family: ui-monospace, monospace; }
  .code-block { margin: 16px 0; border: 1px solid #ccc; border-radius: 8px; }
  .code-head { padding: 6px 12px; border-bottom: 1px solid #ddd; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; table-layout: auto; font-size: 12px; }
  th,td { border: 1px solid #ccc; padding: 6px 8px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
  thead { display: table-header-group; } tr { break-inside: avoid; }
  blockquote { margin-left: 0; border-left: 3px solid #bbb; padding-left: 16px; }
  .citation-group { font-size: 0.8em; } .citation-badge::before { content: '['; } .citation-badge::after { content: ']'; }
  .katex-mathml { display: inline; } .katex-display { display: block; margin: 1em 0; }
  .print-sources { margin-top: 24px; border-top: 1px solid #ccc; font-size: 12px; }
  .print-sources h2 { font-size: 16px; } .print-sources a { overflow-wrap: anywhere; }
  .print-title { margin: 0 0 4px; font-size: 22px; } .print-meta { margin: 0 0 8px; color: #555; font-size: 12px; }
  .print-turn { break-inside: auto; } .print-turn .print-sources { margin-top: 12px; }
  .print-role { margin: 24px 0 8px; padding-top: 12px; border-top: 1px solid #ddd; color: #555; font-size: 12px;
    letter-spacing: .06em; text-transform: uppercase; }
  .user-plain-text { white-space: pre-wrap; }
  @page { margin: 16mm; } @media print { body { margin: 0; } }
`;

function sourcesSection(target: Document, sources: WebSource[] | undefined): HTMLElement | null {
  const actualSources = exportSources(sources);
  if (!actualSources.length) return null;
  const footer = target.createElement('section');
  footer.className = 'print-sources';
  const heading = target.createElement('h2');
  heading.textContent = 'Nguồn';
  const list = target.createElement('ol');
  for (const source of actualSources) {
    const item = target.createElement('li');
    const title = target.createElement('strong');
    title.textContent = source.title || new URL(source.url).hostname;
    const link = target.createElement('a');
    link.href = source.url;
    link.textContent = source.url;
    item.append(title, target.createElement('br'), link);
    list.append(item);
  }
  footer.append(heading, list);
  return footer;
}

/**
 * A dedicated local print document keeps the application, composer and sidebars out of the PDF. The popup opens
 * first, inside the click, so pop-up blockers allow it; `build` fills it from already rendered, safe nodes.
 */
async function printDocument(title: string, build: (target: Document) => HTMLElement): Promise<void> {
  const popup = window.open('', '_blank', 'popup,width=960,height=800');
  if (!popup) throw new Error('Chưa mở được bản in. Cho phép cửa sổ bật lên rồi thử lại nhé.');
  try {
    popup.opener = null;
    const target = popup.document;
    target.documentElement.lang = 'vi';
    const style = target.createElement('style');
    style.textContent = PRINT_CSS;
    const charset = target.createElement('meta');
    charset.setAttribute('charset', 'utf-8');
    target.head.replaceChildren(charset, style);
    target.title = title;
    target.body.replaceChildren(build(target));
    popup.addEventListener('afterprint', () => popup.close(), { once: true });
    await target.fonts?.ready;
    if (popup.closed) return;
    popup.focus();
    popup.print();
  } catch {
    popup.close();
    throw new Error('Chưa mở được bản in. Bạn thử lại nhé.');
  }
}

export async function printResponse(root: HTMLElement, sources?: WebSource[]): Promise<void> {
  return printDocument('Peto — Câu trả lời', target => {
    const main = printableResponse(root, target);
    const footer = sourcesSection(target, sources);
    if (footer) main.append(footer);
    return main;
  });
}

/**
 * Bản in của cả cuộc trò chuyện đang mở (28/11/2026): tiêu đề, ngày xuất, rồi từng tin đã vẽ trên trang dưới nhãn
 * "Bạn"/"Peto", nguồn ngay sau câu trả lời của nó. Nhật ký "Đang làm", nút và ô nhắn không vào bản in.
 */
export function printableConversation(container: HTMLElement, messages: Message[], title: string,
  target: Document = document, exportedAt = new Date()): HTMLElement {
  const main = target.createElement('main');
  const heading = target.createElement('h1');
  heading.className = 'print-title';
  heading.textContent = oneLine(title) || 'Hội thoại với Peto';
  const meta = target.createElement('p');
  meta.className = 'print-meta';
  meta.textContent = `Xuất từ Peto ngày ${exportDate(exportedAt)}`;
  main.append(heading, meta);
  container.querySelectorAll<HTMLElement>(':scope > article[data-role]').forEach((article, index) => {
    const role = article.dataset.role;
    const content = article.querySelector<HTMLElement>('[data-message-content]');
    if ((role !== 'user' && role !== 'assistant') || !content) return;
    const section = target.createElement('section');
    section.className = `print-turn ${role}`;
    const label = target.createElement('h2');
    label.className = 'print-role';
    label.textContent = role === 'user' ? 'Bạn' : 'Peto';
    section.append(label, ...printableResponse(content, target).childNodes);
    const message = messages[index];
    const footer = role === 'assistant' && message?.role === 'assistant' ? sourcesSection(target, message.sources) : null;
    if (footer) section.append(footer);
    main.append(section);
  });
  return main;
}

export async function printConversation(container: HTMLElement, messages: Message[], title: string): Promise<void> {
  return printDocument(`Peto — ${oneLine(title) || 'Hội thoại'}`, target => printableConversation(container, messages, title, target));
}
