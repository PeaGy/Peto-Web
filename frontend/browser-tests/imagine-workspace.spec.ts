import { expect, test, type Page } from '@playwright/test';
import { mockPeto, noPageOverflow } from './fixtures';

/** Ảnh dọc đủ lớn để phát hiện lỗi kích thước; không dùng ảnh 1 px để đánh giá bố cục. */
async function setup(page: Page) {
  await mockPeto(page);
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = 960; canvas.height = 1440;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = '#74c8e9'; ctx.fillRect(0, 0, 960, 1440);
    ctx.fillStyle = '#ffe1a0'; ctx.beginPath(); ctx.arc(690, 320, 125, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#436b7c'; ctx.beginPath(); ctx.moveTo(0, 900); ctx.lineTo(400, 400); ctx.lineTo(960, 1100); ctx.lineTo(0, 1440); ctx.fill();
    ctx.fillStyle = '#245647'; ctx.beginPath(); ctx.moveTo(0, 1050); ctx.lineTo(750, 700); ctx.lineTo(960, 1050); ctx.lineTo(960, 1440); ctx.lineTo(0, 1440); ctx.fill();
    ctx.fillStyle = '#e5cfaf'; ctx.fillRect(350, 1000, 250, 240);
    ctx.fillStyle = '#8c4935'; ctx.beginPath(); ctx.moveTo(300, 1000); ctx.lineTo(475, 850); ctx.lineTo(650, 1000); ctx.fill();
    return canvas.toDataURL('image/png').split(',')[1];
  });
  const image = (id: string) => ({ id, mime: 'image/png', url: `/api/imagine/images/${id}` });
  const job = { id: 'landscape', prompt: 'Ngôi nhà giữa núi xanh', quality: 'medium', resolution: '2k', aspect_ratio: '2:3', created_at: 1, images: [image('portrait'), image('portrait-two')] };
  const posts: Record<string, unknown>[] = [];
  await page.route('**/api/imagine**', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.pathname.startsWith('/api/imagine/images/')) return route.fulfill({ contentType: 'image/png', body: Buffer.from(png, 'base64') });
    if (request.method() === 'POST') {
      posts.push(request.postDataJSON());
      return route.fulfill({ status: 202, json: { job: { ...job, id: 'edited', prompt: posts.at(-1)?.prompt, status: 'running', images: [], n: 1 } } });
    }
    if (url.pathname === '/api/imagine') return route.fulfill({ json: { jobs: [job] } });
    return route.fulfill({ status: 404 });
  });
  return { posts };
}

