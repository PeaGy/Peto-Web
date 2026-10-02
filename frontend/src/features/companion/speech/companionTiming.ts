import { useSyncExternalStore } from 'react';

/** Mốc do bộ nghe báo; không suy ra thời điểm ngừng nói từ âm lượng hay lúc nhận chữ. */
export interface HearingTiming { endedAt?: number; finalizedAt: number }
type Mark = 'firstText' | 'textReady' | 'synthesis' | 'playing' | 'replyDone';
export type TimingStatus = 'running' | 'complete' | 'text-only' | 'stopped' | 'error';
export interface CompanionTiming {
  id: number;
  input: 'voice' | 'text';
  hearingSource?: string;
  voiceSource: string;
  search: boolean;
  sentAt: number;
  hearing?: HearingTiming;
  marks: Partial<Record<Mark, number>>;
  status: TimingStatus;
}
export interface TurnTiming {
  mark(name: Mark): void;
  replace(): void;
  finish(status: Exclude<TimingStatus, 'running'>): void;
}
let records: readonly CompanionTiming[] = [];
let nextId = 0;
const listeners = new Set<() => void>();
const publish = (next: readonly CompanionTiming[]) => { records = next; listeners.forEach(listener => listener()); };
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export const getCompanionTimings = () => records;
export const useCompanionTimings = () => useSyncExternalStore(subscribe, getCompanionTimings);
export const clearCompanionTimings = () => publish([]);

/** Chỉ giữ tối đa năm lượt trong bộ nhớ trang, không lưu chữ, âm thanh, khóa hoặc gửi thống kê đi đâu. */
export function beginCompanionTiming(input: Omit<CompanionTiming, 'id' | 'sentAt' | 'marks' | 'status'>): TurnTiming {
  const id = ++nextId;
  const record: CompanionTiming = { ...input, hearing: input.hearing ? { ...input.hearing } : undefined,
    id, sentAt: performance.now(), marks: {}, status: 'running' };
  publish([record, ...records].slice(0, 5));
  const update = (change: (record: CompanionTiming) => CompanionTiming) => {
    const index = records.findIndex(record => record.id === id && record.status === 'running');
    if (index < 0) return;
    const changed = change(records[index]);
    if (changed !== records[index]) publish(records.map((record, i) => i === index ? changed : record));
  };
  return {
    mark: name => update(record => record.marks[name] !== undefined ? record
      : { ...record, marks: { ...record.marks, [name]: performance.now() } }),
    // Tra web thay nháp: đo chữ đầu của câu trả lời chốt, không lấy tốc độ của phần đã bỏ.
    replace: () => update(record => ({ ...record, marks: {} })),
    finish: status => update(record => ({ ...record,
      status: status === 'complete' && record.marks.playing === undefined ? 'text-only' : status })),
  };
}

export function elapsed(start: number | undefined, end: number | undefined): number | null {
  return start !== undefined && end !== undefined && end >= start ? end - start : null;
}
