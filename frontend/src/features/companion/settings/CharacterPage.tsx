import { lazy, Suspense, useState } from 'react';
import type { CharacterLibrary } from '../characters/useCharacters';
import type { CharacterMotion } from '../characters/characterView';
import CharacterSections from '../characters/CharacterSections';
import CharacterPicker from '../characters/CharacterPicker';
import { CHARACTER } from '../characters/characterConfig';

const Live2DStage = lazy(() => import('../characters/Live2DStage'));
const VRMStage = lazy(() => import('../characters/VRMStage'));

/**
 * Cài đặt → Nhân vật (/companion/settings/character), biến thể "Như AIRI" chủ web chọn ngày 14/10/2026 theo Settings →
 * Models của AIRI: các khối cài đặt gập mở bên trái, nhân vật đứng giữa phần còn lại của trang để thấy ngay mỗi thay đổi.
 * Chủ web bỏ khung giới thiệu của AIRI ("hỗ trợ 2D và 3D") vì chật. Sân khấu ở đây là bản riêng của trang (sân khấu
 * Companion đã gỡ khi mở Cài đặt), không có nền bối cảnh, như trang Models của AIRI.
 */
export default function CharacterPage({ library, motion, onMotionChange, fallbackUrl }: {
  library: CharacterLibrary;
  motion: CharacterMotion;
  onMotionChange: (value: CharacterMotion) => void;
  fallbackUrl?: string;
}) {
  const [picking, setPicking] = useState(false);
  const character = library.selected;
  const vrm = character.format === 'vrm';
  return <>
    <section className="character-page-stage" aria-label={`Sân khấu xem trước · ${character.name}`}>
      {!library.loading && <Suspense fallback={null}>
        {vrm
          ? <VRMStage key={character.id} character={character} motion={motion} onPreview={library.savePreview} />
          : <Live2DStage key={character.id} character={character} name={character.name} fallbackUrl={fallbackUrl} motion={motion}
              onPreview={library.savePreview} />}
      </Suspense>}
    </section>
    <div className="character-page-panel">
      <div className="character-page-current">
        <button type="button" className="character-page-pick" aria-haspopup="dialog" onClick={() => setPicking(true)}>Chọn nhân vật</button>
        <span><strong>{character.name}</strong><small>{vrm ? 'VRM · 3D' : 'Live2D · 2D'}</small></span>
      </div>
      <CharacterSections key={character.id} character={character} motion={motion} onMotionChange={onMotionChange} />
      <p className="character-page-footnote">
        {character.builtin && <><a href={CHARACTER.creditUrl} target="_blank" rel="noopener noreferrer">Hiyori Momose · © Live2D Inc.</a> · </>}
        Lưu trên thiết bị này; phần lớn cài đặt là riêng của từng nhân vật.
      </p>
    </div>
    {picking && <CharacterPicker library={library} onClose={() => setPicking(false)} />}
  </>;
}
