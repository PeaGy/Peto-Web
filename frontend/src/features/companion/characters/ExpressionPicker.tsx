import { useEffect, useId, useState } from 'react';
import {
  BUILTIN_FACE, EMOTIONS, NEUTRAL_LABEL, emotionLabels, faceSource, previewExpression, readExpressions, watchExpressions,
  writeExpressions, type Emotion, type ExpressionChoice, type StageEmotion,
} from './characterExpressions';
import { Dropdown, Field, type DropdownOption } from '../speech/voiceUi';

const AUTO = 'auto';
const CARDS: StageEmotion[] = [...EMOTIONS, 'neutral'];
const label = (emotion: StageEmotion) => emotion === 'neutral' ? NEUTRAL_LABEL : emotionLabels[emotion];

/**
 * Khối Biểu cảm của trang Cài đặt → Nhân vật (phương án B chủ web chọn ngày 2026-09-27): chín thẻ cảm xúc của AIRI, bấm thẻ
 * là nhân vật trên sân khấu bên cạnh làm mặt đó để xem thử; nguồn của thẻ đang chọn hiện bên dưới. Live2D chọn được tệp
 * biểu cảm của model hay mặt dựng sẵn; VRM dùng biểu cảm có sẵn của chuẩn VRM. Trước 14/10/2026 khối này nằm trong hộp
 * che sân khấu nên kèm ảnh chụp mặt; nay sân khấu luôn hiện nên bỏ ảnh đó.
 */
export default function ExpressionPicker({ characterId, choices, format = 'live2d' }: {
  characterId: string;
  choices: ExpressionChoice[];
  format?: 'live2d' | 'vrm';
}) {
  const [preferences, setPreferences] = useState(() => readExpressions(characterId));
  const [selected, setSelected] = useState<StageEmotion | null>(null);
  const sourceId = useId();
  useEffect(() => watchExpressions(characterId, setPreferences), [characterId]);

  function pick(emotion: StageEmotion) {
    setSelected(emotion);
    previewExpression(characterId, emotion);
  }

  function setSource(emotion: Emotion, value: string) {
    const mapping = { ...preferences.mapping };
    if (value === AUTO) delete mapping[emotion]; else mapping[emotion] = value;
    writeExpressions(characterId, { ...preferences, mapping });
    previewExpression(characterId, emotion);
  }

  function options(emotion: Emotion): DropdownOption[] {
    const automatic = faceSource(emotion, choices, { enabled: true, mapping: {} }, true);
    return [
      { value: AUTO, label: 'Tự động', hint: automatic.kind === 'file' ? `Tệp ${automatic.choice.label}` : 'Mặt dựng sẵn' },
      { value: BUILTIN_FACE, label: 'Dựng sẵn', hint: 'Mắt, chân mày, khóe miệng, má' },
      ...choices.map(choice => ({ value: choice.id, label: choice.label, group: 'Tệp biểu cảm của model' })),
      { value: '', label: 'Không dùng', hint: 'Giữ mặt bình thường' },
    ];
  }

  const hint = preferences.enabled
    ? 'Peto tự chọn cảm xúc cho từng câu trả lời.'
    : 'Đang tắt: nhân vật giữ mặt bình thường khi trò chuyện. Bấm thẻ vẫn xem thử được.';
  return <section className="music-vibe-picker expression-picker" aria-label="Biểu cảm">
    <label className="character-effect-option"><span><strong>Biểu cảm theo trò chuyện</strong><small>{hint}</small></span>
      <input type="checkbox" role="switch" aria-label="Biểu cảm theo trò chuyện" checked={preferences.enabled}
        onChange={event => writeExpressions(characterId, { ...preferences, enabled: event.target.checked })} /></label>
    <div className="expression-cards" role="group" aria-label="Cảm xúc">
      {CARDS.map(emotion => <button type="button" key={emotion} className="expression-card" aria-pressed={selected === emotion}
        onClick={() => pick(emotion)}>{label(emotion)}</button>)}
    </div>
    <div className="expression-source">
      {selected === null ? <p className="expression-source-empty">Bấm một thẻ để xem nhân vật làm mặt đó.</p> : <>
        <div className="expression-source-body">
          {selected === 'neutral' ? <p>Nhân vật đang về mặt bình thường.</p> : <>
            {format === 'vrm'
              ? <p>{label(selected)} lấy từ biểu cảm có sẵn của model VRM.</p>
              : <Field id={sourceId} label={`${label(selected)} lấy từ`}>
                <Dropdown id={sourceId} value={preferences.mapping[selected] ?? AUTO} options={options(selected)}
                  onChange={value => setSource(selected, value)} />
              </Field>}
            <p>Nhân vật đang làm mặt {label(selected).toLowerCase()}. Bấm thẻ khác để xem.</p>
          </>}
        </div>
      </>}
    </div>
  </section>;
}
