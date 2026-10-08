import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { checkImagineRequest, createImagineJob, getImagineJob, ImagineRequestUncertainError, unconfirmedImagineRequest } from '../src/shared/api/api';

const payload = { prompt: 'Ghép ảnh', quality: 'medium' as const, resolution: '1k' as const, aspect_ratio: 'auto', n: 1, source_images: [{ data: 'image-one' }, { image_id: 'image-two' }] };
beforeEach(() => sessionStorage.clear());
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it('gửi JSON nhiều ảnh cùng mã chống trùng và nhận lượt nền', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ job: { id: 'job', status: 'queued' } }), { status: 202 }));
  vi.stubGlobal('fetch', fetch);
  expect((await createImagineJob(payload)).status).toBe('queued');
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body).toMatchObject({ ...payload, background: true, request_id: expect.any(String) });
  expect(body.request_id.length).toBeGreaterThanOrEqual(16);
  expect(unconfirmedImagineRequest()).toBeNull();
});

it.each(['network', 'broken-response'])('giữ mã để kiểm tra khi mất phản hồi %s, không tự POST thêm', async mode => {
  const fetch = mode === 'network' ? vi.fn().mockRejectedValue(new TypeError('network')) : vi.fn().mockResolvedValue(new Response('{', { status: 202 }));
  vi.stubGlobal('fetch', fetch);
  await expect(createImagineJob(payload)).rejects.toBeInstanceOf(ImagineRequestUncertainError);
  const request = unconfirmedImagineRequest();
  expect(request).toBeTruthy();
  expect(fetch).toHaveBeenCalledOnce();
  fetch.mockResolvedValue(new Response(JSON.stringify({ job: { id: 'restored', status: 'running' } })));
  expect((await checkImagineRequest(request!))?.id).toBe('restored');
  expect(fetch.mock.calls[1][0]).toBe(`/api/imagine/requests/${request}`);
  expect(unconfirmedImagineRequest()).toBeNull();
});

it('ngắt lần đọc trạng thái bị kẹt để có thể kiểm tra lại, không hủy lượt AI', async () => {
  vi.useFakeTimers();
  let requestSignal!: AbortSignal;
  const fetch = vi.fn((_url, options: RequestInit) => new Promise<Response>((_resolve, reject) => {
    requestSignal = options.signal!;
    requestSignal.addEventListener('abort', () => reject(requestSignal.reason), { once: true });
  }));
  vi.stubGlobal('fetch', fetch);
  const request = getImagineJob('editing').catch(error => error);
  await vi.advanceTimersByTimeAsync(10_000);
  expect(requestSignal.aborted).toBe(true);
  expect(await request).toMatchObject({ name: 'TimeoutError' });
  expect(fetch).toHaveBeenCalledOnce();
  expect(fetch.mock.calls[0][1]).toMatchObject({ cache: 'no-store' });
  fetch.mockResolvedValue(new Response(JSON.stringify({ job: { id: 'editing', status: 'complete', images: [{ id: 'result' }] } })));
  expect((await getImagineJob('editing')).status).toBe('complete');
  expect(vi.getTimerCount()).toBe(0);
});

it.each(['timeout', 'đóng màn hình'])('đọc thân phản hồi bị kẹt: %s ngắt được và dọn timer', async mode => {
  vi.useFakeTimers();
  const external = new AbortController();
  let requestSignal!: AbortSignal;
  vi.stubGlobal('fetch', vi.fn(async (_url, options: RequestInit) => {
    requestSignal = options.signal!;
    return { ok: true, json: () => new Promise((_resolve, reject) => {
      requestSignal.addEventListener('abort', () => reject(requestSignal.reason), { once: true });
    }) } as Response;
  }));
  const request = getImagineJob('editing', external.signal).catch(error => error);
  await vi.advanceTimersByTimeAsync(mode === 'timeout' ? 10_000 : 2000);
  if (mode !== 'timeout') external.abort();
  expect(requestSignal.aborted).toBe(true);
  expect(await request).toMatchObject({ name: mode === 'timeout' ? 'TimeoutError' : 'AbortError' });
  expect(vi.getTimerCount()).toBe(0);
});
