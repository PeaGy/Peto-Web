import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import type { CharacterModel } from './characterLibrary';
import { loadMotionInfo, readIdle, watchIdle, writeIdle, type IdleMotion } from './live2dMotions';
import { readEffects, watchEffects, writeEffects, type CharacterEffects } from './characterEffects';
import ComposerGazeSetting from './ComposerGazeSetting';
import ExpressionPicker from './ExpressionPicker';
import type { ExpressionChoice } from './characterExpressions';
import MotionDriverPicker from './MotionDriverPicker';
import { readMagic, watchMagic, writeMagic } from './magic/magicSettings';
import CharacterSettings from './CharacterSettings';
import {
  COMPACT_QUERY, DEFAULT_VIEW, MAX_ZOOM, MIN_ZOOM, clampView, readCharacterView, watchCharacterView, writeCharacterView,
  type CharacterMotion, type CharacterView,
} from './characterView';
import { BeatSyncBody } from './MusicVibePicker';
import { selectMusicCharacter } from './musicVibe';
import { useRenderQuality, writeRenderQuality } from './renderQuality';
import { Dropdown, type DropdownOption } from '../../../shared/ui/Dropdown';
import { isReducedMotion } from '../../../shared/motion';

/*
 * Các khối của trang Cài đặt → Nhân vật (biến thể "Như AIRI" chủ web chọn ngày 14/10/2026), theo Settings → Models của
 * AIRI: Kích thước và vị trí, Chuyển động, Biểu cảm, Nhún theo nhạc và Hiển thị trên điện thoại. Mỗi khối gập mở được;
 * nhân vật đứng ngay bên cạnh nên mọi thay đổi hiện lên sân khấu tức thì.
 */

export function useCompactScreen() {
  const [compact, setCompact] = useState(() => window.matchMedia?.(COMPACT_QUERY).matches ?? false);
  useEffect(() => {
    const media = window.matchMedia?.(COMPACT_QUERY);
    if (!media) return;
    const change = () => setCompact(media.matches);
    media.addEventListener?.('change', change);
    return () => media.removeEventListener?.('change', change);
  }, []);
  return compact;
}

