import { fitMagic, type MagicModel } from './magicModel';
import calmData from './idle-calm.json';
import excitedData from './speaking-excited.json';

/**
 * Hai bộ chuyển động có sẵn của AIRI, chỉ tải khi một nhân vật bật MAGIC (Live2DStage nạp tệp này bằng import động).
 * Bản ghi đã được lấy mẫu lại 30 Hz đúng như AIRI làm trước khi học, nên nhẹ hơn tệp gốc nhiều (17 KB + 21 KB nén).
 */
export interface MagicProfiles { calm: MagicModel; excited: MagicModel; fitMs: number }

type Dataset = { sampleRateHz: number; frames: number[][] };

/** Thông số AIRI dùng khi chạy thật (`useLive2DMotionMagic`): VAR bậc 20, ridge 0,001. */
const FIT = { order: 20, ridge: 0.001 };

export function fitProfiles(): MagicProfiles {
  const started = performance.now();
  const learn = (data: Dataset) => fitMagic({ sampleRateHz: data.sampleRateHz, frames: data.frames }, FIT);
  const calm = learn(calmData as Dataset);
  const excited = learn(excitedData as Dataset);
  return { calm, excited, fitMs: performance.now() - started };
}
