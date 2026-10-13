import { useId } from 'react';
import { Segmented, type SegmentOption } from '../../settings/settingsUi';
import { Dropdown, type DropdownOption } from '../../../shared/ui/Dropdown';
import type { MagicProfile, MagicSettings, MotionDriver } from './magic/magicSettings';

const DRIVERS: SegmentOption<MotionDriver>[] = [
  { value: 'universal', label: 'Hiện tại', hint: 'Chuyển động của model, đảo mắt và nhìn theo con trỏ' },
  { value: 'magic', label: 'MAGIC', hint: 'Tự sinh chuyển động nhún, lắc liên tục' },
];
const PROFILES: DropdownOption[] = [
  { value: 'excited', label: 'Hào hứng', hint: 'Nhún và nghiêng đầu liên tục, kiểu Neuro-sama. Bộ mặc định của AIRI.' },
  { value: 'calm', label: 'Bình thản', hint: 'Lắc lư nhẹ và chậm, như đang ngồi chờ.' },
  { value: 'speech', label: 'Theo lúc nói', hint: 'Chờ thì bình thản, lúc Peto nói thì hào hứng. AIRI không có kiểu này.' },
];

/**
 * Cách chuyển động của nhân vật Live2D, như "Motion driver: Universal / MAGIC" trong Cài đặt → Models → Animation của AIRI.
 * MAGIC (Markovian Animation Generator with Illusory Conditioning) học kiểu chuyển động từ bản ghi của AIRI rồi tự sinh
 * chuyển động mới không lặp lại; chạy hoàn toàn trong trình duyệt.
 */
export default function MotionDriverPicker({ value, onChange }: { value: MagicSettings; onChange: (value: MagicSettings) => void }) {
  const field = useId();
  const magic = value.driver === 'magic';
  return <div className="motion-driver">
    <div className="motion-driver-row">
      <span><strong>Cách chuyển động</strong>
        <small>{magic ? 'MAGIC tự sinh chuyển động không lặp lại, theo Project AIRI. Tắt chuyển động khi chờ, đảo mắt và nhìn theo con trỏ.'
          : 'Chuyển động khi chờ của model, đảo mắt và nhìn theo con trỏ.'}</small></span>
      <Segmented label="Cách chuyển động" value={value.driver} options={DRIVERS} onChange={driver => onChange({ ...value, driver })} />
    </div>
    {magic && <>
      <label className="motion-driver-label" htmlFor={field} id={`${field}-label`}>Bộ chuyển động MAGIC</label>
      <Dropdown id={field} value={value.profile} options={PROFILES} onChange={profile => onChange({ ...value, profile: profile as MagicProfile })} />
      <div className="character-effect-options">
        <label className="character-effect-option">
          <span><strong>Mắt nhìn thẳng</strong><small>Đầu lắc nhưng mắt vẫn nhìn về phía bạn.</small></span>
          <input type="checkbox" role="switch" aria-label="Mắt nhìn thẳng" checked={value.viewTarget}
            onChange={event => onChange({ ...value, viewTarget: event.target.checked })} />
        </label>
        <label className="character-effect-option">
          <span><strong>MAGIC điều khiển dáng miệng</strong><small>Tắt thì giữ dáng miệng sẵn có của model. Mặt cảm xúc vẫn đè lên.</small></span>
          <input type="checkbox" role="switch" aria-label="MAGIC điều khiển dáng miệng" checked={value.mouthForm}
            onChange={event => onChange({ ...value, mouthForm: event.target.checked })} />
        </label>
      </div>
    </>}
  </div>;
}
