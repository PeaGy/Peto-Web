import type { MagicGenerator } from './magicModel';
import type { MagicProfiles } from './magicProfiles';
import type { MagicSettings } from './magicSettings';
import { controlValue, type ControlBinding, type Live2DControls } from '../live2dControls';

/**
 * Chạy MAGIC trên sân khấu Live2D. Theo AIRI (`model-driver-magic-live2d`, `useLive2DMotionMagic`,
 * `motion-control-spring.ts`, `useMotionUpdatePluginManualControl`; Copyright (c) 2024-PRESENT Neko Ayaka, MIT, xem
 * AIRI-LICENSE.txt): sinh tư thế 30 lần mỗi giây, lọc (bỏ thay đổi dưới ngưỡng rồi làm mượt), lò xo kéo tư thế thật theo
 * mỗi khung hình, rồi ghi vào thông số Live2D chuẩn.
 *
 * Khác AIRI: sinh theo đồng hồ của sân khấu thay vì vòng requestAnimationFrame riêng (dừng cùng sân khấu khi ẩn trang); hai bộ
 * chạy song song để trộn theo lúc nói ("Theo lúc nói"); nhận và nhả quyền điều khiển dần trong khoảng 0,3 giây; theo ánh xạ
 * điều khiển riêng của model nhập (`live2dControls.ts`).
 */
export const POSE_AXES = ['eyeX', 'eyeY', 'eyeSquint', 'headX', 'headY', 'headZ', 'bodyX', 'bodyY', 'bodyZ', 'mouthForm',
  'mouthOpen', 'offsetX', 'offsetY'] as const;
export type PoseAxis = typeof POSE_AXES[number];
export type Pose = Record<PoseAxis, number>;
export const neutralPose = (): Pose => Object.fromEntries(POSE_AXES.map(axis => [axis, 0])) as Pose;

let loading: Promise<MagicProfiles> | null = null;
/** Tải và học hai bộ chuyển động một lần cho cả trang; lỗi thì lần sau thử lại. */
export function loadMagic(): Promise<MagicProfiles> {
  loading ??= import('./magicProfiles').then(module => module.fitProfiles()).catch(error => { loading = null; throw error; });
  return loading;
}

/** Bộ lọc đầu ra của AIRI: kênh đổi dưới `cutoff` thì giữ đích cũ, rồi làm mượt mũ với hệ số `smoothing`. */
export class OutputFilter {
  private accepted: Pose | null = null;
  private output: Pose | null = null;
  constructor(private cutoff = 0.0575, private smoothing = 0.8) {}
  reset() { this.accepted = null; this.output = null; }
  process(input: Pose): Pose {
    if (!this.accepted || !this.output) {
      this.accepted = { ...input };
      this.output = { ...input };
      return { ...input };
    }
    const accepted = { ...this.accepted }, output = { ...this.output };
    for (const axis of POSE_AXES) {
      if (Math.abs(input[axis] - accepted[axis]) >= this.cutoff) accepted[axis] = input[axis];
      output[axis] = this.output[axis] * this.smoothing + accepted[axis] * (1 - this.smoothing);
    }
    this.accepted = accepted;
    this.output = output;
    return { ...output };
  }
}

/** Một bộ chuyển động đang sinh: đủ khung 30 Hz theo thời gian đã trôi (tối đa 250 ms một lần), lọc khung mới nhất. */
export class MagicSource {
  private generator: MagicGenerator | null = null;
  private filter = new OutputFilter();
  private elapsed = 0;
  pose = neutralPose();
  get playing() { return this.generator !== null; }
  start(generator: MagicGenerator) {
    this.generator = generator;
    this.elapsed = 0;
    this.filter.reset();
    this.pose = this.apply(this.generate());
  }
  stop() { this.generator = null; this.filter.reset(); }
  step(deltaMs: number) {
    if (!this.generator) return;
    const interval = 1000 / this.generator.sampleRateHz;
    this.elapsed += Math.min(250, Math.max(0, deltaMs));
    let next: Pose | null = null;
    while (this.elapsed >= interval) { next = this.generate(); this.elapsed -= interval; }
    if (next) this.pose = this.apply(next);
  }
  private generate(): Pose {
    // Nhiễu 1,15 như cài đặt VAR của AIRI.
    const values = this.generator!.next(1.15);
    return Object.fromEntries(POSE_AXES.map((axis, index) => [axis, values[index] ?? 0])) as Pose;
  }
  private apply(pose: Pose): Pose {
    // AIRI mặc định bỏ độ mở miệng sinh ra để khẩu hình theo giọng đọc.
    return { ...this.filter.process(pose), mouthOpen: 0 };
  }
}

