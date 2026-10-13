import { useEffect, useId, useState } from 'react';
import type { CharacterModel } from './characterLibrary';
import { loadMotionInfo, readIdle, watchIdle, writeIdle, type IdleMotion } from './live2dMotions';
import { readEffects, watchEffects, writeEffects, type CharacterEffects } from './characterEffects';
import MusicVibePicker from './MusicVibePicker';
import ComposerGazeSetting from './ComposerGazeSetting';
import ExpressionPicker from './ExpressionPicker';
import type { ExpressionChoice } from './characterExpressions';
import { selectMusicCharacter } from './musicVibe';
import { Dropdown, type DropdownOption } from '../../../shared/ui/Dropdown';
import MotionDriverPicker from './MotionDriverPicker';
import { readMagic, watchMagic, writeMagic } from './magic/magicSettings';

export default function IdleMotionPicker({ character }: { character: CharacterModel }) {
  const field = useId();
  const [choices, setChoices] = useState<IdleMotion[]>([]);
  const [value, setValue] = useState(() => readIdle(character.id));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [effects, setEffects] = useState(() => readEffects(character.id));
  const [hasPhysics, setHasPhysics] = useState(false);
  const [expressions, setExpressions] = useState<ExpressionChoice[]>([]);
  const [magic, setMagic] = useState(() => readMagic(character.id));
  const magicOn = magic.driver === 'magic';
  useEffect(() => selectMusicCharacter(character.id), [character.id]);
  useEffect(() => watchEffects(character.id, setEffects), [character.id]);
  useEffect(() => watchIdle(character.id, setValue), [character.id]);
  useEffect(() => { setMagic(readMagic(character.id)); return watchMagic(character.id, setMagic); }, [character.id]);
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
  // Bảng cài đặt nhân vật cuộn được, nên dùng Dropdown: bảng chọn gốc của trình duyệt không đi theo ô khi cuộn.
  const options: DropdownOption[] = [
    { value: 'auto', label: 'Tự động · ngẫu nhiên nhóm Idle' },
    { value: 'off', label: 'Tắt idle animation' },
    ...[...new Set(choices.map(item => item.group))].flatMap(group => choices.filter(item => item.group === group)
      .map(item => ({ value: item.id, label: item.label, group: group || 'Không tên' }))),
  ];
  return <section className="idle-motion-picker" aria-labelledby={`${field}-title`}>
    <div><h3 id={`${field}-title`}>Chuyển động</h3><p>{character.name} · Live2D</p></div>
    <MotionDriverPicker value={magic} onChange={next => { setMagic(next); writeMagic(character.id, next); }} />
    <label className="motion-driver-label" htmlFor={field} id={`${field}-label`}>Chuyển động khi chờ</label>
    <Dropdown id={field} value={resolved} options={options} disabled={loading || !!error || magicOn}
      onChange={next => { setValue(next); writeIdle(character.id, next); }} />
    {loading ? <p role="status">Đang đọc chuyển động…</p> : error
      ? <p role="alert">{error} <button type="button" className="settings-button" onClick={() => setAttempt(n => n + 1)}>Thử lại</button></p>
      : <p>{selected?.file || (value === 'off' ? 'Đã tắt phát motion khi chờ.' : choices.some(item => item.group === 'Idle')
        ? 'Tự chọn chuyển động trong nhóm Idle của model.' : 'Model không khai báo nhóm Idle. Bạn có thể chọn một chuyển động bên trên.')}</p>}
    <p>{magicOn ? 'MAGIC đang lo chuyển động khi chờ. Chọn "Hiện tại" để dùng lại chuyển động này.'
      : 'Chọn một tệp để phát lặp lại. Tắt idle chỉ dừng motion khi chờ.'}</p>
    <div className="character-effect-options">
      <ComposerGazeSetting characterId={character.id} />
      {([
        ['cursor', 'Nhìn theo con trỏ', magicOn ? 'Tắt khi dùng MAGIC, như AIRI.' : 'Mắt và đầu nhìn theo chuột hoặc điểm chạm.'],
        ['idleEyes', 'Đảo mắt khi chờ', magicOn ? 'Tắt khi dùng MAGIC, như AIRI.' : 'Thỉnh thoảng nhìn quanh khi con trỏ không hoạt động.'],
        ['breath', 'Thở', 'Hiệu ứng thở tự động; mức thể hiện tùy model.'],
        ['physics', 'Vật lý', !loading && !error && !hasPhysics ? 'Model chưa khai báo tệp vật lý.' : 'Chuyển động phụ của tóc, quần áo và phụ kiện.'],
      ] as const).map(([key, title, description]) => <label className="character-effect-option" key={key}>
        <span><strong>{title}</strong><small>{description}</small></span>
        <input type="checkbox" role="switch" aria-label={title} checked={effects[key]}
          disabled={(key === 'physics' && (loading || !!error || !hasPhysics)) || (magicOn && (key === 'cursor' || key === 'idleEyes'))}
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
