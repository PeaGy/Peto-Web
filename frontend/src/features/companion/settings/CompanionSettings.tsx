import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react';
import type { CompanionSettingsPage } from '../../../app/routes';
import type { CharacterModel } from '../characters/characterLibrary';
import { BeatSyncBody } from '../characters/MusicVibePicker';
import { leaveMusicVibe, selectMusicCharacter, useMusicVibe } from '../characters/musicVibe';
import { SceneEditor, useCompanionScene } from '../CompanionScenes';
import { useCompanionSearch } from '../companionSearch';
import CompanionTimingPanel from '../speech/CompanionTimingPanel';
import HearingSettings from '../speech/HearingSettings';
import { useHearing } from '../speech/hearingEngine';
import { hearingProvider } from '../speech/hearingProviders';
import type { LocalVoice } from '../speech/LocalVoice';
import { keyProvider } from '../speech/voiceProviders';
import VoiceSettings from '../speech/VoiceSettings';
import MemorySettings from '../../settings/MemorySettings';
import SearchSettings from '../../settings/SearchSettings';
import { CompanionSettingsIcon, type SettingsIconName } from './settingsIcons';
import './companionSettings.css';

/**
 * Trang cài đặt riêng của Companion tại /companion/settings/ (chủ web chọn biến thể "Thẻ AIRI" ngày 13/10/2026), theo
 * Settings bản web của AIRI: trang đầu là danh sách thẻ lớn, mỗi tầng là một trang có tiêu đề lớn và tên mục cha nhỏ phía
 * trên, thẻ hiện kiểu gợn sóng tỏa ra từ thẻ vừa bấm lần trước (ripple-grid của AIRI). Hộp Cài đặt chung không còn nhóm
 * Companion. Nhân vật vẫn chỉnh trong hộp chọn nhân vật; Trí nhớ là cùng một danh sách với Cài đặt chung.
 */

const PAGES: Record<CompanionSettingsPage, { title: string; desc: string; icon: SettingsIconName; parent?: CompanionSettingsPage }> = {
  home: { title: 'Cài đặt', desc: '', icon: 'settings' },
  modules: { title: 'Mô-đun', desc: 'Giọng nói, nghe, tra web và nhún theo nhạc.', icon: 'layers', parent: 'home' },
  voice: { title: 'Giọng nói', desc: 'Peto đọc câu trả lời thành tiếng.', icon: 'wave', parent: 'modules' },
  hearing: { title: 'Nghe', desc: 'Nói chuyện với Peto qua micro.', icon: 'mic', parent: 'modules' },
  'web-search': { title: 'Tra web', desc: 'Peto tự tra web khi câu hỏi cần tin mới.', icon: 'globe', parent: 'modules' },
  'beat-sync': { title: 'Nhún theo nhạc', desc: 'Nhân vật Live2D nhún theo nhịp bài đang phát.', icon: 'music', parent: 'modules' },
  scene: { title: 'Bối cảnh', desc: 'Nền phía sau nhân vật, độ tối và độ mờ.', icon: 'image', parent: 'home' },
  memory: { title: 'Trí nhớ', desc: 'Những điều Peto nhớ về bạn. Dùng chung với Trò chuyện.', icon: 'bookmark', parent: 'home' },
  diagnostics: { title: 'Chẩn đoán', desc: 'Đo thời gian từ lúc bạn nói tới lúc Peto đáp.', icon: 'gauge', parent: 'home' },
};
const MODULES: CompanionSettingsPage[] = ['voice', 'hearing', 'web-search', 'beat-sync'];
const HOME: (CompanionSettingsPage | 'character')[] = ['character', 'modules', 'scene', 'memory', 'diagnostics'];
/** Khoảng trễ mỗi bậc khoảng cách trên lưới khi thẻ hiện kiểu gợn sóng (AIRI dùng 80 ms). */
const RIPPLE_STEP_MS = 70;
// Thẻ bấm lần trước là tâm gợn sóng của trang kế tiếp, như useRippleGridState của AIRI; giữ qua các lần mở trang.
let rippleOrigin = 0;

