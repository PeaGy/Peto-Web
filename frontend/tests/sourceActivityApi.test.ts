import { afterEach, expect, it, vi } from 'vitest';
import { sendMessage } from '../src/shared/api/api';
import { closeWork } from '../src/features/chat/WorkTimeline';
import type { WebActivity } from '../src/features/chat/sourceActivity';
import type { WorkLog } from '../src/shared/api/api';

afterEach(() => vi.unstubAllGlobals());
const event = (value: object) => `data: ${JSON.stringify(value)}\n\n`;
const web: WebActivity = { version: 1,
  sources: [{ url: 'https://example.com/a', title: 'Nguồn tiếng Việt', snippet: 'Đoạn trích thực tế' }],
  calls: [{ id: 'xai:1:call-1', kind: 'search', operation: 'search', queries: ['màn hình gaming'], state: 'live', source_urls: ['https://example.com/a'] }],
};

it('SSE chia từng byte giữ query Unicode và quan hệ nguồn, bỏ envelope sai phiên bản', async () => {
  const wire = new TextEncoder().encode(event({ type: 'source_activity', web: { ...web, version: 99 } })
    + event({ type: 'source_activity', web }) + event({ type: 'delta', text: 'Đã kiểm tra.' }) + event({ type: 'done' }));
  vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream({
    start(controller) { for (const byte of wire) controller.enqueue(new Uint8Array([byte])); controller.close(); },
  }))));
  const onSourceActivity = vi.fn(), onDelta = vi.fn(), onDone = vi.fn();
  await sendMessage({ message: 'Fixture', conversationId: null, effort: 'low' }, { onSourceActivity, onDelta, onDone });
  expect(onSourceActivity).toHaveBeenCalledExactlyOnceWith(web);
  expect(onDelta).toHaveBeenCalledWith('Đã kiểm tra.');
  expect(onDone).toHaveBeenCalledOnce();
});

it('đóng luồng trên client giữ catalogue và dừng đúng call còn chạy', () => {
  const original = { ms: 20, steps: [], web: { ...web, calls: [...web.calls,
    { ...web.calls[0], id: 'xai:1:done', state: 'done' as const },
    { ...web.calls[0], id: 'xai:1:failed', state: 'failed' as const },
  ] } };
  const stopped = closeWork(original, false, 100)!;
  expect(stopped.web!.calls.map(call => call.state)).toEqual(['stopped', 'done', 'failed']);
  expect(stopped.web!.sources).toEqual(web.sources);
  expect(original.web.calls[0].state).toBe('live');
});

it('đóng luồng loại envelope không hỗ trợ thay vì giữ metadata chưa kiểm tra', () => {
  const work = { ms: 0, steps: [], web: { version: 99 } } as unknown as WorkLog;
  expect(closeWork(work, false, 50)).toEqual({ ms: 50, steps: [], complete: false });
});
