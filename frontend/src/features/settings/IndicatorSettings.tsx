import WorkIndicator from '../chat/indicator/WorkIndicator';
import {
  INDICATORS, INDICATOR_SIZES, setIndicator, setIndicatorSize, useIndicatorSettings,
  type IndicatorChoice, type IndicatorSize,
} from '../chat/indicator/indicatorSettings';
import { Dropdown } from '../../shared/ui/Dropdown';
import { Segmented, SettingsRow } from './settingsUi';

/**
 * Hai hàng của Cài đặt → Giao diện (27/11/2026): chọn hình động ở dòng "Đang làm" và cỡ của nó. Bên cạnh ô chọn có một
 * hình chạy thử đúng lựa chọn và cỡ đang chọn, để thấy ngay mà không phải gửi tin.
 */
export default function IndicatorSettings() {
  const { indicator, size } = useIndicatorSettings();
  return <>
    <SettingsRow label="Chỉ báo đang làm" htmlFor="settings-indicator" labelId="settings-indicator-label"
      desc="Hình động ở dòng Đang làm khi Peto còn đang trả lời. Tetris đổi kiểu theo việc Peto đang làm.">
      <div className="settings-choice settings-indicator">
        <span className="settings-indicator-preview" data-testid="indicator-preview">
          <WorkIndicator mode="autoplay" />
        </span>
        <Dropdown id="settings-indicator" value={indicator} options={INDICATORS}
          onChange={value => setIndicator(value as IndicatorChoice)} />
      </div>
    </SettingsRow>
    <SettingsRow label="Kích thước chỉ báo" desc="Vừa là cỡ của dòng chữ. Rất lớn làm dòng Đang làm cao hơn.">
      <Segmented label="Kích thước chỉ báo" value={`${size}` as `${IndicatorSize}`} options={INDICATOR_SIZES}
        onChange={value => setIndicatorSize(Number(value) as IndicatorSize)} />
    </SettingsRow>
  </>;
}
