import type { Emotion, StageEmotion } from './characterExpressions';

/**
 * Mặt dựng sẵn cho model Live2D không có tệp biểu cảm (Hiyori mẫu không có tệp nào), dựng từ các thông số chuẩn của
 * Cubism: mắt cười, chân mày, khóe miệng, má hồng, hướng nhìn, góc đầu. Model đặt tên thông số khác thì mặt không đổi.
 */
export interface FacePreset {
  /** Kéo dần về giá trị này (mắt cười, chân mày, khóe miệng, má). */
  set?: Record<string, number>;
  /** Nhân với giá trị đang có, để mắt vẫn chớp được (độ mở mắt). */
  scale?: Record<string, number>;
  /** Cộng thêm (độ), để đầu vẫn nhìn theo con trỏ (góc đầu). */
  add?: Record<string, number>;
  /** Miệng hé sẵn khi Peto im lặng (ngạc nhiên, cười); lúc nói thì khẩu hình theo giọng, lấy giá trị lớn hơn. */
  mouthOpen?: number;
}

// Giá trị chỉnh theo ảnh chụp Hiyori thật (2026-09-27). Hiyori: khóe miệng -2..1, mặc định 1 (vốn đã cười nhẹ); độ mở
// mắt 0..1,2, mặc định 1; má -1..1. Mắt cười kiểu "^ ^" là mắt khép bớt cộng mắt cười, không chỉ mắt cười. Chân mày
// Hiyori nằm dưới tóc mái nên gần như không thấy: mặt phải khác nhau nhờ mắt, miệng, má và góc đầu.
export const FACE_PRESETS: Record<Emotion, FacePreset> = {
  happy: {
    set: { ParamEyeLSmile: 1, ParamEyeRSmile: 1, ParamMouthForm: 1, ParamCheek: 0.8, ParamBrowLY: 0.4, ParamBrowRY: 0.4 },
    scale: { ParamEyeLOpen: 0.3, ParamEyeROpen: 0.3 },
    add: { ParamAngleZ: 9 },
    mouthOpen: 0.3,
  },
  sad: {
    set: { ParamBrowLY: -0.4, ParamBrowRY: -0.4, ParamBrowLAngle: 1, ParamBrowRAngle: 1, ParamMouthForm: -1.8, ParamEyeBallY: -0.8,
      ParamCheek: -0.5 },
    scale: { ParamEyeLOpen: 0.6, ParamEyeROpen: 0.6 },
    add: { ParamAngleY: -20, ParamAngleZ: -5 },
  },
  // Giận nhẹ kiểu dỗi ("hừ"): quay mặt đi, mắt liếc lại, má đỏ; không phải giận thật (prompt cũng dặn vậy).
  angry: {
    set: { ParamBrowLY: -0.7, ParamBrowRY: -0.7, ParamBrowLAngle: -1, ParamBrowRAngle: -1, ParamBrowLForm: -1, ParamBrowRForm: -1,
      ParamMouthForm: -1.5, ParamCheek: 0.9, ParamEyeBallX: 0.6 },
    scale: { ParamEyeLOpen: 0.6, ParamEyeROpen: 0.6 },
    add: { ParamAngleX: -24, ParamAngleZ: -7, ParamAngleY: 3 },
  },
  think: {
    set: { ParamEyeBallX: 0.7, ParamEyeBallY: 0.8, ParamBrowLY: 0.6, ParamBrowRY: -0.2, ParamMouthForm: -0.6 },
    scale: { ParamEyeLOpen: 0.9, ParamEyeROpen: 0.9 },
    add: { ParamAngleZ: -12, ParamAngleX: 14, ParamAngleY: 8 },
  },
  surprised: {
    set: { ParamEyeLOpen: 1.2, ParamEyeROpen: 1.2, ParamBrowLY: 1, ParamBrowRY: 1, ParamMouthForm: -0.4, ParamEyeLSmile: 0, ParamEyeRSmile: 0 },
    add: { ParamAngleY: 14 },
    mouthOpen: 0.5,
  },
  awkward: {
    set: { ParamCheek: 1, ParamEyeLSmile: 0.6, ParamEyeRSmile: 0.6, ParamEyeBallX: -0.8, ParamEyeBallY: -0.5, ParamMouthForm: 0,
      ParamBrowLAngle: 0.7, ParamBrowRAngle: 0.7 },
    scale: { ParamEyeLOpen: 0.75, ParamEyeROpen: 0.75 },
    add: { ParamAngleZ: 10, ParamAngleX: -16, ParamAngleY: -8 },
  },
  question: {
    set: { ParamBrowLY: 0.8, ParamBrowRY: -0.3, ParamMouthForm: -0.5, ParamEyeBallY: 0.3 },
    add: { ParamAngleZ: 20, ParamAngleX: 8 },
  },
  curious: {
    set: { ParamEyeLOpen: 1.15, ParamEyeROpen: 1.15, ParamBrowLY: 0.7, ParamBrowRY: 0.7, ParamMouthForm: 1, ParamEyeBallY: 0.3 },
    add: { ParamAngleY: 12, ParamAngleX: -10, ParamAngleZ: -8 },
    mouthOpen: 0.15,
  },
};

/** Ít nhất ngần này thông số mặt chuẩn thì mới coi là model dùng được mặt dựng sẵn. */
const FACE_PARAMETERS = ['ParamEyeLSmile', 'ParamMouthForm', 'ParamBrowLY', 'ParamCheek', 'ParamEyeLOpen'];

