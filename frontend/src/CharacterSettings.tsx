import type { CharacterMotion } from "./characterView";

const OPTIONS: { value: CharacterMotion; label: string; hint: string }[] = [
  { value: "system", label: "Theo máy", hint: "Đứng yên khi thiết bị bật giảm chuyển động" },
  { value: "always", label: "Luôn cử động", hint: "Kể cả khi thiết bị bật giảm chuyển động" },
];

/** Lựa chọn cử động của nhân vật Companion, nằm trong mục Giao diện của Cài đặt. */
export default function CharacterSettings({ value, onChange, onOpenCharacters, selectedName }: {
  value: CharacterMotion;
  onChange: (value: CharacterMotion) => void;
  onOpenCharacters?: () => void;
  selectedName?: string;
}) {
  const reduced = typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;
  return (
    <div className="settings-subsection">
      <div className="character-settings-select"><div><h4>Nhân vật Companion</h4><p className="settings-hint">{selectedName}</p></div><button className="settings-button" onClick={onOpenCharacters}>Chọn nhân vật</button></div>
      <h4 id="character-motion-title">Nhân vật cử động</h4>
      <p className="settings-hint">
        Nhân vật trong Companion lắc lư, thở, chớp mắt và nhìn theo con trỏ.
        {reduced ? " Thiết bị này đang bật giảm chuyển động." : ""}
      </p>
      <div className="theme-options pair-options" role="radiogroup" aria-labelledby="character-motion-title">
        {OPTIONS.map((item) => (
          <label key={item.value} className={value === item.value ? "theme-option selected" : "theme-option"}>
            <input
              type="radio"
              name="character-motion"
              value={item.value}
              checked={value === item.value}
              onChange={() => onChange(item.value)}
            />
            <strong>{item.label}</strong>
            <em>{item.hint}</em>
          </label>
        ))}
      </div>
    </div>
  );
}