/** Lò xo của AIRI với follow 1, inertia 0,6; bước con 1/120 giây để chạy giống nhau ở 24, 30 hay 60 FPS. */
export class PoseSpring {
  private pose = neutralPose();
  private velocity = neutralPose();
  step(target: Pose, deltaSeconds: number): Pose {
    const stiffness = 30 + 190, mass = 0.75 + 0.6 * 2.25;
    const damping = 2 * (1 - 0.6 * 0.75) * Math.sqrt(stiffness * mass);
    const bounded = Math.min(Math.max(Number.isFinite(deltaSeconds) ? deltaSeconds : 0, 0), 0.05);
    const steps = Math.max(1, Math.ceil(bounded * 120));
    const dt = bounded / steps;
    for (let i = 0; i < steps; i++) {
      for (const axis of POSE_AXES) {
        const acceleration = (stiffness * (target[axis] - this.pose[axis]) - damping * this.velocity[axis]) / mass;
        this.velocity[axis] += acceleration * dt;
        this.pose[axis] += this.velocity[axis] * dt;
      }
    }
    return { ...this.pose };
  }
}

const ease = (value: number, target: number, dt: number, tau: number) => value + (target - value) * (1 - Math.exp(-dt / tau));
const seed = () => Math.floor(Math.random() * 0x1_0000_0000) >>> 0;

export class MagicRuntime {
  private calm = new MagicSource();
  private excited = new MagicSource();
  private weight = 0;
  private spring = new PoseSpring();
  /** Tư thế đang áp dụng và mức MAGIC nắm quyền, 0..1 (0 là chuyển động hiện tại toàn quyền). */
  pose = neutralPose();
  owned = 0;

  step(settings: MagicSettings, profiles: MagicProfiles | null, active: boolean, speaking: boolean, deltaSeconds: number) {
    const dt = Math.max(0, Math.min(0.25, Number.isFinite(deltaSeconds) ? deltaSeconds : 0));
    const target = settings.profile === 'calm' ? 0 : settings.profile === 'excited' ? 1 : speaking ? 1 : 0;
    if (active && profiles && !this.calm.playing) {
      this.calm.start(profiles.calm.toGenerator(seed()));
      this.excited.start(profiles.excited.toGenerator(seed()));
      this.weight = target;
    }
    this.calm.step(dt * 1000);
    this.excited.step(dt * 1000);
    this.owned = ease(this.owned, active ? 1 : 0, dt, 0.3);
    if (!active && this.owned < 0.002) {
      this.owned = 0;
      this.calm.stop();
      this.excited.stop();
    }
    // Vào lúc nói nhanh, về bình thản chậm hơn để không giật giữa hai câu.
    this.weight = ease(this.weight, target, dt, target > this.weight ? 0.35 : 0.9);
    const blended = neutralPose();
    for (const axis of POSE_AXES) blended[axis] = this.calm.pose[axis] + (this.excited.pose[axis] - this.calm.pose[axis]) * this.weight;
    if (settings.viewTarget) {
      // `applyLive2DMotionViewTarget` của AIRI: trừ chuyển động đầu khỏi mắt để mắt vẫn nhìn về phía người xem.
      blended.eyeX = Math.max(-1, Math.min(1, -blended.headX));
      blended.eyeY = Math.max(-1, Math.min(1, -blended.headY));
    }
    this.pose = this.spring.step(blended, dt);
  }
}

type Core = {
  getParameterIndex?: (id: string) => number;
  getParameterCount: () => number;
  getParameterValueById: (id: string) => number;
  setParameterValueById: (id: string, value: number) => void;
  getParameterDefaultValue?: (index: number) => number;
};

/**
 * Ghi tư thế MAGIC vào model như `useMotionUpdatePluginManualControl` của AIRI (đầu ×30°, thân ×10°). Model nhập có ánh xạ
 * đầu/mắt riêng thì ghi vào thông số đã ánh xạ. Model thiếu thông số nào thì bỏ qua.
 */
