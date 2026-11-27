import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import WorkTimeline from '../src/features/chat/WorkTimeline';
import { tetrisMode } from '../src/features/chat/indicator/WorkIndicator';
import {
  INDICATOR_KEY, INDICATOR_SIZE_KEY, readIndicator, readIndicatorSize, setIndicator, setIndicatorSize,
} from '../src/features/chat/indicator/indicatorSettings';
import type { WorkLog } from '../src/shared/api/api';

// Chỉ báo đang làm (27/11/2026): Cài đặt → Giao diện chọn Machine Love - 1 (mặc định), Machine Love - 2 hoặc Tetris và cỡ;
// dòng "Đang làm" vẽ nó thay mũi tên khi lượt còn chạy.

const work: WorkLog = { ms: 0, steps: [{ id: 's1', kind: 'search', label: 'Đang tìm trên web…', state: 'live', start: 0 }] };

beforeEach(() => {
  localStorage.clear();
  // jsdom không vẽ canvas; chỉ kiểm phần tử và thuộc tính.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
});

describe('cài đặt chỉ báo', () => {
  it('mặc định Machine Love - 1 cỡ 20; giá trị lạ trong trình duyệt bị bỏ qua', () => {
    expect(readIndicator()).toBe('machine-love-1');
    expect(readIndicatorSize()).toBe(20);
    localStorage.setItem(INDICATOR_KEY, 'pacman');
    localStorage.setItem(INDICATOR_SIZE_KEY, '99');
    expect(readIndicator()).toBe('machine-love-1');
    expect(readIndicatorSize()).toBe(20);
    setIndicator('tetris');
    setIndicatorSize(32);
    expect(localStorage.getItem(INDICATOR_KEY)).toBe('tetris');
    expect(readIndicatorSize()).toBe(32);
  });

  it('Tetris đổi kiểu theo việc Peto đang làm', () => {
    expect(tetrisMode(undefined, false)).toBe('autoplay');
    expect(tetrisMode('think', false)).toBe('autoplay');
    expect(tetrisMode('wait', false)).toBe('autoplay');
    expect(tetrisMode('search', false)).toBe('rain');
    expect(tetrisMode('page', false)).toBe('next');
    expect(tetrisMode('read', false)).toBe('next');
    expect(tetrisMode('code', false)).toBe('stack');
    expect(tetrisMode('search', true)).toBe('stack');
  });
});

describe('dòng Đang làm', () => {
  it('lượt đang chạy: chỉ báo thay mũi tên và đổi ngay khi Cài đặt đổi; xong lượt thì mũi tên quay lại', () => {
    const { container, rerender } = render(<WorkTimeline work={work} live startedAt={performance.now()} answering={false} />);
    const head = container.querySelector('.work-head')!;
    let indicator = head.querySelector<HTMLCanvasElement>('.work-indicator')!;
    expect(indicator.dataset.indicator).toBe('machine-love-1');
    expect(indicator.style.width).toBe('20px');
    expect(head.querySelector('.work-chevron')).toBeNull();

    act(() => { setIndicator('tetris'); setIndicatorSize(24); });
    indicator = head.querySelector<HTMLCanvasElement>('.work-indicator')!;
    expect(indicator.dataset.indicator).toBe('tetris');
    expect(indicator.dataset.mode).toBe('rain');
    expect(indicator.style.width).toBe('24px');

    rerender(<WorkTimeline work={{ ...work, ms: 3000, complete: true, steps: [{ ...work.steps[0], state: 'done', end: 3000 }] }}
      live={false} answering />);
    expect(container.querySelector('.work-indicator')).toBeNull();
    expect(container.querySelector('.work-head .work-chevron')).not.toBeNull();
  });

  it('chưa có bước nào (đang chờ máy chủ) vẫn có chỉ báo', () => {
    const { container } = render(<WorkTimeline work={{ ms: 0, steps: [] }} live startedAt={performance.now()} answering={false} />);
    expect(container.querySelector('.work-head.static .work-indicator')).not.toBeNull();
  });

  it('tab khác đổi cài đặt: tab này vẽ lại theo', () => {
    const { container } = render(<WorkTimeline work={work} live startedAt={performance.now()} answering={false} />);
    act(() => {
      localStorage.setItem(INDICATOR_KEY, 'machine-love-2');
      window.dispatchEvent(new StorageEvent('storage', { key: INDICATOR_KEY }));
    });
    expect(container.querySelector<HTMLCanvasElement>('.work-indicator')!.dataset.indicator).toBe('machine-love-2');
  });
});
