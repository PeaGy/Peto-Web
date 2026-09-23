import { useEffect, useId, useState } from 'react';
import type { CharacterModel } from './characterLibrary';
import { loadMotionInfo, readIdle, watchIdle, writeIdle, type IdleMotion } from './live2dMotions';
import { readEffects, watchEffects, writeEffects, type CharacterEffects } from './characterEffects';
import MusicVibePicker from './MusicVibePicker';
import ExpressionPicker from './ExpressionPicker';
import type { ExpressionChoice } from './characterExpressions';
import { selectMusicCharacter } from './musicVibe';

export default function IdleMotionPicker({ character }: { character: CharacterModel }) {
  const label = useId();
  const [choices, setChoices] = useState<IdleMotion[]>([]);
  const [value, setValue] = useState(() => readIdle(character.id));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [effects, setEffects] = useState(() => readEffects(character.id));
  const [hasPhysics, setHasPhysics] = useState(false);
  const [expressions, setExpressions] = useState<ExpressionChoice[]>([]);
  useEffect(() => selectMusicCharacter(character.id), [character.id]);
  useEffect(() => watchEffects(character.id, setEffects), [character.id]);
  useEffect(() => watchIdle(character.id, setValue), [character.id]);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError('');
    void loadMotionInfo(character).then(info => { if (alive) { setChoices(info.choices); setHasPhysics(info.physics); setExpressions(info.expressions); } })
      .catch(() => { if (alive) setError('Chưa đọc được danh sách chuyển động của model.'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [character.id, attempt]);
  const selected = choices.find(item => item.id === value);
  const resolved = value === 'off' ? 'off' : selected ? value : 'auto';
  return <section className="idle-motion-picker" aria-labelledby={label}>
    <div><h3 id={label}>Chuyển động khi chờ</h3><p>{character.name} · Live2D</p></div>
    <select aria-labelledby={label} value={resolved} disabled={loading || !!error}
      onChange={event => { setValue(event.target.value); writeIdle(character.id, event.target.value); }}>
      <option value="auto">Tự động · ngẫu nhiên nhóm Idle</option>
      <option value="off">Tắt idle animation</option>
      {[...new Set(choices.map(item => item.group))].map(group => <optgroup key={group} label={group || 'Không tên'}>
        {choices.filter(item => item.group === group).map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
      </optgroup>)}
    </select>
    {loading ? <p role="status">Đang đọc chuyển động…</p> : error
      ? <p role="alert">{error} <button type="button" className="settings-button" onClick={() => setAttempt(n => n + 1)}>Thử lại</button></p>
      : <p>{selected?.file || (value === 'off' ? 'Đã tắt phát motion khi chờ.' : choices.some(item => item.group === 'Idle')
        ? 'Tự chọn chuyển động trong nhóm Idle của model.' : 'Model không khai báo nhóm Idle. Bạn có thể chọn một chuyển động bên trên.')}</p>}
    <p>Chọn một tệp để phát lặp lại. Tắt idle chỉ dừng motion khi chờ.</p>
    <div className="character-effect-options">
      {([
        ['cursor', 'Nhìn theo con trỏ', 'Mắt và đầu nhìn theo chuột hoặc điểm chạm.'],
        ['breath', 'Thở', 'Hiệu ứng thở tự động; mức thể hiện tùy model.'],
        ['physics', 'Vật lý', !loading && !error && !hasPhysics ? 'Model chưa khai báo tệp vật lý.' : 'Chuyển động phụ của tóc, quần áo và phụ kiện.'],
      ] as const).map(([key, title, description]) => <label className="character-effect-option" key={key}>
        <span><strong>{title}</strong><small>{description}</small></span>
        <input type="checkbox" role="switch" aria-label={title} checked={effects[key]}
          disabled={key === 'physics' && (loading || !!error || !hasPhysics)}
          onChange={event => {
            const next: CharacterEffects = { ...effects, [key]: event.target.checked };
            setEffects(next); writeEffects(character.id, next);
          }} />
      </label>)}
    </div>
    {!loading && !error && <ExpressionPicker characterId={character.id} choices={expressions} />}
    <MusicVibePicker />
    {!loading && !error && !choices.length && <p>Không có motion được khai báo trong .model3.json.</p>}
  </section>;
}
