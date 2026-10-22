import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AdminDashboard from '../src/features/admin/AdminDashboard';
import * as adminApi from '../src/features/admin/adminApi';
import type { AdminModel, AdminOverview } from '../src/features/admin/adminApi';
import { UnauthorizedError } from '../src/shared/api/api';

vi.mock('../src/features/admin/adminApi', async original => ({
  ...await original<typeof import('../src/features/admin/adminApi')>(), getAdminOverview: vi.fn(),
}));

const model = (values: Partial<AdminModel>): AdminModel => ({
  key: 'luna', label: '6 Luna', service: 'openai', slug: 'gpt-6-luna', surfaces: ['chat', 'agent'], calls: 645, side_calls: 120,
  turns: 520, success_rate: .953, p50_ms: 6200, p95_ms: 21000, first_p50_ms: 2600, first_p95_ms: 9100,
  input_tokens: 5_900_000, cached_tokens: 2_600_000, output_tokens: 890_000, reasoning_tokens: 400_000,
  missing_usage_calls: 0, cache_unknown_calls: 0, cost_usd: 13.33, unpriced_calls: 0, ...values,
});

const bucket = (index: number, empty = false) => ({
  start: 1_760_000_000 + index * 86400, label: `${5 + index}/10`, full: `Ngày ${5 + index}/10`,
  cost: { xai: 0, openai: empty ? 0 : 2 + index, anthropic: empty ? 0 : .5 }, calls: empty ? 0 : 100 + index, empty,
});

function overview(values: Partial<AdminOverview> = {}): AdminOverview {
  return {
    range: '7d', timezone: 'Asia/Ho_Chi_Minh', generated_at: 1_760_600_000, data_since: 1_760_000_000,
    buckets: Array.from({ length: 7 }, (_, index) => bucket(index, index < 2)), bucket_unit: 'day', covered_buckets: 5,
    calls: 3511, turns: 2600, success_rate: .966,
    outcomes: [{ key: 'complete', count: 2512 }, { key: 'stopped', count: 50 }, { key: 'error', count: 20 }, { key: 'timeout', count: 12 }, { key: 'other', count: 6 }],
    latency: { p50_ms: 4200, p95_ms: 16300, first_p50_ms: 1800, first_p95_ms: 5200 },
    cost: { total_usd: 25.83, by_service: { xai: null, openai: 23.33, anthropic: 2.5 }, rates: 'ok',
      unpriced_models: ['Peto'], cache_unknown_models: [], previous_total_usd: 20, not_counted: ['Tạo ảnh (tính theo ảnh)'] },
    previous_calls: 3000,
    models: [model({ key: 'peto', label: 'Peto', service: 'xai', slug: 'grok-4.7', surfaces: ['chat', 'companion'], calls: 2866,
      cost_usd: null, unpriced_calls: 2866 }), model({})],
    searches: 412, accounts: 64, dropped_events: 0, ...values,
  };
}

function show() {
  const handlers = { onUnauthorized: vi.fn(), onForbidden: vi.fn(), onOpenSidebar: vi.fn() };
  render(<AdminDashboard {...handlers} />);
  return handlers;
}

beforeEach(() => {
  vi.mocked(adminApi.getAdminOverview).mockReset();
  localStorage.clear();
});
afterEach(cleanup);

