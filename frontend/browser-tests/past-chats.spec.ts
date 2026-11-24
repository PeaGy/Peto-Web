import { expect, test } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

// Tìm trong cuộc trò chuyện cũ (cách 1, 24/11/2026): bước "Đang làm" liệt kê các cuộc tìm thấy, bấm mở đúng cuộc đó.
test('bước tìm cuộc cũ hiện danh sách và mở lại được cuộc đã tìm thấy', async ({ page }, info) => {
  await mockPeto(page);
  const work = { ms: 6200, complete: true, steps: [
    { id: 'chats-1', kind: 'chats', label: 'Đã tìm trong cuộc trò chuyện cũ', state: 'done', start: 300, end: 1500,
      detail: '“excel”, “công thức”', chats: [{ id: 'OLD', title: 'Sửa bảng lương bị lỗi #VALUE!', at: 1792000000 },
        { id: 'OLD2', title: 'Gộp ô và tính tổng tháng', at: 1791400000 }] },
    { id: 'think-2', kind: 'think', label: 'Đã suy nghĩ', state: 'done', start: 1500, end: 5200 },
  ] };
  const histories: Record<string, object[]> = {
    NOW: [{ id: 1, role: 'user', content: 'Hôm trước bạn chỉ mình sửa lỗi Excel thế nào nhỉ?' },
      { id: 2, role: 'assistant', content: 'Hôm 12/10 mình chỉ bạn bỏ khoảng trắng ở cột B rồi dùng SUMIFS thay SUM.', status: 'complete', work }],
    OLD: [{ id: 3, role: 'user', content: 'Bảng lương bị lỗi #VALUE!' }, { id: 4, role: 'assistant', content: 'Dùng SUMIFS nhé.', status: 'complete' }],
  };
  await page.route('**/api/conversations/*/messages*', route => route.fulfill({ json: {
    messages: histories[new URL(route.request().url()).pathname.split('/').at(-2)!] ?? [] } }));
  await page.goto('/chat/NOW');
  await page.getByRole('button', { name: /Đã làm trong/ }).click();
  const list = page.getByRole('list', { name: 'Cuộc trò chuyện cũ đã tìm thấy' });
  await expect(list.getByRole('link')).toHaveCount(2);
  await expect(page.getByText('“excel”, “công thức”')).toBeVisible();
  await noPageOverflow(page);
  await page.screenshot({ path: info.outputPath('past-chats.png') });
  await list.getByRole('link', { name: /Sửa bảng lương/ }).click();
  await expect(page).toHaveURL(/\/chat\/OLD$/);
  await expect(page.getByText('Dùng SUMIFS nhé.')).toBeVisible();
});
