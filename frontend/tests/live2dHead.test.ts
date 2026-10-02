import { expect, it, vi } from 'vitest';
import { trackLive2DHead } from '../src/features/companion/characters/live2dHead';

function rig(angle = 0) {
  const values = [angle, 0.4];
  const coreModel = {
    update: vi.fn(), getDrawableCount: () => 3, getParameterCount: () => 2,
    getParameterIndex: (id: string) => id === 'ParamAngleX' ? 0 : 2,
    getParameterValueById: () => values[0], setParameterValueById: (_id: string, value: number) => { values[0] = value; },
    getParameterMinimumValue: () => -30, getParameterMaximumValue: () => 30,
    getParameterValueByIndex: (index: number) => values[index],
    setParameterValueByIndex: (index: number, value: number) => { values[index] = value; },
  };
  const source = { hitAreas: { Body: { index: 0 } }, coreModel,
    getDrawableBounds: (index: number) => index === 0 ? { x: 0, y: 0, width: 400, height: 1000 }
      : { x: 100 + values[0] * (index === 1 ? 1 : 0.5), y: 30, width: 100, height: 100 },
    physics: { evaluate: () => { values[1] += 0.1; } },
  };
  return { source, values };
}

it('model chỉ có Body tìm các phần đầu chuyển động, bám vị trí mới và khôi phục mọi tham số trước khi hiển thị', () => {
  const { source, values } = rig(30);
  const read = trackLive2DHead(source);
  expect(values).toEqual([30, 0.4]);
  expect(read()).toEqual({ x: 115, y: 30, width: 115, height: 100 });
  values[0] = -20;
  expect(read()).toEqual({ x: 80, y: 30, width: 110, height: 100 });
  expect(source.coreModel.update).toHaveBeenCalled();
});

it('vùng Head có sẵn được dùng trực tiếp, không xoay model để dò', () => {
  const { source, values } = rig();
  const read = trackLive2DHead({ ...source, hitAreas: { Head: { index: 1 } } });
  expect(read()).toEqual({ x: 100, y: 30, width: 100, height: 100 });
  expect(source.coreModel.update).not.toHaveBeenCalled(); expect(values).toEqual([0, 0.4]);
});

it('model không có góc đầu không nhận Body làm đầu; lỗi dò vẫn trả tham số về giá trị cũ', () => {
  const { source, values } = rig();
  expect(trackLive2DHead({ ...source, coreModel: { ...source.coreModel, getParameterIndex: () => 2 } })()).toBeNull();
  const getBounds = source.getDrawableBounds;
  source.getDrawableBounds = index => { if (values[0] !== 0) throw new Error('Lỗi hình học'); return getBounds(index); };
  expect(() => trackLive2DHead(source)).toThrow('Lỗi hình học');
  expect(values).toEqual([0, 0.4]);
});
