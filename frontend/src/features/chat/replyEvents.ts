import type { ChatHandlers, DocumentArtifact, Message, WorkStep } from '../../shared/api/api';
import { normalizeWeb } from './sourceActivity';
import { safeSources } from './WebSources';

// Cách một sự kiện SSE đổi câu trả lời đang viết (tin cuối). Dùng chung cho tab tự gửi (chatTurn.ts) và tab nhận lượt
// của thiết bị khác (useLiveChat.ts), để hai bên luôn vẽ giống nhau.

type WorkPayload = Parameters<NonNullable<ChatHandlers['onWork']>>[0];
type Web = NonNullable<ReturnType<typeof normalizeWeb>>;
type Sources = Parameters<NonNullable<ChatHandlers['onSources']>>[0];

/** Nhật ký "Đang làm" do máy chủ dựng: mỗi bước tới là thêm hoặc thay theo id; bước "chờ" của trình duyệt bỏ đi. */
export function withStep(last: Message, step: WorkStep): Message {
  return withSteps(last, (steps) => {
    const index = steps.findIndex((item) => item.id === step.id);
    if (index < 0) return [...steps, step];
    const next = [...steps];
    next[index] = { ...step, summary: step.summary ?? steps[index].summary };
    return next;
  });
}

export function withThinking(last: Message, piece: string, id: string | undefined): Message {
  return withSteps(last, (steps) => steps.map((step) => step.id === id ? { ...step, summary: (step.summary ?? '') + piece } : step));
}

export function withSteps(last: Message, change: (steps: WorkStep[]) => WorkStep[]): Message {
  return { ...last, work: { ms: 0, ...last.work, steps: change((last.work?.steps ?? []).filter((step) => step.kind !== 'wait')) } };
}

/** Bản chốt của nhật ký (sự kiện "work"). */
export function withWork(last: Message, work: WorkPayload): Message {
  const { web: rawWeb, ...rest } = work;
  const web = normalizeWeb(rawWeb);
  return { ...last, work: { ...rest, ...(web ? { web } : {}) } };
}

export function withSources(last: Message, sources: Sources): Message {
  return { ...last, sources: safeSources(sources) };
}

export function withSourceActivity(last: Message, web: Web): Message {
  return { ...last, work: { ms: 0, steps: [], ...last.work, web } };
}

/** Peto sửa cùng một tệp vài lần trong một lượt: bản mới thay thẻ của bản trước ngay tại chỗ, như máy chủ lưu. */
export function withArtifact(last: Message, artifact: DocumentArtifact): Message {
  const artifacts = [...(last.artifacts || [])];
  const index = artifacts.findIndex((item) => item.id === artifact.id);
  if (index >= 0) artifacts[index] = artifact;
  else artifacts.push(artifact);
  return { ...last, artifacts };
}
