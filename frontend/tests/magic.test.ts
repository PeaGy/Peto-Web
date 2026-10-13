import { beforeEach, expect, it, vi } from 'vitest';
import { fitMagic, seededRandom } from '../src/features/companion/characters/magic/magicModel';
import { fitProfiles } from '../src/features/companion/characters/magic/magicProfiles';
import { MagicRuntime, OutputFilter, POSE_AXES, magicOffset, magicWriter, neutralPose } from '../src/features/companion/characters/magic/magicMotion';
import { DEFAULT_MAGIC, readMagic, watchMagic, writeMagic } from '../src/features/companion/characters/magic/magicSettings';

beforeEach(() => localStorage.clear());

/** Bản ghi giả: hai kênh trùng nhau (như mắt và đầu trong bản ghi AIRI), một kênh riêng, một kênh đứng yên. */
function sequence(length = 400) {
  const random = seededRandom(7);
  let a = 0, b = 0;
  const frames = Array.from({ length }, (_, i) => {
    a = 0.9 * a + 0.1 * Math.sin(i / 9) + (random() - 0.5) * 0.05;
    b = 0.8 * b + 0.2 * Math.cos(i / 5) + (random() - 0.5) * 0.05;
    return [a, a, b, 0.25];
  });
  return { sampleRateHz: 30, frames };
}

it('học VAR rồi sinh chuyển động: cùng hạt giống thì giống hệt, giữ trong khoảng của bản ghi, kênh trùng đi cùng nhau', () => {
  const data = sequence();
  const model = fitMagic(data, { order: 8, ridge: 0.001 });
  const one = model.toGenerator(42), two = model.toGenerator(42), other = model.toGenerator(43);
  const a = Array.from({ length: 200 }, () => one.next(1.15));
  expect(Array.from({ length: 200 }, () => two.next(1.15))).toEqual(a);
  expect(Array.from({ length: 200 }, () => other.next(1.15))).not.toEqual(a);
  const min = (index: number) => Math.min(...data.frames.map(frame => frame[index]));
  const max = (index: number) => Math.max(...data.frames.map(frame => frame[index]));
  for (const frame of a) {
    expect(frame[0]).toBe(frame[1]);
    expect(frame[3]).toBeCloseTo(0.25);
    for (const index of [0, 2]) {
      expect(frame[index]).toBeGreaterThanOrEqual(min(index));
      expect(frame[index]).toBeLessThanOrEqual(max(index));
    }
  }
  expect(new Set(a.map(frame => frame[0].toFixed(4))).size).toBeGreaterThan(50);
});

it('từ chối bản ghi quá ngắn hoặc không chuyển động', () => {
  expect(() => fitMagic({ sampleRateHz: 30, frames: [[0, 1], [0, 1], [0, 1]] }, { order: 2, ridge: 0.001 })).toThrow('quá ngắn');
  expect(() => fitMagic({ sampleRateHz: 30, frames: sequence(5).frames }, { order: 8, ridge: 0.001 })).toThrow('quá ngắn');
  expect(() => fitMagic({ sampleRateHz: 0, frames: sequence().frames }, { order: 8, ridge: 0.001 })).toThrow('không hợp lệ');
});

it('học được hai bộ chuyển động thật của AIRI và sinh 13 kênh hữu hạn', () => {
  const profiles = fitProfiles();
  for (const model of [profiles.calm, profiles.excited]) {
    const generator = model.toGenerator(1);
    for (let i = 0; i < 300; i++) {
      const frame = generator.next(1.15);
      expect(frame).toHaveLength(POSE_AXES.length);
      expect(frame.every(Number.isFinite)).toBe(true);
    }
  }
});

it('bộ lọc giữ kênh đổi dưới ngưỡng và làm mượt kênh đổi lớn', () => {
  const filter = new OutputFilter();
  expect(filter.process({ ...neutralPose(), headX: 0 }).headX).toBe(0);
  expect(filter.process({ ...neutralPose(), headX: 0.05 }).headX).toBe(0);
  const moved = filter.process({ ...neutralPose(), headX: 1 }).headX;
  expect(moved).toBeCloseTo(0.2);
});

