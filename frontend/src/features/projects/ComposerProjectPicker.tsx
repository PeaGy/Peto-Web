import { useState } from 'react';
import { ComposerSheet } from '../chat/ComposerSheet';
import type { useProjects } from './useProjects';

export default function ComposerProjectPicker({ state, activeId, disabled, onSelect, onCreate }: {
  state: ReturnType<typeof useProjects>; activeId: string | null; disabled: boolean;
  onSelect: (id: string | null) => void; onCreate: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const name = state.projects.find(item => item.id === activeId)?.name ?? 'Dự án';
  const matches = state.projects.filter(item => item.name.toLocaleLowerCase('vi').includes(query.trim().toLocaleLowerCase('vi')));
  function select(id: string | null) {
    setOpen(false);
    if (id !== activeId) onSelect(id);
  }
  return <>
    <button type="button" className="mobile-project-trigger" aria-label={`Chọn dự án: ${name}`}
      disabled={disabled} aria-haspopup="dialog" aria-expanded={open && !disabled}
      onClick={() => { setQuery(''); setOpen(true); }}>
      <span>{name}</span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="m5 9 7 7 7-7" stroke="currentColor" strokeWidth="2" /></svg>
    </button>
    {open && !disabled && <ComposerSheet label="Chọn dự án" onClose={() => setOpen(false)}>
      <div className="sheet-projects">
        <input type="search" aria-label="Tìm dự án" placeholder="Tìm dự án" value={query} onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') e.preventDefault(); }} />
        <div className="sheet-project-list">
          {state.loading && <p role="status">Đang tải dự án…</p>}
          {state.error && <p role="alert">{state.error} <button type="button" onClick={() => void state.refresh()}>Thử lại</button></p>}
          {activeId && <button type="button" className="sheet-option" onClick={() => select(null)}>Ngoài dự án</button>}
          {matches.map(item => <button type="button" className="sheet-option" key={item.id} aria-pressed={activeId === item.id}
            onClick={() => select(item.id)}>{item.name}</button>)}
          {!state.loading && !state.error && !matches.length && <p>{query.trim() ? 'Không tìm thấy dự án.' : 'Chưa có dự án.'}</p>}
        </div>
        <button type="button" className="sheet-option" onClick={() => { setOpen(false); onCreate(); }}>＋ Tạo dự án mới</button>
      </div>
    </ComposerSheet>}
  </>;
}
