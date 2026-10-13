/**
 * MAGIC ("Markovian Animation Generator with Illusory Conditioning"): học kiểu chuyển động từ một bản ghi rồi sinh chuyển
 * động mới vô tận, không lặp lại bản ghi. Chuyển từ Project AIRI (PR #2376, `packages/motion-driver-magic`, commit b60533b).
 * Copyright (c) 2024-PRESENT Neko Ayaka. Giấy phép MIT, xem AIRI-LICENSE.txt cùng thư mục.
 *
 * Chỉ giữ VAR (tự hồi quy vector, hồi quy ridge): bản chạy thật của AIRI dùng VAR, AR-HMM chỉ có trong công cụ dev. Thuật
 * toán giữ nguyên; Peto đổi chú thích sang tiếng Việt và gộp các tệp nhỏ lại.
 */

/** Một bản ghi lấy mẫu đều, sẵn sàng để học. */
export interface TrainingSequence {
  sampleRateHz: number;
  frames: readonly (readonly number[])[];
}

/** Một dòng khung hình sinh ra có hạt giống riêng. */
export interface MagicGenerator {
  readonly sampleRateHz: number;
  next: (noiseScale?: number) => number[];
}

export interface MagicModel {
  readonly sampleRateHz: number;
  /** Tạo một dòng sinh độc lập; hai hạt giống khác nhau cho hai chuyển động khác nhau. */
  toGenerator: (seed: number) => MagicGenerator;
}

/** Một kênh có thay đổi trong bản ghi, gộp cả các kênh trùng hệt nó (bản ghi của AIRI cho mắt, đầu, thân chung một giá trị). */
interface Channel { valueIndices: number[]; mean: number; scale: number; minimum: number; maximum: number }

const average = (values: readonly number[]) => values.reduce((sum, value) => sum + value, 0) / values.length;

function createChannels(frames: readonly (readonly number[])[]): Channel[] {
  const channels: Channel[] = [];
  for (let valueIndex = 0; valueIndex < frames[0].length; valueIndex++) {
    const values = frames.map(frame => frame[valueIndex]);
    const mean = average(values);
    const scale = Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length);
    if (scale <= 1e-8) continue;
    const same = channels.find(channel => frames.every(frame => Math.abs(frame[channel.valueIndices[0]] - frame[valueIndex]) <= 1e-8));
    if (same) { same.valueIndices.push(valueIndex); continue; }
    channels.push({ valueIndices: [valueIndex], mean, scale, minimum: Math.min(...values), maximum: Math.max(...values) });
  }
  return channels;
}

/** Hệ số chặn rồi `order` khung trước, mỗi khung đủ các kênh. */
function feature(frames: readonly number[][], order: number, channelCount: number, endIndex = frames.length): number[] {
  const values = [1];
  for (let lag = 1; lag <= order; lag++) {
    const frame = frames[endIndex - lag];
    for (let channel = 0; channel < channelCount; channel++) values.push(frame[channel]);
  }
  return values;
}

function predict(coefficients: readonly number[][], values: readonly number[]): number[] {
  const prediction = new Array<number>(coefficients[0].length).fill(0);
  for (let row = 0; row < values.length; row++) {
    for (let output = 0; output < prediction.length; output++) prediction[output] += values[row] * coefficients[row][output];
  }
  return prediction;
}

/** Giải hệ đối xứng xác định dương bằng phân tích Cholesky, nhiều cột vế phải một lượt. */
function solvePositiveDefinite(matrix: readonly number[][], targets: readonly number[][]): number[][] {
  const size = matrix.length, outputs = targets[0].length;
  const lower = Array.from({ length: size }, () => new Array<number>(size).fill(0));
  for (let row = 0; row < size; row++) {
    for (let column = 0; column <= row; column++) {
      let value = matrix[row][column];
      for (let index = 0; index < column; index++) value -= lower[row][index] * lower[column][index];
      if (row === column) {
        if (value <= 1e-12) throw new Error('Bản ghi chuyển động không đủ để học MAGIC.');
        lower[row][column] = Math.sqrt(value);
      } else lower[row][column] = value / lower[column][column];
    }
  }
  const middle = Array.from({ length: size }, () => new Array<number>(outputs).fill(0));
  for (let row = 0; row < size; row++) {
    for (let output = 0; output < outputs; output++) {
      let value = targets[row][output];
      for (let column = 0; column < row; column++) value -= lower[row][column] * middle[column][output];
      middle[row][output] = value / lower[row][row];
    }
  }
  const solution = Array.from({ length: size }, () => new Array<number>(outputs).fill(0));
  for (let row = size - 1; row >= 0; row--) {
    for (let output = 0; output < outputs; output++) {
      let value = middle[row][output];
      for (let column = row + 1; column < size; column++) value -= lower[column][row] * solution[column][output];
      solution[row][output] = value / lower[row][row];
    }
  }
  return solution;
}

