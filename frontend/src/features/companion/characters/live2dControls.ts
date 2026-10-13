import type { Cubism4InternalModel } from 'pixi-live2d-display/cubism4';

export const CONTROL_LABELS = {
  headX: 'Quay đầu ngang', headY: 'Gật đầu', headZ: 'Nghiêng đầu',
  eyeX: 'Mắt nhìn ngang', eyeY: 'Mắt nhìn dọc', mouth: 'Mở miệng',
} as const;
export type Live2DControl = keyof typeof CONTROL_LABELS;
export interface ControlBinding { id: string; inputMin: number; inputMax: number; outputMin: number; outputMax: number }
export type Live2DControls = Partial<Record<Live2DControl, ControlBinding>>;
export interface ControlReview {
  source?: string;
  bindings: { role: Live2DControl; id: string; verified: boolean }[];
  warnings: string[];
}

const INPUTS: Record<string, Live2DControl> = {
  FaceAngleX: 'headX', FaceAngleY: 'headY', FaceAngleZ: 'headZ',
  EyeLeftX: 'eyeX', EyeRightX: 'eyeX', EyeLeftY: 'eyeY', EyeRightY: 'eyeY', MouthOpen: 'mouth',
};

function validBinding(binding: ControlBinding): boolean {
  return typeof binding.id === 'string' && !!binding.id && binding.id.length <= 128 && !/[\x00-\x1f]/.test(binding.id)
    && [binding.inputMin, binding.inputMax, binding.outputMin, binding.outputMax].every(Number.isFinite)
    && Number.isFinite(binding.inputMax - binding.inputMin) && Number.isFinite(binding.outputMax - binding.outputMin)
    && binding.inputMin !== binding.inputMax && binding.outputMin !== binding.outputMax;
}

/** Chỉ nhận các chức năng Peto hỗ trợ; không chạy phím nóng, plugin hoặc thiết lập khác của VTube Studio. */
export function parseControlBindings(parameters: unknown, knownIds?: Set<string>) {
  const controls: Live2DControls = {}, review: ControlReview = { bindings: [], warnings: [] };
  if (!Array.isArray(parameters) || parameters.length > 512) {
    review.warnings.push('Danh sách điều khiển VTube Studio không hợp lệ. Peto dùng điều khiển mặc định.');
    return { controls, review };
  }
  for (const role of Object.keys(CONTROL_LABELS) as Live2DControl[]) {
    const candidates = parameters.filter(item => item && typeof item.Input === 'string' && Object.hasOwn(INPUTS, item.Input) && INPUTS[item.Input] === role);
    if (!candidates.length) continue;
    const bindings = candidates.map(item => ({ id: item.OutputLive2D, inputMin: item.InputRangeLower, inputMax: item.InputRangeUpper,
      outputMin: item.OutputRangeLower, outputMax: item.OutputRangeUpper }));
    if (bindings.some(binding => !validBinding(binding))) {
      review.warnings.push(`${CONTROL_LABELS[role]} có thông số không hợp lệ; chức năng này dùng mặc định.`);
      continue;
    }
    const unique = [...new Map(bindings.map(binding => [JSON.stringify(binding), binding])).values()];
    if (unique.length !== 1) {
      review.warnings.push(`${CONTROL_LABELS[role]} có nhiều ánh xạ khác nhau; chức năng này dùng mặc định.`);
      continue;
    }
    const binding = unique[0] as ControlBinding;
    controls[role] = binding;
    review.bindings.push({ role, id: binding.id, verified: knownIds?.has(binding.id) ?? false });
  }
  const conflicts = review.bindings.filter(binding => review.bindings.some(other => other.role !== binding.role && other.id === binding.id));
  if (conflicts.length) {
    for (const binding of conflicts) delete controls[binding.role];
    review.bindings = review.bindings.filter(binding => !conflicts.includes(binding));
    review.warnings.push('Một thông số được gán cho nhiều chức năng khác nhau; các chức năng đó dùng mặc định.');
  }
  if (review.bindings.some(binding => !binding.verified)) {
    review.warnings.push('Một số thông số điều khiển chưa được xác nhận trong danh sách của model. Peto kiểm tra lại khi tải nhân vật và dùng mặc định nếu thông số không tồn tại.');
  }
  return { controls, review };
}

export function controlValue(binding: ControlBinding, value: number): number {
  const ratio = Math.max(0, Math.min(1, (value - binding.inputMin) / (binding.inputMax - binding.inputMin)));
  return binding.outputMin + ratio * (binding.outputMax - binding.outputMin);
}

const GAZE_PROPERTIES = {
  headX: 'idParamAngleX', headY: 'idParamAngleY', headZ: 'idParamAngleZ', eyeX: 'idParamEyeBallX', eyeY: 'idParamEyeBallY',
} as const;
const STANDARD_IDS: Record<Live2DControl, string> = {
  headX: 'ParamAngleX', headY: 'ParamAngleY', headZ: 'ParamAngleZ', eyeX: 'ParamEyeBallX', eyeY: 'ParamEyeBallY', mouth: 'ParamMouthOpenY',
};

/** Ánh xạ chỉ thuộc một model. Không có cấu hình hợp lệ thì không thay đổi bất kỳ phương thức nào của SDK. */
export function applyLive2DControls(internal: Cubism4InternalModel, controls: Live2DControls) {
  const core = internal.coreModel, accepted: Live2DControls = {};
  for (const role of Object.keys(CONTROL_LABELS) as Live2DControl[]) {
    const binding = controls[role];
    if (!binding || !validBinding(binding) || binding.id === STANDARD_IDS[role]) continue;
    const index = core.getParameterIndex(binding.id);
    if (index >= 0 && index < core.getParameterCount()) accepted[role] = binding;
  }
  const gazeRoles = (Object.keys(GAZE_PROPERTIES) as (keyof typeof GAZE_PROPERTIES)[]).filter(role => accepted[role]);
  if (gazeRoles.length) {
    for (const role of gazeRoles) internal[GAZE_PROPERTIES[role]] = accepted[role]!.id;
    const original = internal.updateFocus;
    internal.updateFocus = function () {
      const bases = gazeRoles.map(role => core.getParameterValueById(accepted[role]!.id));
      original.call(this);
      const { x, y } = this.focusController;
      const inputs = { headX: x * 30, headY: y * 30, headZ: x * y * -30, eyeX: x, eyeY: y };
      gazeRoles.forEach((role, index) => core.setParameterValueById(accepted[role]!.id, bases[index] + controlValue(accepted[role]!, inputs[role])));
    };
  }
  return accepted;
}