function useCompact() {
  const query = '(max-width: 720px)';
  const [compact, setCompact] = useState(() => window.matchMedia?.(query).matches ?? false);
  useEffect(() => {
    const media = window.matchMedia?.(query);
    if (!media) return;
    const change = () => setCompact(media.matches);
    media.addEventListener?.('change', change);
    return () => media.removeEventListener?.('change', change);
  }, []);
  return compact;
}

export default function CompanionSettings({ page, onNavigate, onExit, voice, character, onOpenCharacters, onUnauthorized }: {
  page: CompanionSettingsPage;
  onNavigate: (page: CompanionSettingsPage) => void;
  /** Nút quay lại ở trang đầu: về sân khấu Companion. */
  onExit: () => void;
  voice: LocalVoice;
  character: CharacterModel;
  onOpenCharacters: () => void;
  onUnauthorized: () => void;
}) {
  const meta = PAGES[page];
  const parent = meta.parent ? PAGES[meta.parent] : null;
  const scroll = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const firstPage = useRef(true);
  const compact = useCompact();

  // Đổi trang thì về đầu trang và chuyển tiêu điểm lên tiêu đề, để bàn phím và trình đọc màn hình theo kịp.
  useLayoutEffect(() => {
    scroll.current?.scrollTo?.({ top: 0 });
    if (firstPage.current) { firstPage.current = false; return; }
    heading.current?.focus({ preventScroll: true });
  }, [page]);
  // Rời hẳn Companion từ trang này thì thôi chia sẻ âm thanh cho Nhún theo nhạc (như lúc sân khấu bị gỡ).
  useEffect(() => () => leaveMusicVibe(), []);

  const open = (next: CompanionSettingsPage, index: number) => { rippleOrigin = index; onNavigate(next); };
  const delay = (index: number, cols: number) => {
    const origin = Math.max(0, rippleOrigin);
    const distance = Math.abs(Math.floor(index / cols) - Math.floor(origin / cols)) + Math.abs((index % cols) - (origin % cols));
    return distance * RIPPLE_STEP_MS;
  };

  return (
    <main className="companion-settings" aria-labelledby="companion-settings-title">
      <div className="companion-settings-scroll" ref={scroll}>
        <div className="companion-settings-column">
          <header className="companion-settings-head">
            <button type="button" className="companion-settings-back" aria-label={`Quay lại ${parent ? parent.title : 'Companion'}`}
              data-tip={parent ? parent.title : 'Companion'} onClick={() => (meta.parent ? onNavigate(meta.parent) : onExit())}>
              <CompanionSettingsIcon name="chevronLeft" size={22} />
            </button>
            <div key={page} className="companion-settings-heading">
              <span className="companion-settings-parent">{parent ? parent.title : 'Companion'}</span>
              <h1 id="companion-settings-title" ref={heading} tabIndex={-1}>{meta.title}</h1>
            </div>
          </header>

          <div key={page} className="companion-settings-page">
            {page === 'home' && (
              <div className="companion-settings-list">
                {HOME.map((entry, index) => entry === 'character'
                  ? <SettingsCard key="character" icon="character" title="Nhân vật" delay={delay(index, 1)}
                      desc={`Đang dùng: ${character.name} · ${character.format === 'vrm' ? 'VRM' : 'Live2D'}`}
                      note="Chọn, nhập và chỉnh nhân vật trong hộp chọn nhân vật"
                      onClick={() => { rippleOrigin = index; onOpenCharacters(); }} />
                  : <SettingsCard key={entry} icon={PAGES[entry].icon} title={PAGES[entry].title} desc={PAGES[entry].desc}
                      delay={delay(index, 1)} onClick={() => open(entry, index)} />)}
              </div>
            )}
            {page === 'modules' && <Modules voice={voice} character={character} cols={compact ? 1 : 2} delay={delay} onOpen={open} />}
            {page === 'voice' && <div className="companion-settings-groups"><VoiceSettings voice={voice} open /></div>}
            {page === 'hearing' && <div className="companion-settings-groups"><HearingSettings open /></div>}
            {page === 'web-search' && <div className="companion-settings-groups"><SearchSettings /></div>}
            {page === 'beat-sync' && <BeatSyncPage character={character} />}
            {page === 'scene' && <ScenePage character={character} />}
            {page === 'memory' && <div className="companion-settings-groups"><MemorySettings open onUnauthorized={onUnauthorized} /></div>}
            {page === 'diagnostics' && <div className="companion-settings-card"><CompanionTimingPanel /></div>}
          </div>
        </div>
      </div>
      <div key={`deco-${page}`} className="companion-settings-deco" aria-hidden="true">
        <CompanionSettingsIcon name={meta.icon} size={compact ? 150 : 220} />
      </div>
    </main>
  );
}

