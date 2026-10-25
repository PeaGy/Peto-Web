import type { Root, RootContent } from 'mdast';
import type { WebSource } from '../../shared/api/api';
import { citationIndex, safeSourceUrl } from './sourceData';
import './citations.css';

// Transform Markdown nodes, not HTML strings: code, link labels, images and user messages stay literal.
const MARKER = /\[(?:web|x|src):[^\]\r\n]{0,128}\]|\ue200cite(?:\ue202[^\ue201\r\n]{1,100})+\ue201/g;
const TAIL = /\[(?:w(?:e(?:b(?::[^\]\r\n]{0,128})?)?)?|x(?::[^\]\r\n]{0,128})?|s(?:r(?:c(?::[^\]\r\n]{0,128})?)?)?)?$|\ue200(?:c(?:i(?:t(?:e(?:\ue202[^\ue201\r\n]*)?)?)?)?)?$/;
const PARTIAL_LINK = /\[\[[0-9]{0,9}(?:\](?:\](?:\([^\)\r\n]*)?)?)?$/;

function citeNode(refs: string[]): RootContent {
  return { type: 'emphasis', children: [], data: { hName: 'cite', hProperties: { 'data-citation-refs': JSON.stringify(refs.slice(0, 128)) } } };
}
function refsOf(node: RootContent | undefined): string[] | undefined {
  if (!node) return;
  const value = node.data?.hProperties?.['data-citation-refs'];
  return node.data?.hName === 'cite' && typeof value === 'string' ? JSON.parse(value) : undefined;
}

export function remarkCitations({ sources, writing }: { sources: WebSource[]; writing: boolean }) {
  const urls = new Set(sources.map(source => source.url));
  return (tree: Root) => {
    function walk(parent: { children: RootContent[] }) {
      const children: RootContent[] = [];
      function append(node: RootContent) {
        const refs = refsOf(node);
        let previous = children[children.length - 1];
        if (refs && previous?.type === 'text' && /^[ \t]{0,16}$/.test(previous.value) && refsOf(children[children.length - 2])) {
          children.pop(); previous = children[children.length - 1];
        }
        const old = previous && refsOf(previous);
        if (refs && old) children[children.length - 1] = citeNode([...new Set([...old, ...refs])]);
        else children.push(node);
      }
      for (const node of parent.children) {
        if (node.type === 'link') {
          const label = node.children.length === 1 && node.children[0].type === 'text' ? node.children[0].value : '';
          if (/^\[[0-9]{1,9}\]$/.test(label) && safeSourceUrl(node.url) && urls.has(node.url)) {
            append(citeNode([`url:${label.slice(1, -1)}:${node.url}`]));
          } else append(node);
          continue;
        }
        if (node.type === 'text') {
          let offset = 0;
          for (const match of node.value.matchAll(MARKER)) {
            if (match.index > offset) append({ type: 'text', value: node.value.slice(offset, match.index) });
            const refs = match[0][0] === '[' ? [match[0].slice(1, -1)] : match[0].slice(6, -1).split('\ue202');
            append(citeNode(refs));
            offset = match.index + match[0].length;
          }
          let tail = node.value.slice(offset);
          // Hide incomplete control syntax while chunks/metadata arrive. A stopped partial reference stays honest.
          const partialLink = writing ? PARTIAL_LINK.exec(tail) : null;
          const pending = partialLink || TAIL.exec(tail);
          if (pending && (writing || pending[0].length > 2)) {
            tail = tail.slice(0, pending.index);
            if (tail) append({ type: 'text', value: tail });
            if (!writing) append(citeNode(['unavailable']));
          } else if (tail) append({ type: 'text', value: tail });
          // GFM can auto-link the URL following an unfinished [[N]](. Hold those sibling nodes too.
          if (partialLink) break;
          continue;
        }
        if ('children' in node && node.type !== 'linkReference') {
          walk(node as { children: RootContent[] });
        }
        append(node);
      }
      parent.children = children;
    }
    walk(tree);
  };
}

export function CitationGroup({ refs, sources, writing }: { refs: string[]; sources: WebSource[]; writing: boolean }) {
  const index = citationIndex(sources);
  const seen = new Set<string>();
  return <span className="citation-group" aria-label="Trích dẫn nguồn">{refs.slice(0, 128).map(ref => {
    const native = /^url:([0-9]{1,9}):(.*)$/.exec(ref);
    const source = native ? sources.find(item => item.url === native[2]) : index.get(ref);
    const key = source?.url ?? ref;
    if (seen.has(key)) return null;
    seen.add(key);
    const label = native?.[1] ?? (/^(?:web|x):([0-9]+)$/.exec(ref)?.[1])
      ?? (source ? String(sources.indexOf(source) + 1) : '?');
    if (!source) {
      const description = writing ? 'Đang nhận thông tin nguồn' : 'Chưa xác định được nguồn trích dẫn';
      return <span key={key} className="citation-badge citation-unavailable" tabIndex={0}
        aria-label={description} data-tip={description}>{writing ? '…' : '?'}</span>;
    }
    return <a key={key} className="citation-badge" href={source.url} target="_blank" rel="noopener noreferrer"
      aria-label={`Nguồn ${label}: ${source.title}`} data-tip={`${source.title}\n${source.url}`}>{label}</a>;
  })}</span>;
}