it('nhận quyền dần khi bật, theo lúc nói ở bộ "Theo lúc nói", nhả quyền hẳn khi tắt', () => {
  const profiles = fitProfiles();
  const runtime = new MagicRuntime();
  const speech = { ...DEFAULT_MAGIC, driver: 'magic' as const, profile: 'speech' as const };
  runtime.step(speech, profiles, false, false, 0.033);
  expect(runtime.owned).toBe(0);
  const heads = new Set<string>();
  let together = 0;
  for (let i = 0; i < 120; i++) {
    runtime.step(speech, profiles, true, i >= 60, 1 / 30);
    heads.add(runtime.pose.headX.toFixed(3));
    together += runtime.pose.eyeX * runtime.pose.headX;
  }
  expect(runtime.owned).toBeGreaterThan(0.99);
  expect(heads.size).toBeGreaterThan(10);
  // Mắt nhìn thẳng: mắt đi ngược chiều đầu.
  expect(together).toBeLessThan(0);
  expect(runtime.pose.mouthOpen).toBeCloseTo(0, 3);
  for (let i = 0; i < 60; i++) runtime.step(speech, profiles, false, false, 1 / 30);
  expect(runtime.owned).toBe(0);
});

it('ghi thông số Live2D chuẩn, theo ánh xạ riêng của model, và trả thông số về mặc định khi nhả quyền', () => {
  const ids = ['ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'ParamBodyAngleX', 'ParamEyeBallX', 'ParamMouthForm', 'ParamEyeLOpen', 'ParamEyeROpen', 'HeadIn'];
  const values = new Map(ids.map(id => [id, id === 'ParamMouthForm' ? 1 : id.includes('Open') ? 1 : 0]));
  const core = {
    getParameterIndex: (id: string) => ids.indexOf(id), getParameterCount: () => ids.length,
    getParameterValueById: (id: string) => values.get(id)!,
    setParameterValueById: vi.fn((id: string, value: number) => { values.set(id, value); }),
    getParameterDefaultValue: (index: number) => ids[index] === 'ParamMouthForm' ? 1 : 0,
  };
  const pose = { ...neutralPose(), headX: 0.5, headY: -0.2, bodyX: 0.3, eyeX: -0.5, mouthForm: -0.4, eyeSquint: 0.5, offsetX: 1, offsetY: 0.5 };
  const writer = magicWriter(core);
  writer.body(pose, 1, true);
  expect(values.get('ParamAngleX')).toBe(15);
  expect(values.get('ParamAngleY')).toBeCloseTo(-6);
  expect(values.get('ParamBodyAngleX')).toBeCloseTo(3);
  expect(values.get('ParamEyeBallX')).toBe(-0.5);
  expect(values.get('ParamMouthForm')).toBe(-0.4);
  expect(core.setParameterValueById.mock.calls.some(([id]) => id === 'ParamBodyAngleY')).toBe(false);
  writer.squint(pose, 1);
  expect(values.get('ParamEyeLOpen')).toBe(0.5);
  // Tắt dáng miệng: về dáng mặc định của model.
  writer.body(pose, 1, false);
  expect(values.get('ParamMouthForm')).toBe(1);
  // Nhả quyền: thông số không ai ghi lại về mặc định, thông số chuyển động thường vừa ghi thì giữ làm gốc.
  writer.body(pose, 1, true);
  values.set('ParamAngleY', 4);
  for (let weight = 0.9; weight > 0; weight -= 0.1) writer.body(pose, Number(weight.toFixed(2)), true);
  writer.body(pose, 0, true);
  expect(values.get('ParamAngleX')).toBeCloseTo(1.5);
  expect(Math.abs(values.get('ParamMouthForm')! - 1)).toBeLessThan(0.15);
  const mapped = magicWriter(core, { headX: { id: 'HeadIn', inputMin: -30, inputMax: 30, outputMin: -10, outputMax: 10 } });
  mapped.body(pose, 1, true);
  expect(values.get('HeadIn')).toBeCloseTo(5);
  expect(magicOffset(pose, 0.5)).toEqual({ x: 10, y: -10 });
});

it('cài đặt MAGIC mặc định là Hiện tại, riêng từng nhân vật, sửa giá trị hỏng', () => {
  expect(readMagic('a')).toEqual(DEFAULT_MAGIC);
  expect(DEFAULT_MAGIC.driver).toBe('universal');
  const listener = vi.fn();
  const stop = watchMagic('a', listener);
  writeMagic('b', { ...DEFAULT_MAGIC, driver: 'magic' });
  expect(listener).not.toHaveBeenCalled();
  writeMagic('a', { ...DEFAULT_MAGIC, driver: 'magic', profile: 'speech', mouthForm: false });
  expect(listener).toHaveBeenCalledWith({ driver: 'magic', profile: 'speech', viewTarget: true, mouthForm: false });
  stop();
  localStorage.setItem('peto-character-magic:c', JSON.stringify({ driver: 'x', profile: 'loud', viewTarget: 'yes' }));
  expect(readMagic('c')).toEqual(DEFAULT_MAGIC);
  localStorage.setItem('peto-character-magic:d', 'hỏng');
  expect(readMagic('d')).toEqual(DEFAULT_MAGIC);
});