const icon = (children: ReactNode) => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>;
const ICONS = {
  frame: icon(<><path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4" /><circle cx="12" cy="10" r="2.6" /><path d="M7.5 17a4.8 4.8 0 0 1 9 0" /></>),
  motion: icon(<><path d="M5 15c2-6 4-6 7 0s5 6 7 0" /><path d="M5 8h2M17 8h2" /></>),
  face: icon(<><circle cx="12" cy="12" r="8.5" /><path d="M8.5 14.5a4.2 4.2 0 0 0 7 0M9 9.8h.01M15 9.8h.01" /></>),
  music: icon(<><path d="M9 18V5l11-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="17" cy="16" r="3" /></>),
  display: icon(<><rect x="6.5" y="3" width="11" height="18" rx="2.5" /><path d="M11 18h2" /></>),
};
const ResetIcon = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
  strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 10a8 8 0 1 1 1 7M4 4v6h6" /></svg>;
const Chevron = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
  strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>;

/** Khối gập mở, như Section của AIRI: tiêu đề có biểu tượng, nội dung mở ra theo chiều cao. */
function Section({ title, icon: sectionIcon, open, onToggle, children }: {
  title: string; icon: ReactNode; open: boolean; onToggle: () => void; children: ReactNode;
}) {
  const id = useId();
  // Đang mở dần thì cắt phần thừa; mở hẳn rồi mới cho tràn, để danh sách thả xuống không bị khung khối cắt mất.
  const [settled, setSettled] = useState(open);
  useEffect(() => {
    if (!open) { setSettled(false); return; }
    const timer = window.setTimeout(() => setSettled(true), isReducedMotion() ? 0 : 260);
    return () => window.clearTimeout(timer);
  }, [open]);
  return <section className={`character-section${open ? ' open' : ''}`} data-settled={open && settled ? '' : undefined}>
    <h2 className="character-section-head">
      <button type="button" id={`${id}-head`} aria-expanded={open} aria-controls={`${id}-body`} onClick={onToggle}>
        <span className="character-section-icon">{sectionIcon}</span>
        <span className="character-section-title">{title}</span>
        <span className="character-section-chevron"><Chevron /></span>
      </button>
    </h2>
    <div className="character-section-body" id={`${id}-body`} role="region" aria-labelledby={`${id}-head`} inert={!open}>
      <div><div className="character-section-inner">{children}</div></div>
    </div>
  </section>;
}

function Range({ label, value, min, max, unit, onChange, onReset }: {
  label: string; value: number; min: number; max: number; unit: string; onChange: (value: number) => void; onReset: () => void;
}) {
  const id = useId();
  return <div className="character-range">
    <div className="character-range-head">
      <label htmlFor={id}>{label}</label>
      <button type="button" className="character-range-reset" aria-label={`Đặt lại ${label.toLowerCase()}`} data-tip="Đặt lại" onClick={onReset}>
        <ResetIcon />
      </button>
      <output htmlFor={id}>{value}{unit}</output>
    </div>
    <input id={id} type="range" min={min} max={max} step={1} value={value} onChange={event => onChange(Number(event.target.value))} />
  </div>;
}

/**
 * Kích thước và vị trí (AIRI: Scale And Position). Ghi góc nhìn cho sân khấu đổi ngay; thanh trượt đi theo cuộn hay kéo trên
 * sân khấu. Chỉ gửi mức phóng khi kéo Thu phóng: sân khấu phóng quanh đầu nhân vật rồi báo lại độ dời mới.
 */
function ViewSettings({ character }: { character: CharacterModel }) {
  const [view, setView] = useState<CharacterView>(() => readCharacterView(character.id));
  const source = useRef({}).current;
  const compact = useCompactScreen();
  useEffect(() => {
    setView(readCharacterView(character.id));
    return watchCharacterView(character.id, (next, from) => { if (from !== source) setView(next); });
  }, [character.id, source]);
  if (character.format === 'vrm') return <p className="character-section-note">Model VRM luôn đứng giữa khung; chưa chỉnh được cỡ và vị trí.</p>;
  const change = (patch: Partial<CharacterView>) => {
    const next = clampView({ ...view, ...patch });
    setView(next);
    writeCharacterView(next, character.id, source);
  };
  const reachX = Math.round((0.35 + view.zoom / 2) * 100);
  return <>
    <Range label="Thu phóng" unit="%" value={Math.round(view.zoom * 100)} min={MIN_ZOOM * 100} max={MAX_ZOOM * 100}
      onChange={value => change({ zoom: value / 100 })} onReset={() => change({ zoom: 1 })} />
    <Range label="Ngang" unit="%" value={Math.round(view.panX * 100)} min={-reachX} max={reachX}
      onChange={value => change({ panX: value / 100 })} onReset={() => change({ panX: 0 })} />
    <Range label="Dọc" unit="%" value={Math.round(view.panY * 100)} min={-50} max={Math.round(view.zoom * 100)}
      onChange={value => change({ panY: value / 100 })} onReset={() => change({ panY: 0 })} />
    <div className="character-section-actions">
      <button type="button" className="settings-button" onClick={() => change(DEFAULT_VIEW)}>Về vừa khung</button>
    </div>
    <p className="character-section-note">{compact
      ? 'Trên điện thoại nhân vật giữ khung cố định như AIRI; cỡ và vị trí này dùng khi mở bằng máy tính.'
      : 'Trên sân khấu: cuộn chuột để phóng, giữ chuột giữa rồi kéo để dời, bấm đúp để về vừa khung.'}</p>
  </>;
}

/** Chuyển động, biểu cảm và vật lý mà .model3.json khai báo (chỉ Live2D). */
function useMotionInfo(character: CharacterModel) {
  const [info, setInfo] = useState<{ choices: IdleMotion[]; physics: boolean; expressions: ExpressionChoice[] }>({ choices: [], physics: false, expressions: [] });
  const [loading, setLoading] = useState(character.format === 'live2d');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const latest = useRef(character); latest.current = character;
  useEffect(() => {
    if (latest.current.format !== 'live2d') return;
    let alive = true;
    setLoading(true); setError('');
    void loadMotionInfo(latest.current).then(next => { if (alive) setInfo(next); })
      .catch(() => { if (alive) setError('Chưa đọc được danh sách chuyển động của model.'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [character.id, attempt]);
  return { ...info, loading, error, retry: () => setAttempt(n => n + 1) };
}
type MotionInfo = ReturnType<typeof useMotionInfo>;

/**
 * Chuyển động (AIRI: Animation): cử động chung, cách chuyển động (Hiện tại hay MAGIC), chuyển động khi chờ và các hiệu ứng
 * phụ. Như AIRI, MAGIC khóa chuyển động khi chờ, nhìn theo con trỏ và đảo mắt.
 */
function MotionSettings({ character, info, motion, onMotionChange }: {
  character: CharacterModel; info: MotionInfo; motion: CharacterMotion; onMotionChange: (value: CharacterMotion) => void;
}) {
  const field = useId();
  const [value, setValue] = useState(() => readIdle(character.id));
  const [effects, setEffects] = useState(() => readEffects(character.id));
  const [magic, setMagic] = useState(() => readMagic(character.id));
  useEffect(() => watchEffects(character.id, setEffects), [character.id]);
  useEffect(() => watchIdle(character.id, setValue), [character.id]);
  useEffect(() => watchMagic(character.id, setMagic), [character.id]);
  const general = <div className="character-motion-general"><CharacterSettings value={motion} onChange={onMotionChange} /></div>;
  if (character.format === 'vrm') return <>{general}<div className="character-effect-options"><ComposerGazeSetting characterId={character.id} /></div></>;
  const magicOn = magic.driver === 'magic';
  const selected = info.choices.find(item => item.id === value);
  const resolved = value === 'off' ? 'off' : selected ? value : 'auto';
  // Khối cuộn được, nên dùng Dropdown: bảng chọn gốc của trình duyệt không đi theo ô khi cuộn.
  const options: DropdownOption[] = [
    { value: 'auto', label: 'Tự động · ngẫu nhiên nhóm Idle' },
    { value: 'off', label: 'Tắt idle animation' },
    ...[...new Set(info.choices.map(item => item.group))].flatMap(group => info.choices.filter(item => item.group === group)
      .map(item => ({ value: item.id, label: item.label, group: group || 'Không tên' }))),
  ];
  return <>
    {general}
    <MotionDriverPicker value={magic} onChange={next => { setMagic(next); writeMagic(character.id, next); }} />
    <label className="motion-driver-label" htmlFor={field} id={`${field}-label`}>Chuyển động khi chờ</label>
    <Dropdown id={field} value={resolved} options={options} disabled={info.loading || !!info.error || magicOn}
      onChange={next => { setValue(next); writeIdle(character.id, next); }} />
    {info.loading ? <p className="character-section-note" role="status">Đang đọc chuyển động…</p> : info.error
      ? <p className="character-section-note" role="alert">{info.error} <button type="button" className="settings-button" onClick={info.retry}>Thử lại</button></p>
      : <p className="character-section-note">{magicOn ? 'MAGIC đang lo chuyển động khi chờ. Chọn "Hiện tại" để dùng lại chuyển động này.'
        : selected?.file || (value === 'off' ? 'Đã tắt phát motion khi chờ.' : info.choices.some(item => item.group === 'Idle')
          ? 'Tự chọn chuyển động trong nhóm Idle của model.' : info.choices.length
            ? 'Model không khai báo nhóm Idle. Bạn có thể chọn một chuyển động bên trên.' : 'Không có motion được khai báo trong .model3.json.')}</p>}
    <div className="character-effect-options">
      <ComposerGazeSetting characterId={character.id} />
      {([
        ['cursor', 'Nhìn theo con trỏ', magicOn ? 'Tắt khi dùng MAGIC, như AIRI.' : 'Mắt và đầu nhìn theo chuột hoặc điểm chạm.'],
        ['idleEyes', 'Đảo mắt khi chờ', magicOn ? 'Tắt khi dùng MAGIC, như AIRI.' : 'Thỉnh thoảng nhìn quanh khi con trỏ không hoạt động.'],
        ['breath', 'Thở', 'Hiệu ứng thở tự động; mức thể hiện tùy model.'],
        ['physics', 'Vật lý', !info.loading && !info.error && !info.physics ? 'Model chưa khai báo tệp vật lý.' : 'Chuyển động phụ của tóc, quần áo và phụ kiện.'],
      ] as const).map(([key, title, description]) => <label className="character-effect-option" key={key}>
        <span><strong>{title}</strong><small>{description}</small></span>
        <input type="checkbox" role="switch" aria-label={title} checked={effects[key]}
          disabled={(key === 'physics' && (info.loading || !!info.error || !info.physics)) || (magicOn && (key === 'cursor' || key === 'idleEyes'))}
          onChange={event => {
            const next: CharacterEffects = { ...effects, [key]: event.target.checked };
            setEffects(next); writeEffects(character.id, next);
          }} />
      </label>)}
    </div>
  </>;
}

/** Nhún theo nhạc: cùng phần thân với trang Nhún theo nhạc; độ mạnh và độ nhạy lưu theo nhân vật. */
function BeatSettings({ characterId }: { characterId: string }) {
  useEffect(() => selectMusicCharacter(characterId), [characterId]);
  return <div className="character-beat"><BeatSyncBody /></div>;
}

/** Hiển thị trên điện thoại (gần Model Parameters → render scale, FPS của AIRI). Máy tính luôn 30 FPS nên chỉ hiện trên điện thoại. */
function DisplaySettings() {
  const quality = useRenderQuality();
  const sharpId = useId();
  const smoothId = useId();
  return <>
    <label className="motion-driver-label" htmlFor={sharpId} id={`${sharpId}-label`}>Chất lượng hình ảnh</label>
    <Dropdown id={sharpId} value={quality.sharp ? 'high' : 'normal'} options={[{ value: 'normal', label: 'Tiết kiệm · 1×' }, { value: 'high', label: 'Cao · tối đa 2×' }]}
      onChange={next => writeRenderQuality({ ...quality, sharp: next === 'high' })} />
    <label className="motion-driver-label" htmlFor={smoothId} id={`${smoothId}-label`}>Độ mượt</label>
    <Dropdown id={smoothId} value={quality.smooth ? 'high' : 'normal'} options={[{ value: 'normal', label: 'Tiết kiệm · 24 FPS' }, { value: 'high', label: 'Cao · tối đa 60 FPS' }]}
      onChange={next => writeRenderQuality({ ...quality, smooth: next === 'high' })} />
    <p className="character-section-note">Áp dụng cho Live2D và VRM trên thiết bị này. Mức cao có thể dùng nhiều pin và làm máy ấm hơn.</p>
  </>;
}

/** Mọi khối của nhân vật đang chọn. Khối Kích thước và vị trí mở sẵn, như AIRI. */
export default function CharacterSections({ character, motion, onMotionChange }: {
  character: CharacterModel; motion: CharacterMotion; onMotionChange: (value: CharacterMotion) => void;
}) {
  const [open, setOpen] = useState<Set<string>>(() => new Set(['frame']));
  const info = useMotionInfo(character);
  const compact = useCompactScreen();
  const toggle = (key: string) => setOpen(previous => {
    const next = new Set(previous);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const live2d = character.format !== 'vrm';
  const section = (key: string, title: string, children: ReactNode) =>
    <Section title={title} icon={ICONS[key as keyof typeof ICONS]} open={open.has(key)} onToggle={() => toggle(key)}>{children}</Section>;
  return <div className="character-sections">
    {section('frame', 'Kích thước và vị trí', <ViewSettings character={character} />)}
    {section('motion', 'Chuyển động', <MotionSettings character={character} info={info} motion={motion} onMotionChange={onMotionChange} />)}
    {section('face', 'Biểu cảm', live2d && info.loading ? <p className="character-section-note" role="status">Đang đọc biểu cảm…</p>
      : <ExpressionPicker characterId={character.id} choices={info.expressions} format={live2d ? 'live2d' : 'vrm'} />)}
    {live2d && section('music', 'Nhún theo nhạc', <BeatSettings characterId={character.id} />)}
    {compact && section('display', 'Hiển thị trên điện thoại', <DisplaySettings />)}
  </div>;
}
