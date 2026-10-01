import type { CharacterMotion } from "./characterView";
import { Segmented, SettingsRow, type SegmentOption } from "../../settings/settingsUi";

const OPTIONS: SegmentOption<CharacterMotion>[] = [
  { value: "system", label: "Theo máy", hint: "Đứng yên khi thiết bị bật giảm chuyển động" },
  { value: "always", label: "Luôn cử động", hint: "Kể cả khi thiết bị bật giảm chuyển động" },
];

/** Nhân vật Companion và cách nó cử động: hai hàng trong mục Giao diện của Cài đặt. */
export default function CharacterSettings({ value, onChange, onOpenCharacters, selectedName }: {
  value: CharacterMotion;
  onChange: (value: CharacterMotion) => void;
  onOpenCharacters?: () => void;
  selectedName?: string;
}) {
  const reduced = typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;
  return (
    <>
      <SettingsRow label="Nhân vật Companion" desc={selectedName ? `Đang dùng: ${selectedName}` : undefined}>
        <button type="button" className="settings-button" onClick={onOpenCharacters}>Chọn nhân vật</button>
      </SettingsRow>
      <SettingsRow
        label="Nhân vật cử động"
        desc={"Nhân vật trong Companion lắc lư, thở, chớp mắt và nhìn theo con trỏ. Theo máy thì đứng yên khi thiết bị bật "
          + `giảm chuyển động.${reduced ? " Thiết bị này đang bật." : ""}`}
      >
        <Segmented label="Nhân vật cử động" value={value} options={OPTIONS} onChange={onChange} />
      </SettingsRow>
    </>
  );
}
