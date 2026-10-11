import { useEffect, useRef, useState } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import { UnauthorizedError } from '../../shared/api/api';
import { getWordPreview, type WordBlock, type WordPart, type WordPreview } from './documentApi';
import { parseWordChange, VERBS } from './wordChanges';
import './sheetView.css';
import './wordView.css';

/** Khối có phần Peto chèn hay xóa: 'ins', 'del', cả hai ('mixed') hoặc không. */
function blockState(block: WordBlock): 'ins' | 'del' | 'mixed' | null {
  const states = new Set<string>();
  if (block.state) states.add(block.state);
  for (const part of block.parts ?? []) if (part.state) states.add(part.state);
  for (const row of block.rows ?? []) {
    if (row.state) states.add(row.state);
    for (const cell of row.cells) for (const part of cell.parts) if (part.state) states.add(part.state);
  }
  if (!states.size) return null;
  return states.size > 1 ? 'mixed' : (states.values().next().value as 'ins' | 'del');
}

function TeX({ tex, display }: { tex: string; display?: boolean }) {
  // KaTeX chỉ dựng HTML từ LaTeX máy chủ đọc ra tệp, không chạy lệnh tùy ý (trust mặc định là false).
  const html = katex.renderToString(tex, { throwOnError: false, displayMode: !!display, strict: 'ignore' });
  return <span className={display ? 'wv-math display' : 'wv-math'} dangerouslySetInnerHTML={{ __html: html }} />;
}

function Parts({ parts }: { parts: WordPart[] }) {
  return <>{parts.map((part, index) => {
    const cls = [part.state === 'ins' ? 'wv-ins' : part.state === 'del' ? 'wv-del' : '', part.b ? 'wv-b' : '', part.i ? 'wv-i' : '']
      .filter(Boolean).join(' ') || undefined;
    if (part.image) return <span key={index} className={`wv-image${cls ? ` ${cls}` : ''}`}>[Hình]</span>;
    if (part.math !== undefined) return <span key={index} className={cls}><TeX tex={part.math} display={part.display} /></span>;
    return <span key={index} className={cls}>{part.text}</span>;
  })}</>;
}

function Block({ block }: { block: WordBlock }) {
  if (block.type === 'table') return <div className="wv-table-wrap"><table className="wv-table"><tbody>
    {(block.rows ?? []).map((row, r) => <tr key={r} className={row.state === 'del' ? 'wv-row-del' : undefined}>
      {row.cells.map((cell, c) => <td key={c} colSpan={cell.span}><Parts parts={cell.parts} /></td>)}
    </tr>)}
  </tbody></table></div>;
  return <p className={`wv-p${block.align ? ` wv-${block.align}` : ''}${block.heading ? ' wv-heading' : ''}`}>
    {block.label && <span className="wv-label">{block.label} </span>}<Parts parts={block.parts ?? []} />
  </p>;
}

/** Xem tệp Word người dùng Peto đã sửa bằng Theo dõi thay đổi (mẫu "Nhật ký" chủ web chọn ngày 12/10/2026, như bản Excel):
 * danh sách thay đổi ở trên, bấm một dòng thì tới đúng chỗ; dưới là nội dung tệp theo màu của app, phần chèn tô nền
 * xanh, phần xóa gạch đỏ. Dựng lại từ nội dung tệp, không phải bố cục Word. */
export default function WordView({ id, version, onUnauthorized }: { id: string; version: number; onUnauthorized?: () => void }) {
  const [data, setData] = useState<WordPreview | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [listOpen, setListOpen] = useState(true);
  const [active, setActive] = useState<number | null>(null);
  const body = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError(''); setActive(null);
    getWordPreview(id, version, controller.signal).then(value => { if (!controller.signal.aborted) setData(value); }).catch(reason => {
      if (controller.signal.aborted) return;
      if (reason instanceof UnauthorizedError) onUnauthorized?.();
      else setError(reason instanceof Error ? reason.message : 'Chưa mở được tệp Word.');
    });
    return () => controller.abort();
  }, [id, version, retry, onUnauthorized]);

  if (error) return <div className="document-panel-empty" role="alert"><p>{error}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Thử lại</button></div>;
  if (!data) return <div className="document-panel-empty" role="status">Đang mở tệp Word…</div>;

  // Khối nào thuộc thay đổi nào: theo mã dấu sửa (w:id) mỗi thay đổi đã tạo, nên đúng cả khi tệp còn dấu của lần sửa trước.
  const targets = data.changes.map(change => {
    const [low, high] = change.revs.length ? change.revs : [1, 0];
    return data.blocks.flatMap((block, index) => (block.revs ?? []).some(rev => rev >= low && rev <= high) ? [index] : []);
  });
  const highlighted = new Set(active === null ? [] : targets[active]);
  const pick = (index: number) => {
    setActive(index);
    const first = targets[index][0];
    if (first !== undefined) body.current?.querySelector(`[data-block="${first}"]`)?.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
  };

  return <div className="sheet-view wv-view">
    {data.changes.length > 0 && <section className={`wb-log-panel${listOpen ? ' open' : ''}`} aria-label="Peto đã sửa">
      <button type="button" className="wb-log-head" aria-expanded={listOpen} onClick={() => setListOpen(value => !value)}>
        <span>Peto đã sửa</span><small>{data.changes.length} thay đổi</small>
        <svg className="wb-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      {listOpen && <ol className="wb-log">
        {data.changes.map((item, index) => {
          const change = parseWordChange(item.text);
          return <li key={index}>
            <button type="button" aria-pressed={active === index} disabled={!targets[index].length} onClick={() => pick(index)}>
              <span className="wb-log-where">{change.where || '—'}</span>
              <span><span className={`wv-kind ${change.kind}`}>{VERBS[change.kind]}</span> {change.text}</span>
            </button>
          </li>;
        })}
      </ol>}
    </section>}
    <div className="wv-doc" ref={body} tabIndex={0} aria-label={`Nội dung ${data.title}`}>
      {data.blocks.map((block, index) => {
        const state = blockState(block);
        return <div key={index} data-block={index} className={`wv-block${state ? ` wv-${state}-block` : ''}${highlighted.has(index) ? ' wv-active' : ''}`}>
          <Block block={block} />
        </div>;
      })}
      {data.truncated && <p className="wv-truncated">Tệp dài: bản xem dừng ở đây. Tải tệp để xem hết.</p>}
    </div>
  </div>;
}
