import type { AdminChatMetrics } from './adminApi';
import { num, secs } from './format';

const efforts: Record<string, string> = { low: 'Thấp', medium: 'Trung bình', high: 'Cao', unknown: 'Chưa ghi nhận' };

/** Số đo vận hành có phạm vi và cỡ mẫu; không phải điểm thông minh hoặc độ đúng của câu trả lời. */
export function ChatMetrics({ data }: { data?: AdminChatMetrics }) {
  if (!data) return null;
  return <details className="adm-card adm-chat-metrics">
    <summary>Ngữ cảnh và phục hồi Chat</summary>
    <dl className="adm-chat-counts">
      <div><dt>Tóm tắt ngữ cảnh</dt><dd>{num(data.summary.complete)} / {num(data.summary.attempts)} lần</dd>
        <small>{num(data.summary.errors)} lỗi · {num(data.summary.source_changed)} nguồn đổi · {num(data.summary.cancelled)} bị ngắt</small>
        <small>{num(data.summary.sdk_calls)} request AI, {num(data.summary.usage_calls)} có usage · p50/p95 {secs(data.summary.p50_ms)} / {secs(data.summary.p95_ms)} (n={num(data.summary.latency_samples)})</small></div>
      <div><dt>Ngữ cảnh vượt hạn mức</dt><dd>{num(data.context_overflows)} lượt</dd></div>
      <div><dt>Lỗi công cụ</dt><dd>{num(data.tools.errors)} / {num(data.tools.results)} kết quả</dd><small>{num(data.tools.web_errors)} lượt tìm hoặc mở trang lỗi</small>
        <small>{num(data.tools.code_runs ?? 0)} lần Peto chạy mã · {num(data.tools.code_errors ?? 0)} lần lỗi</small></div>
      <div><dt>Đọc lịch sử để phục hồi</dt><dd>{num(data.recovery.checks)} lần</dd>
        <small>{num(data.recovery.complete)} đầy đủ · {num(data.recovery.partial)} một phần · {num(data.recovery.pending)} đang chạy · {num(data.recovery.missing)} chưa có reply</small></div>
    </dl>
    <div className="adm-table-wrap" tabIndex={0} role="region" aria-label="Số đo Chat theo model và mức suy nghĩ">
      <table className="adm-table"><thead><tr><th scope="col">Model / mức suy nghĩ</th><th scope="col">Hoàn tất / lượt</th>
        <th scope="col">Mẫu xong / chữ đầu</th><th scope="col">Xong p50 / p95</th><th scope="col">Chữ đầu p50 / p95</th></tr></thead>
        <tbody>{data.configs.map(row => <tr key={`${row.model}/${row.slug}/${row.effort}`}><th scope="row">{row.label} · {efforts[row.effort] ?? row.effort}<small>{row.slug ?? 'Chưa ghi model API'}</small></th>
          <td>{num(row.complete)} / {num(row.turns)}</td><td>{num(row.total_samples)} / {num(row.first_samples)}</td>
          <td>{secs(row.p50_ms)} / {secs(row.p95_ms)}</td><td>{secs(row.first_p50_ms)} / {secs(row.first_p95_ms)}</td></tr>)}</tbody></table>
      {!data.configs.length && <p className="adm-empty">Chưa có lượt Chat trong khoảng này.</p>}
    </div>
    <p className="adm-empty">Thời gian xong chỉ tính lượt hoàn tất; chữ đầu tính các lượt có số đo. Mẫu nhỏ chưa đủ kết luận về tốc độ.
      {' '}{num(data.legacy_turns)} lượt cũ chưa ghi mức suy nghĩ. Summary/lỗi/phục hồi chỉ gồm sự kiện từ bản cập nhật này; một lượt phục hồi có thể đọc nhiều lần, không tính được lỗi mạng chưa tới máy chủ. Không chấm chất lượng nội dung.</p>
  </details>;
}
