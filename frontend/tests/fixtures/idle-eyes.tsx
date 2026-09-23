import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import Live2DStage from '../../src/Live2DStage';
import { DEFAULT_CHARACTER } from '../../src/characterLibrary';
import { writeEffects } from '../../src/characterEffects';
import { writeIdle } from '../../src/live2dMotions';
import { CHARACTER } from '../../src/characterConfig';
import '../../src/styles.css';
// Dedicated preference ID: never changes the user's Hiyori settings.
const character = { ...DEFAULT_CHARACTER, id: 'test-idle-eyes' };
writeEffects(character.id, { cursor: false, idleEyes: true, breath: false, physics: false });
writeIdle(character.id, 'off');
function Fixture() {
  const [enabled, setEnabled] = useState(true);
  const [motion, setMotion] = useState<'system' | 'always'>('system');
  return <main style={{ maxWidth: 800, margin: 'auto', padding: 16 }}>
    <h1>Idle eyes — Hiyori thật</h1><p>Nhìn theo chuột, motion, thở và vật lý đều tắt. Chỉ kiểm tra mắt nhìn quanh.</p>
    <p id="eye-samples">Đang lấy mẫu tham số thực ngay trước khi vẽ…</p>
    <button onClick={() => { setEnabled(!enabled); writeEffects(character.id, { cursor: false, idleEyes: !enabled, breath: false, physics: false }); }}>{enabled ? 'Tắt đảo mắt' : 'Bật đảo mắt'}</button>
    <button onClick={() => setMotion(motion === 'system' ? 'always' : 'system')}>{motion === 'system' ? 'Cho phép đầu cử động' : 'Theo giảm chuyển động hệ thống'}</button>
    <div style={{ height: 640 }}><Live2DStage character={character} name="Hiyori" motion={motion} /></div>
  </main>;
}
async function bootstrap() {
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement('script'); script.src = CHARACTER.coreUrl;
    script.onload = () => resolve(); script.onerror = reject; document.head.append(script);
  });
  const { Live2DModel } = await import('pixi-live2d-display/cubism4');
  const original = Live2DModel.from;
  // Fixture-only sampling at the actual Cubism render boundary, after production hooks.
  Live2DModel.from = async function (...args: Parameters<typeof original>) {
    const model = await original.apply(this, args);
    const core = model.internalModel.coreModel;
    const update = core.update.bind(core);
    let min = Infinity, max = -Infinity, count = 0;
    core.update = () => {
      const x = core.getParameterValueById('ParamEyeBallX');
      min = Math.min(min, x); max = Math.max(max, x); count++;
      if (count % 15 === 0) {
        const label = document.getElementById('eye-samples');
        if (label) label.textContent = `Rendered frames: ${count}; eye X: ${x.toFixed(3)}; range: ${min.toFixed(3)} … ${max.toFixed(3)}`;
      }
      update();
    };
    return model;
  } as typeof original;
  createRoot(document.getElementById('root')!).render(<Fixture />);
}
void bootstrap();
