import type { WebSource } from '../../shared/api/api';
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

export function responseMarkdown(text: string, sources?: WebSource[]): string {
  const actualSources = exportSources(sources);
  if (!actualSources.length) return text;
  const lines = actualSources.map(source => {
    const title = (source.title || new URL(source.url).hostname).replace(/[\r\n\x00-\x1f]/g, ' ').replace(/[\\[\]]/g, '\\$&');
    const url = source.url.replace(/[<>]/g, character => character === '<' ? '%3C' : '%3E');
    const ids = source.citation_ids?.filter(id => /^(?:web:[0-9]+|x:[0-9]+|src:[a-f0-9]+|turn[0-9]+(?:search|view|fetch)[0-9]+)$/.test(id));
    return `- [${title}](<${url}>)${ids?.length ? ` (${ids.join(', ')})` : ''}`;
  });
  return `${text}\n\n---\n\n## Nguồn\n\n${lines.join('\n')}\n`;
}

export function saveResponseMarkdown(text: string, sources?: WebSource[], messageId?: number): void {
  downloadBlob(new Blob([responseMarkdown(text, sources)], { type: 'text/markdown;charset=utf-8' }),
    messageId === undefined ? 'peto-response.md' : `peto-response-${messageId}.md`);
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
    if (DROP_TAGS.has(tag) || source.matches('[data-export-exclude],.katex-html,.table-actions,.code-actions,.code-collapsed-summary')) return;
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
  @page { margin: 16mm; } @media print { body { margin: 0; } }
`;

/** A dedicated local print document keeps the application, composer and sidebars out of the PDF. */
export async function printResponse(root: HTMLElement, sources?: WebSource[]): Promise<void> {
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
    target.title = 'Peto — Câu trả lời';
    const main = printableResponse(root, target);
    const actualSources = exportSources(sources);
    if (actualSources.length) {
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
      main.append(footer);
    }
    target.body.replaceChildren(main);
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
