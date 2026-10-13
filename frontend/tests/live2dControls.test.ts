import { expect, it, vi } from 'vitest';
import type { Cubism4InternalModel } from 'pixi-live2d-display/cubism4';
import { applyLive2DControls, controlValue, parseControlBindings, type ControlBinding } from '../src/features/companion/characters/live2dControls';

const binding: ControlBinding = { id: 'HeadInput', inputMin: -30, inputMax: 30, outputMin: -20, outputMax: 20 };
const parameter = (Input: string, OutputLive2D = 'HeadInput') => ({ Input, OutputLive2D,
  InputRangeLower: -30, InputRangeUpper: 30, OutputRangeLower: -20, OutputRangeUpper: 20 });

it('chỉ nhận chức năng đã hỗ trợ và giữ chiều đảo cùng khoảng điều khiển', () => {
  const result = parseControlBindings([parameter('FaceAngleX'), parameter('BrowLeftY', 'BrowInput'),
    { ...parameter('EyeLeftX', 'EyeInput'), InputRangeLower: -1, InputRangeUpper: 1, OutputRangeLower: 1, OutputRangeUpper: -1 }], new Set(['HeadInput', 'EyeInput']));
  expect(Object.keys(result.controls)).toEqual(['headX', 'eyeX']);
  expect(result.review.warnings).toEqual([]);
  expect(controlValue(result.controls.eyeX!, 1)).toBe(-1);
  expect(controlValue(binding, 100)).toBe(20);
  expect(parseControlBindings([{ ...parameter('FaceAngleX'), OutputRangeLower: -1e308, OutputRangeUpper: 1e308 }]).controls).toEqual({});
});

it('không tự chọn ánh xạ xung đột hoặc thông số thiếu; danh sách hiển thị thiếu chỉ đánh dấu chờ xác nhận', () => {
  const result = parseControlBindings([parameter('FaceAngleX'), parameter('FaceAngleY', 'HeadInput'),
    parameter('EyeLeftX', 'Left'), parameter('EyeRightX', 'Right'), { ...parameter('MouthOpen'), InputRangeUpper: -30 }]);
  expect(result.controls).toEqual({});
  expect(result.review.warnings).toHaveLength(3);
  const pending = parseControlBindings([parameter('FaceAngleX')], new Set());
  expect(pending.controls.headX).toEqual(binding);
  expect(pending.review.bindings[0].verified).toBe(false);
});

function runtime(ids: string[]) {
  const values = new Map(ids.map(id => [id, 0]));
  const internal = {
    idParamAngleX: 'ParamAngleX', idParamAngleY: 'ParamAngleY', idParamAngleZ: 'ParamAngleZ', idParamEyeBallX: 'ParamEyeBallX', idParamEyeBallY: 'ParamEyeBallY',
    focusController: { x: 0.5, y: 0 },
    coreModel: { getParameterIndex: (id: string) => ids.includes(id) ? ids.indexOf(id) : ids.length,
      getParameterCount: () => ids.length, getParameterValueById: (id: string) => values.get(id) ?? 0,
      setParameterValueById: vi.fn((id: string, value: number) => values.set(id, value)) },
    updateFocus() { this.coreModel.setParameterValueById(this.idParamAngleX, (values.get(this.idParamAngleX) ?? 0) + this.focusController.x * 30); },
  };
  return { internal, values, model: internal as unknown as Cubism4InternalModel };
}

it('không thay phương thức hay ID của model chuẩn và bỏ qua ID không tồn tại trong MOC thật', () => {
  const { internal, model } = runtime(['ParamAngleX']);
  const original = internal.updateFocus;
  expect(applyLive2DControls(model, {})).toEqual({});
  expect(applyLive2DControls(model, { headX: binding })).toEqual({});
  expect(applyLive2DControls(model, { headX: { ...binding, id: 'ParamAngleX' } })).toEqual({});
  expect(internal.updateFocus).toBe(original);
  expect(internal.idParamAngleX).toBe('ParamAngleX');
});

it('đưa góc nhìn vào tham số riêng trước vật lý, giữ nền motion và không đổi model khác', () => {
  const custom = runtime(['ParamAngleX', 'HeadInput']), standard = runtime(['ParamAngleX']);
  custom.values.set('HeadInput', 2);
  applyLive2DControls(custom.model, { headX: binding });
  custom.internal.updateFocus(); standard.internal.updateFocus();
  expect(custom.values.get('HeadInput')).toBe(12);
  expect(custom.values.get('ParamAngleX')).toBe(0);
  expect(standard.values.get('ParamAngleX')).toBe(15);
});
