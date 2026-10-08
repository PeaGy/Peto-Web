import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { checkImagineRequest, createImagineJob, ImagineRequestUncertainError, unconfirmedImagineRequest } from '../src/shared/api/api';

const payload = { prompt: 'Ghép ảnh', quality: 'medium' as const, resolution: '1k' as const, aspect_ratio: 'auto', n: 1, source_images: [{ data: 'image-one' }, { image_id: 'image-two' }] };
beforeEach(() => sessionStorage.clear());
afterEach(() => vi.unstubAllGlobals());

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
