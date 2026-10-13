import type { CharacterMotion } from "./characterView";
import { Segmented, SettingsRow, type SegmentOption } from "../../settings/settingsUi";

const OPTIONS: SegmentOption<CharacterMotion>[] = [
  { value: "system", label: "Theo máy", hint: "Đứng yên khi thiết bị bật giảm chuyển động" },
  { value: "always", label: "Luôn cử động", hint: "Kể cả khi thiết bị bật giảm chuyển động" },
];

/**
 * Nhân vật cử động: một hàng trong hộp chọn nhân vật. Trước ngày 13/10/2026 nó nằm ở Cài đặt → Nhân vật; hộp Cài đặt chung
 * nay không còn nhóm Companion, và hộp chọn nhân vật là nơi chỉnh nhân vật (chủ web chốt cùng ngày).
 */
export default function CharacterSettings({ value, onChange }: {
  value: CharacterMotion;
  onChange: (value: CharacterMotion) => void;
}) {
  const reduced = typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;
  return (
    <SettingsRow
      label="Nhân vật cử động"
      desc={"Nhân vật trong Companion lắc lư, thở, chớp mắt và nhìn theo con trỏ. Theo máy thì đứng yên khi thiết bị bật "
        + `giảm chuyển động.${reduced ? " Thiết bị này đang bật." : ""}`}
    >
      <Segmented label="Nhân vật cử động" value={value} options={OPTIONS} onChange={onChange} />
    </SettingsRow>
  );
}
