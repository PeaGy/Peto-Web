import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import * as api from '../src/shared/api/api';
import UsageSettings, { percentLabel } from '../src/features/settings/UsageSettings';

const usage: api.WeeklyUsage = {
  measuring: true, unlimited: false, started_at: 1_795_000_000, resets_at: 1_795_604_800, used_percent: 47.4,
  groups: [
    { key: 'chat', label: 'Trò chuyện', percent: 24.2 }, { key: 'agent', label: 'Peto Agent', percent: 15 },
    { key: 'companion', label: 'Companion', percent: 0.4 }, { key: 'imagine', label: 'Tạo ảnh', percent: 0 },
  ],
  unpriced_calls: 0,
};

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Cài đặt → Mức dùng', () => {
  it('hiện phần trăm, giờ đặt lại, từng mục và dòng đang đo', async () => {
    vi.spyOn(api, 'getUsage').mockResolvedValue(usage);
    const { container } = render(<UsageSettings open onUnauthorized={() => {}} />);
    expect(await screen.findByText('47%')).toBeTruthy();
    expect(screen.getByText(/Đặt lại/)).toBeTruthy();
    expect(screen.getByRole('img', { name: 'Đã dùng 47% mức dùng trong tuần' })).toBeTruthy();
    expect(screen.getByText('Đang đo thử, chưa giới hạn.')).toBeTruthy();
    // Mục chưa dùng không có đoạn trên thanh nhưng vẫn có trong chú thích.
    expect(container.querySelectorAll('.usage-fill')).toHaveLength(3);
    expect(container.querySelector('.usage-legend')!.textContent).toContain('Tạo ảnh 0%');
    expect(container.querySelector('.usage-legend')!.textContent).toContain('Companion <1%');
  });

  it('chưa dùng gì trong tuần thì nói tuần mới bắt đầu từ lần dùng tới', async () => {
    vi.spyOn(api, 'getUsage').mockResolvedValue({ ...usage, started_at: null, resets_at: null, used_percent: 0,
      groups: usage.groups.map(group => ({ ...group, percent: 0 })) });
    render(<UsageSettings open onUnauthorized={() => {}} />);
    expect(await screen.findByText('Tuần mới bắt đầu từ lần dùng tới')).toBeTruthy();
  });

  it('vượt 100% thì thanh vẫn vừa khung', async () => {
    vi.spyOn(api, 'getUsage').mockResolvedValue({ ...usage, used_percent: 150,
      groups: [{ key: 'chat', label: 'Trò chuyện', percent: 150 }, ...usage.groups.slice(1).map(group => ({ ...group, percent: 0 }))] });
    const { container } = render(<UsageSettings open onUnauthorized={() => {}} />);
    expect((await screen.findAllByText('150%')).length).toBeGreaterThan(0);
    expect((container.querySelector('.usage-fill') as HTMLElement).style.width).toBe('100%');
  });

  it('phần trăm làm tròn, phần lẻ dưới 1% không thành 0%', () => {
    expect(percentLabel(0)).toBe('0%');
    expect(percentLabel(0.3)).toBe('<1%');
    expect(percentLabel(47.4)).toBe('47%');
  });
});
