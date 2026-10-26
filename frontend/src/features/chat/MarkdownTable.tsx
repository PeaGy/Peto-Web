import { useRef, useState, type ReactNode } from 'react';
import { CheckIcon, CopyIcon, DownloadIcon } from './messageUtilityIcons';
import { copyTable, saveTable } from './tableExport';
import { useMessageCopy } from './useMessageCopy';
import './messageUtilities.css';

export default function MarkdownTable({ children, pending = false }: { children: ReactNode; pending?: boolean }) {
  const table = useRef<HTMLTableElement>(null);
  const { state, label, run } = useMessageCopy();
  const [saveFailed, setSaveFailed] = useState(false);
  return <div className="markdown-table">
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Bảng nội dung"><table ref={table}>{children}</table></div>
    <div className="table-actions" data-export-exclude>
      <button type="button" className={`message-utility-button${state === 'done' ? ' done' : ''}`} aria-label={`${label} bảng`}
        data-tip disabled={pending} onClick={() => void run(async () => { if (table.current) await copyTable(table.current); })}>
        {state === 'done' ? <CheckIcon /> : <CopyIcon />}
      </button>
      <button type="button" className="message-utility-button" aria-label={saveFailed ? 'Chưa lưu được bảng, thử lại' : 'Lưu bảng CSV'} data-tip disabled={pending}
        onClick={() => { try { if (table.current) saveTable(table.current); setSaveFailed(false); } catch { setSaveFailed(true); } }}><DownloadIcon /></button>
      {(state === 'fail' || saveFailed) && <span className="message-utility-error" role="status">{saveFailed ? 'Chưa lưu được bảng. Bạn thử lại nhé.' : 'Chưa chép được bảng. Bạn thử lại nhé.'}</span>}
    </div>
  </div>;
}