/** Số ngẫu nhiên đều theo hạt giống (mulberry32), để cùng hạt giống thì cùng chuyển động. */
export function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state += 0x6D2B79F5;
    let value = state;
    value = Math.imul(value ^ value >>> 15, value | 1);
    value ^= value + Math.imul(value ^ value >>> 7, value | 61);
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
}

/**
 * Học VAR bậc `order` (số khung trước dùng để đoán khung sau), phạt ridge theo số dòng học. Lúc sinh, mỗi khung là dự đoán
 * cộng một phần dư lấy ngẫu nhiên từ chính bản ghi, nhân `noiseScale`, rồi kẹp trong khoảng của bản ghi.
 */
export function fitMagic(sequence: TrainingSequence, { order, ridge }: { order: number; ridge: number }): MagicModel {
  const frames = sequence.frames;
  if (!(sequence.sampleRateHz > 0) || !Number.isInteger(order) || order < 1) throw new Error('Thông số học MAGIC không hợp lệ.');
  if (!frames.length || !frames[0].length || frames.some(frame => frame.length !== frames[0].length)) {
    throw new Error('Bản ghi chuyển động không hợp lệ.');
  }
  const channels = createChannels(frames);
  if (!channels.length || frames.length <= order + 1) throw new Error('Bản ghi chuyển động quá ngắn hoặc không chuyển động.');
  const baseline = Array.from({ length: frames[0].length }, (_, index) => average(frames.map(frame => frame[index])));
  const training = frames.map(frame => channels.map(channel => (frame[channel.valueIndices[0]] - channel.mean) / channel.scale));
  const count = channels.length, features = 1 + order * count;

  const gram = Array.from({ length: features }, () => new Array<number>(features).fill(0));
  const cross = Array.from({ length: features }, () => new Array<number>(count).fill(0));
  for (let index = order; index < training.length; index++) {
    const values = feature(training, order, count, index);
    const target = training[index];
    for (let row = 0; row < features; row++) {
      for (let column = 0; column <= row; column++) gram[row][column] += values[row] * values[column];
      for (let output = 0; output < count; output++) cross[row][output] += values[row] * target[output];
    }
  }
  for (let row = 0; row < features; row++) for (let column = 0; column < row; column++) gram[column][row] = gram[row][column];
  for (let index = 1; index < features; index++) gram[index][index] += ridge * (training.length - order);
  const coefficients = solvePositiveDefinite(gram, cross);

  const residuals: number[][] = [];
  for (let index = order; index < training.length; index++) {
    const prediction = predict(coefficients, feature(training, order, count, index));
    residuals.push(training[index].map((value, channel) => value - prediction[channel]));
  }

  return Object.freeze({
    sampleRateHz: sequence.sampleRateHz,
    toGenerator(seed: number): MagicGenerator {
      const random = seededRandom(seed);
      const start = Math.floor(random() * (training.length - order));
      const history = training.slice(start, start + order).map(frame => [...frame]);
      return {
        sampleRateHz: sequence.sampleRateHz,
        next(noiseScale = 1) {
          const prediction = predict(coefficients, feature(history, order, count));
          const residual = residuals[Math.floor(random() * residuals.length)];
          const next = prediction.map((value, index) => {
            const channel = channels[index];
            const raw = channel.mean + (value + residual[index] * noiseScale) * channel.scale;
            return (Math.min(channel.maximum, Math.max(channel.minimum, raw)) - channel.mean) / channel.scale;
          });
          history.shift();
          history.push(next);
          const frame = [...baseline];
          channels.forEach((channel, index) => {
            const value = Math.min(channel.maximum, Math.max(channel.minimum, channel.mean + next[index] * channel.scale));
            for (const valueIndex of channel.valueIndices) frame[valueIndex] = value;
          });
          return frame;
        },
      };
    },
  });
}
