import type { CharacterMotion } from "./characterView";
import { useReducedMotion } from "../../../shared/motion";
import { Segmented, SettingsRow, type SegmentOption } from "../../settings/settingsUi";

const OPTIONS: SegmentOption<CharacterMotion>[] = [
  { value: "system", label: "Theo cài đặt chung", hint: "Đứng yên khi Cài đặt → Giao diện → Chuyển động là Giảm" },
  { value: "always", label: "Luôn cử động", hint: "Kể cả khi Chuyển động là Giảm" },
];

/**
 * Nhân vật cử động: hàng đầu của khối Chuyển động ở Cài đặt Companion → Nhân vật (14/10/2026). Trước 13/10/2026 nó nằm ở
 * Cài đặt chung → Nhân vật, rồi một ngày trong hộp chọn nhân vật. Áp dụng cho mọi nhân vật.
 */
export default function CharacterSettings({ value, onChange }: {
  value: CharacterMotion;
  onChange: (value: CharacterMotion) => void;
}) {
  const reduced = useReducedMotion();
  return (
    <SettingsRow
      label="Nhân vật cử động"
      desc={"Nhân vật trong Companion lắc lư, thở, chớp mắt và nhìn theo con trỏ. Theo cài đặt chung thì đứng yên khi "
        + `Cài đặt → Giao diện → Chuyển động là Giảm.${reduced ? " Hiện đang giảm chuyển động." : ""}`}
    >
      <Segmented label="Nhân vật cử động" value={value} options={OPTIONS} onChange={onChange} />
    </SettingsRow>
  );
}
