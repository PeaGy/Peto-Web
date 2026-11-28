import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow, openSidebar, title } from './fixtures';

const markdown = '## So sánh\n\nGiá thường là **$0.40**, công thức $x^2 + y^2 = 1$. Xem [bảng giá](https://example.com/gia).\n\n'
  + '| Hạng mục | Giá |\n| --- | --- |\n| Input | $2.00 |\n| Output | $10.00 |\n\n```js\nconst greeting = "Xin chào";\n```';

// Link chia sẻ cuộc trò chuyện (28/11/2026): hộp Chia sẻ từ menu ⋯, trang công khai /s/{id} và Cài đặt → Link chia sẻ.
const SHARE_ID = 'Abc123_def-456GHIjk';
const shot = (name: string, mobile: boolean) =>
  `C:/Users/binhb/AppData/Local/Temp/claude/345eac0d2351f8ee/cc9b967d-f93c-4daf-9903-ad5a81ecd4ca/scratchpad/share-${name}-${mobile ? 'mobile' : 'pc'}.png`;

async function mockShares(page: Page) {
  const state = { share: null as null | Record<string, unknown>, posts: [] as unknown[] };
  await page.route('**/api/conversations/A/share', async route => {
    if (route.request().method() === 'POST') {
      state.posts.push(route.request().postDataJSON());
      state.share = { id: SHARE_ID, conversation_id: 'A', title, include_images: Boolean((route.request().postDataJSON() as { include_images: boolean }).include_images),
        created_at: 1764300000, updated_at: 1764300000, message_count: 2 };
    }
    await route.fulfill({ json: { share: state.share } });
  });
  await page.route('**/api/shares', route => route.fulfill({ json: { shares: state.share ? [state.share] : [] } }));
  await page.route(`**/api/shares/${SHARE_ID}`, async route => { state.share = null; await route.fulfill({ json: { deleted: true } }); });
  return state;
}

test('menu ⋯ → Chia sẻ: tạo link, chép link, kèm ảnh khi tích', async ({ page, isMobile }) => {
  await mockPeto(page);
  await page.addInitScript(() => {
    Object.assign(window, { copied: '' });
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (text: string) => { (window as unknown as { copied: string }).copied = text; } } });
  });
  const state = await mockShares(page);
  await page.goto('/chat/A');
  await expect(page.getByText('Giúp tôi so sánh giá và công thức nhé.')).toBeVisible();
  await openSidebar(page);
  await page.locator('.conv').filter({ has: page.getByRole('button', { name: title, exact: true }) }).hover();
  await page.getByRole('button', { name: `Tùy chọn ${title}`, exact: true }).click();
  await page.getByRole('dialog', { name: 'Tùy chọn hội thoại' }).getByRole('button', { name: 'Chia sẻ' }).click();

  const dialog = page.getByRole('dialog', { name: 'Chia sẻ cuộc trò chuyện' });
  await expect(dialog.getByText('Link chứa nguyên văn các tin nhắn, kể cả tên hay chi tiết riêng nếu có trong đó.', { exact: false })).toBeVisible();
  await expect(dialog.getByText('Trí nhớ và hồ sơ của bạn không được chia sẻ.', { exact: false })).toBeVisible();
  await expect(dialog.getByRole('checkbox', { name: 'Kèm ảnh bạn đã gửi' })).not.toBeChecked();
  await page.screenshot({ path: shot('dialog-new', isMobile) });
  await dialog.getByRole('button', { name: 'Tạo link' }).click();
  const link = dialog.getByRole('textbox', { name: 'Link chia sẻ' });
  await expect(link).toHaveValue(new RegExp(`/s/${SHARE_ID}$`));
  expect(state.posts).toEqual([{ include_images: false }]);
  await dialog.getByRole('button', { name: 'Chép link' }).click();
  await expect(dialog.getByRole('button', { name: 'Đã chép' })).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { copied: string }).copied)).toMatch(new RegExp(`/s/${SHARE_ID}$`));
  await page.screenshot({ path: shot('dialog-link', isMobile) });

  await dialog.getByRole('checkbox', { name: 'Kèm ảnh bạn đã gửi' }).check();
  await dialog.getByRole('button', { name: 'Cập nhật link' }).click();
  await expect(dialog.getByText('có ảnh', { exact: false })).toBeVisible();
  expect(state.posts.at(-1)).toEqual({ include_images: true });
  await dialog.getByRole('button', { name: 'Xong' }).click();
  await expect(dialog).toHaveCount(0);
  await noPageOverflow(page);
});

