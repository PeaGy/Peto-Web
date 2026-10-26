import { downloadBlob } from './responseExport';

function cellText(cell: HTMLTableCellElement): string {
  const clone = cell.cloneNode(true) as HTMLElement;
  clone.querySelectorAll('button,script,style,.citation-group,.citation-badge,[data-export-exclude]').forEach(node => node.remove());
  // textContent misses <br>. Use DOM text nodes, never HTML or toolbar labels.
  function read(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? '';
    if (node instanceof Element && node.tagName === 'BR') return '\n';
    const value = [...node.childNodes].map(read).join('');
    return node instanceof Element && /^(?:P|DIV|LI)$/.test(node.tagName) ? `${value}\n` : value;
  }
  // The Markdown renderer already turns assistant citation controls into .citation-group.
  // Remaining marker-looking text can be literal code, a link label or a user's own table.
  return read(clone).replace(/\u00a0/g, ' ').trim();
}

/** Read a clone of each cell; exports must not modify citations or the displayed table. */
export function tableRows(table: HTMLTableElement): string[][] {
  return [...table.rows].map(row => [...row.cells].map(cellText));
}

/** Quoting CSV alone does not stop spreadsheet formulas, including formulas behind leading whitespace. */
export function spreadsheetCell(value: string): string {
  return /^[\s\uFEFF]*[=+\-@]/.test(value) || /^[\t\r]/.test(value) ? `'${value}` : value;
}

export function rowsToCsv(rows: string[][]): string {
  return rows.map(row => row.map(value => {
    const safe = spreadsheetCell(value);
    return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
  }).join(',')).join('\r\n');
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]!);
}

export function rowsToHtml(rows: string[][]): string {
  return `<table><tbody>${rows.map((row, index) => `<tr>${row.map(value => {
    const tag = index === 0 ? 'th' : 'td';
    return `<${tag}>${escapeHtml(spreadsheetCell(value)).replace(/\r?\n/g, '<br>')}</${tag}>`;
  }).join('')}</tr>`).join('')}</tbody></table>`;
}

export async function copyTable(table: HTMLTableElement): Promise<void> {
  const rows = tableRows(table);
  const csv = rowsToCsv(rows);
  if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
    try {
      await navigator.clipboard.write([new ClipboardItem({
        'text/plain': new Blob([csv], { type: 'text/plain' }),
        'text/html': new Blob([rowsToHtml(rows)], { type: 'text/html' }),
      })]);
      return;
    } catch { /* Some browsers accept plaintext but reject text/html. */ }
  }
  await navigator.clipboard.writeText(csv);
}

export function saveTable(table: HTMLTableElement): void {
  // UTF-8 BOM keeps Vietnamese readable when the CSV is opened directly in Excel.
  downloadBlob(new Blob(['\uFEFF', rowsToCsv(tableRows(table))], { type: 'text/csv;charset=utf-8' }), 'peto-table.csv');
}