describe('Trang Quản trị', () => {
  it('hiện ô số liệu, bảng model và đánh dấu model chưa có đơn giá', async () => {
    vi.mocked(adminApi.getAdminOverview).mockResolvedValue(overview());
    show();
    expect(await screen.findByText('$25,83')).toBeTruthy();
    const tiles = within(document.querySelector<HTMLElement>('.adm-tiles')!);
    expect(tiles.getByText('3.511')).toBeTruthy();
    expect(tiles.getByText('96,6%')).toBeTruthy();
    expect(tiles.getByText('16,3 s')).toBeTruthy();
    expect(screen.getByText(/so với kỳ trước/).textContent).toMatch(/^▲ 29,[12]% so với kỳ trước$/);
    expect(screen.getByText(/mới có 5\/7 ngày/)).toBeTruthy();
    const table = screen.getByRole('table', { name: 'Số liệu theo model' });
    const peto = within(table).getByText('Peto').closest('tr')!;
    expect(within(peto).getByText('Chưa có đơn giá')).toBeTruthy();
    expect(within(peto).getByText('Chat · Companion')).toBeTruthy();
    expect(screen.getByText(/Ước tính, không phải hóa đơn/)).toBeTruthy();
    // Peto dùng gói thuê bao: chú thích ghi "chưa có giá" chứ không phải $0,00.
    const legend = within(screen.getByRole('list', { name: 'Chú thích màu' }));
    expect(legend.getByText('chưa có giá')).toBeTruthy();
    expect(legend.queryByText('$0,00')).toBeNull();
    expect(screen.getByText(/Chưa có đơn giá hoặc thiếu token: Peto/)).toBeTruthy();
    expect(vi.mocked(adminApi.getAdminOverview).mock.calls[0][0]).toBe('7d');
  });

  it('Peto tính theo số tiền xAI tự báo thì ghi rõ nguồn của con số', async () => {
    const base = overview();
    vi.mocked(adminApi.getAdminOverview).mockResolvedValue(overview({ cost: { ...base.cost, unpriced_models: [], reported_models: ['Peto'] } }));
    show();
    expect(await screen.findByText(/Peto: tính theo số tiền xAI tự báo cho từng lần gọi/)).toBeTruthy();
    expect(screen.queryByText(/Chưa có đơn giá hoặc thiếu token/)).toBeNull();
  });

  it('không có dữ liệu thì nói rõ, không hiện số 0 giả', async () => {
    vi.mocked(adminApi.getAdminOverview).mockResolvedValue(overview({
      data_since: null, covered_buckets: 0, calls: 0, turns: 0, success_rate: null, models: [], searches: 0, accounts: 0,
      buckets: Array.from({ length: 7 }, (_, index) => bucket(index, true)),
      outcomes: [{ key: 'complete', count: 0 }, { key: 'stopped', count: 0 }, { key: 'error', count: 0 }, { key: 'timeout', count: 0 }, { key: 'other', count: 0 }],
      latency: { p50_ms: null, p95_ms: null, first_p50_ms: null, first_p95_ms: null },
      cost: { total_usd: null, by_service: null, rates: 'missing', unpriced_models: [], cache_unknown_models: [], previous_total_usd: null, not_counted: [] },
    }));
    show();
    expect(await screen.findByText(/Chưa có dữ liệu. Số liệu bắt đầu ghi/)).toBeTruthy();
    expect(screen.getAllByText('Chưa có đơn giá').length).toBeGreaterThan(0);
    expect(screen.getByText('Chưa có lượt nào')).toBeTruthy();
    expect(screen.getByText('Chưa có lượt gọi nào trong khoảng này.')).toBeTruthy();
    expect(screen.getByText(/Chưa khai tệp giá/)).toBeTruthy();
    expect(screen.queryByText('$0,00')).toBeNull();
  });

  it('đổi khoảng thời gian thì tải lại, giữ khung cũ và nhớ lựa chọn', async () => {
    let finish!: (value: AdminOverview) => void;
    vi.mocked(adminApi.getAdminOverview).mockResolvedValueOnce(overview())
      .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    show();
    await screen.findByText('$25,83');
    fireEvent.click(screen.getByRole('radio', { name: '30 ngày' }));
    await waitFor(() => expect(vi.mocked(adminApi.getAdminOverview).mock.calls[1][0]).toBe('30d'));
    // Đang tải: số cũ vẫn ở đó, khung chỉ mờ đi.
    expect(screen.getByText('$25,83')).toBeTruthy();
    expect(document.querySelector('.adm.refreshing')).toBeTruthy();
    await act(async () => finish(overview({ range: '30d', cost: { ...overview().cost, total_usd: 99.5, previous_total_usd: null } })));
    expect(await screen.findByText('$99,50')).toBeTruthy();
    expect(screen.getByText('Chưa đủ dữ liệu để so kỳ trước')).toBeTruthy();
    expect(localStorage.getItem('peto-admin-range')).toBe('30d');
  });

  it('404 thì rời trang, hết phiên thì về đăng nhập, lỗi khác cho thử lại', async () => {
    vi.mocked(adminApi.getAdminOverview).mockRejectedValueOnce(new adminApi.AdminForbiddenError('x'));
    const forbidden = show();
    await waitFor(() => expect(forbidden.onForbidden).toHaveBeenCalled());
    cleanup();

    vi.mocked(adminApi.getAdminOverview).mockRejectedValueOnce(new UnauthorizedError());
    const expired = show();
    await waitFor(() => expect(expired.onUnauthorized).toHaveBeenCalled());
    cleanup();

    vi.mocked(adminApi.getAdminOverview).mockRejectedValueOnce(new Error('Máy chủ bận')).mockResolvedValueOnce(overview());
    show();
    expect(await screen.findByText('Máy chủ bận')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
    expect(await screen.findByText('$25,83')).toBeTruthy();
  });

  it('biểu đồ chi phí đọc được bằng bàn phím', async () => {
    vi.mocked(adminApi.getAdminOverview).mockResolvedValue(overview());
    show();
    const chart = await screen.findByRole('group', { name: /Chi phí ước tính theo thời gian/ });
    fireEvent.keyDown(chart, { key: 'ArrowLeft' });
    const tip = document.querySelector('.adm-tip')!;
    expect(tip.textContent).toContain('Ngày 11/10');
    expect(tip.textContent).toContain('$8,50');
    fireEvent.keyDown(chart, { key: 'ArrowLeft' });
    expect(document.querySelector('.adm-tip')!.textContent).toContain('Ngày 10/10');
  });
});
