import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow, openSidebar } from './fixtures';

test('Tạo ảnh chỉ dùng Loading chính xuyên suốt tải module và thư viện, kể cả F5', async ({ page }) => {
  await mockPeto(page);
  let releaseModule!: () => void, releaseJobs!: () => void;
  let requestedModule!: () => void, requestedJobs!: () => void;
  const moduleRequested = new Promise<void>(resolve => { requestedModule = resolve; });
  const moduleWaiting = new Promise<void>(resolve => { releaseModule = resolve; });
  const jobsRequested = new Promise<void>(resolve => { requestedJobs = resolve; });
  let jobsWaiting = new Promise<void>(resolve => { releaseJobs = resolve; });
  let loads = 0;
  await page.route('**/features/imagine/Imagine.tsx*', async route => {
    requestedModule(); await moduleWaiting; await route.continue();
  });
  await page.route('**/api/imagine', async route => {
    loads++; requestedJobs(); await jobsWaiting; await route.fulfill({ json: { jobs: [] } });
  });
  const loading = page.getByRole('status', { name: 'Loading', exact: true });
  const prompt = page.getByRole('textbox', { name: 'Bức ảnh bạn muốn tạo' });
  const checkWaiting = async () => {
    await expect(loading).toBeVisible();
    await expect(loading).toHaveClass(/brand-loading--screen/);
    await expect(prompt).toHaveCount(0);
    await expect(page.getByText('Đang mở bộ ảnh của bạn')).toHaveCount(0);
  };
  try {
    await page.goto('/#imagine');
    await moduleRequested; await checkWaiting();
    releaseModule(); await jobsRequested; await checkWaiting();
    releaseJobs();
    await expect(prompt).toBeVisible();
    await expect(loading).toHaveCount(0);
    // Ô nhập đã được đo trước khi hiện, nên vùng ảnh chừa đúng chiều cao dock ngay từ đầu.
    const dockSize = await page.locator('.imagine').evaluate(node => ({
      measured: parseFloat((node as HTMLElement).style.getPropertyValue('--studio-dock-height')),
      actual: (node.querySelector('.studio-dock') as HTMLElement).offsetHeight,
    }));
    expect(dockSize.measured).toBe(dockSize.actual);
    expect(dockSize.actual).toBeGreaterThan(0);
    await noPageOverflow(page);
    const initialLoads = loads;
    if (!await page.locator('.sidebar').isVisible()) await page.getByRole('button', { name: 'Mở menu', exact: true }).click();
    await expect(page.locator('.sidebar')).toBeVisible();
    await page.getByRole('button', { name: 'Trò chuyện', exact: true }).click();
    await openSidebar(page); await page.getByRole('button', { name: 'Tạo ảnh', exact: true }).click();
    await expect(prompt).toBeVisible(); await expect(loading).toHaveCount(0);
    expect(loads).toBe(initialLoads);
    jobsWaiting = new Promise<void>(resolve => { releaseJobs = resolve; });
    await page.reload(); await checkWaiting(); releaseJobs();
    await expect(prompt).toBeVisible(); await expect(loading).toHaveCount(0);
    expect(loads).toBe(initialLoads * 2);
  } finally { releaseModule(); releaseJobs(); }
});
