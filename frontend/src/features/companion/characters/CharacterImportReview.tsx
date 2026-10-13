import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Live2DImportReport } from './characterImport';
import { CONTROL_LABELS } from './live2dControls';

const size = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(2)} MB`;
export default function CharacterImportReview({ report, busy, error, onCancel, onConfirm }: {
  report: Live2DImportReport; busy: boolean; error: string; onCancel: () => void; onConfirm: (useControls: boolean) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [useControls, setUseControls] = useState(true);
  useEffect(() => { dialog.current?.showModal(); return () => dialog.current?.close(); }, []);
  const errors = report.issues.filter(issue => issue.severity === 'error').length;
  const warnings = report.issues.length - errors;
  return createPortal(<dialog ref={dialog} className="import-review" aria-labelledby="import-review-title"
    onCancel={event => { event.preventDefault(); event.stopPropagation(); if (!busy) onCancel(); }}>
    <header className="character-picker-head"><div><h2 id="import-review-title">Trước khi nhập</h2>
      <p>Kiểm tra tài nguyên và những điểm cần lưu ý của model.</p></div>
      <button type="button" className="dialog-close" aria-label="Đóng kiểm tra model" disabled={busy} onClick={onCancel}>×</button></header>
    <div className="import-review-body">
      <div className="import-review-model"><span>Live2D · .model3.json</span><strong>{report.entry || report.name}</strong>
        <small>{report.files} tệp · {size(report.bytes)} sau giải nén</small></div>
      <h3>Tài nguyên</h3>
      <div className="import-review-stats">
        {([[report.motions, 'Chuyển động'], [report.expressions, 'Biểu cảm']] as const).map(([resource, label]) =>
          <div key={label}><span>{label}</span><strong>{new Set([...resource.found, ...resource.referenced]).size}</strong>
            <small>{resource.referenced.length} khai báo · {resource.found.length} tìm thấy</small></div>)}
        <div><span>Tham số</span><strong>{report.parameters ?? '—'}</strong><small>{report.parameters === null ? 'Chưa có dữ liệu hiển thị' : 'Theo tệp DisplayInfo (.cdi3.json)'}</small></div>
        <div><span>Texture</span><strong>{report.textures.length}</strong><small>Được khai báo</small></div>
      </div>
      <p className="import-review-hint">Vật lý: {report.physics ? 'có tệp được khai báo' : 'chưa có tệp được khai báo'}. Tham số trong DisplayInfo có thể không bao gồm toàn bộ tham số của model.</p>
      {report.controls && <section className="import-review-controls" aria-labelledby="import-controls-title">
        <h3 id="import-controls-title">Điều khiển nhân vật</h3>
        {report.controls.bindings.length ? <>
          <label className="character-effect-option"><span><strong>Dùng cấu hình điều khiển của model</strong>
            <small>Áp dụng cho đầu, hướng mắt và mở miệng khi có ánh xạ riêng.</small></span>
            <input type="checkbox" role="switch" checked={useControls} disabled={busy} onChange={event => setUseControls(event.target.checked)} /></label>
          <p className="import-review-hint">{useControls ? 'Đã tìm thấy ánh xạ từ VTube Studio. Các chức năng còn lại dùng mặc định.' : 'Nhân vật sẽ dùng điều khiển mặc định của Peto.'}</p>
          <details><summary>Xem thông số điều khiển</summary><dl>{report.controls.bindings.map(binding =>
            <div key={binding.role}><dt>{CONTROL_LABELS[binding.role]}</dt><dd><code>{binding.id}</code>{!binding.verified && <small>Kiểm tra lại khi tải nhân vật</small>}</dd></div>)}</dl></details>
        </> : <p className="import-review-hint">Chưa có ánh xạ riêng phù hợp. Nhân vật dùng điều khiển mặc định của Peto.</p>}
      </section>}
      <div className="import-review-issue-head"><h3>Kết quả kiểm tra</h3><span>{errors} lỗi · {warnings} cảnh báo</span></div>
      {report.issues.length ? <ul className="import-review-issues">{report.issues.map((issue, index) => <li key={index} data-severity={issue.severity}>
        <span aria-hidden="true">{issue.severity === 'error' ? '⨯' : '!'}</span><div><strong>{issue.severity === 'error' ? 'Lỗi' : 'Lưu ý'}</strong><p>{issue.message}</p>
          {issue.paths?.length && <details><summary>Xem các tệp</summary><ul>{issue.paths.map(path => <li key={path}>{path}</li>)}</ul></details>}</div>
      </li>)}</ul> : <p className="import-review-ok">Không phát hiện lỗi cấu hình hoặc thiếu tệp được khai báo.</p>}
      <p className="import-review-hint">Đây là kiểm tra gói tệp; khả năng hiển thị thực tế còn phụ thuộc model và thiết bị. Chỉ lưu trên trình duyệt này sau khi bạn xác nhận.</p>
      {error && <p role="alert" className="character-library-error">{error}</p>}
    </div>
    <footer className="import-review-actions"><button type="button" className="settings-button" disabled={busy} onClick={onCancel}>Hủy</button>
      <button type="button" className="settings-button import-confirm" disabled={busy || errors > 0 || !report.prepared} onClick={() => onConfirm(useControls)}>
        {busy ? 'Đang nhập…' : errors ? 'Cần sửa lỗi trước khi nhập' : warnings ? 'Vẫn nhập model' : 'Nhập model'}</button></footer>
  </dialog>, document.body);
}