function SettingsCard({ icon, title, desc, note, on, delay, onClick }: {
  icon: SettingsIconName; title: string; desc: string; note?: string; on?: boolean; delay: number; onClick: () => void;
}) {
  return (
    <button type="button" className="companion-settings-item" style={{ '--delay': `${delay}ms` } as CSSProperties} onClick={onClick}>
      <span className="companion-settings-item-text">
        <span className="companion-settings-item-title">
          {title}
          {on !== undefined && <span className={on ? 'companion-settings-dot on' : 'companion-settings-dot'} aria-label={on ? 'đang bật' : 'đang tắt'} />}
        </span>
        <span className="companion-settings-item-desc">{desc}</span>
        {note && <span className="companion-settings-item-note">{note}</span>}
      </span>
      <CompanionSettingsIcon name={icon} size={92} className="companion-settings-item-icon" />
    </button>
  );
}

function Modules({ voice, character, cols, delay, onOpen }: {
  voice: LocalVoice;
  character: CharacterModel;
  cols: number;
  delay: (index: number, cols: number) => number;
  onOpen: (page: CompanionSettingsPage, index: number) => void;
}) {
  const hearing = useHearing();
  const search = useCompanionSearch();
  const music = useMusicVibe();
  const voiceName = voice.source === 'official' ? 'Giọng Peto' : voice.source === 'home' ? 'Máy nhà của Peto'
    : keyProvider(voice.source)?.name ?? voice.source;
  const status: Record<string, { on: boolean; desc: string }> = {
    voice: !voice.enabled ? { on: false, desc: 'Đang tắt · Peto chỉ nhắn chữ' }
      : { on: true, desc: voice.status === 'missing' ? `${voiceName} · chưa nói được` : voiceName },
    hearing: {
      on: hearing.listening && !hearing.testing,
      desc: `${hearing.source === 'browser' ? 'Có sẵn trong trình duyệt' : hearingProvider(hearing.source)?.name ?? hearing.source}`
        + ` · ${hearing.language === 'vi' ? 'Tiếng Việt' : 'Tiếng Anh'}${hearing.listening && !hearing.testing ? ' · đang nghe' : ''}`,
    },
    'web-search': { on: search, desc: search ? 'Peto tự quyết khi nào cần tra' : 'Đang tắt' },
    'beat-sync': character.format === 'vrm' ? { on: false, desc: 'Chỉ dùng với nhân vật Live2D' }
      : { on: music.status === 'active', desc: music.status === 'active' ? 'Đang nhún theo nguồn nhạc' : 'Chưa chọn nguồn nhạc' },
  };
  return (
    <div className="companion-settings-grid" style={{ '--cols': cols } as CSSProperties}>
      {MODULES.map((module, index) => (
        <SettingsCard key={module} icon={PAGES[module].icon} title={PAGES[module].title} desc={status[module].desc}
          on={status[module].on} delay={delay(index, cols)} onClick={() => onOpen(module, index)} />
      ))}
    </div>
  );
}

function BeatSyncPage({ character }: { character: CharacterModel }) {
  const live2d = character.format !== 'vrm';
  // Độ mạnh và độ nhạy lưu theo từng nhân vật, như trong hộp chọn nhân vật.
  useEffect(() => { if (live2d) selectMusicCharacter(character.id); }, [character.id, live2d]);
  if (!live2d) {
    return <div className="companion-settings-card"><p className="companion-settings-note">
      Nhún theo nhạc hiện chỉ chạy với nhân vật Live2D. {character.name} là model VRM.
    </p></div>;
  }
  return <div className="companion-settings-card beat-sync-page"><BeatSyncBody /></div>;
}

function ScenePage({ character }: { character: CharacterModel }) {
  const scene = useCompanionScene(character.id);
  return <div className="companion-settings-card scene-page">
    <p className="companion-settings-note">Lưu trên thiết bị này, riêng cho {character.name}.</p>
    <SceneEditor scene={scene} />
  </div>;
}
