import { useEffect, useState } from 'react';
import { readEffects, watchEffects, writeEffects } from './characterEffects';

export default function ComposerGazeSetting({ characterId }: { characterId: string }) {
  const [effects, setEffects] = useState(() => readEffects(characterId));
  useEffect(() => { setEffects(readEffects(characterId)); return watchEffects(characterId, setEffects); }, [characterId]);
  return <label className="character-effect-option">
    <span><strong>Nhìn vào ô chat khi bạn gõ</strong><small>Chỉ trên máy tính. Ngừng gõ thì trở lại nhìn như bình thường.</small></span>
    <input type="checkbox" role="switch" aria-label="Nhìn vào ô chat khi bạn gõ" checked={effects.composerGaze}
      onChange={event => writeEffects(characterId, { ...effects, composerGaze: event.target.checked })} />
  </label>;
}
