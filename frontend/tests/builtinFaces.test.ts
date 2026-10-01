import { expect, it, vi } from 'vitest';
import { FACE_PRESETS, FaceBlend, faceApplier, vrmFace, type CubismCore } from '../src/features/companion/characters/builtinFaces';
import { EMOTIONS } from '../src/features/companion/characters/characterExpressions';

function core(ids: string[], range: [number, number] = [-1, 1]): CubismCore & Record<string, ReturnType<typeof vi.fn>> {
  return {
    getParameterIndex: (id: string) => ids.indexOf(id), getParameterCount: () => ids.length,
    getParameterMinimumValue: () => range[0], getParameterMaximumValue: () => range[1],
    setParameterValueById: vi.fn(), multiplyParameterValueById: vi.fn(), addParameterValueById: vi.fn(),
  } as never;
}
const HIYORI = ['ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'ParamCheek', 'ParamEyeLOpen', 'ParamEyeLSmile', 'ParamEyeROpen',
  'ParamEyeRSmile', 'ParamEyeBallX', 'ParamEyeBallY', 'ParamBrowLY', 'ParamBrowRY', 'ParamBrowLAngle', 'ParamBrowRAngle',
  'ParamBrowLForm', 'ParamBrowRForm', 'ParamMouthForm'];

it('has a face for every emotion, built only from the standard parameters Hiyori has', () => {
  for (const emotion of EMOTIONS) {
    const ids = Object.values(FACE_PRESETS[emotion]).flatMap(part => Object.keys(part));
    expect(ids.length).toBeGreaterThan(2);
    expect(ids.filter(id => !HIYORI.includes(id))).toEqual([]);
  }
});

it('fades a face in quickly, out slowly, and cross-fades between two', () => {
  const blend = new FaceBlend();
  blend.show('happy');
  // Một khung dài (tab vừa quay lại) chỉ tính 0,1 s, để mặt không bật phắt lên.
  expect(blend.step(5)[0].weight).toBeCloseTo(1 - Math.exp(-0.1 / 0.15), 3);
  for (let i = 0; i < 20; i++) blend.step(0.05);
  expect(blend.step(0.05)).toEqual([{ emotion: 'happy', weight: expect.closeTo(1, 2) }]);
  blend.show('sad');
  const both = blend.step(0.1);
  expect(both.map(layer => layer.emotion)).toEqual(['happy', 'sad']);
  expect(both[0].weight).toBeGreaterThan(both[1].weight);
  blend.show('neutral');
  for (let i = 0; i < 100; i++) blend.step(0.05);
  expect(blend.step(0.05)).toEqual([]);
});

it('applies blends, keeps blinking by scaling eye openness, adds head tilt and stays inside each range', () => {
  const model = core(HIYORI, [0, 1]);
  const face = faceApplier(model);
  expect(face.supported()).toBe(true);
  // Ngạc nhiên hé miệng sẵn: trả về độ mở nền theo trọng số.
  expect(face.apply([{ emotion: 'surprised', weight: 0.5 }])).toBeCloseTo(0.25);
  // 1,2 vượt biên [0, 1] của model thì bị kẹp về 1.
  expect(model.setParameterValueById).toHaveBeenCalledWith('ParamEyeLOpen', 1, 0.5);
  face.apply([{ emotion: 'sad', weight: 1 }]);
  expect(model.multiplyParameterValueById).toHaveBeenCalledWith('ParamEyeLOpen', 0.6, 1);
  expect(model.addParameterValueById).toHaveBeenCalledWith('ParamAngleY', -20, 1);
  expect(model.setParameterValueById).toHaveBeenCalledWith('ParamMouthForm', 0, 1);
});

it('skips parameters a model does not have and refuses models without a face', () => {
  const model = core(['ParamAngleX', 'ParamAngleY', 'ParamAngleZ']);
  const face = faceApplier(model);
  expect(face.supported()).toBe(false);
  face.apply([{ emotion: 'happy', weight: 1 }]);
  expect(model.setParameterValueById).not.toHaveBeenCalled();
  expect(model.addParameterValueById).toHaveBeenCalledWith('ParamAngleZ', 9, 1);
});

it('maps emotions onto VRM presets, preferring an expression the model defines itself', () => {
  const presets = new Set(['happy', 'sad', 'angry', 'surprised', 'relaxed']);
  expect(vrmFace([{ emotion: 'happy', weight: 0.5 }], name => presets.has(name))).toEqual(
    { values: new Map([['happy', 0.5]]), roll: 0, mouth: 0.1 });
  const think = vrmFace([{ emotion: 'think', weight: 1 }], name => presets.has(name));
  expect(think.values).toEqual(new Map([['relaxed', 0.35]]));
  expect(think.roll).toBe(-5);
  expect(vrmFace([{ emotion: 'think', weight: 1 }], name => name === 'think').values).toEqual(new Map([['think', 1]]));
  expect(vrmFace([{ emotion: 'curious', weight: 1 }], () => false).values.size).toBe(0);
});
