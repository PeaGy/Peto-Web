import { useEffect, useState } from 'react';
import { EMOTIONS, emotionLabels, expressionFor, previewExpression, readExpressions, watchExpressions, writeExpressions,
  type ExpressionChoice } from './characterExpressions';

export default function ExpressionPicker({ characterId, choices }: { characterId: string; choices: ExpressionChoice[] }) {
  const [preferences, setPreferences] = useState(() => readExpressions(characterId));
  useEffect(() => watchExpressions(characterId, setPreferences), [characterId]);
  return <section className="music-vibe-picker" aria-label="Biểu cảm">
    <label className="character-effect-option"><span><strong>Biểu cảm theo trò chuyện</strong>
      <small>{choices.length ? 'Nhận biết dấu hiệu cảm xúc trong câu trả lời; có thể gán lại bên dưới.' : 'Model chưa khai báo tệp biểu cảm riêng.'}</small></span>
      <input type="checkbox" role="switch" aria-label="Biểu cảm theo trò chuyện" disabled={!choices.length} checked={preferences.enabled && !!choices.length}
        onChange={event => writeExpressions(characterId, { ...preferences, enabled: event.target.checked })} /></label>
    {!!choices.length && <details><summary>Gán biểu cảm</summary>
      {EMOTIONS.map(emotion => {
        const selected = expressionFor(emotion, choices, preferences);
        return <div className="expression-mapping" key={emotion}>
          <label>{emotionLabels[emotion]}<select value={preferences.mapping[emotion] ?? 'auto'}
            onChange={event => {
              const mapping = { ...preferences.mapping };
              if (event.target.value === 'auto') delete mapping[emotion]; else mapping[emotion] = event.target.value;
              writeExpressions(characterId, { ...preferences, mapping });
            }}>
            <option value="auto">Tự nhận diện tên tệp</option><option value="">Không dùng</option>
            {choices.map(choice => <option key={choice.id} value={choice.id}>{choice.label}</option>)}
          </select></label>
          <button type="button" className="settings-button" disabled={!selected} onClick={() => previewExpression(characterId, selected?.id || '')}>Thử {emotionLabels[emotion].toLowerCase()}</button>
        </div>;
      })}
      <button type="button" className="settings-button" onClick={() => previewExpression(characterId, '')}>Về bình thường</button>
    </details>}
  </section>;
}