export interface FaceLayer { emotion: Emotion; weight: number }

/** Chuyển mặt mượt: mặt mới hiện dần (~0,15 s), mặt cũ tan dần (~0,5 s), hai mặt có thể chồng nhau lúc giao nhau. */
export class FaceBlend {
  private layers: (FaceLayer & { target: number })[] = [];

  show(emotion: StageEmotion | null) {
    for (const layer of this.layers) layer.target = 0;
    if (!emotion || emotion === 'neutral') return;
    const layer = this.layers.find(item => item.emotion === emotion);
    if (layer) layer.target = 1;
    else this.layers.push({ emotion, weight: 0, target: 1 });
  }

  step(seconds: number): FaceLayer[] {
    const dt = Math.max(0, Math.min(0.1, seconds));
    const rise = 1 - Math.exp(-dt / 0.15), fall = 1 - Math.exp(-dt / 0.5);
    for (const layer of this.layers) layer.weight += (layer.target - layer.weight) * (layer.target > layer.weight ? rise : fall);
    this.layers = this.layers.filter(layer => layer.target > 0 || layer.weight > 0.005);
    return this.layers.map(({ emotion, weight }) => ({ emotion, weight }));
  }
}

export interface CubismCore {
  getParameterIndex(id: string): number;
  getParameterCount(): number;
  getParameterMinimumValue(index: number): number;
  getParameterMaximumValue(index: number): number;
  setParameterValueById(id: string, value: number, weight?: number): void;
  multiplyParameterValueById(id: string, value: number, weight?: number): void;
  addParameterValueById(id: string, value: number, weight?: number): void;
}

/** Áp các lớp mặt lên model mỗi khung hình, sau motion và trước khi model cập nhật (sự kiện beforeModelUpdate). */
export function faceApplier(core: CubismCore) {
  const ranges = new Map<string, [number, number] | null>();
  const range = (id: string) => {
    if (!ranges.has(id)) {
      const index = core.getParameterIndex(id);
      ranges.set(id, index >= 0 && index < core.getParameterCount()
        ? [core.getParameterMinimumValue(index), core.getParameterMaximumValue(index)] : null);
    }
    return ranges.get(id) ?? null;
  };
  return {
    supported: () => FACE_PARAMETERS.filter(id => range(id)).length >= 3,
    /** Áp các lớp; trả về độ mở miệng nền của mặt, để khẩu hình theo giọng lấy giá trị lớn hơn. */
    apply(layers: FaceLayer[]): number {
      let mouth = 0;
      for (const { emotion, weight } of layers) {
        if (weight <= 0) continue;
        const preset = FACE_PRESETS[emotion];
        mouth += (preset.mouthOpen ?? 0) * weight;
        for (const [id, value] of Object.entries(preset.set ?? {})) {
          const bounds = range(id);
          if (bounds) core.setParameterValueById(id, Math.min(bounds[1], Math.max(bounds[0], value)), weight);
        }
        for (const [id, factor] of Object.entries(preset.scale ?? {})) if (range(id)) core.multiplyParameterValueById(id, factor, weight);
        for (const [id, value] of Object.entries(preset.add ?? {})) if (range(id)) core.addParameterValueById(id, value, weight);
      }
      return Math.min(1, mouth);
    },
  };
}

/**
 * Nhân vật VRM: các biểu cảm có sẵn của chuẩn VRM (happy, sad, angry, surprised, relaxed) pha theo cảm xúc, cộng góc
 * nghiêng đầu. Model có biểu cảm tự đặt trùng tên cảm xúc (ví dụ "think") thì dùng biểu cảm đó.
 */
export const VRM_EMOTIONS: Record<Emotion, { expressions: [string, number][]; roll?: number; mouth?: number }> = {
  happy: { expressions: [['happy', 1]], mouth: 0.2 },
  sad: { expressions: [['sad', 1]] },
  angry: { expressions: [['angry', 0.7]] },
  surprised: { expressions: [['surprised', 1]], mouth: 0.4 },
  think: { expressions: [['relaxed', 0.35]], roll: -5 },
  awkward: { expressions: [['happy', 0.3], ['relaxed', 0.4]], roll: 4 },
  question: { expressions: [['surprised', 0.3]], roll: 9 },
  curious: { expressions: [['happy', 0.25], ['surprised', 0.35]], roll: -3 },
};

/** Giá trị từng biểu cảm VRM và góc nghiêng đầu (độ) cho các lớp mặt đang hiện. */
export function vrmFace(layers: FaceLayer[], hasExpression: (name: string) => boolean) {
  const values = new Map<string, number>();
  let roll = 0, mouth = 0;
  for (const { emotion, weight } of layers) {
    const preset = VRM_EMOTIONS[emotion];
    const own = !['happy', 'sad', 'angry', 'surprised'].includes(emotion) && hasExpression(emotion);
    for (const [name, amount] of own ? [[emotion, 1] as [string, number]] : preset.expressions) {
      if (hasExpression(name)) values.set(name, Math.min(1, (values.get(name) ?? 0) + amount * weight));
    }
    roll += (preset.roll ?? 0) * weight;
    mouth += (preset.mouth ?? 0) * weight;
  }
  return { values, roll, mouth: Math.min(1, mouth) };
}