test('trang /s/{id}: đọc được không cần đăng nhập, không có ô nhắn; link hỏng báo rõ', async ({ page, isMobile }) => {
  // Người xem chưa đăng nhập: mọi API khác trả 401. Chỉ bắt đường dẫn /api/…, không bắt tệp mã src/shared/api/api.ts.
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 401, json: { detail: 'Chưa đăng nhập' } }));
  await page.route(`**/api/shared/${SHARE_ID}`, route => route.fulfill({ json: {
    title: 'So sánh giá và công thức', updated_at: 1764300000, include_images: false,
    messages: [
      { role: 'user', content: 'Giúp tôi so sánh giá và công thức nhé.', attachments: [{ name: 'bang-gia.xlsx', kind: 'file' }] },
      { role: 'assistant', content: markdown, documents: [{ title: 'Báo cáo', filename: 'bao-cao.docx' }] },
    ] } }));
  await page.route('**/api/shared/khong-con-link-nay-nua', route => route.fulfill({ status: 404, json: { detail: 'Link chia sẻ không còn hoặc đã bị thu hồi.' } }));
  await page.goto(`/s/${SHARE_ID}`);
  await expect(page.getByRole('heading', { name: 'So sánh giá và công thức' })).toBeVisible();
  await expect(page.getByText('Giúp tôi so sánh giá và công thức nhé.')).toBeVisible();
  await expect(page.locator('article[data-role="assistant"] table')).toBeVisible();
  await expect(page.getByText('Tệp đính kèm: bang-gia.xlsx')).toBeVisible();
  await expect(page.getByText('Tài liệu Peto tạo: bao-cao.docx')).toBeVisible();
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Trò chuyện với Peto' })).toHaveAttribute('href', '/');
  // Link mở thẻ mới có mô tả cho trình đọc màn hình (index.html #new-tab-hint), tên link giữ nguyên.
  await expect(page.getByRole('link', { name: 'bảng giá', exact: true })).toHaveAccessibleDescription('Mở trong thẻ mới');
  await page.screenshot({ path: shot('page', isMobile), fullPage: false });
  await noPageOverflow(page);

  await page.goto('/s/khong-con-link-nay-nua');
  await expect(page.getByRole('heading', { name: 'Không mở được link' })).toBeVisible();
  await expect(page.getByText('Link chia sẻ không còn hoặc đã bị thu hồi.')).toBeVisible();
});

test('Cài đặt → Link chia sẻ: liệt kê và xóa link', async ({ page }) => {
  await mockPeto(page);
  const state = await mockShares(page);
  state.share = { id: SHARE_ID, conversation_id: 'A', title, include_images: true, created_at: 1764300000, updated_at: 1764300000, message_count: 2 };
  await page.goto('/');
  await expect(page.getByLabel('Nhắn cho Peto', { exact: true })).toBeVisible();
  await openSidebar(page);
  await page.getByRole('button', { name: /^Tài khoản · / }).click();
  await page.getByRole('menuitem', { name: 'Cài đặt', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'Cài đặt', exact: true });
  await settings.getByRole('button', { name: 'Link chia sẻ', exact: true }).click();
  const list = settings.getByRole('list', { name: 'Danh sách link chia sẻ' });
  await expect(list.getByRole('link', { name: new RegExp(title) })).toHaveAttribute('href', new RegExp(`/s/${SHARE_ID}$`));
  await list.getByRole('button', { name: `Xóa link: ${title}` }).click();
  await settings.getByRole('button', { name: 'Xóa link', exact: true }).click();
  await expect(list.getByRole('listitem')).toHaveCount(0);
  await expect(settings.getByText('Bạn chưa chia sẻ cuộc trò chuyện nào.')).toBeVisible();
});