test('thư viện có ô ảnh nhỏ và khung xem vừa màn hình trên PC/mobile', async ({ page }, testInfo) => {
  const { posts } = await setup(page);
  if (testInfo.project.name === 'pc') await page.setViewportSize({ width: 1920, height: 960 });
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Thư viện', exact: true }).last().click();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh' });
  const tile = library.getByRole('button', { name: 'Xem ảnh: Ngôi nhà giữa núi xanh', exact: true }).first();
  await expect(tile.locator('img')).toHaveJSProperty('naturalWidth', 960);
  await expect(page.locator('.image-nav-rail')).toHaveCount(0);
  await expect(library.getByText(/Chọn theo thứ tự mong muốn/)).toHaveCount(0);
  const bounds = (await tile.boundingBox())!;
  expect(bounds.width).toBeLessThanOrEqual(360);
  expect(Math.abs(bounds.width - bounds.height)).toBeLessThan(1);
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('library.png') });
  await library.getByRole('button', { name: 'Chọn', exact: true }).click();
  await library.getByRole('button', { name: 'Chọn ảnh: Ngôi nhà giữa núi xanh', exact: true }).first().click();
  await expect(library.getByLabel('Bức ảnh bạn muốn tạo')).toHaveCount(0);
  await expect(library.getByRole('button', { name: 'Tải xuống', exact: true })).toBeEnabled();
  await page.screenshot({ path: testInfo.outputPath('library-selected.png') });
  await library.getByRole('button', { name: 'Hủy', exact: true }).click();
  await tile.click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('960 × 1440');
  await expect(viewer.locator('.image-nav-rail')).toHaveCount(0);
  const stage = (await viewer.locator('.workspace-canvas').boundingBox())!;
  const shown = (await viewer.locator('.workspace-picture img').boundingBox())!;
  expect(shown.width).toBeLessThanOrEqual(stage.width);
  expect(shown.height).toBeLessThanOrEqual(stage.height);
  await expect(viewer.getByRole('button', { name: 'Gửi chỉnh sửa ảnh' })).toBeDisabled();
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('workspace.png') });
  await viewer.getByRole('button', { name: 'Bảng màu', exact: true }).click();
  await viewer.getByRole('button', { name: 'Lấy màu từ ảnh' }).click();
  await expect(viewer.getByRole('button', { name: /^Màu #/ })).toHaveCount(4);
  await viewer.getByRole('button', { name: 'Bắc Âu', exact: true }).click();
  await expect(viewer.getByLabel('Mô tả chỉnh sửa ảnh')).toHaveValue(/Áp dụng bảng màu bắc âu/);
  expect(posts).toHaveLength(0);
  await page.screenshot({ path: testInfo.outputPath('palette.png') });
  await viewer.getByRole('button', { name: 'Quay lại', exact: true }).click();
  await expect(library).toBeVisible();
  await expect(tile.locator('img')).toHaveAttribute('src', '/api/imagine/images/portrait');
  await library.getByRole('button', { name: 'Quay lại Tạo ảnh' }).click();
  await expect(library).not.toBeVisible();
});

test('cắt/vẽ tạo nguồn PNG mới, hoàn tác giữ ảnh gốc, chỉ gửi khi bấm gửi', async ({ page }, testInfo) => {
  const { posts } = await setup(page);
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Xem ảnh 1: Ngôi nhà giữa núi xanh', exact: true }).click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('960 × 1440');
  await viewer.getByRole('button', { name: 'Cắt ảnh', exact: true }).click();
  await viewer.getByLabel('Tỉ lệ cắt').selectOption('1:1');
  await page.screenshot({ path: testInfo.outputPath('crop.png') });
  // Escape chỉ hủy vùng cắt; khung xem vẫn mở.
  await page.keyboard.press('Escape');
  await expect(viewer).toBeVisible();
  await expect(viewer.getByLabel('Tỉ lệ cắt')).toHaveCount(0);
  await viewer.getByRole('button', { name: 'Cắt ảnh', exact: true }).click();
  await viewer.getByRole('button', { name: 'Cắt', exact: true }).click();
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('864 × 864');
  await viewer.getByRole('button', { name: 'Hoàn tác chỉnh sửa' }).click();
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('960 × 1440');
  await viewer.getByRole('button', { name: 'Làm lại chỉnh sửa' }).click();
  await expect(viewer.getByLabel('Kích thước ảnh thực tế')).toHaveText('864 × 864');
  await viewer.getByRole('button', { name: 'Bút vẽ', exact: true }).click();
  const canvas = viewer.getByLabel('Vẽ ghi chú lên ảnh');
  const bounds = (await canvas.boundingBox())!;
  // Pointer dùng cùng đường xử lý cho chuột và cảm ứng.
  await canvas.dispatchEvent('pointerdown', { pointerId: 1, pointerType: 'mouse', button: 0, clientX: bounds.x + bounds.width / 2, clientY: bounds.y + bounds.height / 2 });
  await canvas.dispatchEvent('pointermove', { pointerId: 1, pointerType: 'mouse', clientX: bounds.x + bounds.width * .75, clientY: bounds.y + bounds.height / 2 });
  await canvas.dispatchEvent('pointerup', { pointerId: 1, pointerType: 'mouse' });
  await expect(viewer.getByRole('button', { name: 'Hoàn tác nét vẽ' })).toBeEnabled();
  await viewer.getByRole('button', { name: 'Hoàn tác nét vẽ' }).click();
  await expect(viewer.getByRole('button', { name: 'Áp dụng nét vẽ' })).toBeDisabled();
  await viewer.getByRole('button', { name: 'Làm lại nét vẽ' }).click();
  await viewer.getByRole('button', { name: 'Áp dụng nét vẽ' }).click();
  const data = await viewer.locator('.workspace-picture img').getAttribute('src');
  expect(data).toMatch(/^data:image\/png;base64,/);
  const pixel = await viewer.locator('.workspace-picture img').evaluate(async img => {
    const image = img as HTMLImageElement; await image.decode();
    const c = document.createElement('canvas'); c.width = image.naturalWidth; c.height = image.naturalHeight;
    const ctx = c.getContext('2d')!; ctx.drawImage(image, 0, 0);
    return [...ctx.getImageData(c.width / 2, c.height / 2, 1, 1).data];
  });
  expect(pixel).toEqual([255, 255, 255, 255]);
  await noPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('brush.png') });
  expect(posts).toHaveLength(0);
  await viewer.getByLabel('Mô tả chỉnh sửa ảnh').fill('Đổi thành tranh màu nước');
  await viewer.getByRole('button', { name: 'Gửi chỉnh sửa ảnh' }).click();
  await expect(viewer).not.toBeVisible();
  expect(posts).toHaveLength(1);
  expect(posts[0]).toMatchObject({ n: 1, background: true, source_image: { data: data!.split(',')[1] }, prompt: 'Đổi thành tranh màu nước' });
  await expect(page.getByRole('button', { name: 'Xem ảnh 1: Ngôi nhà giữa núi xanh', exact: true }).locator('img')).toHaveAttribute('src', '/api/imagine/images/portrait');
});


test('bấm ảnh để xem, nhấn giữ để chọn và hủy chọn trả về xem ảnh', async ({ page }) => {
  await setup(page);
  await page.goto('/#imagine');
  await page.getByRole('button', { name: 'Thư viện', exact: true }).last().click();
  const library = page.getByRole('dialog', { name: 'Thư viện ảnh' });
  const tile = library.locator('[data-image-id="portrait"]');
  await tile.click();
  const viewer = page.getByRole('dialog', { name: 'Xem ảnh đã tạo' });
  await expect(viewer).toBeVisible();
  await viewer.getByRole('button', { name: 'Quay lại', exact: true }).click();
  await expect(library.getByRole('button', { name: 'Chọn', exact: true })).toBeVisible();
  const box = (await tile.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  // Chờ trạng thái do cử chỉ giữ thực sự, không bấm nút Chọn để giả lập.
  await expect(library.getByRole('button', { name: 'Hủy', exact: true })).toHaveText('1 đã chọn');
  await page.mouse.up();
  await expect(tile).toHaveAttribute('aria-pressed', 'true');
  await expect(viewer).not.toBeVisible();
  await expect(library.getByRole('menu')).toHaveCount(0);
  await expect(library.getByText(/Chọn theo thứ tự mong muốn/)).toHaveCount(0);
  await library.locator('[data-image-id="portrait-two"]').click();
  await expect(library.getByRole('button', { name: 'Hủy', exact: true })).toHaveText('2 đã chọn');
  await library.getByRole('button', { name: 'Hủy', exact: true }).click();
  await tile.click();
  await expect(viewer).toBeVisible();
  await noPageOverflow(page);
});
