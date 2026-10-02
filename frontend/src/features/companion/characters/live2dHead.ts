import type { HeadBox } from './stageInteraction';

interface HeadSource {
  hitAreas?: Record<string, { index: number }>;
  getDrawableBounds(index: number): HeadBox;
  coreModel: {
    update(): void;
    getDrawableCount?(): number;
    getParameterCount(): number;
    getParameterIndex(id: string): number;
    getParameterValueById?(id: string): number;
    setParameterValueById(id: string, value: number): void;
    getParameterMinimumValue?(index: number): number;
    getParameterMaximumValue?(index: number): number;
    getParameterValueByIndex?(index: number): number;
    setParameterValueByIndex?(index: number, value: number): void;
  };
  physics?: { evaluate(core: HeadSource['coreModel'], seconds: number): void };
}

/** Theo AIRI head-anchor.ts: vùng Head/Face, hoặc các drawable bị góc đầu làm dịch chuyển. Chọn một lần khi tải model. */
export function trackLive2DHead(source: HeadSource) {
  const core = source.coreModel;
  let tracked: number[] = [];
  const area = Object.entries(source.hitAreas ?? {}).find(([name]) => /^(head|face)$/i.test(name))?.[1];
  if (area) tracked = [area.index];
  else if (core.getDrawableCount && core.getParameterValueById && core.getParameterMinimumValue && core.getParameterMaximumValue) {
    const count = core.getDrawableCount();
    const angles = ['ParamAngleX', 'ParamAngleY', 'ParamAngleZ'].map(id => ({ id, index: core.getParameterIndex(id) }))
      .filter(({ index }) => index >= 0 && index < core.getParameterCount());
    if (count && angles.length) {
      const held = angles.map(({ id }) => core.getParameterValueById!(id));
      const parameters = core.getParameterValueByIndex && core.setParameterValueByIndex
        ? Array.from({ length: core.getParameterCount() }, (_, index) => core.getParameterValueByIndex!(index)) : null;
      const restore = () => {
        if (parameters) parameters.forEach((value, index) => core.setParameterValueByIndex!(index, value));
        else angles.forEach(({ id }, i) => core.setParameterValueById(id, held[i]));
      };
      const settle = () => {
        for (let i = 0; i < 18; i++) source.physics?.evaluate(core, 1 / 30);
        core.update();
      };
      try {
        settle();
        const resting = Array.from({ length: count }, (_, index) => ({ ...source.getDrawableBounds(index) }));
        angles.forEach(({ id, index }, i) => {
          const min = core.getParameterMinimumValue!(index), max = core.getParameterMaximumValue!(index);
          core.setParameterValueById(id, Math.abs(max - held[i]) >= Math.abs(held[i] - min) ? max : min);
        });
        settle();
        const travelled = resting.map((before, index) => {
          const after = source.getDrawableBounds(index);
          return Math.hypot(after.x - before.x, after.y - before.y)
            + Math.hypot(after.width - before.width, after.height - before.height);
        });
        const largest = Math.max(...travelled);
        if (largest > 0) tracked = travelled.flatMap((distance, index) => distance >= largest * 0.2 ? [index] : []);
      } finally {
        restore(); settle(); restore(); core.update();
      }
    }
  }
  return () => {
    let head: HeadBox | null = null;
    for (const index of tracked) {
      const rect = source.getDrawableBounds(index);
      if (!(rect.width > 0 && rect.height > 0)) continue;
      if (!head) head = { ...rect };
      else {
        const right = Math.max(head.x + head.width, rect.x + rect.width), bottom = Math.max(head.y + head.height, rect.y + rect.height);
        head.x = Math.min(head.x, rect.x); head.y = Math.min(head.y, rect.y);
        head.width = right - head.x; head.height = bottom - head.y;
      }
    }
    return head;
  };
}
