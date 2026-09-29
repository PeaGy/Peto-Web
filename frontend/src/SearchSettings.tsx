import { useId } from 'react';
import { useCompanionSearch, writeCompanionSearch } from './companionSearch';
import { SettingsGroup, SettingsRow, SettingsSwitch } from './settingsUi';

/** Cài đặt → Tra web (phương án A chủ web chọn ngày 2026-09-28, giống Modules → Web Search của AIRI). */
export default function SearchSettings() {
  const on = useCompanionSearch();
  const id = useId();
  return (
    <SettingsGroup>
      <SettingsRow
        label="Cho Peto tra web trong Companion"
        htmlFor={id}
        desc={on
          ? 'Trong Companion, Peto tự tra web khi cần, như thời tiết hay tin tức. Câu có tra chậm hơn vài giây.'
          : 'Đang tắt: trong Companion, Peto trả lời bằng những gì đã biết, không tra web.'}
      >
        <SettingsSwitch id={id} label="Cho Peto tra web trong Companion" checked={on} onChange={writeCompanionSearch} />
      </SettingsRow>
      <p className="settings-note">Tab Trò chuyện có công tắc riêng ở menu +.</p>
    </SettingsGroup>
  );
}