export function magicWriter(core: Core, controls?: Live2DControls) {
  const has = (id: string) => {
    const index = core.getParameterIndex?.(id);
    return index !== undefined && index >= 0 && index < core.getParameterCount();
  };
  const target = (binding: ControlBinding | undefined, standard: string, scale: number) => binding && has(binding.id)
    ? { id: binding.id, value: (input: number) => controlValue(binding, input * scale) }
    : has(standard) ? { id: standard, value: (input: number) => input * scale } : null;
  const head = [target(controls?.headX, 'ParamAngleX', 30), target(controls?.headY, 'ParamAngleY', 30), target(controls?.headZ, 'ParamAngleZ', 30)];
  const eyes = [target(controls?.eyeX, 'ParamEyeBallX', 1), target(controls?.eyeY, 'ParamEyeBallY', 1)];
  const body = ['ParamBodyAngleX', 'ParamBodyAngleY', 'ParamBodyAngleZ'].map(id => target(undefined, id, 10));
  const mouthForm = has('ParamMouthForm') ? 'ParamMouthForm' : null;
  const lids = ['ParamEyeLOpen', 'ParamEyeROpen'].filter(has);
  const defaults = new Map<string, number>();
  const defaultOf = (id: string) => {
    if (!defaults.has(id)) defaults.set(id, core.getParameterDefaultValue?.(core.getParameterIndex!(id)) ?? 0);
    return defaults.get(id)!;
  };
  // Số ghi ở đây được model lưu lại sang khung sau. Lúc nhả quyền, thông số nào chuyển động thường không ghi lại (vẫn đúng
  // bằng số MAGIC ghi lần trước) thì kéo về mặc định của model, để về "Hiện tại" không kẹt góc đầu hay dáng miệng.
  const written = new Map<string, number>();
  let lastWeight = 0;
  let releasing = false;
  const set = (id: string, value: number, weight: number) => {
    const current = core.getParameterValueById(id);
    const untouched = written.has(id) && Math.abs(current - written.get(id)!) < 1e-6;
    const base = releasing && untouched ? defaultOf(id) : current;
    const next = weight >= 1 ? value : base + (value - base) * weight;
    core.setParameterValueById(id, next);
    written.set(id, next);
  };
  return {
    /** Gọi ở `afterMotionUpdate`: trước vật lý, để tóc và váy đung đưa theo đầu như ở AIRI. */
    body(pose: Pose, weight: number, ownMouthForm: boolean) {
      releasing = weight < lastWeight;
      lastWeight = weight;
      if (weight <= 0) { written.clear(); return; }
      [pose.headX, pose.headY, pose.headZ].forEach((value, i) => { const item = head[i]; if (item) set(item.id, item.value(value), weight); });
      [pose.eyeX, pose.eyeY].forEach((value, i) => { const item = eyes[i]; if (item) set(item.id, item.value(value), weight); });
      [pose.bodyX, pose.bodyY, pose.bodyZ].forEach((value, i) => { const item = body[i]; if (item) set(item.id, item.value(value), weight); });
      // Tắt "MAGIC điều khiển dáng miệng" thì giữ dáng miệng mặc định của model (Hiyori cười sẵn), vì chuyển động chờ đã tắt.
      if (mouthForm) set(mouthForm, ownMouthForm ? pose.mouthForm : defaultOf(mouthForm), weight);
    },
    /** Gọi ở `beforeModelUpdate`, sau chớp mắt: nheo bằng cách nhân độ mở mắt, nên mắt vẫn chớp (như AIRI). */
    squint(pose: Pose, weight: number) {
      if (weight <= 0) return;
      const open = 1 - Math.max(0, Math.min(1, pose.eyeSquint)) * weight;
      for (const id of lids) core.setParameterValueById(id, core.getParameterValueById(id) * open);
    },
  };
}

/** Dịch cả model như AIRI (`getLive2DMotionControlModelOffset`): ngang tối đa 20 px, dọc 40 px. */
export function magicOffset(pose: Pose, weight: number) {
  return { x: pose.offsetX * 20 * weight, y: -pose.offsetY * 40 * weight };
}
