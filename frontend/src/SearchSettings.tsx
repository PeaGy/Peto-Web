import { useCompanionSearch, writeCompanionSearch } from './companionSearch';

/** Cài đặt → Tra web (phương án A chủ web chọn ngày 2026-09-28, giống Modules → Web Search của AIRI). */
export default function SearchSettings() {
  const on = useCompanionSearch();
  return (
    <section className="settings-section" aria-labelledby="search-settings-title">
      <div className="voice-head">
        <h3 id="search-settings-title">Tra web</h3>
        <label className="voice-switch">
          <span aria-hidden="true">{on ? 'Đang bật' : 'Đang tắt'}</span>
          <input
            type="checkbox"
            role="switch"
            aria-label="Cho Peto tra web trong Companion"
            checked={on}
            onChange={(event) => writeCompanionSearch(event.target.checked)}
          />
        </label>
      </div>
      <p className="settings-hint">
        {on
          ? 'Trong Companion, Peto tự tra web khi cần, như thời tiết hay tin tức. Câu có tra chậm hơn vài giây.'
          : 'Đang tắt: trong Companion, Peto trả lời bằng những gì đã biết, không tra web.'}
        {' '}Tab Trò chuyện có công tắc riêng ở menu +.
      </p>
    </section>
  );
}
