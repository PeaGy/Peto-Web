import { useState } from 'react';
import { clearCompanionTimings, elapsed, useCompanionTimings, type TimingStatus } from './companionTiming';
import { keyProvider } from './voiceProviders';
import { hearingProvider } from './hearingProviders';

const states: Record<TimingStatus, string> = {
  running: 'Đang đo', complete: 'Đã phát tiếng', 'text-only': 'Chỉ có chữ', stopped: 'Đã dừng', error: 'Có lỗi',
};
const duration = (value: number | null) => value === null ? 'Chưa đo được' : `${(value / 1000).toFixed(2)} giây`;

/** Kết quả lượt thật; mở mục này không tạo thêm cuộc gọi AI, tạo giọng hay bật micro. */
export default function CompanionTimingPanel() {
  const records = useCompanionTimings();
  const [picked, setPicked] = useState<number | null>(null);
  const record = records.find(item => item.id === picked) ?? records[0];
  const rows: [string, number | null][] = record ? [
    ['Ngừng nói → chốt lời', elapsed(record.hearing?.endedAt, record.hearing?.finalizedAt)],
    ['Chốt lời → gửi', elapsed(record.hearing?.finalizedAt, record.sentAt)],
    ['Gửi → chữ đầu tiên', elapsed(record.sentAt, record.marks.firstText)],
    ['Chữ đầu → sẵn sàng đọc', elapsed(record.marks.firstText, record.marks.textReady)],
    ['Tạo tiếng → bắt đầu phát', elapsed(record.marks.synthesis, record.marks.playing)],
    [record.input === 'voice' ? 'Ngừng nói → bắt đầu phát' : 'Gửi → bắt đầu phát',
      elapsed(record.input === 'voice' ? record.hearing?.endedAt : record.sentAt, record.marks.playing)],
  ] : [];
  return <details className="companion-timing">
    <summary>Kiểm tra tốc độ Companion</summary>
    <p>Đo các lượt trò chuyện trên trang này. Không lưu nội dung hoặc gửi thống kê lên máy chủ.</p>
    {!record ? <p>Chưa có lượt đo. Gửi một lời nhắn trong Companion rồi quay lại đây.</p> : <>
      <div className="companion-timing-controls">
        <label>Lượt đo <select value={record.id} onChange={event => setPicked(Number(event.target.value))}>
          {records.map((item, index) => <option key={item.id} value={item.id}>
            {index === 0 ? 'Gần nhất' : `Trước ${index} lượt`} · {states[item.status]}
          </option>)}
        </select></label>
        <button type="button" onClick={clearCompanionTimings}>Xóa kết quả đo</button>
      </div>
      <p>{record.input === 'voice' ? 'Nhắn bằng micro' : 'Nhắn bằng chữ'} · {record.search ? 'Tra web bật' : 'Tra web tắt'}</p>
      <p>Giọng chọn khi gửi: {record.voiceSource === 'official' ? 'Giọng Peto' : record.voiceSource === 'home'
        ? 'Local Voice của Peto' : keyProvider(record.voiceSource)?.name ?? 'Nguồn khác'}.
        {record.hearingSource && <> Nguồn nghe: {record.hearingSource === 'browser'
          ? 'Có sẵn trong trình duyệt' : hearingProvider(record.hearingSource)?.name ?? 'Nguồn khác'}.</>}
      </p>
      <dl>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{duration(value)}</dd></div>)}</dl>
      <p>Chốt lời → gửi gồm thời gian bạn chờ bấm Gửi hoặc thời gian Tự gửi. Chữ đầu → sẵn sàng đọc gồm chờ câu hoàn chỉnh; bật Tra web sẽ chờ câu trả lời chốt. Tạo tiếng → bắt đầu phát gồm mạng và chuẩn bị âm thanh.</p>
      {record.input === 'voice' && <p>Tính từ câu chốt cuối cùng của lượt. Mốc ngừng nói dựa trên thông báo của bộ nghe, có thể trễ hơn lúc bạn ngừng nói thật. Mốc thiếu hoặc thứ tự không xác định sẽ hiện Chưa đo được.</p>}
    </>}
  </details>;
}
